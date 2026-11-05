"""Bootstrap is opt-in, only already-running root telnet is used."""
import asyncio
import base64
import pathlib
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'shwm_magic_remote_bridge'))
from bootstrap import (
    validate_key, bootstrap_command, REMOTE_PYTHON, BootstrapError,
    TelnetFilter, add_via_existing_telnet, auto_pair, shell_install_command,
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

    def test_short_shell_installer_append_only_and_idempotent(self):
        key = shwm_public_key()
        tag = '010203040506'
        with tempfile.TemporaryDirectory() as folder:
            directory = pathlib.Path(folder) / 'root' / '.ssh'
            directory.mkdir(parents=True)
            target = directory / 'authorized_keys'
            existing = b'ssh-ed25519 OLDER_KEY old-device\n'
            target.write_bytes(existing)
            script = shell_install_command(key, tag, str(directory))
            self.assertNotIn('python -c', script)
            self.assertLess(len(script), 1400)
            for status in ('ADDED', 'ALREADY'):
                proc = subprocess.run(['sh'], input=script.encode(), capture_output=True, check=True)
                self.assertIn(('SHWM_RESULT_' + tag + ':' + status).encode(), proc.stdout)
            self.assertEqual(target.read_bytes(), existing + key.encode() + b'\n')

    def test_short_shell_refuses_symlink(self):
        key = shwm_public_key()
        with tempfile.TemporaryDirectory() as folder:
            directory = pathlib.Path(folder) / 'ssh'
            real = pathlib.Path(folder) / 'real'
            real.mkdir()
            directory.symlink_to(real, target_is_directory=True)
            code = shell_install_command(key, '010203040506', str(directory))
            p = subprocess.run(['sh'], input=code.encode(), capture_output=True, check=True)
            self.assertIn(b'PATH_UNSAFE', p.stdout)
            self.assertFalse((real / 'authorized_keys').exists())

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
            commands.append(await asyncio.wait_for(reader.readuntil(b'\n'), 5))
            probe = await asyncio.wait_for(reader.readuntil(b'\n'), 5)
            commands.append(probe)
            match = re.search(rb"'([0-9a-f]{12})' \"\$\(", probe)
            assert match, probe
            tag = match.group(1)
            writer.write(b'\r\nSHWM_PROBE_' + tag + b'_UID_0\r\n')
            await writer.drain()
            payload = await asyncio.wait_for(reader.readuntil(b'\nfi\n'), 5)
            commands.append(payload)
            writer.write(b'\r\nSHWM_RESULT_' + tag + b':ADDED\r\n')
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
        self.assertIn(b'K=\'ssh-ed25519 ', commands[2])

    async def test_telnet_non_root_refuses_before_mutation(self):
        seen = []
        async def fake(reader, writer):
            writer.write(b'root@webos:~# ')
            await writer.drain()
            seen.append(await reader.readuntil(b'\n'))
            probe = await reader.readuntil(b'\n')
            seen.append(probe)
            tag = re.search(rb"'([0-9a-f]{12})' \"\$\(", probe).group(1)
            writer.write(b'\nSHWM_PROBE_' + tag + b'_UID_1000\n')
            await writer.drain()
            writer.close()
        server = await asyncio.start_server(fake, '127.0.0.1', 0)
        port = server.sockets[0].getsockname()[1]
        with patch('bootstrap.ipaddress.ip_address') as mock_ip:
            class Local:
                version=4
                is_private=True
                is_loopback=False
                is_link_local=False
                def __str__(self): return '127.0.0.1'
            mock_ip.return_value=Local()
            async with server:
                with self.assertRaises(BootstrapError) as exc:
                    await add_via_existing_telnet('192.168.1.224',shwm_public_key(),port=port)
        self.assertEqual(exc.exception.code,'TELNET_NOT_ROOT')
        self.assertEqual(len(seen),2)

    async def test_missing_confirmation_must_check_ssh_read_only(self):
        opts = {'tv_host': '192.168.1.224'}
        with patch('bootstrap.check_current_ssh', new=AsyncMock(side_effect=[False, True])) as ssh, \
             patch('bootstrap.add_via_existing_telnet',
                   new=AsyncMock(side_effect=BootstrapError('TELNET_COMMAND_UNCONFIRMED'))) as install:
            self.assertEqual(await auto_pair(opts,shwm_public_key(),lambda o: []),'PAIRED')
            self.assertEqual(ssh.await_count,2)
            install.assert_awaited_once()

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
