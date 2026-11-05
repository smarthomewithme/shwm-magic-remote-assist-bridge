import sys
import pathlib
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'shwm_magic_remote_bridge'))
from app import is_voice_press, tv_remote_command

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

    def test_remote_code_encoded(self):
        command = tv_remote_command(8)
        self.assertTrue(command.startswith('python -u -c'))
        self.assertTrue(command.endswith(' 8'))

if __name__ == '__main__':
    unittest.main()
