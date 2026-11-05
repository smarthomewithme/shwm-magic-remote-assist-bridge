# SHWM Magic Remote Assist Bridge — instrukcja (v0.1.5)

To dodatek HAOS, a nie integracja Marketplace/HACS.

## Instalacja

Home Assistant → Ustawienia → Aplikacje → Zainstaluj aplikację / Sklep → menu ⋮ → Repozytoria.
Dodaj adres: https://github.com/smarthomewithme/shwm-magic-remote-assist-bridge

Odśwież sklep i wybierz SHWM Magic Remote Assist Bridge.

## Wymagania

- LG webOS z rootem, SSH (root), działającymi voiceinput, luna-send i gniazdem mikrofonu.
- Glasshouse ze zdarzeniem przycisku MIC w encji event.*_remote_button.
- Skonfigurowany Assist ze sprawnym polskim STT w HAOS.
- Sieć lokalna: telewizor osiągalny z Home Assistant.

## Konfiguracja

W dodatku zmień tv_host na prywatny adres IP swojego LG (np. 192.168.1.224), remote_event_entity na encję przycisku Glasshouse (np. event.salon_lgtv_remote_button). tv_ssh_port to zwykle 22. record_seconds to liczba sekund nagrywania (5–20, domyślnie 8). pipeline_id pozostaw pusty dla domyślnego Assist.

Na początek execute_commands: false. Zmień log_transcript: true tylko na czas diagnozy, potem wyłącz.

Uruchom dodatek i w jego logu znajdź TV SSH PUBLIC KEY. Dopisz WYŁĄCZNIE jego publiczny klucz ssh-ed25519 do istniejącego pliku ~/.ssh/authorized_keys na telewizorze. NIE NADPISUJ pliku i nie udostępniaj klucza prywatnego ani tokenów. Przetestuj najpierw zdarzenie MIC i STT, dopiero potem rozważ execute_commands: true.

## Ograniczenia i bezpieczeństwo

Obecny kod jest prototypem i NIE został jeszcze przetestowany jako dodatek na HAOS. Zewnętrzne testy potwierdziły przechwytywanie mikrofonu, polskie STT i wykonanie potoku na LG 65NANO863PA / webOS 6.5.3. Inne LG trzeba sprawdzić.

Aplikacja nie rusza partycji systemowych LG, nie zapisuje WAV, nie modyfikuje Glasshouse. Jedna konfiguracja telewizora na instancję; sztywne okno nagrania; brak TTS i nakładki na ekranie TV. Stan urządzenia w HA trzeba weryfikować niezależnie od deklaracji agenta.

Jeżeli SSH zgłosi HOST KEY CHANGED, zweryfikuj tożsamość TV zamiast wyłączać sprawdzanie klucza.

## Odinstalowanie

Zatrzymaj i odinstaluj dodatek. Jeśli chcesz, usuń tylko dopisany wcześniej klucz publiczny z authorized_keys TV.

## Tryb ręczny na testowym HA — bez zmiany Glasshouse MQTT

Wymagany działający Assist/STT na testowym HA. Nie trzeba przepinać Glasshouse, a encja pilota nie musi istnieć w testowym HA.

1. Ustaw `tv_host` na IP telewizora, `manual_test_enabled: true`, `execute_commands: false` oraz `log_transcript: true`. Zachowaj przykładową `remote_event_entity`, jeśli Glasshouse nie jest połączony z testowym HA.
2. Uruchom aplikację ponownie. Dodaj jej klucz **publiczny SSH** z dziennika do `authorized_keys` telewizora, nie usuwając istniejących wpisów.
3. W testowym HA wejdź do **Narzędzia deweloperskie → Zdarzenia**. Typ zdarzenia: `shwm_magic_remote_test`; dane: `{}`. Kliknij **Wywołaj zdarzenie**.
4. Natychmiast **naciśnij i przytrzymaj MIC** w pilocie. Aplikacja odczeka 2 sekundy na aktywację urządzenia, następnie pobierze dźwięk i prześle go do STT testowego HA.
5. W Dzienniku szukaj `Manual event received`, `PCM streamed to Assist`, `STT succeeded`. Ręczny test jest zawsze STT-only, nawet jeśli dla normalnej obsługi włączono wykonywanie komend.

Po teście ustaw `manual_test_enabled: false` i `log_transcript: false`. Glasshouse na produkcyjnym HA pozostaje nietknięty.

## Test samego mikrofonu bez STT — v0.1.2

Dla osobnego testowego HA bez STT zaznacz `manual_test_enabled: true` oraz `manual_audio_only: true`, pozostawiając `execute_commands: false`. Ponownie uruchom dodatek. Z narzędzi deweloperskich wywołaj zdarzenie `shwm_magic_remote_test` z danymi `{}`, a następnie przytrzymaj MIC na pilocie.

Tryb audio-only łączy się przez SSH z LG, uruchamia voiceinput, odczytuje PCM16/16000Hz i oblicza liczbę bajtów, czas, peak i RMS. Nie wywołuje Assist ani STT; nie zapisuje próbek ani WAV. Komunikat `AUDIO-ONLY TEST PASSED` potwierdza przechwycenie dźwięku przez dodatek. Jeśli wartość `peak=0` i `rms=0`, sprawdź mikrofon oraz przytrzymanie MIC.

Jeżeli aplikacja nie może połączyć się z TV, sprawdź, czy jej publiczny klucz SSH został dopisany do `authorized_keys` TV. Nie usuwaj wcześniej istniejących kluczy. `manual_audio_only: false` zachowuje dotychczasowy test STT.

## Opcjonalne automatyczne kończenie mowy (v0.1.3)

`vad_enabled: false` (domyślnie) zachowuje sprawdzone stałe nagrywanie do `record_seconds`.
`vad_enabled: true` uruchamia prosty detektor energii PCM po stronie dodatku.
`vad_rms_threshold: 250` oraz `vad_silence_ms: 1500` pozwalają określić próg RMS i czas ciszy.
Detektor potrzebuje dwóch kolejnych ramek głośniejszych od progu (200 ms), potem co najmniej 1,5 sekundy ciszy. Jeśli nie potwierdzi końca mowy, użyje stałego limitu czasu.
**Uwaga:** hałas/TV i cicha mowa mogą wpływać na wykrycie. Na głównym HA nie włączaj automatycznego kończenia przed testami STT.
W `manual_audio_only` zawsze mierzymy całe nagranie.

## Pilot przy wyłączonym telewizorze — jak diagnozować

Nie deklarujemy działania pilota przy TV w standby. Testuj osobno: (1) TV włączony, (2) wygaszony sam ekran bez usypiania webOS, (3) zwykłe wyłączenie Power. Za każdym razem na testowym HA uruchom `shwm_magic_remote_test` w trybie `manual_audio_only: true` i naciśnij MIC.
LG 2021 webOS6 ma ustawienie Quick Start+ zwykle w Ustawienia → Ogólne → Urządzenia → Zarządzanie telewizorem → Quick Start+. Quick Start+ nie gwarantuje jednak działania SSH/voiceinput.
Nie zmieniaj firmware, usługi root, ani Glasshouse/MQTT.

## v0.1.4: diagnostyka i bezpieczne wznowienie

- `mic_retry_enabled: true`: po błędzie `TV_MIC_UNAVAILABLE`, **zanim rozpocznie się audio**, ponawia otwarcie mikrofonu tylko raz. Nie ponawia transkrypcji ani wykonywania akcji.
- Logi `STATUS`: `MIC_DETECTED`, `ASSIST_CONNECT`, `STT_READY`, `SSH_CONNECT`, `TV_MIC_READY`, `RECORDING`, `AUDIO_COMPLETE`, `STT_SUCCESS`, `ASSIST_INTENT_SUCCESS`, `COMPLETE`, `FAILED`.
- Osobne błędy: `SSH_AUTH_FAILED`, `SSH_HOST_KEY_ERROR`, `TV_SSH_UNREACHABLE`, `TV_MIC_UNAVAILABLE`, `TV_AUDIO_TIMEOUT`, `TV_CAPTURE_FAILED`.
- Pierwszy test na głównym HA: `execute_commands: false`, `vad_enabled: false`, `manual_test_enabled: false`, `manual_audio_only: false`, `log_transcript: true`. Skonfiguruj realną `remote_event_entity` z Glasshouse oraz potok Assist ze STT.
- Nie ruszamy plików Glasshouse ani systemowych partycji LG. Każda instalacja dodatku ma własny publiczny klucz SSH, który trzeba dopisać (bez nadpisywania) do `authorized_keys` na LG.

## v0.1.5 — automatyczne dodanie klucza przez Glasshouse

Gdy Glasshouse obsługuje zarządzanie kluczami SSH przez `/api/ssh`, nie trzeba już używać terminala LG. Dodatek ma panel **Otwórz interfejs WWW**, dostępny jedynie dla administratora HA (Ingress). W Glasshouse musi być skonfigurowany token administracyjny (`Server → Advanced`) oraz aktywne sterowanie (`allowControl`). Otwórz panel SHWM, wprowadź token i kliknij **Dodaj klucz SSH do LG**. Dodatek dodaje **wyłącznie swój klucz publiczny**, sprawdza odcisk w odpowiedzi, nigdy nie kasuje istniejących kluczy i nie powtarza instalacji istniejącego klucza. Token nie jest zapisywany w `/data`, w konfiguracji ani w logach; klucz prywatny pozostaje na HA. Jeśli brak endpointu, można skopiować klucz z panelu i dodać go w Glasshouse: `Server → Advanced → SSH keys`.

Nie da się dodać nowego klucza bez wcześniejszego uwierzytelnienia właściciela telewizora. Standardowe połączenie HTTP pomiędzy HA a Glasshouse (port 8080) jest **nieszyfrowane** — używaj parowania tylko w zaufanej sieci LAN. Nie stosuj telnetu ani domyślnego hasła SSH jako automatycznego obejścia zabezpieczeń. Po parowaniu zweryfikuj zwykłym testem MIC, czy SSH rzeczywiście działa.


## 0.1.6 — samodzielne parowanie jednym kliknięciem bez modyfikowania Glasshouse

Panel dodatku HA zawiera przycisk "Sparuj automatycznie z LG".
Po kliknięciu przez administratora HA:
1. Sprawdza obecne logowanie SSH kluczem dodatku.
2. Gdy nie działa, może użyć wyłącznie JUŻ AKTYWNEGO, lokalnego
   Telnetu root na porcie 23 w zrootowanym LG.
   Nie włącza Telnetu, nie podaje loginów ani haseł.
3. Dopisuje tylko ściśle zweryfikowany własny klucz SSH do
   /home/root/.ssh/authorized_keys. Nigdy nie usuwa innych kluczy.
4. Ponawia test prawdziwego logowania własnym kluczem SSH.
5. Sukces wyświetla dopiero po potwierdzeniu połączenia.

Jeżeli Telnet nie jest aktywny, ta droga nie zadziała. Pozostaje
jednorazowe autoryzowanie poprzez Glasshouse z tokenem lub ręczne dodanie
klucza przez właściciela. Nie istnieje legalny, niezależny od
wcześniejszej autoryzacji sposób automatycznego uzyskania root.
Telnet jest kanałem niezabezpieczonym — po sparowaniu należy go wyłączyć
w Homebrew Channel, jeśli działał. Nie należy otwierać go specjalnie
dla użytkowników w niezaufanej sieci.

Nie modyfikuje Glasshouse, MQTT, mikrofonu ani logiki Assist. Komendy
HA pozostają domyślnie wyłączone. Wymagane testy na rzeczywistym LG.


## v0.1.7 — diagnostyka TELNET_NO_CONFIRMATION

Jeśli v0.1.6 zgłosiło TELNET_NO_CONFIRMATION, to znaczy, że połączenie
TCP/Telnet istniało, ale dodatek nie otrzymał pozytywnego wyniku z polecenia
instalacyjnego. To nie dowodzi, że klucz nie został zapisany.

1. Zaktualizuj dodatek do v0.1.7, uruchom go, otwórz Interfejs WWW.
2. Najpierw kliknij **Sprawdź samo SSH (bez zmian na LG)**. To jedynie
   próba logowania w trybie BatchMode=yes z obecnym kluczem dodatku; nie
   dodaje nic do authorized_keys i nie uruchamia Telnetu.
3. Jeśli SSH działa, można przejść do mikrofonu. Nie ponawiaj parowania.
4. Jeśli SSH nie działa, naciśnij *Sparuj automatycznie z LG*. Nowy
   bootstrap weryfikuje krótkim poleceniem, czy Telnet wykonuje komendy
   jako root (UID 0), zanim zapisze cokolwiek. Potem korzysta z krótkiego
   polecenia powłoki, dopisującego dokładnie własny klucz SSH (z ochroną
   przed duplikatami i symlinkami).
5. Jeśli pojawi się TELNET_SHELL_NO_REPLY, TCP Telnet odpowiada, ale
   nie zwraca odpowiedzi z powłoki. W tym wypadku nie wykonano polecenia
   zmieniającego pliki. TELNET_NOT_ROOT i TELNET_LOGIN_REQUIRED również
   oznaczają, że nie dopisano klucza.
6. TELNET_COMMAND_UNCONFIRMED: nie mamy odpowiedzi z zapisu. Dodatek
   próbuje wtedy kontrolnie odczytać SSH. Jeśli nadal nie działa,
   pokaże błąd — nie wykonuje ponowienia zapisu w ciemno.

Nie przesyłaj kluczy prywatnych ani tokenów. Możesz bezpiecznie przekazać
jedynie kody błędów, etap testu i informacje, czy SSH działa.
Po udanym parowaniu zamknij Telnet root na TV, jeśli jest uruchomiony.

Glasshouse nie jest modyfikowany. execute_commands domyślnie false.


## v0.1.8 — szybkie kończenie VAD i ponowne wykorzystanie SSH

Poprawka opóźnienia zaobserwowanego na domowym HA 2026-11-05:
po VAD: speech finished występowało około 2 s oczekiwania,
zanim AUDIO_COMPLETE potwierdził zakończenie strumienia.
Teraz dodatek może wysłać do działającego skryptu na TV krótki
sygnał stop przez istniejący kanał SSH, a skrypt zwalnia gniazdo
audio i zamyka proces Luna. Normalnie ma na to do 0.9 s, a po tym
czasie pozostaje ograniczony timeoutem terminate/kill.

Nowa opcja:
- ssh_warmup_enabled: true — w czasie uruchomienia dodatku
  inicjuje istniejącym kluczem SSH krótkie połączenie typu true
  i pozwala mu pozostać w prywatnym gnieździe /run/shwm_magic_remote/
  do 180 s bezczynności. Przy kolejnym naciśnięciu MIC połączenie
  SSH może zostać ponownie wykorzystane. Nie uruchamia mikrofonu
  w tle. Nie zmienia żadnego pliku Glasshouse ani TV.
- ssh_warmup_enabled: false — wyłącza tę optymalizację
  (przydatne, jeśli dany telewizor źle toleruje dłuższe sesje SSH).

Przeprowadź test porównawczy po aktualizacji:
1. Zostaw execute_commands: false, record_seconds: 8,
   vad_enabled: true, vad_rms_threshold: 250 oraz
   vad_silence_ms: 1500, dopóki pełna komenda jest rozpoznawana.
2. Uruchom dodatek i sprawdź SSH_WARMUP_READY (albo
   SSH_WARMUP_SKIPPED, jeśli telewizor nie jest dostępny).
3. Naciśnij MIC i po krótkiej chwili wypowiedz całe polecenie,
   np. "Włącz światło w salonie".
4. W logach porównaj MIC_DETECTED → TV_MIC_READY,
   VAD: speech finished → AUDIO_COMPLETE
   oraz pełną transkrypcję STT.
5. Jeśli VAD ucina głos, zmierz tempo i ostrożnie zwiększ
   vad_silence_ms (np. 1800), nie obniżając od razu progu RMS.

Ograniczenie: mikrofon Magic Remote nie może nagrać słów wypowiedzianych
ZANIM otworzy się usługa voiceinput. SSH warm-up tylko zmniejsza
narzut sieciowy; nie obiecuje natychmiastowego startu. Poza tym
ControlPersist przez czas działania utrzymuje połączenie SSH,
dlatego w razie problemów ze standby należy wyłączyć opcję.


## v2 BETA testing (branch beta-v2; NOT a stable release)

Official HA Supervisor supports adding a different branch as a separate repository:

`https://github.com/smarthomewithme/shwm-magic-remote-assist-bridge#beta-v2`

Add it via Home Assistant → Settings → Apps → Install app → ⋮ → Repositories.
Install **SHWM Magic Remote Assist Bridge (v2 BETA)**. This is a different
add-on with a separate `/data` store and a newly generated SSH identity.
The original v0.1.9 installed from the main repository stays unchanged.
**Stop the v0.1.9 add-on before starting v2 BETA**; the beta has manual boot
and should not launch automatically. Verify it is stopped after HA restarts.

Configure `tv_host`, `remote_event_entity` and Assist pipeline on the beta
like in your working 0.1.9. Leave `execute_commands:false` while comparing
voice performance. The beta's key is NOT the v0.1.9 key, so open the
beta Web UI and first use the read-only SSH check. If unpaired, authorize
ONLY beta's public key using the same owner-controlled pairing flow. If
Telnet was disabled after the original pairing, the one-click local
Telnet bootstrap cannot succeed. Use an already supported authenticated
Glasshouse-token path or owner-managed key authorization. Do not reactivate
unprotected root Telnet just to avoid one setup step.

After each MIC press open beta → Web UI → **Odśwież diagnostykę**.
The panel shows: `HA event connected`, `session active`, `last_result`,
`event_to_mic_seconds`, `audio_captured_seconds`,
`capture_cleanup_seconds`, `assist_after_audio_seconds`, and total.
It retains at most five in-memory results; restarting beta clears them.
Log timestamps and user speech are NOT kept in this panel.

Compare two runs of v0.1.9 and two runs of beta, then repeat after the
Magic Remote has been idle. The first press may only wake the remote; if
there is no `MIC_DETECTED`, the event was missing before the add-on.
The add-on cannot wake a sleeping Bluetooth remote through SSH.

Rollback: stop v2 beta, start original v0.1.9 and verify its existing SSH
key and Glasshouse event. If the beta was paired, its own public key may
remain on the TV until the owner explicitly removes exactly that entry.
Do not uninstall or overwrite the original v0.1.9 until v2 has passed
hardware, audio quality and no-duplicate-command tests.
