"""Regression and integration checks for isolated v2 beta status dashboard."""
import base64
import json
import math
import pathlib
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from aiohttp import web, ClientSession

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'shwm_magic_remote_bridge'))
from runtime_status import BridgeStatus
from pairing import create_panel, page
from app import task_finished


def key():
    raw=struct.pack('>I',11)+b'ssh-ed25519'+struct.pack('>I',32)+bytes(range(32))
    return 'ssh-ed25519 '+base64.b64encode(raw).decode()+' shwm-magic-remote-assist'


class BridgeStatusTests(unittest.TestCase):
    def test_lifecycle_with_bounded_no_secret_metrics(self):
        now=[100.]
        b=BridgeStatus(clock=lambda:now[0])
        self.assertFalse(b.snapshot()['ready'])
        b.set_ready(True)
        self.assertTrue(b.begin())
        self.assertFalse(b.begin())
        b.set_phase('MIC_STARTING')
        b.set_phase('WAITING_ASSIST')
        b.complete('OK',{
            'event_to_mic_seconds':1.12345,
            'audio_captured_seconds':2,
            'total_seconds':4.8,
            'token':'abc-do-not-store',
            'transcript':'turn on the light',
            'capture_cleanup_seconds':float('nan'),
            'assist_after_audio_seconds':float('inf'),
            'tv_mic_ready_seconds':-1,
        })
        s=b.snapshot()
        self.assertFalse(s['active'])
        self.assertEqual(s['phase'],'READY')
        self.assertEqual(s['last_result'],'OK')
        self.assertEqual(s['last_timings']['event_to_mic_seconds'],1.123)
        self.assertNotIn('token',s['last_timings'])
        self.assertNotIn('transcript',json.dumps(s))
        self.assertNotIn('nan',json.dumps(s).lower())
        self.assertNotIn('infinity',json.dumps(s).lower())
        self.assertEqual(len(s['history']),1)
        s['history'][0]['timings']['audio_captured_seconds']=999
        self.assertEqual(b.snapshot()['history'][0]['timings']['audio_captured_seconds'],2)

    def test_history_is_five_only_and_no_spoofed_result(self):
        b=BridgeStatus()
        b.set_ready(True)
        for i in range(7):
            self.assertTrue(b.begin())
            b.complete('BOGUS',{ 'total_seconds':i })
        s=b.snapshot()
        self.assertEqual(s['sessions'],7)
        self.assertEqual(s['last_result'],'INTERNAL_ERROR')
        self.assertEqual([x['session'] for x in s['history']],[3,4,5,6,7])
        with self.assertRaises(ValueError):
            b.set_phase('SECRET_EXFILTRATION')

    def test_error_task_classified_and_not_stuck(self):
        b=BridgeStatus()
        b.set_ready(True)
        b.begin()
        fake=SimpleNamespace(cancelled=lambda:False,exception=lambda:RuntimeError('sensitive token X'))
        with self.assertLogs('shwm_magic_remote',level='ERROR'):
            task_finished(fake, b)
        s=b.snapshot()
        self.assertFalse(s['active'])
        self.assertEqual(s['last_result'],'ASSIST_ERROR')
        self.assertNotIn('sensitive',json.dumps(s))


class PanelStatusTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.pub=pathlib.Path(self.tmp.name)/'key.pub'
        self.pub.write_text(key()+'\n',encoding='ascii')
        self.monitor=BridgeStatus()
        self.monitor.set_ready(True)
        self.monitor.begin()
        self.monitor.complete('NO_SPEECH', {'audio_captured_seconds':1.6})
        self.app=create_panel(
            {'tv_host':'192.168.1.224','glasshouse_port':8080},
            str(self.pub),lambda opts:[],monitor=self.monitor)
        self.patch=patch('pairing.INGRESS_IP','127.0.0.1')
        self.patch.start()
        self.runner=web.AppRunner(self.app)
        await self.runner.setup()
        self.site=web.TCPSite(self.runner,'127.0.0.1',0)
        await self.site.start()
        self.url='http://127.0.0.1:'+str(self.site._server.sockets[0].getsockname()[1])

    async def asyncTearDown(self):
        await self.runner.cleanup()
        self.patch.stop()
        self.tmp.cleanup()

    async def test_read_only_status_ignores_key_credentials(self):
        async with ClientSession() as client:
            async with client.get(self.url+'/status') as response:
                self.assertEqual(response.status,200)
                self.assertEqual(response.headers['Cache-Control'],'no-store')
                response_body=await response.json()
            async with client.get(self.url+'/') as response:
                html=await response.text()
        self.assertEqual(response_body['state']['last_result'],'NO_SPEECH')
        self.assertEqual(response_body['state']['last_timings']['audio_captured_seconds'],1.6)
        self.assertNotIn('ssh-ed25519',json.dumps(response_body))
        self.assertNotIn('192.168.',json.dumps(response_body))
        self.assertIn('id="status-refresh"',html)
        self.assertIn("fetch('status'",html)
        self.assertIn("lines.join('\\n')",html)

    async def test_status_forbidden_without_ingress_origin(self):
        with patch('pairing.INGRESS_IP','10.0.0.1'):
            async with ClientSession() as client:
                async with client.get(self.url+'/status') as response:
                    self.assertEqual(response.status,403)
                    self.assertNotIn('last_timings',await response.text())


if __name__=='__main__':
    unittest.main()
