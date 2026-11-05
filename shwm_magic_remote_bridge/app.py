"""SHWM Magic Remote Assist Bridge: Glasshouse event -> LG PCM -> HA Assist.

Experimental HAOS add-on. Explicit pairing can append its public SSH key to the TV.
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
from pairing import start_panel

DATA_DIR = pathlib.Path('/data')
KEY = DATA_DIR / 'id_ed25519'
KNOWN_HOSTS = DATA_DIR / 'known_hosts'
HELPER = pathlib.Path(__file__).with_name('tv_capture.py')
SUPERVISOR_WS = 'ws://supervisor/core/websocket'
LOG = logging.getLogger('shwm_magic_remote')
MANUAL_EVENT = 'shwm_magic_remote_test'
APP_VERSION = '0.1.9'
SSH_MUX_DIR = pathlib.Path('/run/shwm_magic_remote')
SSH_MUX_SOCKET = SSH_MUX_DIR / 'control'


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
    glasshouse_port = int(opts.get('glasshouse_port', 8080))
    if not 1 <= glasshouse_port <= 65535:
        raise ValueError('invalid glasshouse_port')
    opts['glasshouse_port'] = glasshouse_port
    opts['record_seconds'] = seconds
    opts['execute_commands'] = bool(opts.get('execute_commands', False))
    opts['log_transcript'] = bool(opts.get('log_transcript', False))
    opts['pipeline_id'] = str(opts.get('pipeline_id') or '')
    opts['manual_test_enabled'] = bool(opts.get('manual_test_enabled', False))
    opts['manual_audio_only'] = bool(opts.get('manual_audio_only', False))
    opts['mic_retry_enabled'] = bool(opts.get('mic_retry_enabled', True))
    opts['ssh_warmup_enabled'] = bool(opts.get('ssh_warmup_enabled', True))
    opts['vad_enabled'] = bool(opts.get('vad_enabled', False))
    opts['vad_rms_threshold'] = int(opts.get('vad_rms_threshold', 250))
    opts['vad_silence_ms'] = int(opts.get('vad_silence_ms', 1500))
    if not 100 <= opts['vad_rms_threshold'] <= 4000 or not 800 <= opts['vad_silence_ms'] <= 3500:
        raise ValueError('invalid VAD settings')
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
    SSH_MUX_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    SSH_MUX_DIR.chmod(0o700)


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
    args = ['ssh', '-T',
            '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
            '-o', 'ConnectTimeout=8', '-o', 'ServerAliveInterval=5',
            '-o', 'ServerAliveCountMax=2',
            '-o', 'ClearAllForwardings=yes',
            '-o', 'StrictHostKeyChecking=accept-new',
            '-o', 'UserKnownHostsFile=' + str(KNOWN_HOSTS)]
    if opts.get('ssh_warmup_enabled', True):
        # Add-on-private socket: the control master never exposes the
        # privileged SSH connection to the rest of HA or the LAN.
        args.extend(['-o', 'ControlMaster=auto',
                     '-o', 'ControlPersist=180',
                     '-o', 'ControlPath=' + str(SSH_MUX_SOCKET)])
    return args + ['-i', str(KEY), '-p', str(opts['tv_ssh_port']),
                   'root@' + opts['tv_host']]


async def warmup_ssh(opts):
    """Warm the authorized SSH transport; no microphone or TV writes."""
    started = time.monotonic()
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *ssh_args(opts), 'true',
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=12)
        except asyncio.TimeoutError:
            if proc.returncode is None:
                proc.kill()
            await proc.communicate()
            LOG.info('SSH_WARMUP_SKIPPED reason=timeout')
            return
        if proc.returncode == 0:
            LOG.info('SSH_WARMUP_READY duration_seconds=%.2f', time.monotonic() - started)
        else:
            # May simply be the user's first installation before pairing.
            # Never log public host banners, usernames or private data.
            LOG.info('SSH_WARMUP_SKIPPED reason=%s',
                     classify_capture_error(stderr.decode('utf-8', 'replace')))
    except OSError:
        LOG.info('SSH_WARMUP_SKIPPED reason=local_ssh_unavailable')
    except asyncio.CancelledError:
        if proc is not None and proc.returncode is None:
            proc.kill()
            await proc.communicate()
        raise


def tv_remote_command(seconds):
    payload = base64.b64encode(HELPER.read_bytes()).decode('ascii')
    # The code is carried over SSH and executed in RAM, never written on TV.
    return ("python -u -c 'import base64;exec(base64.b64decode(\"" + payload +
            "\"))' " + str(seconds))



class TvCaptureError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def classify_capture_error(stderr):
    msg = str(stderr).lower()
    if 'permission denied' in msg or 'publickey' in msg or 'authentication failed' in msg:
        return 'SSH_AUTH_FAILED'
    if 'host key verification failed' in msg or 'remote host identification has changed' in msg:
        return 'SSH_HOST_KEY_ERROR'
    if ('connection refused' in msg or 'connection timed out' in msg or
            'no route to host' in msg or 'could not resolve hostname' in msg):
        return 'TV_SSH_UNREACHABLE'
    if 'fail to find voice device' in msg or 'tv_stream_error unable_to_connect_socket' in msg:
        return 'TV_MIC_UNAVAILABLE'
    if 'timed out waiting for voice stream' in msg:
        return 'TV_AUDIO_TIMEOUT'
    return 'TV_CAPTURE_FAILED'


async def stop_capture_process(proc, graceful=False):
    """Ask the TV helper to stop on VAD; never wait two seconds first.

    If a previous TV helper ignores stdin, fall back to the existing bounded
    terminate/kill cleanup. No repeated microphone or Assist operations.
    """
    if proc.returncode is not None:
        return
    if graceful and proc.stdin is not None:
        try:
            proc.stdin.write(b'S\n')
            await asyncio.wait_for(proc.stdin.drain(), timeout=0.5)
            await asyncio.wait_for(proc.wait(), timeout=0.9)
            return
        except (BrokenPipeError, ConnectionResetError, asyncio.TimeoutError):
            pass
    if proc.returncode is None and not graceful:
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
            return
        except asyncio.TimeoutError:
            pass
    if proc.returncode is None:
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=1.5)
    except asyncio.TimeoutError:
        if proc.returncode is None:
            proc.kill()
        await proc.wait()


async def open_tv_capture(opts):
    """At most one retry for missing voice device, before ANY audio/Assist action."""
    total_attempts = 2 if opts['mic_retry_enabled'] else 1
    for attempt in range(1, total_attempts + 1):
        LOG.info('STATUS SSH_CONNECT attempt=%d/%d tv=%s', attempt, total_attempts, opts['tv_host'])
        proc = await asyncio.create_subprocess_exec(
            *ssh_args(opts), tv_remote_command(opts['record_seconds']),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timed_out = False
        prefix = b''
        try:
            try:
                prefix = await asyncio.wait_for(proc.stdout.readexactly(8), timeout=25)
            except asyncio.IncompleteReadError:
                pass
            except asyncio.TimeoutError:
                timed_out = True
        except BaseException:
            # Interrupted startup must not leak a privileged SSH subprocess.
            await stop_capture_process(proc)
            raise
        if prefix == b'SHWMPCM1':
            LOG.info('STATUS TV_MIC_READY attempt=%d', attempt)
            return proc
        await stop_capture_process(proc)
        error_details = (await proc.stderr.read()).decode('utf-8', 'replace')
        if timed_out:
            error_details += ' timed out waiting for voice stream'
        code = classify_capture_error(error_details)
        LOG.warning('STATUS TV_CAPTURE_ERROR code=%s attempt=%d/%d exit=%s',
                    code, attempt, total_attempts, proc.returncode)
        if code == 'TV_MIC_UNAVAILABLE' and attempt < total_attempts:
            LOG.info('STATUS MIC_RETRY: one retry before audio, not repeating Assist actions')
            await asyncio.sleep(0.7)
            continue
        raise TvCaptureError(code)
    raise TvCaptureError('TV_CAPTURE_FAILED')


async def pipe_voice_to_ha(ws, handler_id, opts, metrics=None):
    metrics = metrics if metrics is not None else {}
    capture_open_at = time.monotonic()
    proc = await open_tv_capture(opts)
    ready_at = time.monotonic()
    metrics['tv_mic_ready_seconds'] = ready_at - capture_open_at
    LOG.info('STATUS RECORDING')
    bytes_sent = 0
    carry = b''
    detector = VoiceEndDetector(opts['vad_rms_threshold'], opts['vad_silence_ms']) if opts['vad_enabled'] else None
    auto_stopped = False
    try:
        async with asyncio.timeout(opts['record_seconds'] + 20):
            while True:
                block = await proc.stdout.read(6400)
                if not block:
                    break
                block = carry + block
                even = len(block) & ~1
                if even:
                    aligned = block[:even]
                    await ws.send_bytes(bytes([handler_id]) + aligned)
                    bytes_sent += even
                    if detector is not None and detector.feed(aligned):
                        auto_stopped = True
                        LOG.info('VAD: speech finished, stopping at %.2fs (RMS threshold=%d; silence=%dms)',
                                 bytes_sent / 32000, opts['vad_rms_threshold'], opts['vad_silence_ms'])
                        break
                carry = block[even:]
        if not bytes_sent:
            raise RuntimeError('TV microphone returned no audio samples')
    finally:
        capture_ended_at = time.monotonic()
        # End the HA STT audio stream even after a failed capture.
        if not ws.closed:
            try:
                await ws.send_bytes(bytes([handler_id]))
            except Exception:
                pass
        await stop_capture_process(proc, graceful=auto_stopped)
        stderr = await proc.stderr.read()
        if stderr:
            LOG.info('TV capture diagnostic: %s', stderr.decode('utf-8', 'replace')[:1300].strip())
    cleanup_done_at = time.monotonic()
    metrics['capture_cleanup_seconds'] = cleanup_done_at - capture_ended_at
    metrics['audio_captured_seconds'] = bytes_sent / 32000
    metrics['vad_stopped'] = auto_stopped
    LOG.info('STATUS CAPTURE_TIMING ssh_tv_ready_seconds=%.2f cleanup_seconds=%.2f audio_seconds=%.2f vad_stop=%s',
             metrics['tv_mic_ready_seconds'], metrics['capture_cleanup_seconds'],
             metrics['audio_captured_seconds'], auto_stopped)
    if detector is not None and not auto_stopped:
        LOG.info('VAD: no confirmed end of speech, capture ended at maximum')
    LOG.info('STATUS AUDIO_COMPLETE bytes=%d audio_seconds=%.2f', bytes_sent, bytes_sent / 32000)


async def run_pipeline(session, token, opts, manual_test=False):
    started_at = time.monotonic()
    execute_commands = opts['execute_commands'] and not manual_test
    LOG.info('STATUS ASSIST_CONNECT execute_commands=%s manual=%s', execute_commands, manual_test)
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
        assist_ready_at = time.monotonic()
        LOG.info('STATUS STT_READY setup_seconds=%.2f', assist_ready_at - started_at)
        metrics = {}
        await pipe_voice_to_ha(ws, handler_id, opts, metrics)
        audio_done_at = time.monotonic()
        no_speech = False
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
                    LOG.info('STATUS STT_SUCCESS after_audio_seconds=%.2f%s',
                             time.monotonic() - audio_done_at,
                             ': ' + value if opts['log_transcript'] else ' (text hidden)')
                elif etype == 'intent-end':
                    response = (data.get('intent_output') or {}).get('response') or {}
                    speech = ((response.get('speech') or {}).get('plain') or {}).get('speech')
                    LOG.info('STATUS ASSIST_INTENT_SUCCESS%s',
                             ': ' + str(speech) if opts['log_transcript'] else ' (text hidden)')
                elif etype == 'error':
                    # A silent or early-triggered MIC is not an SSH/TV failure.
                    # No intent can run when STT recognizes no text.
                    if data.get('code') == 'stt-no-text-recognized':
                        no_speech = True
                        LOG.info('STATUS NO_SPEECH recognized_text=false; check MIC readiness and remote wake-up')
                        break
                    raise RuntimeError('Assist error: ' + str(data)[:700])
                elif etype == 'run-end':
                    break
        done_at = time.monotonic()
        LOG.info('STATUS SESSION_TIMING assist_ready_seconds=%.2f tv_mic_ready_seconds=%.2f audio_seconds=%.2f cleanup_seconds=%.2f assist_after_audio_seconds=%.2f total_seconds=%.2f',
                 assist_ready_at - started_at, metrics.get('tv_mic_ready_seconds', 0.0),
                 metrics.get('audio_captured_seconds', 0.0), metrics.get('capture_cleanup_seconds', 0.0),
                 done_at - audio_done_at, done_at - started_at)
        LOG.info('STATUS COMPLETE result=%s total_seconds=%.2f execute_commands=%s manual_test=%s',
             'NO_SPEECH' if no_speech else 'OK', done_at - started_at, execute_commands, manual_test)

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


class VoiceEndDetector:
    """Optional RMS silence detector for 16kHz mono PCM16 LE.

    Speech requires 200ms of continuous signal above threshold.
    Silence countdown only starts after confirming speech.
    """
    FRAME_BYTES = 3200  # 100ms

    def __init__(self, rms_threshold=250, silence_ms=1500):
        self.rms_threshold = rms_threshold
        self.silence_frames = (silence_ms + 99) // 100
        self.pending = bytearray()
        self.voiced_frames = 0
        self.quiet_frames = 0
        self.frames = 0
        self.speech_confirmed = False
        self.done = False

    def feed(self, pcm):
        if self.done:
            return True
        self.pending.extend(pcm)
        while len(self.pending) >= self.FRAME_BYTES:
            frame = bytes(self.pending[:self.FRAME_BYTES])
            del self.pending[:self.FRAME_BYTES]
            n, energy, _ = pcm16_metrics(frame)
            self.frames += 1
            rms = math.sqrt(energy / n)
            if rms >= self.rms_threshold:
                self.voiced_frames += 1
                self.quiet_frames = 0
                if self.voiced_frames >= 2:
                    self.speech_confirmed = True
            elif not self.speech_confirmed:
                self.voiced_frames = 0
            else:
                self.quiet_frames += 1
            if (self.speech_confirmed and
                    self.quiet_frames >= self.silence_frames and
                    self.frames >= 20):
                self.done = True
                return True
        return False


async def probe_tv_audio(opts):
    """Check TV SSH + voiceinput microphone without using a HA STT pipeline."""
    LOG.info('AUDIO-ONLY: requesting LG microphone over SSH (Assist/STT disabled)')
    proc = await open_tv_capture(opts)
    LOG.info('STATUS RECORDING')
    total_bytes = 0
    samples = 0
    energy = 0
    peak = 0
    carry = b''
    try:
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
        await stop_capture_process(proc)
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
    LOG.info('SHWM Magic Remote Assist Bridge v%s', APP_VERSION)
    LOG.info('Glasshouse required: TV %s, event entity %s', opts['tv_host'], opts['remote_event_entity'])
    LOG.warning('Execute commands: %s (FALSE = STT-only)', opts['execute_commands'])
    LOG.info('Microphone pre-audio retry: %s', opts['mic_retry_enabled'])
    LOG.info('SSH warm-up: %s', opts['ssh_warmup_enabled'])
    LOG.info('Auto-stop VAD: %s (threshold=%d, silence=%dms)',
             'ON' if opts['vad_enabled'] else 'OFF', opts['vad_rms_threshold'], opts['vad_silence_ms'])
    if opts['manual_test_enabled']:
        LOG.info('Manual test enabled. Fire HA event: %s (%s)', MANUAL_EVENT,
                 'AUDIO-ONLY' if opts['manual_audio_only'] else 'STT-only')
    try:
        await start_panel(opts, str(KEY) + '.pub', ssh_args)
    except OSError:
        LOG.error('Pairing panel unavailable; audio bridge continues')
    if opts['ssh_warmup_enabled']:
        asyncio.create_task(warmup_ssh(opts))
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
                            LOG.info('STATUS BUSY: voice event ignored while session active')
                            continue
                        if manual_test:
                            LOG.info('Manual event received: preparing %s microphone test',
                                     'AUDIO-ONLY' if opts['manual_audio_only'] else 'STT-only')
                            active = asyncio.create_task(run_manual_test(session, token, opts))
                        else:
                            LOG.info('STATUS MIC_DETECTED source=Glasshouse')
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
        if isinstance(exc, TvCaptureError):
            LOG.error('STATUS FAILED stage=TV_AUDIO code=%s', exc.code)
        elif isinstance(exc, asyncio.TimeoutError):
            LOG.error('STATUS FAILED stage=ASSIST code=TIMEOUT')
        else:
            LOG.error('STATUS FAILED reason=%s', str(exc)[:500])


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        asyncio.run(run(settings()))
    except KeyboardInterrupt:
        pass
    except Exception:
        LOG.exception('Fatal startup error')
        raise
