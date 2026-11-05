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
