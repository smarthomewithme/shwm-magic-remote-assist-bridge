"""Optional one-time Glasshouse SSH public-key pairing via HA administrator ingress."""
import base64
import hashlib
import html
import logging
from pathlib import Path
import aiohttp
from aiohttp import web
from tvcode import request_tv_code, confirm_tv_code, TvCodeError

LOG = logging.getLogger('shwm_pair')
INGRESS_IP = '172.30.32.2'

class PairError(Exception):
    pass

def fingerprint(key):
    words = key.split()
    if len(words) < 2 or words[0] != 'ssh-ed25519':
        raise PairError('INVALID_PUBLIC_KEY')
    try:
        raw = base64.b64decode(words[1], validate=True)
    except (ValueError, base64.binascii.Error):
        raise PairError('INVALID_PUBLIC_KEY') from None
    if len(raw) < 12:
        raise PairError('INVALID_PUBLIC_KEY')
    return 'SHA256:' + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')

def validate_token(token):
    if not isinstance(token, str) or not 1 <= len(token) <= 1024 or '\n' in token or '\r' in token:
        raise PairError('TOKEN_REQUIRED')
    return token

async def pair_key(session, url, public_key, token):
    """Call only the official add-key endpoint; no password/default/telnet fallback."""
    token = validate_token(token)
    target_fp = fingerprint(public_key)
    url = url.rstrip('/') + '/api/ssh'
    headers = {'Authorization': 'Bearer ' + token}
    try:
        async with session.get(url, headers=headers, allow_redirects=False) as res:
            if res.status in (401, 403):
                raise PairError('GLASSHOUSE_AUTH_ERROR')
            if res.status != 200:
                raise PairError('GLASSHOUSE_UNSUPPORTED')
            try:
                data = await res.json()
            except (ValueError, aiohttp.ContentTypeError):
                raise PairError('GLASSHOUSE_UNSUPPORTED') from None
        if not isinstance(data, dict) or data.get('ok') is not True or not isinstance(data.get('keys'), list):
            raise PairError('GLASSHOUSE_UNSUPPORTED')
        if data.get('needsToken'):
            raise PairError('GLASSHOUSE_TOKEN_NOT_CONFIGURED')
        if not data.get('writable'):
            raise PairError('GLASSHOUSE_READ_ONLY')
        if any(isinstance(k, dict) and k.get('fingerprint') == target_fp for k in data['keys']):
            return 'ALREADY_PAIRED', target_fp
        async with session.post(url, json={'action': 'add', 'key': public_key},
                                headers=headers, allow_redirects=False) as res:
            if res.status in (401, 403):
                raise PairError('GLASSHOUSE_AUTH_ERROR')
            if res.status != 200:
                raise PairError('GLASSHOUSE_ADD_FAILED')
            try:
                result = await res.json()
            except (ValueError, aiohttp.ContentTypeError):
                raise PairError('GLASSHOUSE_ADD_FAILED') from None
        if not isinstance(result, dict) or result.get('ok') is not True or not isinstance(result.get('keys'), list):
            raise PairError('GLASSHOUSE_ADD_FAILED')
        if not any(isinstance(k, dict) and k.get('fingerprint') == target_fp for k in result['keys']):
            raise PairError('GLASSHOUSE_NOT_VERIFIED')
        return 'PAIRED', target_fp
    except (aiohttp.ClientError, TimeoutError):
        raise PairError('TV_UNREACHABLE') from None

def page(ip, port, pub):
    ip, pub, fp = html.escape(ip), html.escape(pub), html.escape(fingerprint(pub))
    return f"""<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SHWM Parowanie LG</title><style>
:root{{color-scheme:dark;font-family:system-ui}}body{{background:#0f172a;color:#f8fafc;padding:18px}}
main{{max-width:640px;margin:auto;background:#1e293b;padding:22px;border-radius:16px}}
input{{display:block;width:100%;box-sizing:border-box;padding:12px;margin:12px 0;background:#0f172a;color:white;border:1px solid #64748b;border-radius:8px}}
button{{padding:12px;background:#38bdf8;color:#0f172a;font-weight:bold;border:0;border-radius:8px}}
button:disabled{{opacity:.5}}small{{color:#cbd5e1}}pre{{white-space:pre-wrap;word-break:break-word}}a{{color:#7dd3fc}}
</style></head><body><main>
<h2>Magic Remote – parowanie SSH</h2>
<p>Telewizor: <b>{ip}</b>. Wystarczy raz dopisać nasz klucz publiczny przez Glasshouse, bez terminala.</p>
<h3>Nowe parowanie bez tokenu — kod na ekranie LG</h3>
<p>Kliknij Wyślij prośbę. Na telewizorze pojawi się 8-cyfrowy kod ważny dwie minuty. Wpisz go tutaj, a Glasshouse sam doda klucz publiczny tego HA. Wymaga Glasshouse z nowym modułem SHWM.</p>
<button type="button" id="tv-start">Wyślij prośbę do LG</button>
<form id="tv-form" autocomplete="off" hidden>
<label for="tv-pin">Kod z telewizora</label>
<input id="tv-pin" inputmode="numeric" pattern="[0-9]{{8}}" maxlength="8" autocomplete="off" required>
<button type="submit">Potwierdź parowanie</button>
</form>
<p role="status" id="tv-status"></p>
<hr>
<details><summary>Starsza metoda — token administracyjny Glasshouse</summary>
<p>W starszym Glasshouse token jest wymagany do modyfikacji kluczy SSH.</p>
<form id="form" autocomplete="off">
<label for="token">Token administracyjny Glasshouse (jednorazowo)</label>
<input type="password" id="token" autocomplete="off" required>
<button type="submit" id="submit">Dodaj klucz SSH do LG</button>
</form><p role="status" id="result"></p>
<p><small>Token nie jest zapisywany. Uwaga: Glasshouse na porcie {port} używa HTTP. Korzystaj tylko w zaufanej sieci LAN.</small></p>
</details>
<details><summary>Klucz publiczny — kopiowanie awaryjne</summary><pre>{pub}</pre><small>Odcisk: {fp}</small></details>
</main><script>
const f=document.getElementById('form'),t=document.getElementById('token'),b=document.getElementById('submit'),r=document.getElementById('result');
let tvTicket=null;
const tvStart=document.getElementById('tv-start');
const tvForm=document.getElementById('tv-form');
const tvPin=document.getElementById('tv-pin');
const tvStatus=document.getElementById('tv-status');
tvStart.addEventListener('click', async()=>{{
 tvStart.disabled=true;tvForm.hidden=true;tvTicket=null;
 tvStatus.textContent='Wysyłam prośbę do telewizora…';
 try{{
   const res=await fetch('tv-code-start',{{method:'POST',headers:{{'Content-Type':'application/json'}},
     body:JSON.stringify({{}}),credentials:'same-origin',cache:'no-store'}});
   const data=await res.json();
   if(data.ok){{
     tvTicket=data.ticket;tvForm.hidden=false;
     tvStatus.textContent='Odczytaj kod z ekranu telewizora i wpisz go tutaj (2 minuty).';
   }}else{{
     tvStatus.textContent='Nie udało się: '+data.code;
   }}
 }}catch(_err){{tvStatus.textContent='Błąd komunikacji z panelem dodatku.'}}
 finally{{tvStart.disabled=false;}}
}});
tvForm.addEventListener('submit',async e=>{{
 e.preventDefault();if(!tvTicket)return;
 const code=tvPin.value;tvPin.value='';
 tvStatus.textContent='Sprawdzam kod…';
 try{{
  const res=await fetch('tv-code-finish',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{ticket:tvTicket,code}}),credentials:'same-origin',cache:'no-store'}});
  const data=await res.json();
  if(data.ok){{
   tvForm.hidden=true;tvTicket=null;
   tvStatus.textContent='Sparowano. Klucz SSH został dodany do telewizora.';
  }}else{{tvStatus.textContent='Nie udało się: '+data.code;}}
 }}catch(_err){{tvStatus.textContent='Błąd komunikacji z panelem dodatku.'}}
}});
f.addEventListener('submit',async e=>{{
e.preventDefault();const token=t.value;t.value='';b.disabled=true;r.textContent='Łączenie…';
try{{const response=await fetch('pair',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{token}}),credentials:'same-origin',cache:'no-store'}});
const d=await response.json();r.textContent=d.ok?(d.status==='ALREADY_PAIRED'?'Klucz już jest na LG.':'Klucz dodany do LG!'):'Problem z parowaniem: '+d.code;
}}catch(e){{r.textContent='Błąd połączenia z panelem dodatku.'}}finally{{b.disabled=false}}
}});
</script></body></html>"""

def create_panel(opts, public_key_path):
    panel = web.Application(client_max_size=4096)
    key_path = Path(public_key_path)
    ip, port = opts['tv_host'], opts.get('glasshouse_port', 8080)
    url = f'http://{ip}:{port}'

    @web.middleware
    async def ingress_only(request, handler):
        if request.remote != INGRESS_IP:
            return web.Response(status=403, text='Ingress required')
        return await handler(request)
    panel.middlewares.append(ingress_only)

    async def home(_request):
        pub = key_path.read_text(encoding='ascii').strip()
        return web.Response(text=page(ip, port, pub), content_type='text/html',
            headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer',
                     'X-Content-Type-Options':'nosniff',
                     'Content-Security-Policy':"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'self'; base-uri 'none'"})

    async def pair(request):
        if request.content_type != 'application/json':
            return web.json_response({'ok':False,'code':'JSON_REQUIRED'},status=415)
        try:
            body = await request.json()
            token = body.get('token') if isinstance(body, dict) else None
            pub = key_path.read_text(encoding='ascii').strip()
            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
                result, fp = await pair_key(session, url, pub, token)
            LOG.info('SSH_PAIR status=%s fingerprint=%s tv=%s',result,fp,ip)
            return web.json_response({'ok':True,'status':result,'fingerprint':fp},headers={'Cache-Control':'no-store'})
        except PairError as exc:
            LOG.warning('SSH_PAIR_FAILED code=%s tv=%s',str(exc),ip)
            return web.json_response({'ok':False,'code':str(exc)},status=400,headers={'Cache-Control':'no-store'})
        except (ValueError,OSError):
            return web.json_response({'ok':False,'code':'LOCAL_ERROR'},status=500)
    async def start_tv_code(request):
        if request.content_type != 'application/json':
            return web.json_response({'ok': False, 'code': 'JSON_REQUIRED'}, status=415)
        try:
            public_key = key_path.read_text(encoding='ascii').strip()
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
                ticket = await request_tv_code(session, url, public_key)
            LOG.info('TV_CODE_PAIRING_REQUESTED tv=%s', ip)
            return web.json_response({'ok': True, 'ticket': ticket},
                                     headers={'Cache-Control': 'no-store'})
        except TvCodeError as error:
            LOG.info('TV_CODE_PAIRING_REQUEST_FAILED code=%s', error)
            return web.json_response({'ok': False, 'code': str(error)}, status=400)
        except OSError:
            return web.json_response({'ok': False, 'code': 'LOCAL_KEY_ERROR'}, status=500)

    async def complete_tv_code(request):
        if request.content_type != 'application/json':
            return web.json_response({'ok': False, 'code': 'JSON_REQUIRED'}, status=415)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise TvCodeError('INVALID_JSON')
            public_key = key_path.read_text(encoding='ascii').strip()
            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
                status = await confirm_tv_code(
                    session, url, body.get('ticket'), body.get('code'),
                    fingerprint(public_key))
            LOG.info('TV_CODE_PAIRING_COMPLETE tv=%s status=%s', ip, status)
            return web.json_response({'ok': True, 'status': status},
                                     headers={'Cache-Control': 'no-store'})
        except TvCodeError as error:
            LOG.info('TV_CODE_PAIRING_FAILED code=%s', error)
            return web.json_response({'ok': False, 'code': str(error)}, status=400)
        except (ValueError, OSError):
            return web.json_response({'ok': False, 'code': 'LOCAL_ERROR'}, status=500)

    panel.router.add_get('/',home)
    panel.router.add_post('/pair',pair)
    panel.router.add_post('/tv-code-start',start_tv_code)
    panel.router.add_post('/tv-code-finish',complete_tv_code)
    return panel

async def start_panel(opts, public_key_path):
    runner=web.AppRunner(create_panel(opts,public_key_path))
    await runner.setup()
    try:
        site=web.TCPSite(runner,'0.0.0.0',8099)
        await site.start()
    except Exception:
        await runner.cleanup()
        raise
    LOG.info('Glasshouse key pairing panel ready via HA ingress')
    return runner
