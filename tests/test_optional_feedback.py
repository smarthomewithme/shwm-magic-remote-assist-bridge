"""Regression tests for v2.1.6 optional TV feedback and local icons."""
import asyncio
import json
import pathlib
import shlex
import struct
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import aiohttp

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] /
                       "shwm_magic_remote_bridge"))

from app import run_pipeline
from tv_icons import KINDS, icon_png
from tv_toast import (TvToastNotifier, SessionToast, tv_toast_command,
                      toast_message, TV_ICON_DIR, TOAST_MESSAGES)


def opts():
    return {
        "tv_host": "192.168.1.224", "tv_toasts_enabled": True,
        "tv_toast_icons_enabled": False, "tv_toast_transcript_enabled": True,
        "tv_toast_assist_reply_enabled": True, "execute_commands": True,
        "record_seconds": 8, "pipeline_id": "", "log_transcript": False,
    }


def event(kind, data=None):
    return SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data=json.dumps({
        "type": "event", "id": 17,
        "event": {"type": kind, "data": data or {}}
    }))


class TVTextTests(unittest.TestCase):
    def test_static_status_unchanged(self):
        cmd = tv_toast_command("DONE")
        data = json.loads(shlex.split(cmd)[-1])
        self.assertEqual(data, {"message": TOAST_MESSAGES["DONE"]})

    def test_private_content_is_sanitized_and_truncated(self):
        malicious = "Otwórz bramę; $(rm -rf /)\n" + "a" * 120 + "\u202e"
        cmd = tv_toast_command("HEARD", malicious)
        args = shlex.split(cmd)
        self.assertEqual(args[:4], ["luna-send", "-n", "1", "-f"])
        data = json.loads(args[-1])
        value = data["message"]
        self.assertTrue(value.startswith("Usłyszałem: "))
        self.assertLessEqual(len(value), 60)
        self.assertNotIn("\n", value)
        self.assertNotIn("\u202e", value)
        self.assertNotIn("iconUrl", data)
        self.assertIn("$(rm -rf /)", value)  # displayed, never executed

    def test_disallow_dynamic_without_text_and_unapproved_images(self):
        with self.assertRaises(ValueError):
            tv_toast_command("HEARD")
        with self.assertRaises(ValueError):
            tv_toast_command("DONE", "arbitrary override")
        with self.assertRaises(ValueError):
            tv_toast_command("DONE", icon_url="file:///etc/passwd")
        with self.assertRaises(ValueError):
            toast_message("HEARD", "\x00\n")

    def test_known_local_icon_field(self):
        png_url = "file://" + TV_ICON_DIR + "/done.png"
        data = json.loads(shlex.split(tv_toast_command("DONE", icon_url=png_url))[-1])
        self.assertEqual(data["iconUrl"], png_url)

    def test_icons_are_valid_80_by_80_png(self):
        for kind in KINDS:
            blob = icon_png(kind)
            self.assertEqual(blob[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", blob[16:24]), (80, 80))
            self.assertLess(len(blob), 20000)


class FeedbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_optional_transcript_and_confirmed_response(self):
        ws = SimpleNamespace(
            send_json=AsyncMock(),
            receive_json=AsyncMock(return_value={
                "type": "event", "id": 17,
                "event": {"type": "run-start", "data": {"runner_data": {
                    "stt_binary_handler_id": 17
                }}}
            }),
            receive=AsyncMock(side_effect=[
                event("stt-end", {"stt_output": {"text": "Włącz światło w jadalni"}}),
                event("intent-end", {"intent_output": {"response": {
                    "response_type": "action_done",
                    "speech": {"plain": {"speech": "Włączyłem światło w jadalni."}}
                }}}),
                event("run-end")
            ])
        )

        class Context:
            async def __aenter__(self): return ws
            async def __aexit__(self, *args): return False

        async def fake_capture(ws, handler_id, settings, metrics, toast=None):
            self.assertEqual(handler_id, 17)
            metrics.update({"tv_mic_ready_seconds": 0.8,
                            "audio_captured_seconds": 2,
                            "capture_cleanup_seconds": 0.05})
            toast.emit("LISTENING")

        notice = SimpleNamespace(emit=Mock(), emit_detail=Mock(),
                                 processing_after=Mock())
        with patch("app.auth_ws", new=AsyncMock(return_value=Context())), \
             patch("app.pipe_voice_to_ha", new=AsyncMock(side_effect=fake_capture)):
            await run_pipeline(None, "ignored", opts(), toast=notice)

        notice.emit.assert_called_once_with("LISTENING")
        self.assertEqual(
            [call.args for call in notice.emit_detail.call_args_list],
            [("HEARD", "Włącz światło w jadalni"),
             ("ACTION_DETAIL", "Włączyłem światło w jadalni.")]
        )
        ws.send_json.assert_awaited_once()

    async def test_disabled_details_fall_back_to_original_done(self):
        notice = TvToastNotifier({**opts(), "tv_toasts_enabled": False},
                                 lambda _: ["ssh"])
        with patch("tv_toast.asyncio.create_subprocess_exec", new=AsyncMock()) as spawn:
            session = notice.new_session()
            session.emit_detail("HEARD", "example")
            session.emit("DONE")
            await asyncio.sleep(0)
            spawn.assert_not_awaited()

    async def test_terminal_detail_cancels_pending_processing(self):
        notice = TvToastNotifier(opts(), lambda _: ["ssh"])
        with patch.object(notice, "send", new=AsyncMock(return_value=True)) as send:
            session = notice.new_session()
            session.processing_after(0.02)
            session.emit_detail("ACTION_DETAIL", "Włączyłem światło")
            await asyncio.sleep(0.06)
        self.assertEqual([call.args[0] for call in send.await_args_list],
                         ["ACTION_DETAIL"])

    async def test_session_newer_message_discards_old_private_content(self):
        notice = TvToastNotifier(opts(), lambda _: ["ssh"])
        with patch.object(notice, "send", new=AsyncMock(return_value=True)) as send:
            old = notice.new_session()
            old.emit_detail("HEARD", "Prywatna wypowiedź")
            new = notice.new_session()
            new.emit("LISTENING")
            await asyncio.sleep(0.02)
        self.assertEqual([call.args[0] for call in send.await_args_list], ["LISTENING"])

    async def test_legacy_status_defaults_have_no_private_message(self):
        notice = TvToastNotifier(opts(), lambda _: ["ssh"])
        with patch.object(notice, "send", new=AsyncMock(return_value=True)) as send:
            notice.emit("DONE")
            await asyncio.sleep(0.02)
        send.assert_awaited_once_with("DONE")


if __name__ == "__main__":
    unittest.main()
