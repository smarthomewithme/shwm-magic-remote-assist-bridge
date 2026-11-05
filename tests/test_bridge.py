import sys
import pathlib
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'shwm_magic_remote_bridge'))
from app import is_voice_press, is_manual_test_event, tv_remote_command, settings, pcm16_metrics

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
        self.assertEqual(pcm16_metrics(b'\\x00' * 640), (320, 0, 0))

    def test_pcm16_metrics_odd_byte_count(self):
        with self.assertRaises(ValueError):
            pcm16_metrics(b'\\x00')

    def test_settings_default_audio_only_disabled(self):
        import tempfile, json, os
        cfg = {'tv_host': '192.168.1.224',
               'remote_event_entity': 'event.lg_tv_remote_button'}
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'options.json')
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(cfg, fh)
            self.assertFalse(settings(path)['manual_audio_only'])

    def test_remote_code_encoded(self):
        command = tv_remote_command(8)
        self.assertTrue(command.startswith('python -u -c'))
        self.assertTrue(command.endswith(' 8'))

if __name__ == '__main__':
    unittest.main()
