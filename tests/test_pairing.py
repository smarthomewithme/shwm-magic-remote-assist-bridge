import base64
import hashlib
import pathlib
import struct
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'shwm_magic_remote_bridge'))
from aiohttp import web, ClientSession
from pairing import fingerprint, validate_token, pair_key, PairError

class PairingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.raw=struct.pack('>I',11)+b'ssh-ed25519'+b'dummy'
        self.pub='ssh-ed25519 '+base64.b64encode(self.raw).decode()+' test'
        self.fp=fingerprint(self.pub)
        self.keys=[]
        self.calls=[]
        async def handler(request):
            if request.headers.get('Authorization')!='Bearer my-token':
                return web.json_response({'ok':False},status=401)
            if request.method=='GET':
                self.calls.append('get')
                return web.json_response({'ok':True,'writable':True,'needsToken':False,'keys':self.keys})
            self.calls.append('post')
            data=await request.json()
            if data.get('action')!='add' or data.get('key')!=self.pub:
                return web.json_response({'ok':False},status=400)
            self.keys.append({'fingerprint':self.fp})
            return web.json_response({'ok':True,'keys':self.keys})
        app=web.Application()
        app.router.add_route('*','/api/ssh',handler)
        self.runner=web.AppRunner(app)
        await self.runner.setup()
        site=web.TCPSite(self.runner,'127.0.0.1',0)
        await site.start()
        port=site._server.sockets[0].getsockname()[1]
        self.url='http://127.0.0.1:'+str(port)

    async def asyncTearDown(self):
        await self.runner.cleanup()

    async def test_add_only_once(self):
        async with ClientSession() as session:
            a=await pair_key(session,self.url,self.pub,'my-token')
            b=await pair_key(session,self.url,self.pub,'my-token')
        self.assertEqual(a,('PAIRED',self.fp))
        self.assertEqual(b,('ALREADY_PAIRED',self.fp))
        self.assertEqual(self.calls,['get','post','get'])

    async def test_wrong_token_no_mutation(self):
        async with ClientSession() as session:
            with self.assertRaises(PairError):
                await pair_key(session,self.url,self.pub,'incorrect')
        self.assertEqual(self.calls,[])
        self.assertEqual(self.keys,[])

    async def test_empty_token(self):
        with self.assertRaises(PairError):
            validate_token('')

    async def test_fingerprint(self):
        expected='SHA256:'+base64.b64encode(hashlib.sha256(self.raw).digest()).decode().rstrip('=')
        self.assertEqual(self.fp,expected)
