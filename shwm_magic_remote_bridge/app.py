"""SHWM Magic Remote Assist Bridge: Glasshouse event -> LG PCM -> HA Assist.

Experimental add-on for Home Assistant OS. Does not install anything on TV.
No PCM/WAV recordings, private SSH keys only in persistent add-on /data.
"""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import logging
import os
import pathlib
import math
import struct
import subprocess
import time

import aiohttp

DATA_DIR = pathlib.Path('/data')
KEY = DATA_DIR / 'id_ed25519'
KNOWN_HOSTS = DATA_DIR / 'known_hosts'
HELPER = pathlib.Path(__file__).with_name('tv_capture.py')
SUPERVISOR_WS = 'ws://supervisor/core/websocket'
LOG = logging.getLogger('shwm_magic_remote')
MANUAL_EVENT = 'shwm_magic_remote_test'


def settings(path='/data/options.json'):
    with open(path, encoding='utf-8') as fh:
        opts = json.load(fh)
    host = opts.get('tv_host', '')
    ip = ipaddress.ip_address(host)
    if not ip.is_private or ip.is_loopback or ip.is_link_local:
        raise ValueError('tv_host must be a private LAN IP')
    entity = str(opts.get('remote_event_entity', ''))
    if not entity.startswith('event.'):
        raise ValueError('remote_event_entity must begin with event.')
    port = int(opts.get('tv_ssh_port', 22))
    seconds = int(opts.get('record_seconds', 8))
    if not 1 <= port <= 65535 or not 5 <= seconds <= 20:
        raise ValueError('invalid SSH port or record_seconds (5 to 20)')
    opts['tv_host'] = str(ip)
    opts['tv_ssh_port'] = port
    opts['record_seconds'] = seconds
    opts['execute_commands'] = bool(opts.get('execute_commands', False))
    opts['log_transcript'] = bool(opts.get('log_transcript', False))
    opts['pipeline_id'] = str(opts.get('pipeline_id') or '')
    opts['manual_test_enabled'] = bool(opts.get('manual_test_enabled', False))
    opts['manual_audio_only'] = bool(opts.get('manual_audio_only', False))
    return opts


def ensure_key():
    DATA_DIR.mkdir(exist_ok=True, parents=True)
    if not KEY.exists():
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '',
                        '-C', 'shwm-magic-remote-assist', '-f', str(KEY)],
                       check=True, timeout=20)
        LOG.warning('NEW SSH KEY GENERATED. Add this PUBLIC key to the TV authorized_keys:')
    os.chmod(KEY, 0o600)
    pub = pathlib.Path(str(KEY) + '.pub').read_text(encoding='ascii').strip()
    LOG.warning('TV SSH PUBLIC KEY (safe to share): %s', pub)
    LOG.info('Private key is stored only in app persistent /data')


def is_voice_press(event, entity):
    data = event.get('event', {}).get('data', {})
    if data.get('entity_id') != entity:
        return False
    old = data.get('old_state') or {}
    new = data.get('new_state') or {}
    if not old or old.get('state') in ('unknown', 'unavailable', None):
        return False
    if new.get('state') in ('unknown', 'unavailable', None):
        return False
    if new.get('state') == old.get('state'):
        return False
    attrs = new.get('attributes') or {}
    return attrs.get('event_type') == 'voice' and attrs.get('button') in (None, 'voice')


def is_manual_test_event(message):
    return (message.get('type') == 'event'
            and message.get('id') == 2
            and (message.get('event') or {}).get('event_type') == MANUAL_EVENT)


async def auth_ws(session, token):
    ws = await session.ws_connect(SUPERVISOR_WS, heartbeat=20, timeout=aiohttp.ClientWSTimeout(ws_close=15), max_msg_size=1024*1024)
    try:
        message = await asyncio.wait_for(ws.receive_json(), timeout=15)
        if message.get('type') != 'auth_required':
            raise RuntimeError('HA WebSocket did not request auth')
        await ws.send_json({'type': 'auth', 'access_token': token})
        message = await asyncio.wait_for(ws.receive_json(), timeout=15)
        if message.get('type') != 'auth_ok':
            raise RuntimeError('Home Assistant WebSocket authentication failed')
        return ws
    except Exception:
        await ws.close()
        raise


def ssh_args(opts):
    return ['ssh', '-T',
            '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
            '-o', 'ConnectTimeout=8', '-o', 'ServerAliveInterval=5',
            '-o', 'ServerAliveCountMax=2',
            '-o', 'ClearAllForwardings=yes',
            '-o', 'StrictHostKeyChecking=accept-new',
            '-o', 'UserKnownHostsFile=' + str(KNOWN_HOSTS),
            '-i', str(KEY), '-p', str(opts['tv_ssh_port']),
            'root@' + opts['tv_host']]


def tv_remote_command(seconds):
    payload = base64.b64encode(HELPER.read_bytes()).decode('ascii')
    # The code is carried over SSH and executed in RAM, never written on TV.
    return ("python -u -c 'import base64;exec(base64.b64decode(\"" + payload +
            "\"))' " + str(seconds))


async def pipe_voice_to_ha(ws, handler_id, opts):
    proc = await asyncio.create_subprocess_exec(
        *ssh_args(opts), tv_remote_command(opts['record_seconds']),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    bytes_sent = 0
    carry = b''
    try:
        try:
            prefix = await asyncio.wait_for(proc.stdout.readexactly(8), timeout=25)
        except asyncio.IncompleteReadError:
            prefix = b''
        if prefix != b'SHWMPCM1':
            raise RuntimeError('TV microphone stream did not start (no SHWMPCM1 marker)')
        async with asyncio.timeout(opts['record_seconds'] + 20):
            while True:
                block = await proc.stdout.read(6400)
                if not block:
                    break
                block = carry + block
                even = len(block) & ~1
                if even:
                    await ws.send_bytes(bytes([handler_id]) + block[:even])
                    bytes_sent += even
                carry = block[even:]
        if not bytes_sent:
            raise RuntimeError('TV microphone returned no audio samples')
    finally:
        # End the HA STT audio stream even after a failed capture.
        if not ws.closed:
            try:
                await ws.send_bytes(bytes([handler_id]))
            except Exception:
                pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except asyncio.TimeoutError:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        stderr = await proc.stderr.read()
        if stderr:
            LOG.info('TV capture diagnostic: %s', stderr.decode('utf-8', 'replace')[:1300].strip())
    LOG.info('PCM streamed to Assist: %d bytes (%.1f s)', bytes_sent, bytes_sent / 32000)


async def run_pipeline(session, token, opts, manual_test=False):
    execute_commands = opts['execute_commands'] and not manual_test
    async with await auth_ws(session, token) as ws:
        cmd = {'id': 17, 'type': 'assist_pipeline/run', 'start_stage': 'stt',
               'end_stage': 'intent' if execute_commands else 'stt',
               'input': {'sample_rate': 16000}, 'timeout': 90}
        if opts['pipeline_id']:
            cmd['pipeline'] = opts['pipeline_id']
        await ws.send_json(cmd)
        handler_id = None
        while handler_id is None:
            msg = await asyncio.wait_for(ws.receive_json(), timeout=20)
            if msg.get('type') == 'result' and msg.get('id') == 17 and not msg.get('success'):
                raise RuntimeError('HA rejected pipeline start: ' + str(msg.get('error'))[:400])
            if msg.get('type') == 'event' and msg.get('id') == 17:
                event = msg.get('event') or {}
                if event.get('type') == 'run-start':
                    handler_id = (event.get('data') or {}).get('runner_data', {}).get('stt_binary_handler_id')
                if event.get('type') == 'error':
                    raise RuntimeError('Assist error: ' + str(event.get('data'))[:400])
        if not isinstance(handler_id, int) or not 0 <= handler_id <= 255:
            raise RuntimeError('HA returned invalid audio handler ID')
        await pipe_voice_to_ha(ws, handler_id, opts)
        async with asyncio.timeout(90):
            while True:
                message = await ws.receive()
                if message.type != aiohttp.WSMsgType.TEXT:
                    raise RuntimeError('HA WebSocket closed while waiting for pipeline result')
                msg = json.loads(message.data)
                if msg.get('type') != 'event' or msg.get('id') != 17:
                    continue
                event = msg.get('event') or {}
                etype = event.get('type')
                data = event.get('data') or {}
                if etype == 'stt-end':
                    value = (data.get('stt_output') or {}).get('text', '')
                    LOG.info('STT succeeded%s', ': ' + value if opts['log_transcript'] else ' (text hidden)')
                elif etype == 'intent-end':
                    response = (data.get('intent_output') or {}).get('response') or {}
                    speech = ((response.get('speech') or {}).get('plain') or {}).get('speech')
                    LOG.info('Assist intent finished%s', ': ' + str(speech) if opts['log_transcript'] else '')
                elif etype == 'error':
                    raise RuntimeError('Assist error: ' + str(data)[:700])
                elif etype == 'run-end':
                    break
        LOG.info('Assist session complete (execute_commands=%s; manual_test=%s)', execute_commands, manual_test)

def pcm16_metrics(chunk):
    """Return (samples, sum_of_squares, peak); no audio is stored."""
    if len(chunk) % 2:
        raise ValueError('PCM16 chunk must contain an even number of bytes')
    n = 0
    energy = 0
    peak = 0
    for (sample,) in struct.iter_unpack('<h', chunk):
        n += 1
        energy += sample * sample
        peak = max(peak, abs(sample))
    return n, energy, peak


async def probe_tv_audio(opts):
    """Check TV SSH + voiceinput microphone without using a HA STT pipeline."""
    LOG.info('AUDIO-ONLY: requesting LG microphone over SSH (Assist/STT disabled)')
    proc = await asyncio.create_subprocess_exec(
        *ssh_args(opts), tv_remote_command(opts['record_seconds']),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    total_bytes = 0
    samples = 0
    energy = 0
    peak = 0
    carry = b''
    try:
        try:
            prefix = await asyncio.wait_for(proc.stdout.readexactly(8), timeout=25)
        except asyncio.IncompleteReadError:
            prefix = b''
        if prefix != b'SHWMPCM1':
            raise RuntimeError('TV audio not available: SSH or voiceinput did not return SHWMPCM1 (check SSH key and logs)')
        async with asyncio.timeout(opts['record_seconds'] + 20):
            while True:
                block = await proc.stdout.read(6400)
                if not block:
                    break
                block = carry + block
                even = len(block) & ~1
                if even:
                    aligned = block[:even]
                    count, squared, local_peak = pcm16_metrics(aligned)
                    samples += count
                    energy += squared
                    peak = max(peak, local_peak)
                    total_bytes += even
                carry = block[even:]
        if not total_bytes:
            raise RuntimeError('TV audio returned zero PCM samples')
        LOG.info('TV AUDIO DIAGNOSTIC: PCM16/16000Hz bytes=%d duration=%.2fs peak=%d rms=%.1f',
                 total_bytes, total_bytes / 32000, peak, math.sqrt(energy / samples))
        if peak == 0:
            LOG.warning('TV audio contains silence only; check that MIC is held')
    finally:
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except asyncio.TimeoutError:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        stderr = await proc.stderr.read()
        if stderr:
            LOG.info('TV SSH/capture diagnostic: %s', stderr.decode('utf-8', 'replace')[:1800].strip())
    if proc.returncode != 0:
        raise RuntimeError('TV microphone capture command failed (exit=%d)' % proc.returncode)
    LOG.info('AUDIO-ONLY TEST PASSED: microphone capture verified without STT, Assist or saved WAV')


async def run_manual_test(session, token, opts):
    LOG.info('MANUAL TEST: hold Magic Remote MIC now; opening microphone in 2 seconds')
    await asyncio.sleep(2)
    # Manual event must never perform home automation actions.
    if opts['manual_audio_only']:
        await probe_tv_audio(opts)
    else:
        await run_pipeline(session, token, opts, manual_test=True)


async def run(opts):
    token = os.environ.get('SUPERVISOR_TOKEN')
    if not token:
        raise RuntimeError('SUPERVISOR_TOKEN missing (must run inside HA OS app)')
    ensure_key()
    LOG.info('Glasshouse required: TV %s, event entity %s', opts['tv_host'], opts['remote_event_entity'])
    LOG.warning('Execute commands: %s (FALSE = STT-only)', opts['execute_commands'])
    if opts['manual_test_enabled']:
        LOG.info('Manual test enabled. Fire HA event: %s (%s)', MANUAL_EVENT,
                 'AUDIO-ONLY' if opts['manual_audio_only'] else 'STT-only')
    async with aiohttp.ClientSession() as session:
        last_press = 0.0
        active = None
        while True:
            try:
                async with await auth_ws(session, token) as ws:
                    subscriptions = [(1, 'state_changed')]
                    if opts['manual_test_enabled']:
                        subscriptions.append((2, MANUAL_EVENT))
                    for request_id, event_type in subscriptions:
                        await ws.send_json({'id': request_id,
                                            'type': 'subscribe_events',
                                            'event_type': event_type})
                        result = await asyncio.wait_for(ws.receive_json(), timeout=15)
                        if (result.get('type') != 'result' or
                                result.get('id') != request_id or
                                not result.get('success')):
                            raise RuntimeError('Could not subscribe to HA event ' + event_type)
                    LOG.info('Ready: press MIC on Glasshouse Magic Remote')
                    if opts['manual_test_enabled']:
                        LOG.info('Ready for manual test. Fire event: %s', MANUAL_EVENT)
                    async for message in ws:
                        if message.type != aiohttp.WSMsgType.TEXT:
                            break
                        payload = json.loads(message.data)
                        manual_test = (opts['manual_test_enabled'] and is_manual_test_event(payload))
                        glasshouse_press = (payload.get('type') == 'event' and
                                            payload.get('id') == 1 and
                                            is_voice_press(payload, opts['remote_event_entity']))
                        if not manual_test and not glasshouse_press:
                            continue
                        now = time.monotonic()
                        if now - last_press < 2:
                            continue
                        last_press = now
                        if active is not None and not active.done():
                            LOG.info('Voice event ignored: session already running')
                            continue
                        if manual_test:
                            LOG.info('Manual event received: preparing %s microphone test',
                                     'AUDIO-ONLY' if opts['manual_audio_only'] else 'STT-only')
                            active = asyncio.create_task(run_manual_test(session, token, opts))
                        else:
                            LOG.info('Glasshouse MIC pressed: starting Assist audio stream')
                            active = asyncio.create_task(run_pipeline(session, token, opts))
                        active.add_done_callback(task_finished)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOG.error('HA event stream disconnected: %s; reconnecting in 5 seconds', exc)
            await asyncio.sleep(5)


def task_finished(task):
    if task.cancelled():
        LOG.warning('Assist session cancelled')
        return
    exc = task.exception()
    if exc:
        LOG.error('Assist session failed: %s', exc)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        asyncio.run(run(settings()))
    except KeyboardInterrupt:
        pass
    except Exception:
        LOG.exception('Fatal startup error')
        raise
