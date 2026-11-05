# Changelog

## 0.1.6 — PROTOTYPE in feature branch only (not released)

- Add token-free TV PIN pairing client UI (requires proposed Glasshouse server API).
- Add strict ES5 pairing prototype for Glasshouse and Node/Python unit tests.
- Preserve v0.1.5 token method, no MIC or MQTT changes.
- Needs Glasshouse maintainers' security review and live TV verification.


## 0.1.5 — Glasshouse pairing panel

- Add admin-only Home Assistant Ingress panel with one-time Glasshouse token entry.
- Use Glasshouse authenticated GET/POST /api/ssh to add and fingerprint-check ONLY our SSH public key.
- No saved credentials, no telnet/default-password fallback, no unrelated authorized_keys edits.
- Retain existing Glasshouse event handling, Assist pipeline and audio-only test unchanged.

## 0.1.4 — robust Glasshouse to Assist bridge

- Pre-audio microphone retry once only when TV voice device temporarily unavailable.
- Categorized SSH/offline/host key/audio failures with structured status messages.
- Diagnostic stages and pipeline setup / STT / total latency measurements.
- Version logged on startup; VAD and execute_commands remain OFF by default.
- No modified TV files, no copied Glasshouse code.

## 0.1.3 — optional speech auto-stop

- Optional conservative RMS energy-based VAD in Assist streaming.
- No changes to default fixed-duration audio capture.
- Adjustable RMS threshold and silence limit; never stops before confirmed speech.
- Four unit tests for VAD and screen-off/standby diagnostic guidance.

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
