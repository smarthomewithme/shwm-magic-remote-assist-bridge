"""Optional client for the proposed Glasshouse on-screen TV-code pairing.

No Glasshouse admin token, TV password, or private SSH key is ever read.
Disabled in practice until an upstream Glasshouse version implements the endpoints.
"""
import re
import aiohttp

class TvCodeError(Exception):
    pass

async def request_tv_code(session, glasshouse_url, public_key):
    if not isinstance(public_key, str) or not public_key.startswith('ssh-ed25519 '):
        raise TvCodeError('PUBLIC_KEY_INVALID')
    try:
        async with session.post(
            glasshouse_url.rstrip('/') + '/api/shwm-pair/request',
            json={'public_key': public_key},
            allow_redirects=False,
        ) as response:
            if response.status in (401, 403, 404, 405):
                raise TvCodeError('GLASSHOUSE_PAIRING_NOT_SUPPORTED')
            if response.status != 200:
                raise TvCodeError('GLASSHOUSE_PAIRING_NOT_READY')
            try:
                data = await response.json()
            except (ValueError, aiohttp.ContentTypeError):
                raise TvCodeError('GLASSHOUSE_INVALID_RESPONSE') from None
        if not isinstance(data, dict) or data.get('ok') is not True:
            raise TvCodeError('GLASSHOUSE_PAIRING_REFUSED')
        ticket = data.get('ticket')
        if not isinstance(ticket, str) or not re.fullmatch(r'[0-9a-f]{48}', ticket):
            raise TvCodeError('GLASSHOUSE_INVALID_RESPONSE')
        if 'code' in data or 'pin' in data:
            raise TvCodeError('TV_CODE_EXPOSED_ON_NETWORK')
        return ticket
    except (aiohttp.ClientError, TimeoutError):
        raise TvCodeError('GLASSHOUSE_UNREACHABLE') from None

async def confirm_tv_code(session, glasshouse_url, ticket, code, expected_fingerprint):
    if not isinstance(ticket, str) or not re.fullmatch(r'[0-9a-f]{48}', ticket):
        raise TvCodeError('INVALID_TICKET')
    if not isinstance(code, str) or not re.fullmatch(r'\d{8}', code):
        raise TvCodeError('INVALID_CODE')
    try:
        async with session.post(
            glasshouse_url.rstrip('/') + '/api/shwm-pair/complete',
            json={'ticket': ticket, 'code': code},
            allow_redirects=False,
        ) as response:
            if response.status in (401, 403, 404, 405):
                raise TvCodeError('GLASSHOUSE_PAIRING_NOT_SUPPORTED')
            if response.status != 200:
                raise TvCodeError('PIN_INVALID_OR_EXPIRED')
            try:
                data = await response.json()
            except (ValueError, aiohttp.ContentTypeError):
                raise TvCodeError('GLASSHOUSE_INVALID_RESPONSE') from None
        if not isinstance(data, dict) or data.get('ok') is not True:
            raise TvCodeError('PAIRING_REFUSED')
        if data.get('fingerprint') != expected_fingerprint or data.get('status') not in ('PAIRED','ALREADY_PAIRED'):
            raise TvCodeError('KEY_FINGERPRINT_MISMATCH')
        return data.get('status')
    except (aiohttp.ClientError, TimeoutError):
        raise TvCodeError('GLASSHOUSE_UNREACHABLE') from None
