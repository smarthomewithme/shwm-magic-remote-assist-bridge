"""Optional webOS bottom-right overlay: safe payloads and graceful fallback."""
import asyncio
import json
import pathlib
import shlex
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] /
                       "shwm_magic_remote_bridge"))
from tv_toast import TvToastNotifier, tv_overlay_command, TV_OVERLAY_APP_ID


class OverlayContract(unittest.TestCase):
    def test_fixed_app_id_safe_text_and_bottom_right_app_styles(self):
        cmd = tv_overlay_command("HEARD", 'Cześć"; $(touch /tmp/pwn)', icons=True)
        args = shlex.split(cmd)
        self.assertEqual(args[:5], ["luna-send", "-n", "1", "-f",
                                    "luna://com.webos.applicationManager/launch"])
        data = json.loads(args[-1])
        self.assertEqual(data["id"], TV_OVERLAY_APP_ID)
        self.assertEqual(data["params"]["kind"], "listen")
        self.assertIn('$(touch /tmp/pwn)', data["params"]["message"])
        self.assertTrue(data["params"]["icons"])
        self.assertFalse(tv_overlay_command("DONE",icons=False).endswith("true"))
        with self.assertRaises(ValueError):
            tv_overlay_command("INVALID", "x")

    def test_no_overlays_without_explicit_optin(self):
        obj = TvToastNotifier({"tv_toasts_enabled": True,
                               "tv_toast_icons_enabled": True}, lambda _: [])
        self.assertFalse(obj.overlay_enabled)


class OverlayTransport(unittest.IsolatedAsyncioTestCase):
    async def test_overlay_accepted_uses_one_launch_no_native_toast(self):
        obj = TvToastNotifier({"tv_toasts_enabled": True,
                               "tv_overlay_enabled": True,
                               "tv_toast_icons_enabled": True}, lambda _: ["ssh"])
        async def run_cmd(command, kind, *, mode, icon_url=None):
            self.assertEqual(mode, "overlay")
            self.assertIn("applicationManager/launch", command)
            return True, "ACCEPTED"
        with patch.object(obj, "_send_luna", new=AsyncMock(side_effect=run_cmd)) as send:
            ok,reason = await obj.send_diagnostic("DONE")
        self.assertEqual((ok,reason),(True,"ACCEPTED"))
        send.assert_awaited_once()

    async def test_overlay_unavailable_falls_back_to_text_only_standard(self):
        obj = TvToastNotifier({"tv_toasts_enabled": True,
                               "tv_overlay_enabled": True,
                               "tv_toast_icons_enabled": True}, lambda _: ["ssh"])
        seen=[]
        async def send_cmd(command, kind, *, mode, icon_url=None):
            seen.append((command,mode))
            if mode=="overlay": return False, "SERVICE_REJECTED"
            return True,"ACCEPTED"
        with patch.object(obj, "_send_luna", new=send_cmd):
            ok, reason = await obj.send_diagnostic("DONE")
        self.assertEqual((ok,reason),(True,"ACCEPTED"))
        self.assertEqual([i[1] for i in seen], ["overlay","native"])
        fallback_payload=json.loads(shlex.split(seen[-1][0])[-1])
        self.assertEqual(fallback_payload, {"message": "SHWM Voice: polecenie przyjęte"})

    async def test_overlay_mode_does_not_install_temporary_icons(self):
        obj = TvToastNotifier({"tv_toasts_enabled": True,
                               "tv_overlay_enabled": True,
                               "tv_toast_icons_enabled": True}, lambda _: [])
        with patch("tv_toast.asyncio.create_subprocess_exec",new=AsyncMock()) as spawn:
            await obj.prepare_icons()
        spawn.assert_not_awaited()

    async def test_disabled_master_prevents_any_talk_to_tv(self):
        obj = TvToastNotifier({"tv_toasts_enabled": False,
                               "tv_overlay_enabled": True}, lambda _: [])
        with patch.object(obj, "_send_luna",new=AsyncMock()) as send:
            self.assertEqual(await obj.send_diagnostic("DONE"),
                             (False, "FEATURE_DISABLED"))
        send.assert_not_awaited()


class OverlayMarkup(unittest.TestCase):
    def test_markup_is_ephemeral_and_does_not_interpret_user_text(self):
        page = (pathlib.Path(__file__).resolve().parents[1] /
                "tv_overlay/index.html").read_text(encoding="utf-8")
        self.assertIn('right:54px;bottom:52px', page)
        self.assertIn('label.textContent=message.slice(0,140)', page)
        self.assertIn('PalmSystem.setInputRegion', page)
        self.assertIn('PalmSystem.window.setFocus(false)', page)
        self.assertIn('window.close()', page)
        self.assertNotIn('innerHTML', page)
        self.assertNotIn('fetch(', page)
        self.assertNotIn('XMLHttpRequest', page)


if __name__ == "__main__":
    unittest.main()
