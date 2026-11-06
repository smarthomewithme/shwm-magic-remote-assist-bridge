# Changelog

## 2.1.2 — native LG toast invocation verified by owner

- The LG accepted `luna-send -n 1 -f luna://com.webos.notification/createToast '{"message":"Test Home Assistant"}'` with `returnValue: true` when run locally; v2.1.1 used an unverified `-a webosbrew` caller and `sourceId`.
- Match the verified invocation, using fixed short Polish messages and no caller or source override; keep the same authorized SSH identity.
- Read structured Luna JSON from stdout or stderr; when none is returned, log only SSH exit code and byte counts to support diagnosis, never raw TV output.
- Single bounded toast attempt only; no retries, changes to TV files, Glasshouse, microphone, STT, Assist commands or existing configuration.
- LG physical display via the add-on still requires one explicit `Wyświetl test na TV` check after upgrading; an accepted Luna response is not proof that the notification was visibly rendered.


## 2.1.1 — diagnostic error codes for LG toast failures

- Improve the existing TV notification test: return a specific, allowlisted diagnostic reason instead of hiding every failure behind NOT_CONFIRMED.
- Distinguish SSH connectivity, missing luna-send, missing/unparseable JSON response, unknown source, rejected caller permissions, invalid source ID, and other structured service errors.
- Accept a real structured Luna JSON response even if luna-send includes harmless text before the JSON; never infer success from words in an error message.
- Do not log or display raw LG stderr, SSH output or full service errors, which could contain sensitive details.
- Same existing add-on slug, SSH key, Glasshouse event entity, Assist, MIC and VAD configuration; no changes to LG filesystem, app identities or notification permissions.
- Does not claim to fix a TV-side permission failure. Retest "Wyświetl test na TV" once and inspect the new reason code before choosing the next action.


## 2.1.0 — optional LG webOS on-screen toast feedback

- Add optional `tv_toasts_enabled: false` (safe default), an on-screen assistant feedback feature for owner-rooted webOS TVs. Existing installs stay silent until the owner turns it on.
- Uses the already authorized SSH key to call the native LG `com.webos.notification/createToast` service. Does not change Glasshouse, system partitions, webOS startup files, or require installing another app.
- Fixed, short Polish messages for LISTENING, accepted action, question answered, STT-only completion, no speech, AI provider unavailable, and general error. No model-provided text, user utterances or secrets are sent to TV notifications.
- Toast requests run as separately bounded tasks. An unavailable notification service never blocks, aborts or retries microphone capture/Assist actions.
- Admin-only Web UI includes a `Wyświetl test na TV` button, confirming whether the TV accepted a request before enabling a real voice command.
- Native toasts are transient system UI (~5 seconds), not a persistent overlay or customizable widget; on actual LG firmware this must be verified in a physical TV test.
- Preserve add-on slug, key storage, auto-boot, VAD, SSH multiplexing, and existing voice bridge behavior.


## 2.0.1 — isolate slow Assist replies without changing working LG capture

- Analyze measured per-session latency. When Assist takes 5+ seconds after audio, emit `STATUS LATENCY_WARNING stage=ASSIST_AFTER_AUDIO` and flag `ASSIST_RESPONSE` in the admin panel. Other hints highlight slow TV MIC startup or capture cleanup.
- Show the five most recent session totals *and* their Assist wait times, plus count of MIC presses ignored while a previous command was processing.
- Separate `ASSIST_QUERY_ANSWER` from an `ASSIST_INTENT_SUCCESS response_type=action_done`: answering whether the television is on is not a device action.
- Preserve the `AI_ROUTER_UNAVAILABLE` classification introduced in v2.0.0, with no automatic intent retries.
- Preserve all Home Assistant configuration, add-on slug, persistent SSH key, voiceinput, VAD, Glasshouse, MQTT, and no additional permissions.
- This update improves diagnosis, not the underlying AI provider speed. Run comparisons on a live LG before considering VAD timing or conversation-agent changes.


## 2.0.0 — in-place update of the existing SHWM Home Assistant app

- Keep the exact original Home Assistant add-on slug `shwm_magic_remote_bridge` and its persistent /data SSH key. No new add-on, second pairing, or duplicate microphone event subscriber.
- Add administrator-only, read-only voice session status to the existing web UI: HA subscription status, active phase, five latest outcomes and stage-by-stage timings. Status records contain no PCM, transcripts, passwords or tokens.
- FIX: HA Assist can send `intent-end` with a spoken provider-error response. Such a response is NOT proof of a performed home action. Flag known Cloudflare 503 cooldown / "Fallback providers are disabled ... SHWM_ROUTER_TOKEN" as `AI_ROUTER_UNAVAILABLE`, not `ASSIST_INTENT_SUCCESS`.
- Also differentiate structured intent errors (`INTENT_ERROR`), missing/ambiguous results (`INTENT_UNVERIFIED`) and valid `action_done` / `query_answer` replies.
- Log `ASSIST_INTENT_FAILED` without repeating the full provider message. Never retry a potentially already-executed home command automatically.
- This only fixes classification and diagnostics. It DOES NOT configure SHWM_ROUTER_TOKEN or repair the upstream AI provider; those settings belong to the separate Home Assistant AI router.
- Existing Glasshouse/MQTT, LG audio capture, VAD, SSH warm-up, permissions and key-pairing behavior remain unchanged.
- Version is 2.0.0, but the addon still uses experimental stage until repeated physical LG compatibility/voice tests have passed.


## 0.1.9 — structured latency diagnostics and idle-MIC result

- Log CAPTURE_TIMING split into TV SSH/voiceinput start, PCM duration and cleanup after VAD.
- Log SESSION_TIMING split into Assist/STT setup, TV MIC ready, audio duration, cleanup, STT/intent completion and total.
- Classify only HA STT code stt-no-text-recognized as NO_SPEECH, not a generic TV/SSH failure; other pipeline errors are still failures.
- Keep microphone, key pairing, Glasshouse, MQTT and actions logic unchanged. Diagnostic values are local timings, not benchmarks.
- Keep execute_commands and VAD safety defaults unchanged.
- Test before deciding how to reduce latency or improve the remote wake-up experience.


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
