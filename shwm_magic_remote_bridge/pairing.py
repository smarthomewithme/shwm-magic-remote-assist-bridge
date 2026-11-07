"""Optional one-time Glasshouse SSH public-key pairing via HA administrator ingress."""
import asyncio
import base64
import hashlib
import html
import logging
from pathlib import Path
import aiohttp
from aiohttp import web
from bootstrap import auto_pair, check_current_ssh, BootstrapError

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
<h2>Magic Remote — v2.0</h2>
<p>Telewizor: <b>{ip}</b>. Połącz nasz dodatek z telewizorem bez kopiowania klucza i bez modyfikowania Glasshouse.</p>
<p><strong>Nie trzeba niczego zmieniać w Glasshouse.</strong> Sprawdzimy klucz SSH, a jeżeli potrzeba, skorzystamy wyłącznie z już działającego na zrootowanym LG dostępu administracyjnego Telnet. Nie włączamy go ani nie stosujemy domyślnych haseł.</p>
<button type="button" id="ssh-check">Najpierw sprawdź samo SSH (bez zmian na LG)</button>
<p role="status" id="ssh-status"></p>
<button type="button" id="auto-pair">Sparuj automatycznie z LG</button>
<p role="status" id="auto-result"></p>
<p><small>Jeżeli Telnet na telewizorze jest wyłączony, automatyczne parowanie nie będzie możliwe. Wtedy można skorzystać z wcześniejszej autoryzacji lub poniższego wariantu Glasshouse. Po udanym parowaniu wyłącz niepotrzebny Telnet na LG.</small></p>
<details><summary>Alternatywa: token administratora Glasshouse</summary>
<p>Jeżeli masz już token Glasshouse, dodatek może nim jednorazowo autoryzować klucz SSH bez użycia Telnetu.</p>
<form id="form" autocomplete="off">
<label for="token">Token administracyjny Glasshouse (jednorazowo)</label>
<input type="password" id="token" autocomplete="off" required>
<button type="submit" id="submit">Dodaj klucz SSH do LG</button>
</form><p role="status" id="result"></p></details>
<details><summary>Klucz publiczny — kopiowanie awaryjne</summary><pre>{pub}</pre><small>Odcisk: {fp}</small></details>
<section aria-label="Diagnostyka glosu"><h3>Ostatnia sesja głosowa</h3>
<p>Panel pokazuje ostatnie pięć wyników i czas etapów; nie zapisuje nagrań ani transkrypcji.</p>
<button type="button" id="status-refresh">Odśwież diagnostykę</button>
<pre id="status-output" aria-live="polite">Wybierz Odśwież diagnostykę.</pre></section>
<section aria-label="Powiadomienia webOS"><h3>Powiadomienia na ekranie LG</h3>
<p>Opcjonalne powiadomienia LG: włącz <code>tv_toasts_enabled</code>. Dodatkowe opcje w konfiguracji: <code>tv_toast_icons_enabled</code> (ikony PNG w /tmp LG), <code>tv_toast_transcript_enabled</code> (usłyszane słowa), <code>tv_toast_assist_reply_enabled</code> (odpowiedź Assist). Wypowiedzi mogą zawierać prywatne dane, więc domyślnie są ukryte. Ikony sprawdź na prawdziwym ekranie przyciskiem poniżej.</p>
<button type="button" id="toast-test">Wyświetl test na TV</button>
<p id="toast-status" role="status"></p></section>
<p><small>Parowanie wykorzystujące aktywny Telnet oraz alternatywne API Glasshouse HTTP jest nieszyfrowane: stosuj je wyłącznie we własnej, zaufanej sieci LAN. Nie otwieraj portów z Internetu.</small></p>
</main><script>
const f=document.getElementById('form'),t=document.getElementById('token'),b=document.getElementById('submit'),r=document.getElementById('result');
const autoButton=document.getElementById('auto-pair'),autoResult=document.getElementById('auto-result');
const checkButton=document.getElementById('ssh-check'),sshStatus=document.getElementById('ssh-status');
const statusRefresh=document.getElementById('status-refresh'),statusOutput=document.getElementById('status-output');
const toastTest=document.getElementById('toast-test'),toastStatus=document.getElementById('toast-status');
toastTest.addEventListener('click',async()=>{{
 toastTest.disabled=true;toastStatus.textContent='Wysyłam test do LG…';
 try{{
  const response=await fetch('test-toast',{{method:'POST',
   headers:{{'Content-Type':'application/json'}},credentials:'same-origin',
   body:JSON.stringify({{confirm:true}}),cache:'no-store'}});
  const data=await response.json();
  toastStatus.textContent=data.ok?
   'LG potwierdził przyjęcie powiadomienia. Sprawdź obraz telewizora.':
   (data.code==='FEATURE_DISABLED'?'Najpierw włącz tv_toasts_enabled w konfiguracji.':
    'Nieudany test LG: '+data.code+'. Sprawdź log STATUS TV_TOAST_SKIPPED.');
 }}catch(_err){{toastStatus.textContent='Błąd komunikacji z dodatkiem.';}}
 finally{{toastTest.disabled=false;}}
}});
statusRefresh.addEventListener('click', async()=>{{
 statusRefresh.disabled=true; statusOutput.textContent='Odczytuję stan Bridge…';
 try{{
  const response=await fetch('status',{{method:'GET',credentials:'same-origin',cache:'no-store'}});
  const d=await response.json();
  if(!d.ok)throw new Error('not-ready');
  const s=d.state;
  const fmt=n=>typeof n==='number'?n.toFixed(2)+' s':'—';
  let lines=[
    'Wersja: '+s.version,
    'Zdarzenia HA: '+(s.ready?'POŁĄCZONO':'BRAK POŁĄCZENIA'),
    'Sesja: '+(s.active?'TRWA':'BEZCZYNNOŚĆ')+' / '+s.phase,
    'Liczba sesji: '+s.sessions,
    'Ostatni wynik: '+s.last_result,
    'MIC podczas trwającej sesji (pominięte): '+s.ignored_busy_events,
    'Czas MIC od zdarzenia: '+fmt(s.last_timings.event_to_mic_seconds),
    'Dźwięk: '+fmt(s.last_timings.audio_captured_seconds),
    'Zamykanie: '+fmt(s.last_timings.capture_cleanup_seconds),
    'Odpowiedź Assist: '+fmt(s.last_timings.assist_after_audio_seconds),
    'STT po nagraniu: '+fmt(s.last_timings.stt_after_audio_seconds),
    'Interpretacja/wykonanie po STT: '+fmt(s.last_timings.intent_after_stt_seconds),
    'Finalizacja potoku: '+fmt(s.last_timings.pipeline_finish_seconds),
    'Łącznie: '+fmt(s.last_timings.total_seconds),
    'Najwolniejszy etap: '+({{
      'ASSIST_RESPONSE':'Przetwarzanie Assist — szczegóły w rozbiciu etapów',
      'TV_MIC_STARTUP':'Uruchamianie mikrofonu LG / SSH',
      'TV_CAPTURE_CLEANUP':'Kończenie przechwytywania na LG',
      'NONE':'Brak wyraźnej anomalii'
    }}[s.last_bottleneck]||'Brak danych')
  ];
  if(s.history.length)lines.push('Ostatnie sesje: '+s.history.map(x=>
    '#'+x.session+' '+x.result+' ('+fmt(x.timings.total_seconds)+', Assist '+fmt(x.timings.assist_after_audio_seconds)+')'
  ).join(' | '));
  statusOutput.textContent=lines.join('\\n');
 }}catch(_err){{statusOutput.textContent='Brak danych diagnostycznych. Sprawdź log dodatku.';}}
 finally{{statusRefresh.disabled=false;}}
}});
checkButton.addEventListener('click',async()=>{{
 checkButton.disabled=true;sshStatus.textContent='Sprawdzam SSH bez zmian na LG…';
 try{{
  const response=await fetch('check-ssh',{{method:'POST',
   headers:{{'Content-Type':'application/json'}},
   body:JSON.stringify({{}}),credentials:'same-origin',cache:'no-store'}});
  const result=await response.json();
  sshStatus.textContent=result.ok?
   (result.authorized?'SSH działa! Klucz tego dodatku jest już autoryzowany.':'SSH jeszcze nie pozwala na logowanie kluczem dodatku.') :
   ('Test SSH: '+result.code);
 }}catch(_err){{sshStatus.textContent='Błąd komunikacji z panelem HA.';}}
 finally{{checkButton.disabled=false;}}
}});

autoButton.addEventListener('click',async()=>{{
 autoButton.disabled=true;
 autoResult.textContent='Sprawdzam autoryzację LG…';
 try{{
  const response=await fetch('auto-pair',{{method:'POST',
   headers:{{'Content-Type':'application/json'}},
   body:JSON.stringify({{confirm:true}}),credentials:'same-origin',cache:'no-store'}});
  const result=await response.json();
  autoResult.textContent=result.ok?
   (result.status==='ALREADY_AUTHORIZED'?'Połączenie SSH już działa. Gotowe!':'Sparowano! Klucz dodany i SSH zweryfikowane.') :
   (result.code==='TELNET_NOT_AVAILABLE'?'Na LG nie działa Telnet. Wybierz inną metodę pierwszej autoryzacji.':
    result.code==='KEY_ADDED_BUT_SSH_NOT_READY'?'Klucz zapisano, ale SSH nie odpowiada. Sprawdź, czy SSH jest włączone w Homebrew Channel.':
    result.code==='TELNET_SHELL_NO_REPLY'?'Telnet odpowiada, ale nie wykonuje krótkiego polecenia diagnostycznego. Nie zmieniono kluczy.':
    result.code==='TELNET_NOT_ROOT'?'Telnet nie daje uprawnień root. Nie zmieniono kluczy.':
    result.code==='TELNET_LOGIN_REQUIRED'?'Telnet wymaga logowania. Nie próbujemy domyślnych haseł.':
    result.code==='TELNET_COMMAND_UNCONFIRMED'?'Nie ma pewności, czy zapis się wykonał. Użyj przycisku „Sprawdź samo SSH”, nie ponawiaj w ciemno.':
    'Automatyczne parowanie nie powiodło się: '+result.code);
 }}catch(_err){{autoResult.textContent='Błąd połączenia z panelem HA.';}}
 finally{{autoButton.disabled=false;}}
}});
f.addEventListener('submit',async e=>{{
e.preventDefault();const token=t.value;t.value='';b.disabled=true;r.textContent='Łączenie…';
try{{const response=await fetch('pair',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{token}}),credentials:'same-origin',cache:'no-store'}});
const d=await response.json();r.textContent=d.ok?(d.status==='ALREADY_PAIRED'?'Klucz już jest na LG.':'Klucz dodany do LG!'):'Problem z parowaniem: '+d.code;
}}catch(e){{r.textContent='Błąd połączenia z panelem dodatku.'}}finally{{b.disabled=false}}
}});
</script></body></html>"""

def create_panel(opts, public_key_path, ssh_args, monitor=None, notifier=None):
    panel = web.Application(client_max_size=4096)
    key_path = Path(public_key_path)
    ip, port = opts['tv_host'], opts.get('glasshouse_port', 8080)
    url = f'http://{ip}:{port}'
    auto_lock = asyncio.Lock()

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
    async def do_auto_pair(request):
        if request.content_type != 'application/json':
            return web.json_response({'ok': False, 'code': 'JSON_REQUIRED'}, status=415)
        try:
            body = await request.json()
            if not isinstance(body, dict) or body.get('confirm') is not True:
                return web.json_response({'ok': False, 'code': 'EXPLICIT_CONFIRMATION_REQUIRED'}, status=400)
            if auto_lock.locked():
                return web.json_response({'ok': False, 'code': 'PAIRING_IN_PROGRESS'}, status=409)
            async with auto_lock:
                own_public_key = key_path.read_text(encoding='ascii').strip()
                status = await auto_pair(opts, own_public_key, ssh_args)
            LOG.info('AUTO_PAIR status=%s tv=%s', status, ip)
            return web.json_response({'ok': True, 'status': status}, headers={'Cache-Control': 'no-store'})
        except BootstrapError as exc:
            LOG.warning('AUTO_PAIR_FAIL code=%s tv=%s', exc.code, ip)
            return web.json_response({'ok': False, 'code': exc.code}, status=400,
                                     headers={'Cache-Control': 'no-store'})
        except (OSError, ValueError):
            LOG.warning('AUTO_PAIR_FAIL code=LOCAL_ERROR tv=%s', ip)
            return web.json_response({'ok': False, 'code': 'LOCAL_ERROR'}, status=500)

    async def check_ssh_only(request):
        if request.content_type != 'application/json':
            return web.json_response({'ok':False,'code':'JSON_REQUIRED'},status=415)
        try:
            # Read-only connection check: no telnet and no key writes.
            authorized = await check_current_ssh(opts, ssh_args)
            LOG.info('SSH_READ_ONLY_CHECK authorized=%s tv=%s',authorized,ip)
            return web.json_response({'ok':True,'authorized':authorized},
                                     headers={'Cache-Control':'no-store'})
        except BootstrapError as exc:
            LOG.warning('SSH_READ_ONLY_CHECK_FAILED code=%s tv=%s',exc.code,ip)
            return web.json_response({'ok':False,'code':exc.code},status=400)
        except (OSError, ValueError):
            return web.json_response({'ok':False,'code':'SSH_CHECK_FAILED'},status=500)

    async def status(_request):
        if monitor is None:
            return web.json_response({'ok':False,'code':'STATUS_UNAVAILABLE'},status=503)
        return web.json_response({'ok':True,'state':monitor.snapshot()},
                                 headers={'Cache-Control':'no-store'})

    async def test_toast(request):
        if request.content_type != 'application/json':
            return web.json_response({'ok':False,'code':'JSON_REQUIRED'},status=415)
        try:
            body=await request.json()
        except (ValueError, TypeError):
            return web.json_response({'ok':False,'code':'JSON_INVALID'},status=400)
        if not isinstance(body,dict) or body.get('confirm') is not True:
            return web.json_response({'ok':False,'code':'CONFIRM_REQUIRED'},status=400)
        if notifier is None or not notifier.enabled:
            return web.json_response({'ok':False,'code':'FEATURE_DISABLED'},status=409,
                                     headers={'Cache-Control':'no-store'})
        accepted,reason=await notifier.send_diagnostic('TEST')
        return web.json_response({'ok':accepted,'code':reason},
                                 status=200 if accepted else 503,
                                 headers={'Cache-Control':'no-store'})

    panel.router.add_get('/',home)
    panel.router.add_get('/status',status)
    panel.router.add_post('/test-toast',test_toast)
    panel.router.add_post('/pair',pair)
    panel.router.add_post('/auto-pair',do_auto_pair)
    panel.router.add_post('/check-ssh',check_ssh_only)
    return panel

async def start_panel(opts, public_key_path, ssh_args, monitor=None, notifier=None):
    runner=web.AppRunner(create_panel(opts,public_key_path,ssh_args,
                                     monitor=monitor,notifier=notifier))
    await runner.setup()
    try:
        site=web.TCPSite(runner,'0.0.0.0',8099)
        await site.start()
    except Exception:
        await runner.cleanup()
        raise
    LOG.info('Glasshouse key pairing panel ready via HA ingress')
    return runner
