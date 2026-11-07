# Changelog

## 2.1.9 — read-only LG voiceinput state discovery with opt-in MIC OFF stop

- Glasshouse's `MIC_DETECTED` is a button-press trigger, not evidence of an active/off state.
- Observe existing `voiceinput/startStreaming` Luna output non-blockingly while capturing PCM. Only explicit `voice start`, `voice stop`, and `voice end` messages are logged, with no PCM storage or TV modifications.
- The experimental `mic_off_stop_enabled` option defaults to **false**; if OFF is truly emitted after START during capture, owners can opt in to finish early. Otherwise existing VAD and `record_seconds` remain unchanged. The hard time limit is preserved for safety, not removed.
- Physical LG validation is mandatory before using OFF mode; do not infer this from CI or ON alone. Existing 2.1.8 overlay, Glasshouse and Assist behavior stay unchanged.


## 2.1.8 — optional lower-right LG web app overlay (pilot)

- Native LG `createToast` places `standard` at bottom-center, `light` top-right, and `advanced` bottom-center. There is no documented native bottom-right position. No fake `position` parameter is sent.
- Add **disabled-by-default** `tv_overlay_enabled`. This launches a small, separate transparent webOS overlay app `com.smarthomewithme.voiceoverlay` with a bottom-right card and inline SVG icons, for fixed status or opted-in short STT/Assist details. The overlay's appinfo.json, HTML and icon are bundled under `tv_overlay/`.
- One-time TV app installation is manual via webOS Dev Manager / ares-install. No auto-install, TV rootfs modification, firmware hooks or background watcher.
- Launch failures fall back once to the verified standard native **text-only** notification, without retrying any Home Assistant command. An accepted Luna `launch` is not proof of actual display.
- Overlay attempts to relinquish key focus/input region immediately and closes after 4.4 s, but must be physically tested on the owner's TV before declaring stable. Disable the toggle to return to v2.1.7 native toasts.
- Microphone, Glasshouse event, VAD, SSH keys, commands and existing options remain unchanged.

## 2.1.7 — display icons using light webOS toasts

- Fix icon-only rendering: the default webOS 6.x `standard` toast draws a zero-width icon slot; when TV icon PNGs have been prepared, submit `type: "light"` along with `iconUrl` to use a toast layout with an icon.
- With icons off or unprepared, preserve the existing text-only default toast and its bottom-of-screen placement. All other code paths, including MIC, Glasshouse and Assist, are unchanged.
- The light layout appears at the upper-right rather than bottom-center on tested LG C1 (webOS 6.5.1); other devices require a physical-screen check. Do not infer success from Luna `returnValue:true` alone.
- Add regression assertions for both icon-light and text-only-default JSON payloads.

## 2.1.6 — optional TV icons, recognized speech, and Assist reply

- Add three independent opt-in settings: `tv_toast_icons_enabled`, `tv_toast_transcript_enabled`, and `tv_toast_assist_reply_enabled`. All default to false; `tv_toasts_enabled` remains the master switch.
- The recognised phrase may appear as a transient `Usłyszałem: ...` toast after `stt-end`. On a classified successful action/query, an optional `Assist: ...` / `Odpowiedź: ...` toast replaces generic DONE/ANSWER. Refused and provider-failed intents never receive a success toast.
- Dynamic strings are Unicode-normalized, stripped of control characters, restricted to 60 display characters, JSON-encoded then shell-quoted, and never written to diagnostics. Explicit opt-in required because they can reveal private speech on a shared TV.
- Generate four local PNG icons (80x80) and put them only in the rooted TV's temporary `/tmp/shwm_magic_remote_icons` via an authenticated, bounded SSH command. If transfer fails, preserve text-only toasts. No system partition writes or new TV apps.
- Existing MIC, VAD, Glasshouse, safe status ordering, SSH keys, Assistant commands, and no-retry rule remain unchanged.
- Test `TV_ICONS_READY`, Luna acceptance, and visible icons on the physical LG. Some webOS TV firmwares may ignore `iconUrl`; icons are optional and never evidence that actions occurred.

## 2.1.5 — session-safe LG feedback and honest Assist stage latency

- Correlate TV status notifications with each MIC session; serialize SSH/Luna sends and discard older queued/in-flight status work when a new session begins. A delayed DONE from an earlier request can no longer be scheduled over a later LISTENING toast.
- Show a fixed `PROCESSING` TV status only when waiting for Assist exceeds 1.5 seconds; suppress it if the intent finishes first. This never blocks the microphone or replays commands.
- Record the individual Home Assistant event timings `stt_after_audio_seconds`, `intent_after_stt_seconds`, and `pipeline_finish_seconds` when the corresponding events exist. Surface them in the admin status panel; unknown timings remain unavailable, never fabricated.
- These times isolate observed WebSocket pipeline stages, **not** separate AI provider inference from HA service execution. No audio/transcript retention or new connectivity permissions.
- Preserve Glasshouse MIC, SSH warm-up, VAD, Assist behavior, no retries, TV rootfs partitions, existing add-on slug and stored /data SSH key.
- CI + on-TV physical toast check required before calling this stable; `TV_TOAST_SENT` confirms Luna acceptance, not proof of a rendered notification.

## 2.1.4 — actionable VAD diagnostics and truthful action feedback

- New installs default to 1100 ms of post-speech silence rather than 1500 ms, saving up to 0.4 s when normal VAD termination works. Existing `/data/options.json` values are respected; set `vad_silence_ms: 1100` manually to trial the shorter pause. If phrases are cut, restore 1500 ms.
- Add privacy-safe `STATUS VAD_DIAGNOSTIC`: whether speech was confirmed, how much above-threshold audio occurred, the longest quiet window, and why no early stop happened. This does not store microphone PCM or change VAD threshold logic.
- A custom Assist agent may wrongly label a refusal as `response_type=action_done`. For explicit refusal phrases seen on the real LG (notably the denied garage gate command), classify `INTENT_DECLINED` and show a no-confirmation toast instead of `DONE`. No automatic retry of any intent.
- Maintain the working v2.1.3 LG toast SSH/stdin handling, Glasshouse, SSH warm-up, MIC and VAD stop mechanism.
- This is a candidate for on-device validation, not a guarantee of universal webOS stability. Test short commands, speech with natural pauses, no speech, and denied/accepted actions before marking stable.


## 2.1.3 — preserve SSH stdin until the LG Luna response

- Root cause of v2.1.2 `NO_VALID_LUNA_RESPONSE`: `ssh_exit=0 stdout_bytes=0 stderr_bytes=0` while direct interactive `luna-send` returned `returnValue:true`.
- The LG/webOS `luna-send` client can exit silently when remote stdin reaches EOF before an asynchronous service reply. Using `stdin=DEVNULL` and `proc.communicate()` caused that condition.
- For TV toast requests only, keep SSH stdin open using `PIPE`, wait up to four seconds for the remote process to exit, then collect its response. No change to microphone streaming (`-T`), SSH multiplexing, Glasshouse or Assist.
- No TV file changes, automatic retries, or false success classification. Added a real local child-process regression test that reproduces EOF-dependent silent exit.
- Test physically on LG after updating: `Wyświetl test na TV`, then verify an actual visible toast and `TV_TOAST_SENT` in logs.


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
