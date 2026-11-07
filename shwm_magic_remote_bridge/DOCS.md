# SHWM Magic Remote Assist Bridge — instrukcja (v0.1.5)

To dodatek HAOS, a nie integracja Marketplace/HACS.

## v2.1.8 — opcjonalna nakładka TV: prawy dolny róg i ikony

Natywnych LG `createToast` nie da się pozycjonować dowolnie. `light` jest u góry po prawej, `advanced` z ikoną — na dole pośrodku. Dla **prawego dolnego rogu** dodatek ma teraz opcję oddzielnej, przezroczystej aplikacji webOS, domyślnie **wyłączoną**.

### Instalacja (jednorazowa, dobrowolna)
1. Pobierz `com.smarthomewithme.voiceoverlay_0.1.0_all.ipk` z zielonego workflow `Package optional LG bottom-right voice overlay` (artifact). Alternatywnie zbuduj paczkę ze źródeł `tv_overlay/` za pomocą oficjalnego `ares-package tv_overlay`.
2. W **webOS Dev Manager** połącz się ze zrootowanym LG, zainstaluj IPK jako zwykłą aplikację. Nie podmieniaj plików systemowych, nie uruchamiaj skryptów root ani usługi w tle.
3. W **Home Assistant → Ustawienia → Aplikacje → SHWM Magic Remote Assist Bridge → Konfiguracja** ustaw:
   - `tv_toasts_enabled: true`
   - `tv_overlay_enabled: true`
   - `tv_toast_icons_enabled: true`
   - `tv_toast_transcript_enabled` i `tv_toast_assist_reply_enabled` według upodobania.
4. Zapisz i uruchom ponownie dodatek, w panelu wybierz `Wyświetl test na TV`. Sprawdź **fizycznie**, czy karta z ikoną pojawia się w prawym dolnym rogu, nie przejmuje sterowania pilotem i samoczynnie znika.
5. Gdy pilot będzie reagował dziwnie lub nie zobaczysz nakładki, ustaw **`tv_overlay_enabled: false`**. Powrót do działających powiadomień natywnych jest natychmiastowy po restarcie dodatku; można odinstalować nakładkę osobno.

Nakładka używa krótkotrwałego okna `defaultWindowType=overlay`, tekstu wpisywanego przez `textContent`, SVG osadzonego w aplikacji i automatycznego `window.close()` po 4,4 s. Nie zapisuje nagrań, transkrypcji ani danych do plików; nie nasłuchuje w sieci i nie działa jako stała usługa TV. W logach `TV_OVERLAY_LAUNCH_ACCEPTED` znaczy tylko zaakceptowane `launch` przez Luna; jeśli aplikacji brak, log pokazuje `TV_OVERLAY_FALLBACK` i wyświetla zwykłe tekstowe powiadomienie.

**Uwaga:** webOS może ograniczać zachowanie nakładek i koncentrację pilota w zależności od firmware. Pierwsze uruchomienie traktuj jako test kompatybilności, bez zakładania pełnego sukcesu.

## v2.1.7 — ikony w małych powiadomieniach LG

Jeśli w v2.1.6 powiadomienia tekstowe działały, ale nie było ikon, przyczyną może być `standard` toast: na webOS 6.x ma miejsce na ikonę o szerokości zero. Po włączeniu `tv_toast_icons_enabled: true` v2.1.7 używa `type: light` razem z lokalnym `iconUrl`. Taki toast pojawia się w prawym górnym rogu, zamiast na dole ekranu. Wyłączenie ikon przywraca poprzedni typ standardowy. Zachowaj `tv_toasts_enabled: true`. Sprawdź fizycznie ikonę na swoim LG; `TV_ICONS_READY` i `TV_TOAST_SENT` same nie potwierdzają rysowania.

## v2.1.6 — opcjonalna grafika i szczegóły poleceń na telewizorze

W Home Assistant → **Ustawienia → Aplikacje → SHWM Magic Remote Assist Bridge → Konfiguracja** są trzy nowe pola, wszystkie domyślnie wyłączone. Pozostaw `tv_toasts_enabled: true`, aby jakiekolwiek powiadomienia były aktywne.

- `tv_toast_icons_enabled: true`: spróbuj pokazać małe ikony (mikrofon, przetwarzanie, sukces, błąd). Po starcie dodatek tworzy **tylko w pamięci tymczasowej LG** `/tmp/shwm_magic_remote_icons/*.png`, bez instalowania aplikacji czy zapisywania partycji systemowych. `TV_ICONS_READY` oznacza utworzenie plików, a `TV_TOAST_SENT icon=requested` jedynie przyjęcie przez Luna. Na konkretnym LG ikonę trzeba obejrzeć na ekranie. Jeżeli TV się zrestartuje, pliki w `/tmp` mogą zniknąć; uruchom wtedy ponownie dodatek lub wyłącz tę opcję.
- `tv_toast_transcript_enabled: true`: po STT pokaże `Usłyszałem: Włącz światło w jadalni`. To są słowa rozpoznane przez STT, nie niezależnie zweryfikowana wypowiedź.
- `tv_toast_assist_reply_enabled: true`: po skutecznie sklasyfikowanej odpowiedzi `action_done` lub `query_answer` pokaże `Assist: Włączyłem światło w jadalni` albo `Odpowiedź: ...`, zamiast ogólnego `Gotowe`. To **deklaracja Assist**, nie niezależna weryfikacja stanu fizycznego urządzenia. Jeśli odpowiedzi brak, zostaje dotychczasowy stały toast. Odmowy i błędy nie są przedstawiane jako sukces.

webOS ogranicza długość komunikatu do 60 znaków, dlatego długi tekst jest skracany. Szczegółowe teksty są przesyłane bezpośrednio przez istniejące SSH i nie są zapisywane w historii sesji ani nowych logach. Mogą jednak ujawniać prywatną wypowiedź wszystkim oglądającym TV — włącz tylko świadomie. Dwa szczegółowe toasty z jednego polecenia mogą chwilowo ustawiać się w kolejce systemowej.

**Bezpieczny test:** najpierw włącz tylko ikony i naciśnij w panelu „Wyświetl test na TV”. Gdy zobaczysz ikonę, możesz oddzielnie sprawdzić tekst rozpoznania i odpowiedź Assist. Test nie wymaga ponownego parowania SSH ani zmian mikrofonu i VAD.

## v2.1.4 — krótsze oczekiwanie i wiarygodny wynik polecenia

Na nowych instalacjach domyślna cisza po wypowiedzi to 1100 ms. **Wcześniej zapisana konfiguracja nie zmienia się automatycznie**: w Ustawienia → Aplikacje → SHWM Magic Remote Assist Bridge → Konfiguracja ustaw `vad_silence_ms: 1100` (zachowując `vad_enabled: true`), zapisz i uruchom ponownie dodatek. Zachowaj `record_seconds: 8` i `vad_rms_threshold: 250` podczas pierwszego porównania; jeśli ucinane są końcówki lub pauzy między słowami, przywróć `vad_silence_ms: 1500`.

Po sesji głosowej sprawdzaj log `STATUS VAD_DIAGNOSTIC`:
- `QUIET_CONFIRMED`: po wykryciu mowy znaleziono wystarczająco długą ciszę.
- `NO_CONFIRMED_SPEECH`: VAD nie zobaczył 200 ms ciągłego sygnału powyżej progu.
- `NO_LONG_ENOUGH_SILENCE`: mowa była, lecz hałas lub kolejne dźwięki zerowały okno ciszy; nagrywanie doszło do limitu.

Gdy asystent odpowie odmową na polecenie (np. brama), nowy wynik `INTENT_DECLINED` i powiadomienie o braku potwierdzenia nie udają sukcesu. Nie ma automatycznego ponowienia ani obchodzenia kontroli bezpieczeństwa. Sprawdź rzeczywisty stan urządzenia niezależnie od odpowiedzi AI. Powiadomienia z v2.1.3 pozostały bez zmian.


## Powiadomienia LG — v2.1.3, zamknięte stdin

W v2.1.2 log `ssh_exit=0 stdout_bytes=0 stderr_bytes=0` oznaczał brak odpowiedzi, mimo że ręczny test `luna-send` działał na TV. Gdy uruchomiony zdalnie `luna-send` dostaje EOF na standardowym wejściu, może natychmiast zakończyć pracę bez odpowiedzi. v2.1.3 utrzymuje to wejście otwarte podczas oczekiwania na pojedynczą odpowiedź Luna (maks. 4 sekundy), a zamyka je dopiero po zakończeniu procesu. Po aktualizacji w **Ustawienia → Apps** sprawdź wersję `v2.1.3`, użyj przycisku **Wyświetl test na TV** i sprawdź faktyczne powiadomienie. Nie wymaga ponownego parowania kluczy SSH; obsługa mikrofonu nie zmieniła się.


## Powiadomienia LG — poprawka v2.1.2

Jeśli v2.1.1 zwracał `NO_VALID_LUNA_RESPONSE`, v2.1.2 używa pojedynczego, minimalnego wywołania `luna-send -n 1 -f` z polem `message` — zgodnego z pozytywnym testem właściciela na LG 65NANO863PA. Nie wymusza `-a webosbrew` ani `sourceId`. Po zaktualizowaniu dodatku w **Ustawienia → Aplikacje** upewnij się, że dziennik pokazuje `v2.1.2`, a następnie wybierz w panelu **Wyświetl test na TV**. Sprawdź, czy powiadomienie pojawiło się na ekranie. Gdy test zawiedzie, skopiuj kod `TV_TOAST_SKIPPED` oraz bezpieczną linię `TV_TOAST_DIAGNOSTIC`, jeśli występuje. Nie uruchamiaj powtórzeń automatycznych; mikrofon i Assist pozostają niezależne.


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


## v2.0.0 — aktualizacja działającego dodatku (bez instalowania drugiego)

Zainstaluj v2.0.0 przez standardowe **Aktualizuj** w dodatku SHWM Magic Remote Assist Bridge w Home Assistant. Nie dodawaj repozytorium beta. Zachowany został dotychczasowy `slug: shwm_magic_remote_bridge`, jego trwały katalog `/data` i klucz SSH telewizora; nie paruj urządzenia ponownie.

W panelu **Interfejs WWW** jest przycisk **Odśwież diagnostykę**. Wyświetla on aktualny stan HA i ostatnie pięć wyników oraz czasy: rozpoczęcia Assist, gotowości mikrofonu, nagrania, VAD i otrzymania odpowiedzi Assist. Nie przechowuje nagrania, rozpoznanych zdań ani haseł.

### Konkretny błąd z logu użytkownika

Wykryta odpowiedź: `intent-end` zawierający tekst:
`Sorry, I had a problem talking to OpenAI: Error code: 503 ... Fallback providers are disabled until SHWM_ROUTER_TOKEN is configured ... cloudflare_transient_cooldown`.

To **nie oznacza wykonania komendy**. Od v2.0.0 log zawiera:
`STATUS ASSIST_INTENT_FAILED code=AI_ROUTER_UNAVAILABLE hint=CHECK_SHWM_ROUTER_TOKEN_AND_PROVIDER_COOLDOWN command_executed=UNCONFIRMED` i `STATUS COMPLETE result=AI_ROUTER_UNAVAILABLE`.

Nie występuje `ASSIST_INTENT_SUCCESS`. Nie ponawiamy automatycznie komend, bo HA mogło już uruchomić akcję. Aby faktycznie naprawić błąd 503, sprawdź osobno konfigurację routera AI/HA: ustawienie `SHWM_ROUTER_TOKEN` (jeżeli zamierzasz używać dostawców zapasowych), jego uprawnienia oraz stan cooldownu/dostawcy pierwotnego. Nie wpisuj sekretów do ustawień SHWM Bridge ani nie udostępniaj tokenu w logach. Jeśli nie używasz zapasowych dostawców, zmień konfigurację/router na zaufaną działającą ścieżkę. W razie niepewności pozostaw `execute_commands:false` i testuj tylko STT.

`ASSIST_INTENT_SUCCESS` jest teraz zarezerwowany dla potwierdzonych strukturalnie odpowiedzi HA o typie `action_done` lub `query_answer`. Odpowiedź `query_answer` to odpowiedź na pytanie, nie potwierdzenie zmiany stanu urządzenia. Sprawdź stan urządzenia w HA niezależnie.

LG/Glasshouse, obecny klucz SSH, VAD, dźwięk, `tv_host` i `remote_event_entity` pozostają bez zmian. W razie problemu wróć do kopii zapasowej dodatku z v0.1.9; nie reinstaluj go i nie usuwaj klucza z LG.

## v2.1.0 — opcjonalne powiadomienia systemowe na LG

Zachowujemy działającą wersję audio i parowanie SSH. Nowa opcja dodatku:

```yaml
tv_toasts_enabled: false
```

Domyślnie WYŁĄCZONA, żeby aktualizacja nie zmieniała odtwarzania TV ani działania MIC. Aby przetestować:

1. Zaktualizuj ten sam dodatek SHWM Magic Remote Assist Bridge do v2.1.0 i w zakładce Konfiguracja ustaw `tv_toasts_enabled: true`.
2. Uruchom dodatek ponownie; sprawdź, czy w logu jest `TV system notifications (optional): True`.
3. Uruchom **Interfejs WWW → Wyświetl test na TV**. To polecenie wysyła tylko stały napis na ekran; nie uruchamia mikrofonu i nie wykonuje żadnej komendy Home Assistant.
4. Jeśli LG potwierdzi `TV_TOAST_SENT kind=TEST`, sprawdź, czy na ekranie pojawia się krótki toast. Sukces API nie dowodzi jeszcze, że użytkownik go zobaczył.
5. Dopiero potem naciśnij MIC; dodatek zgłosi `LISTENING` po otwarciu mikrofonu i wynik Assist po zakończeniu. Gdy telewizor odrzuci powiadomienie, pojawi się `TV_TOAST_SKIPPED reason=...`, ale głos nadal działa niezależnie.

To mechanizm `luna-send -a webosbrew -f -n 1 luna://com.webos.notification/createToast` z dokumentowanego kodu webOS Homebrew Channel. Treść jest zdefiniowana w module tv_toast.py (żadne słowa użytkownika ani odpowiedzi modelu nie trafiają do toasta). Wymaga systemowego interfejsu LG wspierającego ten typ uprawnień. Mechanizm może nie działać na wszystkich webOS i NIE jest zwykłym SDK dla aplikacji trzecich; dlatego wymaga rzeczywistego testu na zrootowanym telewizorze.

Toasty systemowe nie mają własnego layoutu SHWM i znikają automatycznie. Pełny, stylizowany panel z transkrypcją wymaga osobnego projektu nakładki, którego tutaj nie wdrażamy. Jeżeli komunikaty przeszkadzają przy oglądaniu lub nie działają, wyłącz `tv_toasts_enabled` i uruchom dodatek ponownie; reszta funkcji pozostaje niezmieniona.

## v2.1.1 — dlaczego test LG zgłaszał NOT_CONFIRMED?

v2.1.0 pokazywała jedną ogólną informację, nawet jeśli usługa webOS zwróciła konkretny błąd. v2.1.1 naprawia **diagnostykę**, nie zmienia dotychczasowego mechanizmu powiadomień i nie omija uprawnień webOS.

Po aktualizacji otwórz **Interfejs WWW → Wyświetl test na TV**. Teraz przy odmowie dostaniesz dokładniejszy kod, np. `SERVICE_PERMISSION_DENIED`, `SERVICE_UNKNOWN_SOURCE`, `SERVICE_METHOD_UNAVAILABLE`, `SSH_AUTH_FAILED`, `NO_VALID_LUNA_RESPONSE` lub `TIMEOUT`. Ten sam kod znajdziesz w logu `STATUS TV_TOAST_SKIPPED reason=...`.

- `SERVICE_PERMISSION_DENIED`: wywołanie zostało odrzucone przez politykę aplikacji/usługi; nie zmieniaj systemowych uprawnień ani nie podszywaj się pod inną aplikację.
- `SERVICE_UNKNOWN_SOURCE`: webOS nie rozpoznaje identyfikatora źródła. Potrzebne potwierdzenie konfiguracji/wersji Homebrew na danym LG.
- `NO_VALID_LUNA_RESPONSE`: brak poprawnego JSON w stdout polecenia — należy zbadać kompatybilność narzędzia na konkretnym firmware.
- `SSH_AUTH_FAILED`, `TV_SSH_UNREACHABLE`, `LUNA_SEND_NOT_FOUND`: zacznij od SSH, ścieżki poleceń i stanu TV.

Nie przekazujemy ani nie zapisujemy surowych odpowiedzi, haseł i tokenów. Nie powtarzamy nieudanej komendy w pętli. W razie problemów możesz wyłączyć `tv_toasts_enabled`; polecenia głosowe nadal działają.
