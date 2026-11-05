"""Explicit, opt-in local setup of SSH for a rooted LG webOS television.

Never enables telnet or uses passwords. If root telnet is ALREADY active on
the private LAN, append only this add-on's public SSH key, then verify SSH.
Never changes Glasshouse, other authorized_keys entries, or system partitions.
"""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import os
import re
import struct

SHWM_COMMENT = "shwm-magic-remote-assist"


class BootstrapError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def validate_key(public_key):
    if not isinstance(public_key, str) or not 75 <= len(public_key) <= 200:
        raise BootstrapError("PUBLIC_KEY_INVALID")
    if "\n" in public_key or "\r" in public_key or "\x00" in public_key:
        raise BootstrapError("PUBLIC_KEY_INVALID")
    words = public_key.strip().split()
    if len(words) != 3 or words[0] != "ssh-ed25519" or words[2] != SHWM_COMMENT:
        raise BootstrapError("PUBLIC_KEY_INVALID")
    try:
        raw = base64.b64decode(words[1], validate=True)
    except (ValueError, base64.binascii.Error):
        raise BootstrapError("PUBLIC_KEY_INVALID") from None
    if (len(raw) != 51 or struct.unpack(">I", raw[:4])[0] != 11
            or raw[4:15] != b"ssh-ed25519"
            or struct.unpack(">I", raw[15:19])[0] != 32):
        raise BootstrapError("PUBLIC_KEY_INVALID")
    return " ".join(words)


# The script is only run through an ALREADY EXISTING unauthenticated root
# telnet shell on the user's rooted LG. The base64-encoded key argument is
# validated above. This does not open a new login service or use passwords.
REMOTE_PYTHON = r'''
import base64
import os
import sys

p = '/home/root/.ssh/authorized_keys'
folder = os.path.dirname(p)
try:
    if os.geteuid() != 0:
        sys.exit(9)
    key = base64.b64decode(sys.argv[1])
    parts = key.split()
    if len(parts) != 3 or parts[0] != b'ssh-ed25519' or parts[2] != b'shwm-magic-remote-assist':
        sys.exit(10)
    if os.path.islink(folder) or os.path.islink(p):
        sys.exit(11)
    os.umask(0o077)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    os.chmod(folder, 0o700)
    if os.path.isfile(p):
        with open(p, 'rb') as handle:
            existing = handle.read(65537)
        if len(existing) > 65536:
            sys.exit(12)
    else:
        existing = b''
    found = any(
        len(line.split()) >= 2
        and line.split()[0] == b'ssh-ed25519'
        and line.split()[1] == parts[1]
        for line in existing.splitlines()
    )
    if not found:
        with open(p, 'ab') as handle:
            if existing and not existing.endswith(b'\n'):
                handle.write(b'\n')
            handle.write(key + b'\n')
    os.chmod(p, 0o600)
    with open(p, 'rb') as handle:
        result = handle.read(65537)
    verified = any(
        len(line.split()) >= 2
        and line.split()[0] == b'ssh-ed25519'
        and line.split()[1] == parts[1]
        for line in result.splitlines()
    )
    if not verified:
        sys.exit(13)
    sys.stdout.write('SHWM_PAIR_ALREADY_DONE\n' if found else 'SHWM_PAIR_ADDED_DONE\n')
except Exception:
    sys.exit(14)
'''


def bootstrap_command(public_key):
    public_key = validate_key(public_key)
    program = base64.b64encode(REMOTE_PYTHON.encode("ascii")).decode("ascii")
    key = base64.b64encode(public_key.encode("ascii")).decode("ascii")
    return ("python -c 'import base64;exec(base64.b64decode(\""
            + program + "\"))' " + key + "\n")


class TelnetFilter:
    """Strip standard RFC854 IAC negotiation and politely refuse extensions."""
    def __init__(self):
        self.state = "data"
        self.opt_command = 0

    def consume(self, block):
        clean = bytearray()
        responses = bytearray()
        for byte in block:
            if self.state == "data":
                if byte == 255:
                    self.state = "iac"
                else:
                    clean.append(byte)
            elif self.state == "iac":
                if byte == 255:
                    clean.append(255)
                    self.state = "data"
                elif byte in (251, 252, 253, 254):
                    self.opt_command = byte
                    self.state = "option"
                elif byte == 250:
                    self.state = "subneg"
                else:
                    self.state = "data"
            elif self.state == "option":
                if self.opt_command == 251:  # WILL -> DONT
                    responses.extend((255, 254, byte))
                elif self.opt_command == 253:  # DO -> WONT
                    responses.extend((255, 252, byte))
                self.state = "data"
            elif self.state == "subneg":
                if byte == 255:
                    self.state = "subneg_iac"
            elif self.state == "subneg_iac":
                self.state = "data" if byte == 240 else "subneg"
        return bytes(clean), bytes(responses)


async def _recv(reader, writer, wire, timeout=0.6):
    try:
        raw = await asyncio.wait_for(reader.read(4096), timeout=timeout)
    except asyncio.TimeoutError:
        return b""
    if not raw:
        raise BootstrapError("TELNET_CLOSED")
    clean, response = wire.consume(raw)
    if response:
        writer.write(response)
        await writer.drain()
    return clean


def shell_install_command(public_key, nonce, directory="/home/root/.ssh"):
    """Short POSIX shell command: no Python dependency on TV telnet PATH.

    A response is built from separate printf arguments so a terminal echo of
    the command cannot be mistaken for a successful result.
    """
    public_key = validate_key(public_key)
    if not re.fullmatch(r"[0-9a-f]{12}", nonce):
        raise BootstrapError("INVALID_PROBE_ID")
    # This is never shell-controlled user input: add-on generated Ed25519 and
    # a 12-character random nonce. No quotes or substitutions are allowed.
    if not re.fullmatch(r"/[a-zA-Z0-9/_.-]+", directory):
        raise BootstrapError("INVALID_PATH")
    return (
        "K='" + public_key + "'\n"
        "D='" + directory + "'\n"
        'F="$D/authorized_keys"\n'
        'if [ -L "$D" ] || [ -L "$F" ]; then\n'
        "  printf 'SHWM_RESULT_%s:%s\\n' '" + nonce + "' 'PATH_UNSAFE'\n"
        'elif mkdir -p "$D" && chmod 700 "$D" && touch "$F" && chmod 600 "$F"; then\n'
        '  if grep -Fqx "$K" "$F"; then\n'
        "    printf 'SHWM_RESULT_%s:%s\\n' '" + nonce + "' 'ALREADY'\n"
        '  else\n'
        '    if [ -s "$F" ] && [ "$(tail -c 1 "$F" | wc -l)" -eq 0 ]; then\n'
        "      printf '\\n' >> \"$F\"\n"
        '    fi\n'
        "    if printf '%s\\n' \"$K\" >> \"$F\" && grep -Fqx \"$K\" \"$F\"; then\n"
        "      printf 'SHWM_RESULT_%s:%s\\n' '" + nonce + "' 'ADDED'\n"
        '    else\n'
        "      printf 'SHWM_RESULT_%s:%s\\n' '" + nonce + "' 'FAILED'\n"
        '    fi\n'
        '  fi\n'
        'else\n'
        "  printf 'SHWM_RESULT_%s:%s\\n' '" + nonce + "' 'FAILED'\n"
        'fi\n'
    )


async def read_telnet_probe(reader, writer, wire, nonce, timeout=7):
    """Read-only UID check before sending ANY command that changes a file."""
    # Echoed input contains format string, not the resolved marker.
    writer.write(("printf 'SHWM_PROBE_%s_UID_%s\\n' '" + nonce + "' \"$(id -u)\"\n").encode("ascii"))
    await writer.drain()
    body = bytearray()
    pattern = re.compile(rb"(?:^|[\r\n])SHWM_PROBE_" + nonce.encode() +
                         rb"_UID_([0-9]{1,6})(?:[\r\n]|$)")
    async with asyncio.timeout(timeout):
        while len(body) < 8192:
            chunk = await _recv(reader, writer, wire, timeout=0.7)
            if chunk:
                body.extend(chunk)
                if re.search(rb"(?:login|password)\s*:\s*$", bytes(body[-250:]).strip(), re.I):
                    raise BootstrapError("TELNET_LOGIN_REQUIRED")
                match = pattern.search(bytes(body))
                if match:
                    if match.group(1) != b"0":
                        raise BootstrapError("TELNET_NOT_ROOT")
                    return
    raise BootstrapError("TELNET_SHELL_NO_REPLY")


async def add_via_existing_telnet(host, public_key, port=23):
    """Use already-running root telnet after an explicit click; append once."""
    host_ip = ipaddress.ip_address(host)
    if (host_ip.version != 4 or not host_ip.is_private
            or host_ip.is_loopback or host_ip.is_link_local):
        raise BootstrapError("TV_PRIVATE_IPV4_REQUIRED")
    key = validate_key(public_key)
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(str(host_ip), port), timeout=3
        )
    except (OSError, asyncio.TimeoutError):
        raise BootstrapError("TELNET_NOT_AVAILABLE") from None
    import secrets
    nonce = secrets.token_hex(6)
    wire = TelnetFilter()
    try:
        writer.write(b"\n")
        await writer.drain()
        banner = bytearray()
        for _ in range(3):
            try:
                banner.extend(await _recv(reader, writer, wire, timeout=0.3))
            except BootstrapError:
                raise BootstrapError("TELNET_NOT_AVAILABLE") from None
        if re.search(rb"(?:login|password)\s*:\s*$", bytes(banner).strip(), re.I):
            raise BootstrapError("TELNET_LOGIN_REQUIRED")
        try:
            await read_telnet_probe(reader, writer, wire, nonce)
        except asyncio.TimeoutError:
            raise BootstrapError("TELNET_SHELL_NO_REPLY") from None
        writer.write(shell_install_command(key, nonce).encode("ascii"))
        await writer.drain()
        output = bytearray()
        pattern = re.compile(rb"(?:^|[\r\n])SHWM_RESULT_" + nonce.encode() +
                             rb":(ADDED|ALREADY|FAILED|PATH_UNSAFE)(?:[\r\n]|$)")
        try:
            async with asyncio.timeout(12):
                while len(output) < 12288:
                    chunk = await _recv(reader, writer, wire, timeout=0.7)
                    if chunk:
                        output.extend(chunk)
                        found = pattern.search(bytes(output))
                        if found:
                            result = found.group(1)
                            if result == b"ADDED":
                                return "KEY_ADDED"
                            if result == b"ALREADY":
                                return "KEY_ALREADY_PRESENT"
                            if result == b"PATH_UNSAFE":
                                raise BootstrapError("TELNET_PATH_UNSAFE")
                            raise BootstrapError("TELNET_INSTALL_FAILED")
                        if re.search(rb"(?:login|password)\s*:\s*$",
                                     bytes(output[-250:]).strip(), re.I):
                            raise BootstrapError("TELNET_LOGIN_REQUIRED")
        except asyncio.TimeoutError:
            pass
        raise BootstrapError("TELNET_COMMAND_UNCONFIRMED")
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=2)
        except (OSError, asyncio.TimeoutError):
            pass


async def check_current_ssh(opts, ssh_args):
    """Try the add-on's own SSH identity; never use passwords."""
    proc = await asyncio.create_subprocess_exec(
        *ssh_args(opts), "printf SHWM_SSH_READY",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=13)
    except asyncio.TimeoutError:
        if proc.returncode is None:
            proc.kill()
        await proc.communicate()
        return False  # SSH might be offline; the explicit telnet option may still work.
    except BaseException:
        if proc.returncode is None:
            proc.kill()
        await proc.communicate()
        raise
    if proc.returncode == 0 and out.strip() == b"SHWM_SSH_READY":
        return True
    stderr = err.lower()
    if (b"host key verification failed" in stderr
            or b"remote host identification has changed" in stderr):
        raise BootstrapError("SSH_HOST_KEY_CONFLICT")
    return False


async def auto_pair(opts, public_key, ssh_args):
    """Single explicit user action. Existing SSH first, root telnet only if on."""
    validate_key(public_key)
    if await check_current_ssh(opts, ssh_args):
        return "ALREADY_AUTHORIZED"
    try:
        await add_via_existing_telnet(opts["tv_host"], public_key)
    except BootstrapError as exc:
        # If telnet did not confirm, perform a READ-ONLY SSH check. The first
        # attempt might actually have succeeded; never blindly append again.
        if exc.code in ("TELNET_COMMAND_UNCONFIRMED", "TELNET_CLOSED"):
            if await check_current_ssh(opts, ssh_args):
                return "PAIRED"
        raise
    if not await check_current_ssh(opts, ssh_args):
        raise BootstrapError("KEY_ADDED_BUT_SSH_NOT_READY")
    return "PAIRED"
