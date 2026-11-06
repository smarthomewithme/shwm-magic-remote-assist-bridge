"""v2.0.1: safety regression for slow Assist vs healthy LG capture."""
import json
import base64
import struct
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiohttp

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] /
                       'shwm_magic_remote_bridge'))
from app import run_pipeline
from runtime_status import BridgeStatus, latency_bottleneck
from pairing import page


def event(kind, data=None):
    return SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data=json.dumps({
        'type':'event', 'id':17,
        'event':{'type':kind,'data':data or {}}}))


class Context:
    def __init__(self, ws): self.ws=ws
    async def __aenter__(self): return self.ws
    async def __aexit__(self, *args): return False


class LatencyTests(unittest.TestCase):
    def test_assist_response_bottleneck_from_real_lg_values(self):
        self.assertEqual(latency_bottleneck({
            'tv_mic_ready_seconds':0.85,
            'capture_cleanup_seconds':0.04,
            'audio_captured_seconds':4.00,
            'assist_after_audio_seconds':8.12,
            'total_seconds':13.04
        }), 'ASSIST_RESPONSE')
        self.assertEqual(latency_bottleneck({
            'tv_mic_ready_seconds':1.0,
            'capture_cleanup_seconds':0.04,
            'assist_after_audio_seconds':0.0
        }), 'NONE')

    def test_slow_tv_and_cleanup_separately(self):
        self.assertEqual(latency_bottleneck({'tv_mic_ready_seconds':3.5}), 'TV_MIC_STARTUP')
        self.assertEqual(latency_bottleneck({'capture_cleanup_seconds':1.5}), 'TV_CAPTURE_CLEANUP')
        self.assertEqual(latency_bottleneck({'assist_after_audio_seconds':float('nan')}), 'NONE')

    def test_busy_mic_event_is_counted_without_queueing(self):
        status=BridgeStatus()
        status.set_ready(True)
        self.assertTrue(status.begin())
        status.note_busy()
        status.note_busy()
        self.assertFalse(status.begin())
        status.complete('OK', {'assist_after_audio_seconds':8.12,'total_seconds':13.04})
        saved=status.snapshot()
        self.assertEqual(saved['ignored_busy_events'],2)
        self.assertEqual(saved['last_bottleneck'],'ASSIST_RESPONSE')
        self.assertEqual(saved['history'][0]['bottleneck'],'ASSIST_RESPONSE')
        self.assertFalse(saved['active'])
        self.assertEqual(saved['sessions'],1)

    def test_panel_displays_latency_and_busy_summary(self):
        blob = (struct.pack('>I',11) + b'ssh-ed25519' +
                struct.pack('>I',32) + bytes(range(32)))
        public_key = ('ssh-ed25519 ' + base64.b64encode(blob).decode() +
                      ' shwm-magic-remote-assist')
        html=page('192.168.1.224', 8080, public_key)
        self.assertIn('ASSIST_RESPONSE',html)
        self.assertIn('ignored_busy_events',html)
        self.assertIn('x.timings.assist_after_audio_seconds',html)


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def simulate(self, response_type, speech, wait=8.12):
        result={'response':{'response_type':response_type,
                            'speech':{'plain':{'speech':speech}}}}
        ws=SimpleNamespace(
            send_json=AsyncMock(),
            receive_json=AsyncMock(return_value={
                'type':'event','id':17,
                'event':{'type':'run-start','data':{'runner_data':{
                    'stt_binary_handler_id':17}}}}),
            receive=AsyncMock(side_effect=[
                event('stt-end',{'stt_output':{'text':'światło jadalnia wyłącz'}}),
                event('intent-end',{'intent_output':result}),
                event('run-end')
            ])
        )
        status=BridgeStatus()
        status.set_ready(True)
        status.begin()
        async def stub_capture(ws, handler_id, opts, metrics):
            metrics.update({'tv_mic_ready_seconds':0.85,
                            'audio_captured_seconds':4.0,
                            'capture_cleanup_seconds':0.04})
        clock=iter([0.0,0.01,4.9,4.9,4.9+wait])
        with patch('app.auth_ws',new=AsyncMock(return_value=Context(ws))), \
             patch('app.pipe_voice_to_ha',new=AsyncMock(side_effect=stub_capture)), \
             patch('app.time',SimpleNamespace(monotonic=lambda:next(clock))), \
             self.assertLogs('shwm_magic_remote',level='INFO') as logs:
            await run_pipeline(None,'test',{'execute_commands':True,
                'pipeline_id':'','log_transcript':False},monitor=status)
        return '\n'.join(logs.output),status.snapshot(),ws

    async def test_slow_valid_action_warns_but_stays_ok(self):
        logs,state,ws=await self.simulate('action_done','Wyłączyłem światło.',8.12)
        self.assertIn('ASSIST_INTENT_SUCCESS response_type=action_done',logs)
        self.assertIn('LATENCY_WARNING stage=ASSIST_AFTER_AUDIO wait_seconds=8.12',logs)
        self.assertEqual(state['last_bottleneck'],'ASSIST_RESPONSE')
        self.assertEqual(state['last_result'],'OK')
        ws.send_json.assert_awaited_once()

    async def test_query_is_not_reported_as_performed_action(self):
        logs,state,ws=await self.simulate('query_answer','Telewizor jest włączony.',0.75)
        self.assertIn('ASSIST_QUERY_ANSWER',logs)
        self.assertNotIn('ASSIST_INTENT_SUCCESS',logs)
        self.assertNotIn('LATENCY_WARNING',logs)
        self.assertEqual(state['last_result'],'OK')
        ws.send_json.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
