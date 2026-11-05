# SHWM Magic Remote Assist Bridge — instrukcja (v0.1.1)

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
