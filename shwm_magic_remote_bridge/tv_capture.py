# -*- coding: ascii -*-
"""Rooted webOS capture: PCM16LE only on stdout, diagnostics on stderr.

No audio or helper file is saved on the television.
"""
from __future__ import print_function
import os
import sys
import time
import socket
import subprocess

SOCKET_PATH = '/tmp/voiceinput_remote1.soc'
COMMAND = ['luna-send', '-i', '-f',
           'luna://com.webos.service.voiceinput/startStreaming',
           '{"deviceType":"remote","keyType":"thinQtv","subscribe":true}']

def log(message):
    sys.stderr.write(message + '\n')
    sys.stderr.flush()

def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
    seconds = max(5.0, min(seconds, 20.0))
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
        while time.time() < end:
            try:
                block = sock.recv(3200)
            except socket.timeout:
                continue
            if not block:
                break
            block = carry + block
            even = len(block) & ~1
            if even:
                os.write(1, block[:even])
                total += even
            carry = block[even:]
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
            if service.poll() is None:
                try:
                    service.terminate()
                except Exception:
                    pass
            try:
                output = service.communicate()[0]
                if output:
                    if not isinstance(output, str):
                        output = output.decode('utf-8', 'replace')
                    log('TV_VOICEINPUT=' + output.strip()[:1000].replace('\n', ' '))
            except Exception:
                pass

if __name__ == '__main__':
    sys.exit(main())
