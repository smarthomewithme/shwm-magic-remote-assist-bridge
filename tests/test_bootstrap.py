"""Bootstrap is opt-in, only already-running root telnet is used."""
import asyncio
import base64
import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'shwm_magic_remote_bridge'))
from bootstrap import (
    validate_key, bootstrap_command, REMOTE_PYTHON, BootstrapError,
    TelnetFilter, add_via_existing_telnet, auto_pair,
)


def shwm_public_key():
    blob = struct.pack('>I', 11) + b'ssh-ed25519' + struct.pack('>I', 32) + bytes(range(32))
    return 'ssh-ed25519 ' + base64.b64encode(blob).decode() + ' shwm-magic-remote-assist'


class BootstrapUnitTests(unittest.TestCase):
    def test_key_is_strictly_validated(self):
        good = shwm_public_key()
        self.assertEqual(validate_key(good), good)
        for bad in ('', 'ssh-rsa AAA bad', good + '\nrm -rf /',
                    good.replace(' shwm-magic-remote-assist', ' evil'),
                    good.replace('ssh-ed25519', 'ssh-x-ed25519')):
            with self.subTest(bad=bad):
                with self.assertRaises(BootstrapError):
                    validate_key(bad)

    def test_encoded_command_has_no_raw_ssh_key(self):
        text = bootstrap_command(shwm_public_key())
        self.assertIn('python -c ', text)
        self.assertTrue(text.endswith('\n'))
        self.assertNotIn('ssh-ed25519', text)

    def test_shell_python_appends_only_own_key_and_verifies(self):
        key = shwm_public_key()
        with tempfile.TemporaryDirectory() as folder:
            target = pathlib.Path(folder) / 'root' / '.ssh' / 'authorized_keys'
            target.parent.mkdir(parents=True)
            other = b'ssh-ed25519 OLD_KEY existing-device\n'
            target.write_bytes(other)
            # CI runs without root. Only this disposable local simulation
            # bypasses the UID gate; production REMOTE_PYTHON keeps it.
            self.assertIn("if os.geteuid() != 0:", REMOTE_PYTHON)
            program = (REMOTE_PYTHON.replace(
                "p = '/home/root/.ssh/authorized_keys'", 'p = ' + repr(str(target)))
                .replace("if os.geteuid() != 0:", "if False:"))
            param = base64.b64encode(key.encode()).decode()
            one = subprocess.run([sys.executable, '-c', program, param],
                                 capture_output=True, check=True)
            two = subprocess.run([sys.executable, '-c', program, param],
                                 capture_output=True, check=True)
            self.assertEqual(one.stdout.strip(), b'SHWM_PAIR_ADDED_DONE')
            self.assertEqual(two.stdout.strip(), b'SHWM_PAIR_ALREADY_DONE')
            self.assertEqual(target.read_bytes(), other + key.encode() + b'\n')

    def test_filter_telnet_negotiation(self):
        wire = TelnetFilter()
        clean, response = wire.consume(b'Hello' + bytes([255, 251, 1, 255, 253, 3]))
        self.assertEqual(clean, b'Hello')
        self.assertEqual(response, bytes([255, 254, 1, 255, 252, 3]))
        self.assertEqual(wire.consume(b'!')[0], b'!')


class BootstrapNetworkTests(unittest.IsolatedAsyncioTestCase):
    async def test_telnet_simulation(self):
        commands = []

        async def fake_telnet(reader, writer):
            writer.write(bytes([255, 251, 1]) + b'root@webos:~# ')
            await writer.drain()
            data = await asyncio.wait_for(reader.readuntil(b'\n'), 5)
            commands.append(data)
            payload = await asyncio.wait_for(reader.readuntil(b'\n'), 5)
            commands.append(payload)
            writer.write(b'\r\nSHWM_PAIR_ADDED_DONE\r\n')
            await writer.drain()
            await asyncio.sleep(0.2)
            writer.close()
        server = await asyncio.start_server(fake_telnet, '127.0.0.1', 0)
        port = server.sockets[0].getsockname()[1]
        # Function explicitly requires a private non-loopback LAN IP.
        # Patch the IP policy only for this in-process fake server test.
        with patch('bootstrap.ipaddress.ip_address') as mock_ip:
            class FakeIP:
                version = 4
                is_private = True
                is_loopback = False
                is_link_local = False
                def __str__(self):
                    return '127.0.0.1'
            mock_ip.return_value = FakeIP()
            async with server:
                result = await add_via_existing_telnet('192.168.1.224', shwm_public_key(), port=port)
        self.assertEqual(result, 'KEY_ADDED')
        self.assertGreaterEqual(len(commands), 2)
        self.assertIn(b'python -c ', commands[1])

    async def test_existing_ssh_skips_telnet(self):
        opts = {'tv_host': '192.168.1.224'}
        with patch('bootstrap.check_current_ssh', new=AsyncMock(return_value=True)), \
             patch('bootstrap.add_via_existing_telnet', new=AsyncMock()) as telnet:
            self.assertEqual(await auto_pair(opts, shwm_public_key(), lambda _o: []),
                             'ALREADY_AUTHORIZED')
            telnet.assert_not_awaited()

    async def test_new_key_is_verified_by_ssh(self):
        opts = {'tv_host': '192.168.1.224'}
        with patch('bootstrap.check_current_ssh', new=AsyncMock(side_effect=[False, True])) as ssh, \
             patch('bootstrap.add_via_existing_telnet', new=AsyncMock(return_value='KEY_ADDED')) as telnet:
            self.assertEqual(await auto_pair(opts, shwm_public_key(), lambda _o: []), 'PAIRED')
            self.assertEqual(ssh.await_count, 2)
            telnet.assert_awaited_once()

    async def test_no_telnet_never_claims_success(self):
        opts = {'tv_host': '192.168.1.224'}
        with patch('bootstrap.check_current_ssh', new=AsyncMock(return_value=False)), \
             patch('bootstrap.add_via_existing_telnet',
                   new=AsyncMock(side_effect=BootstrapError('TELNET_NOT_AVAILABLE'))):
            with self.assertRaises(BootstrapError) as exc:
                await auto_pair(opts, shwm_public_key(), lambda _o: [])
            self.assertEqual(exc.exception.code, 'TELNET_NOT_AVAILABLE')
