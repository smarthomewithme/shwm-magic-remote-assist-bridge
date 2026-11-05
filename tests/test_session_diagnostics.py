"""Regression tests for latency breakdown and silent microphone events."""
import asyncio
import json
import pathlib
import struct
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiohttp

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] /
                       'shwm_magic_remote_bridge'))
from app import pipe_voice_to_ha, run_pipeline


def options():
    return {
        'tv_host': '192.168.1.224',
        'record_seconds': 8,
        'vad_enabled': True,
        'vad_rms_threshold': 250,
        'vad_silence_ms': 1500,
        'execute_commands': False,
        'log_transcript': False,
        'pipeline_id': ''
    }


class CaptureTimingTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_has_separate_mic_and_cleanup_timings(self):
        voiced = struct.pack('<h', 1000) * 3200
        quiet = b'\x00' * (3200 * 18)
        fake_proc = SimpleNamespace(
            stdout=SimpleNamespace(read=AsyncMock(side_effect=[voiced, quiet])),
            stderr=SimpleNamespace(read=AsyncMock(return_value=b'')),
        )
        fake_ws = SimpleNamespace(closed=False, send_bytes=AsyncMock())
        timing = {}
        with patch('app.open_tv_capture', new=AsyncMock(return_value=fake_proc)), \
             patch('app.stop_capture_process', new=AsyncMock()) as stop, \
             self.assertLogs('shwm_magic_remote', level='INFO') as logs:
            await pipe_voice_to_ha(fake_ws, 17, options(), timing)
        self.assertTrue(timing['vad_stopped'])
        self.assertGreaterEqual(timing['tv_mic_ready_seconds'], 0)
        self.assertGreaterEqual(timing['capture_cleanup_seconds'], 0)
        self.assertGreater(timing['audio_captured_seconds'], 0)
        self.assertIn('CAPTURE_TIMING', '\n'.join(logs.output))
        self.assertEqual(fake_ws.send_bytes.await_args.args[0], b'\x11')
        stop.assert_awaited_once_with(fake_proc, graceful=True)

    async def test_capture_without_vad_preserves_original_cleanup(self):
        fake_proc = SimpleNamespace(
            stdout=SimpleNamespace(read=AsyncMock(side_effect=[b'\0'*6400,b''])),
            stderr=SimpleNamespace(read=AsyncMock(return_value=b'')),
        )
        fake_ws=SimpleNamespace(closed=False,send_bytes=AsyncMock())
        timing={}
        cfg=options()
        cfg['vad_enabled']=False
        with patch('app.open_tv_capture', new=AsyncMock(return_value=fake_proc)), \
             patch('app.stop_capture_process', new=AsyncMock()) as stop:
            await pipe_voice_to_ha(fake_ws, 17, cfg, timing)
        self.assertFalse(timing['vad_stopped'])
        self.assertEqual(timing['audio_captured_seconds'], 0.2)
        stop.assert_awaited_once_with(fake_proc, graceful=False)


class Context:
    def __init__(self, ws):
        self.ws = ws
    async def __aenter__(self):
        return self.ws
    async def __aexit__(self, exc_type, exc, tb):
        return False


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    def pipeline_ws(self, event_type, data=None):
        event = {'type':'event','id':17,
                 'event':{'type':event_type, 'data':data or {}}}
        ws = SimpleNamespace(
            send_json=AsyncMock(),
            receive_json=AsyncMock(return_value={
                'type':'event', 'id':17,
                'event':{'type':'run-start','data':{
                    'runner_data':{'stt_binary_handler_id':17}}}
            }),
            receive=AsyncMock(return_value=SimpleNamespace(
                type=aiohttp.WSMsgType.TEXT,
                data=json.dumps(event)))
        )
        return ws

    async def fake_capture(self, ws, handler, opts, timing):
        self.assertEqual(handler, 17)
        timing.update({
            'tv_mic_ready_seconds':0.12,
            'capture_cleanup_seconds':0.08,
            'audio_captured_seconds':2.5
        })

    async def test_silent_stt_is_no_speech_not_success_or_failure(self):
        ws = self.pipeline_ws('error', {
            'code':'stt-no-text-recognized',
            'message':'No text recognized'})
        with patch('app.auth_ws',new=AsyncMock(return_value=Context(ws))), \
             patch('app.pipe_voice_to_ha',new=AsyncMock(side_effect=self.fake_capture)) as voice, \
             self.assertLogs('shwm_magic_remote',level='INFO') as logs:
            await run_pipeline(None,'irrelevant',options())
        output='\n'.join(logs.output)
        self.assertIn('STATUS NO_SPEECH', output)
        self.assertIn('STATUS SESSION_TIMING', output)
        self.assertIn('STATUS COMPLETE result=NO_SPEECH', output)
        self.assertNotIn('STATUS STT_SUCCESS', output)
        voice.assert_awaited_once()
        ws.send_json.assert_awaited_once()

    async def test_other_assist_errors_keep_failing(self):
        ws=self.pipeline_ws('error', {'code':'pipeline-error','message':'test'})
        with patch('app.auth_ws',new=AsyncMock(return_value=Context(ws))), \
             patch('app.pipe_voice_to_ha',new=AsyncMock(side_effect=self.fake_capture)):
            with self.assertRaisesRegex(RuntimeError,'Assist error'):
                await run_pipeline(None,'irrelevant',options())

    async def test_valid_stt_run_logs_timing_and_success(self):
        ws=self.pipeline_ws('stt-end', {'stt_output':{'text':'Lights'}})
        # A successful pipeline ends with run-end; the test returns the
        # second event after STT so the loop completes.
        ws.receive=AsyncMock(side_effect=[
            SimpleNamespace(type=aiohttp.WSMsgType.TEXT,data=json.dumps({
                'type':'event','id':17,'event':{
                    'type':'stt-end',
                    'data':{'stt_output':{'text':'Lights'}}}})),
            SimpleNamespace(type=aiohttp.WSMsgType.TEXT,data=json.dumps({
                'type':'event','id':17,'event':{
                    'type':'run-end','data':{}}}))
        ])
        with patch('app.auth_ws',new=AsyncMock(return_value=Context(ws))), \
             patch('app.pipe_voice_to_ha',new=AsyncMock(side_effect=self.fake_capture)), \
             self.assertLogs('shwm_magic_remote',level='INFO') as logs:
            await run_pipeline(None,'irrelevant',options())
        output='\n'.join(logs.output)
        self.assertIn('STATUS STT_SUCCESS',output)
        self.assertIn('STATUS COMPLETE result=OK',output)
        self.assertIn('tv_mic_ready_seconds=',output)
