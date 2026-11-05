# SHWM Magic Remote Assist Bridge — instrukcja (v0.1.0)

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
