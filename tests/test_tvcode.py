import base64
import pathlib
import struct
import sys
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'shwm_magic_remote_bridge'))
from aiohttp import web, ClientSession
from pairing import fingerprint, page
from tvcode import request_tv_code, confirm_tv_code, TvCodeError

class TestTvCodeClient(unittest.IsolatedAsyncioTestCase):
    def test_page_exposes_pairing_and_correct_pin_pattern(self):
        raw=struct.pack('>I', 11)+b'ssh-ed25519'+struct.pack('>I',32)+bytes(range(32))
        key='ssh-ed25519 '+base64.b64encode(raw).decode()+' shwm-magic-remote-assist'
        html=page('192.168.1.224',8080,key)
        self.assertIn('pattern="[0-9]{8}"',html)
        self.assertIn('tv-code-start',html)
        self.assertIn('tv-code-finish',html)
        self.assertIn('token',html.lower())

    async def asyncSetUp(self):
        raw=struct.pack('>I', 11)+b'ssh-ed25519'+struct.pack('>I',32)+bytes(range(32))
        self.pub='ssh-ed25519 '+base64.b64encode(raw).decode()+' shwm-magic-remote-assist'
        self.fp=fingerprint(self.pub)
        self.calls=[]
        async def handle(request):
            body=await request.json()
            self.calls.append((request.path,body))
            if request.path.endswith('request'):
                return web.json_response({'ok':True,'ticket':'a'*48,'expires_in':120})
            if body.get('code')=='12345678' and body.get('ticket')=='a'*48:
                return web.json_response({'ok':True,'status':'PAIRED','fingerprint':self.fp})
            return web.json_response({'ok':False,'error':'CODE_INVALID'},status=400)
        app=web.Application()
        app.router.add_post('/api/shwm-pair/request',handle)
        app.router.add_post('/api/shwm-pair/complete',handle)
        self.runner=web.AppRunner(app)
        await self.runner.setup()
        site=web.TCPSite(self.runner,'127.0.0.1',0)
        await site.start()
        self.url='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])

    async def asyncTearDown(self):
        await self.runner.cleanup()

    async def test_mocked_handshake(self):
        async with ClientSession() as s:
            ticket=await request_tv_code(s,self.url,self.pub)
            status=await confirm_tv_code(s,self.url,ticket,'12345678',self.fp)
        self.assertEqual(status,'PAIRED')
        self.assertEqual(self.calls[0][1],{'public_key':self.pub})
        self.assertEqual(self.calls[1][1],{'ticket':'a'*48,'code':'12345678'})

    async def test_wrong_code(self):
        async with ClientSession() as s:
            with self.assertRaises(TvCodeError) as e:
                await confirm_tv_code(s,self.url,'a'*48,'00000000',self.fp)
        self.assertEqual(str(e.exception),'PIN_INVALID_OR_EXPIRED')

    async def test_disallowed_code_format(self):
        async with ClientSession() as s:
            with self.assertRaises(TvCodeError):
                await confirm_tv_code(s,self.url,'a'*48,'1'*7,self.fp)
        self.assertEqual(self.calls,[])

    async def test_fingerprint_mismatch(self):
        async with ClientSession() as s:
            with self.assertRaises(TvCodeError) as e:
                await confirm_tv_code(s,self.url,'a'*48,'12345678','SHA256:someone-else')
        self.assertEqual(str(e.exception),'KEY_FINGERPRINT_MISMATCH')

if __name__ == '__main__':
    unittest.main()
