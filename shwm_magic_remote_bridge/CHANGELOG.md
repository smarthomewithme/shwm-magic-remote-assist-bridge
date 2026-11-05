# Changelog

## 0.1.2 — TV microphone diagnostic without STT

- Optional `manual_audio_only` for manual tests on HA without any STT configuration.
- Measures PCM16 audio bytes, signal peak, RMS and recording duration via SSH and voiceinput.
- Captures no audio files and makes no Home Assistant Assist calls in audio-only mode.
- Existing Glasshouse and STT flows unchanged; audio-only mode disabled by default.

## 0.1.1 — manual test for isolated HA

- Optional `manual_test_enabled` and `shwm_magic_remote_test` Home Assistant event.
- Test HA can capture audio without Glasshouse events or MQTT reconfiguration.
- Manual test always STT-only; 2-second delay lets operator hold MIC.
- Fixed deprecated aiohttp WebSocket timeout argument.

## 0.1.0 — prototype

- Glasshouse MIC event trigger
- Rooted LG webOS voiceinput capture over SSH
- PCM16 16kHz streaming to Home Assistant Assist
- Dedicated persistent SSH key created by add-on
- STT-only mode by default; optional intent execution
- No stored audio; transcript logging off by default
- Unit tests complete; on-device app test still pending
