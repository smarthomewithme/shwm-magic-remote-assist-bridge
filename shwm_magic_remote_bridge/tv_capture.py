# -*- coding: ascii -*-
"""Rooted webOS capture: PCM16LE only on stdout, diagnostics on stderr.

No audio or helper file is saved on the television.
"""
from __future__ import print_function
import os
import sys
import time
import select
import socket
import subprocess
import re

SOCKET_PATH = '/tmp/voiceinput_remote1.soc'
COMMAND = ['luna-send', '-i', '-f',
           'luna://com.webos.service.voiceinput/startStreaming',
           '{"deviceType":"remote","keyType":"thinQtv","subscribe":true}']

def log(message):
    sys.stderr.write(message + '\n')
    sys.stderr.flush()

STATE_RE = re.compile(b'"state"\\s*:\\s*"([^"]{1,64})"')
OFF_STATES = ('voice stop', 'voice end')


class VoiceStateWatcher(object):
    """Watch explicit Luna voiceinput states, never infer OFF from silence."""
    def __init__(self):
        self.tail = b''
        self.last_state = None
        self.saw_start = False
        self.off_seen = False
        self.output_sample = bytearray()

    def feed(self, data, live=True):
        if not data:
            return
        left = 1024 - len(self.output_sample)
        if left > 0:
            self.output_sample.extend(data[:left])
        window = self.tail + data
        previous = len(self.tail)
        for match in STATE_RE.finditer(window):
            if match.end() <= previous:
                continue
            state = match.group(1).decode('ascii', 'replace').strip().lower()
            if state not in ('voice start',) + OFF_STATES:
                continue
            if state != self.last_state and live:
                log('TV_VOICEINPUT_STATE=' + state.replace(' ', '_').upper())
                self.last_state = state
            if state == 'voice start':
                self.saw_start = True
            if state in OFF_STATES and self.saw_start:
                self.off_seen = True
        self.tail = window[-128:]

    def poll(self, stream, live=True):
        if stream is None:
            return
        # Bound each drain even if Luna continuously writes to the pipe.
        for _ in range(8):
            if not select.select([stream], [], [], 0)[0]:
                return
            chunk = os.read(stream.fileno(), 4096)
            if not chunk:
                return
            self.feed(chunk, live=live)
            if len(chunk) < 4096:
                return


def cleanup_voiceinput(service, observer, terminate_wait=0.8, kill_wait=0.5):
    """Release this session's luna-send without unbounded communicate().

    Do not kill unrelated TV services or persist anything to the TV.
    The final status is about the owned child process, NOT a verified
    release of the physical Magic Remote microphone.
    """
    result = 'ALREADY_EXITED'
    try:
        # Close the child's stdin first, then request a normal process exit.
        # The -i subscription can otherwise wait indefinitely for input.
        try:
            if service.stdin is not None:
                service.stdin.close()
        except (OSError, IOError, ValueError):
            pass
        if service.poll() is None:
            result = 'TERM_EXITED'
            try:
                service.terminate()
            except (OSError, IOError):
                pass
            deadline = time.time() + terminate_wait
            while service.poll() is None and time.time() < deadline:
                try:
                    observer.poll(service.stdout, live=False)
                except (OSError, IOError, ValueError):
                    pass
                time.sleep(0.05)
            if service.poll() is None:
                result = 'KILL_EXITED'
                try:
                    service.kill()
                except (OSError, IOError):
                    pass
                deadline = time.time() + kill_wait
                while service.poll() is None and time.time() < deadline:
                    try:
                        observer.poll(service.stdout, live=False)
                    except (OSError, IOError, ValueError):
                        pass
                    time.sleep(0.05)
                if service.poll() is None:
                    result = 'UNCONFIRMED'
    finally:
        try:
            observer.poll(service.stdout, live=False)
        except (OSError, IOError, ValueError):
            pass
        for stream in (service.stdout, service.stderr, service.stdin):
            if stream is not None:
                try:
                    stream.close()
                except (OSError, IOError, ValueError):
                    pass
        output = bytes(observer.output_sample)
        if output:
            log('TV_VOICEINPUT=' + output.decode('utf-8', 'replace').strip()[:1000].replace('\n', ' '))
        log('TV_VOICEINPUT_CLEANUP=' + result)
    return result


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
    seconds = max(5.0, min(seconds, 20.0))
    stop_on_mic_off = len(sys.argv) > 2 and sys.argv[2] == '1'
    observer = VoiceStateWatcher()
    service = None
    sock = None
    try:
        service = subprocess.Popen(COMMAND, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
        deadline = time.time() + 12.0
        while time.time() < deadline:
            candidate = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            candidate.settimeout(0.8)
            try:
                candidate.connect(SOCKET_PATH)
                sock = candidate
                break
            except socket.error:
                candidate.close()
                time.sleep(0.3)
                if service.poll() is not None:
                    break
        if sock is None:
            log('TV_STREAM_ERROR unable_to_connect_socket; service_exit=' + str(service.poll()))
            return 2
        os.write(1, b'SHWMPCM1')
        end = time.time() + seconds
        total = 0
        carry = b''
        end_reason = 'DURATION_LIMIT'
        while time.time() < end:
            # Only poll Luna states for the explicit experimental MIC OFF mode.
            # The normal VAD path avoids extra reads from the TV service.
            if stop_on_mic_off:
                observer.poll(service.stdout)
            if stop_on_mic_off and observer.off_seen:
                end_reason = 'LG_MIC_OFF'
                log('TV_STOP_SIGNAL=MIC_OFF')
                break
            # SSH stdin stays open during capture. A single byte from HA on
            # confirmed speech end allows normal Luna/service cleanup instead
            # of waiting for the full eight-second recording window.
            if select.select([sys.stdin], [], [], 0)[0]:
                os.read(0, 1)
                end_reason = 'BRIDGE_STOP_REQUESTED'
                log('TV_STOP_REQUESTED')
                break
            try:
                block = sock.recv(3200)
            except socket.timeout:
                continue
            if not block:
                end_reason = 'PCM_STREAM_EOF'
                break
            block = carry + block
            even = len(block) & ~1
            if even:
                os.write(1, block[:even])
                total += even
            carry = block[even:]
        log('TV_STREAM_END_REASON=' + end_reason)
        log('TV_STREAM_BYTES=' + str(total))
        return 0 if total else 3
    except Exception as exc:
        log('TV_STREAM_EXCEPTION=' + str(exc))
        return 4
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        if service is not None:
            cleanup_voiceinput(service, observer)

if __name__ == '__main__':
    sys.exit(main())
