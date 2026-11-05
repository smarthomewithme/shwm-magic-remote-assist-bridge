# Changelog

## 0.1.8 — faster MIC startup and graceful VAD stop

- Reuse a private, bounded-lived OpenSSH multiplex connection for quicker subsequent MIC requests. Warm up after startup without changing Glasshouse or launching the TV microphone.
- Add ssh_warmup_enabled: true (toggle off if the LG doesn't support SSH connection sharing or standby is affected).
- When VAD confirms the end of speech, send a cooperative stop signal on the SSH channel; remote voiceinput helper closes the audio socket and terminates Luna subprocess normally.
- Wait up to 0.9s for graceful completion; preserve bounded terminate/kill fallback if the remote LG ignores stop.
- Keep max recording time at record_seconds. No changes to VAD energy thresholds, authenticated SSH onboarding, Glasshouse events, Assist pipeline, or command execution defaults.
- Add regressions for quick stop, fallback cleanup, untouched full-length captures, and SSH pre-warm.
- TV speed gains are estimates until on-device tests; initial captured words cannot be recovered if spoken before TV_MIC_READY.


## 0.1.7 — Diagnose TELNET_NO_CONFIRMATION safely

- Admin-only **Sprawdź samo SSH** button checks add-on authorization without any TV file changes.
- Telnet onboarding now probes a short read-only command and confirms actual root UID before touching authorized_keys.
- Replace long telnet Python invocation with small POSIX shell append-only command; does not depend on Python in Telnet PATH.
- Distinguish missing root/login/shell response/write errors; never log the TV banner or key private material.
- If the Telnet result is uncertain, re-check SSH in read-only mode instead of blindly repeating the write.
- Preserves v0.1.6 capture, Glasshouse MQTT events and Assist behavior.


## 0.1.6 — standalone one-click rooted LG onboarding

- One-button opt-in from HA Ingress without Glasshouse modification.
- Checks own SSH authorization first.
- When rooted TV already exposes local unauthenticated root Telnet, uses it once to append only SHWM public key.
- Never enables Telnet, guesses passwords, deletes other keys, or alters Glasshouse/MQTT.
- Verifies actual SSH access after key install; reports failures without claiming success.
- Previous token-based Glasshouse method remains available.
- Root Telnet is insecure: user should close it after pairing.


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
