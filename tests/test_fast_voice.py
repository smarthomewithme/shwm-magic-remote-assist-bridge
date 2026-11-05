"""Latency and regression tests: fast VAD stop and reusable SSH transport."""
import asyncio
import pathlib
import struct
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'shwm_magic_remote_bridge'))
from app import ssh_args, stop_capture_process, warmup_ssh, pipe_voice_to_ha
import tv_capture


def opts(mux=True, vad=True):
    return {
        'tv_host':'192.168.1.224',
        'tv_ssh_port':22,
        'record_seconds':8,
        'ssh_warmup_enabled':mux,
        'mic_retry_enabled':True,
        'vad_enabled':vad,
        'vad_rms_threshold':250,
        'vad_silence_ms':1500,
    }


class TransportOptionsTests(unittest.TestCase):
    def test_mux_is_private_and_optional(self):
        default=ssh_args(opts())
        self.assertIn('ControlMaster=auto', default)
        self.assertIn('ControlPersist=180', default)
        self.assertTrue(any(v.startswith('ControlPath=/run/shwm_magic_remote/') for v in default))
        self.assertIn('BatchMode=yes', default)
        self.assertNotIn('StrictHostKeyChecking=no', default)
        disabled=ssh_args(opts(mux=False))
        self.assertFalse(any(v.startswith('ControlPath=') for v in disabled))
        self.assertFalse(any(v.startswith('ControlMaster=') for v in disabled))

    def test_tv_helper_listens_for_stop_without_writing_audio_to_file(self):
        source=pathlib.Path(tv_capture.__file__).read_text()
        self.assertIn('select.select([sys.stdin], [], [], 0)',source)
        self.assertIn("log('TV_STOP_REQUESTED')",source)
        self.assertIn('sock.close()',source)
        self.assertIn('service.terminate()',source)


class FastExitTests(unittest.IsolatedAsyncioTestCase):
    def make_proc(self, wait):
        return SimpleNamespace(
            returncode=None,
            stdin=SimpleNamespace(write=Mock(),drain=AsyncMock()),
            wait=AsyncMock(side_effect=wait),
            terminate=Mock(),
            kill=Mock(),
        )

    async def test_vad_stop_sends_signal_and_does_not_wait_two_seconds(self):
        proc=self.make_proc([0])
        with patch('app.asyncio.wait_for',side_effect=lambda aw,timeout:aw) as bounded:
            await stop_capture_process(proc,graceful=True)
        proc.stdin.write.assert_called_once_with(b'S\n')
        proc.stdin.drain.assert_awaited_once()
        proc.wait.assert_awaited_once()
        proc.terminate.assert_not_called()
        proc.kill.assert_not_called()
        self.assertIn(0.9, [x.kwargs['timeout'] for x in bounded.call_args_list])

    async def test_legacy_remote_ignoring_stop_falls_back_to_terminate(self):
        proc=self.make_proc([asyncio.TimeoutError(),0])
        await stop_capture_process(proc,graceful=True)
        proc.stdin.write.assert_called_once()
        proc.terminate.assert_called_once()
        proc.kill.assert_not_called()

    async def test_ordinary_capture_does_not_send_stop_signal(self):
        proc=self.make_proc([0])
        await stop_capture_process(proc,graceful=False)
        proc.stdin.write.assert_not_called()
        proc.terminate.assert_not_called()


class AudioStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_vad_sends_stt_end_and_graceful_tv_stop(self):
        voiced=struct.pack('<h',900) * 3200 # 200ms
        quiet=bytes(3200 * 18)              # 1.8sec
        proc=SimpleNamespace(
            stdout=SimpleNamespace(read=AsyncMock(side_effect=[voiced,quiet])),
            stderr=SimpleNamespace(read=AsyncMock(return_value=b'')),
        )
        ws=SimpleNamespace(closed=False,send_bytes=AsyncMock())
        with patch('app.open_tv_capture',new=AsyncMock(return_value=proc)), \
             patch('app.stop_capture_process',new=AsyncMock()) as stop:
            await pipe_voice_to_ha(ws,17,opts(vad=True))
        stop.assert_awaited_once_with(proc,graceful=True)
        self.assertEqual(ws.send_bytes.await_args_list[-1].args[0],b'\x11')

    async def test_no_vad_keeps_original_capture_cleanup(self):
        pcm=bytes(6400)
        proc=SimpleNamespace(
            stdout=SimpleNamespace(read=AsyncMock(side_effect=[pcm,b''])),
            stderr=SimpleNamespace(read=AsyncMock(return_value=b'')),
        )
        ws=SimpleNamespace(closed=False,send_bytes=AsyncMock())
        with patch('app.open_tv_capture',new=AsyncMock(return_value=proc)), \
             patch('app.stop_capture_process',new=AsyncMock()) as stop:
            await pipe_voice_to_ha(ws,17,opts(vad=False))
        stop.assert_awaited_once_with(proc,graceful=False)


class WarmupTests(unittest.IsolatedAsyncioTestCase):
    async def test_warmup_only_opens_ssh_without_tv_write_or_microphone(self):
        proc=SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(return_value=(b'',b'')),
            kill=Mock()
        )
        with patch('app.asyncio.create_subprocess_exec',new=AsyncMock(return_value=proc)) as spawn:
            await warmup_ssh(opts())
        args=spawn.await_args.args
        self.assertEqual(args[-1],'true')
        self.assertIn('BatchMode=yes',args)
        self.assertNotIn('luna-send',args)
        proc.kill.assert_not_called()


if __name__ == '__main__':
    unittest.main()
