# SHWM Magic Remote Assist Bridge

Experimental **Home Assistant OS app (add-on)** which connects a rooted LG webOS Magic Remote microphone to a Home Assistant Assist pipeline.

> **v0.1.8 experimental** — microphone capture and Polish STT worked with an LG 65NANO863PA and a PowerShell bridge. The HAOS app has not yet undergone on-device integration testing.

## Architecture

Magic Remote MIC → Glasshouse event entity → SHWM app → LG voiceinput over SSH → HA Assist (STT; optionally execute intent).

Requirements: rooted LG with SSH; Glasshouse exposing a voice button event; working `com.webos.service.voiceinput/startStreaming` and `/tmp/voiceinput_remote1.soc`; Home Assistant OS with Assist configured.

## Install

This is a **Home Assistant App**, not a Marketplace/HACS integration. In Home Assistant, open **Settings → Apps → Install app → ⋮ → Repositories**, add the URL below, refresh, select and install the app:

https://github.com/smarthomewithme/shwm-magic-remote-assist-bridge

Set your TV IP and Glasshouse event entity before starting. The app generates a dedicated SSH key; add only its *public* key to the TV's authorized_keys (append, do not replace). See [DOCS](shwm_magic_remote_bridge/DOCS.md) for details.

Default `execute_commands: false` means STT only. No automatic voice activation and no WAV recordings. One TV per app instance. Responses are logged only if enabled. No system partition changes on LG.

## Compatibility and safety

LG models beyond the tested 65NANO863PA / webOS 6.5.3 are unverified. The add-on uses only the private LAN TV IP and verifies SSH host keys (trust on first use). Backup HA before the first install. Do not share private keys or tokens.

## Development

Run `python -m pip install aiohttp==3.12.15 pyyaml`, then `python -m unittest discover -s tests -v`.

License to be chosen. This is a prototype, not a published stable release.

## v0.1.1 — test HA without Glasshouse MQTT

Optional `manual_test_enabled: true` subscribes to `shwm_magic_remote_test`. Fire the event from Developer Tools → Events on the test HA, then hold the Magic Remote MIC. The manual path is always STT-only. The production Glasshouse integration is not changed.

## v0.1.2 — standalone microphone check without STT

On a separate test HA, enable `manual_test_enabled: true` and `manual_audio_only: true` and fire `shwm_magic_remote_test`. The app opens LG voiceinput through SSH and reports PCM byte count, duration, peak and RMS. It does not call STT or Assist. This preserves the normal Glasshouse flow and does not change MQTT configuration.

## v0.1.3 — experimental speech auto-stop

Optional `vad_enabled: true` activates a simple PCM RMS detector with `vad_rms_threshold: 250` and `vad_silence_ms: 1500`. Defaults remain `vad_enabled: false` with the existing fixed 8-second recording. Do not enable on a production HA until independently tested. An AUDIO-ONLY test can be used to probe microphone capture with the TV screen off; regular standby behavior is not verified.

## v0.1.4 — reliability and diagnostics

Keeps Glasshouse as the keypress provider, no code copied from Glasshouse. Provides clearer stage logs and limited pre-audio retry on temporary microphone unavailability, but never repeats an Assist command or an already started stream. Safety defaults: no command execution and VAD off. The first complete STT and Glasshouse integration test on HAOS is still pending.

## v0.1.5 — simpler SSH onboarding

Open the add-on web UI in HA. Enter a Glasshouse administrative token one time to install the add-on's public SSH key via authenticated Glasshouse API. Requires Glasshouse with SSH key endpoint and a configured token; this is a deliberate user-authorized operation, never a bypass. The token is not stored. Note that HTTP on a normal local Glasshouse connection is not encrypted. The existing bridge logic remains unchanged.


## v0.1.6 — one-click onboarding without changing Glasshouse

The administrator-only add-on panel now offers "Sparuj automatycznie z LG".
It first checks whether its own persistent SSH key is already authorized.
Only after an explicit click, if SSH is not authorized, it may use an already
running unauthenticated root Telnet on a rooted LG on the trusted LAN to
append exactly its validated public SSH key; it then confirms new SSH access.
It never starts Telnet, guesses a password, retrieves Glasshouse secrets,
or overwrites existing keys. This is conditional: if root Telnet is disabled
and no SSH authorization exists, a secure owner-driven first pairing step
is still required, such as the previous authenticated Glasshouse method.
Root Telnet is insecure; close it after pairing. Real device testing pending.


## v0.1.7 — read-only SSH verification and safer Telnet diagnosis

If a previous one-click attempt returned TELNET_NO_CONFIRMATION, use the
new **Sprawdź samo SSH** button *before* starting another pairing attempt.
This new action only checks the add-on's existing SSH authorization.
The one-click bootstrap now probes the existing Telnet shell and confirms
root UID with a short read-only command before an append-only key update;
it no longer assumes Python is available in the Telnet PATH. A missing
shell, root access or clear result produces a distinct error code. No
automatic retries that could duplicate or overwrite keys. Glasshouse is
unchanged. On-device compatibility still must be verified.


## v0.1.8 — faster speech interaction, no changes to Glasshouse

Optional SSH warmup reuses an add-on-private OpenSSH control connection for
up to 180 seconds of inactivity (ssh_warmup_enabled: true by default).
This can reduce SSH startup delay but will not recover speech that starts
before the TV voiceinput service is ready. To prevent an extra ~2-second
delay after VAD decides speech has ended, the HA bridge sends a cooperative
stop signal over the existing SSH stdin pipe, giving the TV helper up to
0.9 seconds to clean up the Luna voiceinput subprocess gracefully. A bounded
terminate/kill fallback remains. Disable warmup if long-lived SSH causes
TV standby problems. No persistent audio, modifications to Glasshouse,
remote buttons, TV firmware, or automatic home-command execution.
