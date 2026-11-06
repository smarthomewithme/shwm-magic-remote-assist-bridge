"""v2 in-place upgrade: never label cloud/router errors as executed intent."""
import json
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiohttp

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] /
                       'shwm_magic_remote_bridge'))
from app import classify_intent_result, run_pipeline
from runtime_status import BridgeStatus


def response(text, kind="action_done"):
    return {"response": {
        "response_type": kind,
        "speech": {"plain": {"speech": text}}
    }}


class ClassifierTests(unittest.TestCase):
    def test_observed_503_is_router_error_even_with_action_done(self):
        text = ("Sorry, I had a problem talking to OpenAI: Error code: 503 - "
                "{'error': {'message': 'Fallback providers are disabled until "
                "SHWM_ROUTER_TOKEN is configured.', 'reason': 'cloudflare_transient_cooldown'}}")
        self.assertEqual(classify_intent_result(response(text)),
                         "AI_ROUTER_UNAVAILABLE")

    def test_other_upstream_error_responses(self):
        self.assertEqual(
            classify_intent_result(response("No permission", "error")),
            "INTENT_ERROR")
        self.assertEqual(classify_intent_result(response("Cloudflare_transient_cooldown")),
                         "AI_ROUTER_UNAVAILABLE")
        self.assertEqual(classify_intent_result({}), "INTENT_UNVERIFIED")
        self.assertEqual(classify_intent_result({"response": {"response_type": "action_done", "speech": None}}),
                         "OK")

    def test_real_success_and_status_query(self):
        for kind in ("action_done", "query_answer"):
            with self.subTest(kind=kind):
                self.assertEqual(classify_intent_result(response("Włączam światło", kind)), "OK")

    def test_educational_503_not_misclassified(self):
        self.assertEqual(classify_intent_result(
            response("HTTP error code: 503 means service unavailable.")), "OK")


class Context:
    def __init__(self, ws):
        self.ws=ws
    async def __aenter__(self):
        return self.ws
    async def __aexit__(self, *_):
        return False


def event(kind, data=None):
    return SimpleNamespace(
        type=aiohttp.WSMsgType.TEXT,
        data=json.dumps({"type":"event","id":17,
                         "event":{"type":kind,"data":data or {}}})
    )


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def run_simulated(self, answer, execute_commands=True):
        ws=SimpleNamespace(
            send_json=AsyncMock(),
            receive_json=AsyncMock(return_value={
                "type":"event","id":17,"event":{
                    "type":"run-start","data":{
                        "runner_data":{"stt_binary_handler_id":17}}}}),
            receive=AsyncMock(side_effect=[
                event("stt-end", {"stt_output":{"text":"Włącz światło w jadalni"}}),
                event("intent-end", {"intent_output":answer}) if execute_commands else event("run-end"),
                event("run-end"),
            ])
        )
        opts={"execute_commands":execute_commands, "pipeline_id":"",
              "log_transcript":True}
        monitor=BridgeStatus(version="2.0.0")
        monitor.set_ready(True)
        monitor.begin()
        async def no_capture(ws, handler, opts, metrics):
            metrics.update({"tv_mic_ready_seconds":0.7,
                            "audio_captured_seconds":2.0,
                            "capture_cleanup_seconds":0.05})
        with patch("app.auth_ws",new=AsyncMock(return_value=Context(ws))), \
             patch("app.pipe_voice_to_ha",new=AsyncMock(side_effect=no_capture)), \
             self.assertLogs("shwm_magic_remote",level="INFO") as logs:
            await run_pipeline(None, "ignored", opts, monitor=monitor)
        return "\n".join(logs.output), monitor.snapshot(), ws

    async def test_router_503_is_warning_and_no_action_confirmation(self):
        error = ("Sorry, I had a problem talking to OpenAI: Error code: 503 - "
                 "{'error': {'message': 'Fallback providers are disabled until "
                 "SHWM_ROUTER_TOKEN is configured.', 'reason': 'cloudflare_transient_cooldown'}}")
        log, state, ws = await self.run_simulated(response(error))
        self.assertIn("ASSIST_INTENT_FAILED code=AI_ROUTER_UNAVAILABLE",log)
        self.assertIn("COMPLETE result=AI_ROUTER_UNAVAILABLE",log)
        self.assertNotIn("ASSIST_INTENT_SUCCESS",log)
        self.assertNotIn("Fallback providers",log)
        self.assertNotIn("cloudflare_transient_cooldown",log)
        self.assertEqual(state["last_result"],"AI_ROUTER_UNAVAILABLE")
        self.assertEqual(state["history"][-1]["result"],"AI_ROUTER_UNAVAILABLE")
        ws.send_json.assert_awaited_once()

    async def test_legitimate_success(self):
        log, state, _ = await self.run_simulated(response("Włączam światło w jadalni"))
        self.assertIn("ASSIST_INTENT_SUCCESS response_type=action_done",log)
        self.assertIn("COMPLETE result=OK",log)
        self.assertEqual(state["last_result"],"OK")

    async def test_stt_only_never_executes_intent(self):
        log, state, ws = await self.run_simulated({},execute_commands=False)
        self.assertEqual(state["last_result"],"OK")
        self.assertNotIn("ASSIST_INTENT_SUCCESS",log)
        self.assertEqual(ws.send_json.await_args.args[0]["end_stage"],"stt")

    async def test_error_response_type(self):
        log, state, _=await self.run_simulated(response("Error","error"))
        self.assertIn("COMPLETE result=INTENT_ERROR",log)
        self.assertNotIn("ASSIST_INTENT_SUCCESS",log)
        self.assertEqual(state["last_result"],"INTENT_ERROR")


if __name__=="__main__":
    unittest.main()
