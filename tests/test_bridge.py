import sys
import pathlib
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'shwm_magic_remote_bridge'))
from app import is_voice_press, is_manual_test_event, tv_remote_command, settings, pcm16_metrics, VoiceEndDetector, classify_capture_error

def event(old='2026-11-05T12:00:00', new='2026-11-05T12:00:01', button='voice', entity='event.salon_lgtv_remote_button'):
    return {'event': {'data': {
        'entity_id': entity,
        'old_state': {'state': old, 'attributes': {'event_type': 'red'}},
        'new_state': {'state': new, 'attributes': {'event_type': button, 'button': button}},
    }}}

class EventTests(unittest.TestCase):
    def test_normal_voice(self):
        self.assertTrue(is_voice_press(event(), 'event.salon_lgtv_remote_button'))

    def test_recovery_ignored(self):
        self.assertFalse(is_voice_press(event(old='unavailable'), 'event.salon_lgtv_remote_button'))

    def test_non_voice_ignored(self):
        self.assertFalse(is_voice_press(event(button='red'), 'event.salon_lgtv_remote_button'))

    def test_other_tv_ignored(self):
        self.assertFalse(is_voice_press(event(entity='event.other'), 'event.salon_lgtv_remote_button'))

    def test_same_state_ignored(self):
        self.assertFalse(is_voice_press(event(new='2026-11-05T12:00:00'), 'event.salon_lgtv_remote_button'))

    def test_manual_event(self):
        self.assertTrue(is_manual_test_event({'type': 'event', 'id': 2, 'event': {'event_type': 'shwm_magic_remote_test'}}))

    def test_wrong_manual_event_type(self):
        self.assertFalse(is_manual_test_event({'type': 'event', 'id': 2, 'event': {'event_type': 'other_event'}}))

    def test_wrong_manual_event_id(self):
        self.assertFalse(is_manual_test_event({'type': 'event', 'id': 1, 'event': {'event_type': 'shwm_magic_remote_test'}}))

    def test_settings_default_manual_disabled(self):
        import tempfile, json, os
        cfg = {'tv_host': '192.168.1.224', 'tv_ssh_port': 22,
               'remote_event_entity': 'event.salon_lgtv_remote_button',
               'record_seconds': 8, 'execute_commands': False}
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'options.json')
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(cfg, fh)
            self.assertFalse(settings(path)['manual_test_enabled'])

    def test_pcm16_metrics_normal_signal(self):
        import struct
        block = struct.pack('<hhhh', 0, 100, -200, 32767)
        n, energy, peak = pcm16_metrics(block)
        self.assertEqual(n, 4)
        self.assertEqual(energy, 10000 + 40000 + 32767 ** 2)
        self.assertEqual(peak, 32767)

    def test_pcm16_metrics_silence(self):
        self.assertEqual(pcm16_metrics(b'\x00' * 640), (320, 0, 0))

    def test_pcm16_metrics_odd_byte_count(self):
        with self.assertRaises(ValueError):
            pcm16_metrics(b'\x00')

    def test_settings_default_audio_only_disabled(self):
        import tempfile, json, os
        cfg = {'tv_host': '192.168.1.224',
               'remote_event_entity': 'event.lg_tv_remote_button'}
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'options.json')
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(cfg, fh)
            self.assertFalse(settings(path)['manual_audio_only'])

    def test_vad_ends_after_confirmed_speech(self):
        import struct
        d = VoiceEndDetector(rms_threshold=250, silence_ms=1000)
        voiced = struct.pack('<h', 1200) * 1600
        quiet = bytes(3200)
        self.assertFalse(d.feed(voiced))
        self.assertFalse(d.feed(voiced))
        # Minimum two-second recording prevents premature end on a short word.
        for _ in range(17):
            self.assertFalse(d.feed(quiet))
        self.assertTrue(d.feed(quiet))

    def test_vad_tuning_preserves_existing_settings(self):
        import tempfile, json, os
        base = {'tv_host': '192.168.1.224',
                'remote_event_entity': 'event.salon_lgtv_remote_button'}
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'options.json')
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(base, fh)
            self.assertEqual(settings(path)['vad_silence_ms'], 1100)
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump({**base, 'vad_silence_ms': 1500}, fh)
            self.assertEqual(settings(path)['vad_silence_ms'], 1500)

    def test_vad_tracks_interrupted_silence_without_changing_stop_policy(self):
        import struct
        d = VoiceEndDetector(rms_threshold=250, silence_ms=1100)
        voiced = struct.pack('<h', 1000) * 1600
        quiet = bytes(3200)
        d.feed(voiced)
        d.feed(voiced)
        for _ in range(10):
            self.assertFalse(d.feed(quiet))
        self.assertEqual(d.longest_quiet_frames, 10)
        self.assertFalse(d.feed(voiced))  # A new word cancels the silence window.
        for _ in range(10):
            self.assertFalse(d.feed(quiet))
        self.assertTrue(d.feed(quiet))
        self.assertEqual(d.above_threshold_frames, 3)
        self.assertEqual(d.longest_quiet_frames, 11)

    def test_vad_does_not_stop_before_speech(self):
        d = VoiceEndDetector(rms_threshold=250, silence_ms=1000)
        for _ in range(100):
            self.assertFalse(d.feed(bytes(3200)))
        self.assertFalse(d.speech_confirmed)

    def test_vad_resets_silence_on_new_word(self):
        import struct
        d = VoiceEndDetector(rms_threshold=250, silence_ms=1500)
        voiced = struct.pack('<h', 1200) * 1600
        quiet = bytes(3200)
        d.feed(voiced)
        d.feed(voiced)
        for _ in range(12):
            self.assertFalse(d.feed(quiet))
        self.assertFalse(d.feed(voiced))
        for _ in range(14):
            self.assertFalse(d.feed(quiet))
        self.assertTrue(d.feed(quiet))

    def test_vad_handles_partial_frames(self):
        import struct
        d = VoiceEndDetector(rms_threshold=250, silence_ms=800)
        voiced = struct.pack('<h', 1200) * 1600
        self.assertFalse(d.feed(voiced[:713]))
        self.assertFalse(d.feed(voiced[713:]))
        self.assertEqual(d.frames, 1)

    def test_capture_errors(self):
        cases = [
            ('Permission denied (publickey)', 'SSH_AUTH_FAILED'),
            ('Host key verification failed', 'SSH_HOST_KEY_ERROR'),
            ('Connection timed out', 'TV_SSH_UNREACHABLE'),
            ('TV_STREAM_ERROR unable_to_connect_socket', 'TV_MIC_UNAVAILABLE'),
            ('fail to find voice device', 'TV_MIC_UNAVAILABLE'),
            ('timed out waiting for voice stream', 'TV_AUDIO_TIMEOUT'),
            ('unclassified', 'TV_CAPTURE_FAILED'),
        ]
        for message, code in cases:
            with self.subTest(code=code):
                self.assertEqual(classify_capture_error(message), code)

    def test_retry_default_enabled(self):
        import tempfile, json, os
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'options.json')
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump({'tv_host':'192.168.1.224', 'remote_event_entity':'event.lg_tv_remote_button'}, fh)
            self.assertTrue(settings(path)['mic_retry_enabled'])

    def test_mic_off_opt_in_is_disabled_by_default(self):
        import tempfile, json, os
        cfg = {'tv_host': '192.168.1.224',
               'remote_event_entity': 'event.salon_lgtv_remote_button'}
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'options.json')
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(cfg, fh)
            self.assertFalse(settings(path)['mic_off_stop_enabled'])
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump({**cfg, 'mic_off_stop_enabled': True}, fh)
            self.assertTrue(settings(path)['mic_off_stop_enabled'])
        self.assertTrue(tv_remote_command(8, True).endswith(' 8 1'))

    def test_remote_code_encoded(self):
        import base64, re, shlex, zlib
        from app import HELPER
        command = tv_remote_command(8)
        self.assertTrue(command.startswith('python -u -c'))
        self.assertTrue(command.endswith(' 8'))
        # The 2.1.10 raw-base64 command was >10 KB and rejected by LG SSH.
        # Verify exact source bytes survive compression, without TV file writes.
        self.assertLess(len(command.encode('ascii')), 8192)
        args = shlex.split(command)
        self.assertEqual(args[:3], ['python', '-u', '-c'])
        self.assertEqual(args[-1], '8')
        self.assertIn('exec(zlib.decompress(', args[3])
        match = re.search(r'base64\\.b64decode\\("([^"]+)"\\)', args[3])
        self.assertIsNotNone(match)
        self.assertEqual(zlib.decompress(base64.b64decode(match.group(1))),
                         HELPER.read_bytes())
        self.assertTrue(tv_remote_command(8, True).endswith(' 8 1'))
        self.assertLess(len(tv_remote_command(8, True).encode('ascii')), 8192)




class CaptureStartupTests(unittest.IsolatedAsyncioTestCase):
    def make_fake_proc(self, marker=None, stderr=b'', cancel=False):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        if cancel:
            output = AsyncMock(side_effect=asyncio.CancelledError())
        elif marker is None:
            output = AsyncMock(side_effect=asyncio.IncompleteReadError(partial=b'', expected=8))
        else:
            output = AsyncMock(return_value=marker)
        return SimpleNamespace(stdout=SimpleNamespace(readexactly=output),
                               stderr=SimpleNamespace(read=AsyncMock(return_value=stderr)),
                               returncode=2)

    def opts(self):
        return {'tv_host':'192.168.1.224', 'tv_ssh_port':22,
                'record_seconds':8, 'mic_retry_enabled':True}

    async def test_retry_once_only_when_mic_unavailable(self):
        from unittest.mock import AsyncMock, patch
        from app import open_tv_capture
        bad = self.make_fake_proc(stderr=b'TV_STREAM_ERROR unable_to_connect_socket')
        good = self.make_fake_proc(marker=b'SHWMPCM1')
        with patch('app.asyncio.create_subprocess_exec',
                   new=AsyncMock(side_effect=[bad, good])) as spawn, \
             patch('app.stop_capture_process', new=AsyncMock()) as cleanup, \
             patch('app.asyncio.sleep', new=AsyncMock()) as delay:
            result = await open_tv_capture(self.opts())
            self.assertIs(result, good)
            self.assertEqual(spawn.await_count, 2)
            cleanup.assert_awaited_once_with(bad)
            delay.assert_awaited_once()

    async def test_ssh_exit_255_is_classified_as_remote_exec_failure(self):
        from unittest.mock import AsyncMock, patch
        from app import open_tv_capture, TvCaptureError
        bad = self.make_fake_proc(stderr=b'non-specific remote exec failure')
        bad.returncode = 255
        with patch('app.asyncio.create_subprocess_exec',
                   new=AsyncMock(return_value=bad)) as spawn, \\
             patch('app.stop_capture_process', new=AsyncMock()) as cleanup:
            with self.assertRaises(TvCaptureError) as raised:
                await open_tv_capture(self.opts())
            self.assertEqual(raised.exception.code, 'SSH_REMOTE_EXEC_FAILED')
            self.assertEqual(spawn.await_count, 1)
            cleanup.assert_awaited_once_with(bad)

    async def test_ssh_auth_failure_never_retries(self):
        from unittest.mock import AsyncMock, patch
        from app import open_tv_capture, TvCaptureError
        bad = self.make_fake_proc(stderr=b'Permission denied (publickey)')
        with patch('app.asyncio.create_subprocess_exec',
                   new=AsyncMock(return_value=bad)) as spawn, \
             patch('app.stop_capture_process', new=AsyncMock()) as cleanup:
            with self.assertRaises(TvCaptureError) as raised:
                await open_tv_capture(self.opts())
            self.assertEqual(raised.exception.code, 'SSH_AUTH_FAILED')
            self.assertEqual(spawn.await_count, 1)
            cleanup.assert_awaited_once_with(bad)

    async def test_cancelled_capture_closes_ssh(self):
        import asyncio
        from unittest.mock import AsyncMock, patch
        from app import open_tv_capture
        bad = self.make_fake_proc(cancel=True)
        with patch('app.asyncio.create_subprocess_exec',
                   new=AsyncMock(return_value=bad)), \
             patch('app.stop_capture_process', new=AsyncMock()) as cleanup:
            with self.assertRaises(asyncio.CancelledError):
                await open_tv_capture(self.opts())
            cleanup.assert_awaited_once_with(bad)

if __name__ == '__main__':
    unittest.main()
