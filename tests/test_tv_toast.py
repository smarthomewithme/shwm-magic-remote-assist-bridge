"""v2.1.2: LG-verified toast invocation and voice-path regression tests."""
import asyncio
import base64
import json
import pathlib
import shlex
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import ClientSession, web

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] /
                       'shwm_magic_remote_bridge'))
from app import pipe_voice_to_ha, run_pipeline, task_finished
from pairing import create_panel, page
from tv_toast import TvToastNotifier, tv_toast_command, TOAST_MESSAGES, _luna_reply, _service_reason


def fake_public_key():
    blob = (struct.pack(">I", 11) + b"ssh-ed25519" +
            struct.pack(">I", 32) + bytes(range(32)))
    return "ssh-ed25519 " + base64.b64encode(blob).decode() + " test"


def options(enabled=True):
    return {"tv_host":"192.168.1.224",
            "tv_toasts_enabled":enabled,
            "execute_commands":True,
            "record_seconds":8,
            "vad_enabled":False,
            "vad_rms_threshold":250,
            "vad_silence_ms":1500,
            "pipeline_id":"",
            "log_transcript":False}


class ToastContractTests(unittest.TestCase):
    def test_only_fixed_statuses_and_valid_quoted_json(self):
        for kind, message in TOAST_MESSAGES.items():
            args=shlex.split(tv_toast_command(kind))
            self.assertEqual(args[:4], ["luna-send", "-n", "1", "-f"])
            self.assertEqual(args[4],
                "luna://com.webos.notification/createToast")
            self.assertEqual(json.loads(args[5]), {"message": message})
            self.assertNotIn("-a", args)
            self.assertNotIn("sourceId", args[5])
            self.assertLessEqual(len(message),60)
        with self.assertRaises(ValueError):
            tv_toast_command("USER_TEXT:\"; rm -rf /")
        self.assertNotIn("token",json.dumps(TOAST_MESSAGES).lower())

    def test_web_ui_has_only_one_explicit_test_button(self):
        html=page("192.168.1.224",8080,fake_public_key())
        self.assertIn('id="toast-test"',html)
        self.assertIn("fetch('test-toast'",html)
        self.assertIn("tv_toasts_enabled",html)


class ErrorClassificationTests(unittest.TestCase):
    def test_find_real_luna_json_after_line_prefix(self):
        raw = b'sending request...\\n{ "returnValue": true, "toastId": "test" }\\n'
        self.assertEqual(_luna_reply(raw)["returnValue"], True)

    def test_do_not_treat_prose_success_as_confirmation(self):
        self.assertIsNone(_luna_reply(b'returnValue true'))
        self.assertEqual(_service_reason({"returnValue": False,
                                          "errorText": "Permission Denied"}),
                         "SERVICE_PERMISSION_DENIED")
        self.assertEqual(_service_reason({"returnValue": False,
                                          "errorText": "Unknown Source"}),
                         "SERVICE_UNKNOWN_SOURCE")
        self.assertEqual(_service_reason({"returnValue": False,
                                          "errorCode": 124}),
                         "SERVICE_ERROR_124")


class NotifierTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_by_default_never_opens_ssh(self):
        obj=TvToastNotifier({},lambda _:[])
        self.assertFalse(obj.enabled)
        with patch('tv_toast.asyncio.create_subprocess_exec', new=AsyncMock()) as spawn:
            self.assertFalse(await obj.send("TEST"))
            obj.emit("LISTENING")
            await asyncio.sleep(0)
            spawn.assert_not_awaited()

    async def test_one_fixed_request_and_confirmed_response(self):
        proc=SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(return_value=(b'{"returnValue":true}',b'')),
            kill=Mock())
        obj=TvToastNotifier(options(),lambda _:["ssh","root@192.168.1.224"])
        with patch('tv_toast.asyncio.create_subprocess_exec',new=AsyncMock(return_value=proc)) as spawn, \
             self.assertLogs('shwm_magic_remote',level='INFO') as logs:
            self.assertTrue(await obj.send("TEST"))
        self.assertEqual(spawn.await_args.args[:2],("ssh","root@192.168.1.224"))
        cmd=spawn.await_args.args[-1]
        self.assertEqual(json.loads(shlex.split(cmd)[-1])["message"],
                         TOAST_MESSAGES["TEST"])
        self.assertIn("TV_TOAST_SENT kind=TEST","\n".join(logs.output))
        proc.kill.assert_not_called()

    async def test_structured_luna_response_on_stderr(self):
        proc=SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(return_value=(
                b'', b'warning: harmless notice\\n{"returnValue": true, "toastId": "abc"}\\n')),
            kill=Mock())
        obj=TvToastNotifier(options(),lambda _:["ssh"])
        with patch('tv_toast.asyncio.create_subprocess_exec',new=AsyncMock(return_value=proc)):
            ok,reason=await obj.send_diagnostic("TEST")
        self.assertTrue(ok)
        self.assertEqual(reason, "ACCEPTED")

    async def test_no_structured_reply_logs_only_safe_counts(self):
        stderr=b'remote detail should never appear in logs'
        proc=SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(return_value=(b'',stderr)),
            kill=Mock())
        obj=TvToastNotifier(options(),lambda _:["ssh"])
        with patch('tv_toast.asyncio.create_subprocess_exec',new=AsyncMock(return_value=proc)), \\
             self.assertLogs('shwm_magic_remote',level='INFO') as logs:
            ok,reason=await obj.send_diagnostic("TEST")
        self.assertFalse(ok)
        self.assertEqual(reason, "NO_VALID_LUNA_RESPONSE")
        combined="\\n".join(logs.output)
        self.assertIn("ssh_exit=0",combined)
        self.assertIn("stdout_bytes=0",combined)
        self.assertIn("stderr_bytes="+str(len(stderr)),combined)
        self.assertNotIn("remote detail",combined)

    async def test_failed_toast_is_not_fatal_or_retried(self):
        proc=SimpleNamespace(
            returncode=1,
            communicate=AsyncMock(return_value=(b'{"returnValue":false}',b'')),
            kill=Mock())
        obj=TvToastNotifier(options(),lambda _:["ssh"])
        with patch('tv_toast.asyncio.create_subprocess_exec',new=AsyncMock(return_value=proc)) as spawn:
            self.assertFalse(await obj.send("DONE"))
        spawn.assert_awaited_once()

    async def test_malformed_service_response_is_not_success(self):
        proc=SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(return_value=(b'not json',b'')),
            kill=Mock())
        obj=TvToastNotifier(options(),lambda _:["ssh"])
        with patch('tv_toast.asyncio.create_subprocess_exec',new=AsyncMock(return_value=proc)):
            self.assertFalse(await obj.send("TEST"))

    async def test_rejection_code_is_safe_and_specific(self):
        proc=SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(return_value=(
                b'{"returnValue":false,"errorText":"Permission Denied","secret":"test"}',b'')),
            kill=Mock())
        obj=TvToastNotifier(options(),lambda _:["ssh"])
        with patch('tv_toast.asyncio.create_subprocess_exec',new=AsyncMock(return_value=proc)), \
             self.assertLogs('shwm_magic_remote',level='INFO') as logs:
            ok,reason=await obj.send_diagnostic("TEST")
        self.assertFalse(ok)
        self.assertEqual(reason,"SERVICE_PERMISSION_DENIED")
        self.assertNotIn("secret","\\n".join(logs.output))
        self.assertIn("SERVICE_PERMISSION_DENIED","\\n".join(logs.output))

    async def test_start_status_nonblocking_during_pcm(self):
        proc=SimpleNamespace(
            stdout=SimpleNamespace(read=AsyncMock(side_effect=[bytes(6400),b''])),
            stderr=SimpleNamespace(read=AsyncMock(return_value=b'')))
        ws=SimpleNamespace(closed=False,send_bytes=AsyncMock())
        notice=SimpleNamespace(emit=Mock())
        with patch("app.open_tv_capture",new=AsyncMock(return_value=proc)), \
             patch("app.stop_capture_process",new=AsyncMock()):
            await pipe_voice_to_ha(ws,17,options(),{},toast=notice)
        notice.emit.assert_called_once_with("LISTENING")
        self.assertEqual(ws.send_bytes.await_args.args[0],b'\x11')

    async def test_error_status_does_not_replay_actions(self):
        notice=SimpleNamespace(emit=Mock())
        fake=SimpleNamespace(cancelled=lambda:False,exception=lambda:RuntimeError("failed"))
        with self.assertLogs("shwm_magic_remote",level="ERROR"):
            task_finished(fake, toast=notice)
        notice.emit.assert_called_once_with("ERROR")



class VoiceOutcomeToastTests(unittest.IsolatedAsyncioTestCase):
    async def check(self, response_type, speech, expected):
        import json as module_json
        def event(event_type, data=None):
            return SimpleNamespace(
                type=__import__('aiohttp').WSMsgType.TEXT,
                data=module_json.dumps({
                    "type":"event","id":17,
                    "event":{"type":event_type,"data":data or {}}}))
        ws=SimpleNamespace(
            send_json=AsyncMock(),
            receive_json=AsyncMock(return_value={
                "type":"event","id":17,
                "event":{"type":"run-start",
                         "data":{"runner_data":{"stt_binary_handler_id":17}}}
            }),
            receive=AsyncMock(side_effect=[
                event("stt-end",{"stt_output":{"text":"Testowy tekst"}}),
                event("intent-end",{"intent_output":{
                    "response":{"response_type":response_type,
                    "speech":{"plain":{"speech":speech}}}}}),
                event("run-end")
            ])
        )
        class Context:
            async def __aenter__(self): return ws
            async def __aexit__(self,*args): return False
        async def fake_capture(ws,handler_id,opts,metrics,toast=None):
            self.assertEqual(handler_id,17)
            self.assertIsNotNone(toast)
            metrics.update({"tv_mic_ready_seconds":0.7,
                            "audio_captured_seconds":2.0,
                            "capture_cleanup_seconds":0.02})
            toast.emit("LISTENING")
        note=SimpleNamespace(emit=Mock())
        with patch("app.auth_ws",new=AsyncMock(return_value=Context())), \
             patch("app.pipe_voice_to_ha",new=AsyncMock(side_effect=fake_capture)):
            await run_pipeline(None,"ignored",options(),toast=note)
        self.assertEqual([x.args[0] for x in note.emit.call_args_list],
                         ["LISTENING", expected])
        ws.send_json.assert_awaited_once()

    async def test_action_and_query_have_different_toasts(self):
        await self.check("action_done","Polecenie przyjęte","DONE")
        await self.check("query_answer","Telewizor jest włączony","ANSWER")

    async def test_provider_failure_does_not_toast_success(self):
        await self.check("action_done",
            "Sorry, I had a problem talking to OpenAI: Error code: 503 - cloudflare_transient_cooldown",
            "AI_UNAVAILABLE")


class PanelTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.pub=pathlib.Path(self.temp.name)/"key.pub"
        self.pub.write_text(fake_public_key(),encoding="ascii")
        self.notifier=SimpleNamespace(enabled=True,send_diagnostic=AsyncMock(return_value=(True,"ACCEPTED")))
        self.app=create_panel({"tv_host":"192.168.1.224","glasshouse_port":8080},
            str(self.pub),lambda _:[],notifier=self.notifier)
        self.guard=patch("pairing.INGRESS_IP","127.0.0.1")
        self.guard.start()
        self.runner=web.AppRunner(self.app)
        await self.runner.setup()
        self.site=web.TCPSite(self.runner,"127.0.0.1",0)
        await self.site.start()
        self.url="http://127.0.0.1:"+str(self.site._server.sockets[0].getsockname()[1])

    async def asyncTearDown(self):
        await self.runner.cleanup()
        self.guard.stop()
        self.temp.cleanup()

    async def test_admin_explicit_safe_toast_only(self):
        async with ClientSession() as client:
            async with client.post(self.url+"/test-toast",json={"confirm":True}) as response:
                self.assertEqual(response.status,200)
                self.assertEqual((await response.json())["code"],"ACCEPTED")
        self.notifier.send_diagnostic.assert_awaited_once_with("TEST")

    async def test_sanitized_rejection_code_visible(self):
        self.notifier.send_diagnostic.return_value=(False,"SERVICE_UNKNOWN_SOURCE")
        async with ClientSession() as client:
            async with client.post(self.url+"/test-toast",json={"confirm":True}) as response:
                self.assertEqual(response.status,503)
                self.assertEqual((await response.json())["code"],"SERVICE_UNKNOWN_SOURCE")
        self.notifier.send_diagnostic.assert_awaited_once_with("TEST")

    async def test_no_confirmation_does_not_send_anything(self):
        async with ClientSession() as client:
            async with client.post(self.url+"/test-toast",json={"message":"evil"}) as response:
                self.assertEqual(response.status,400)
        self.notifier.send_diagnostic.assert_not_awaited()

    async def test_disabled_feature_does_not_send_anything(self):
        self.notifier.enabled=False
        async with ClientSession() as client:
            async with client.post(self.url+"/test-toast",json={"confirm":True}) as response:
                self.assertEqual(response.status,409)
                self.assertEqual((await response.json())["code"],"FEATURE_DISABLED")
        self.notifier.send_diagnostic.assert_not_awaited()

    async def test_ingress_policy_on_toast_request(self):
        with patch("pairing.INGRESS_IP","192.0.2.10"):
            async with ClientSession() as client:
                async with client.post(self.url+"/test-toast",json={"confirm":True}) as response:
                    self.assertEqual(response.status,403)
        self.notifier.send_diagnostic.assert_not_awaited()


if __name__=="__main__":
    unittest.main()
