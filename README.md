# SHWM Magic Remote Assist Bridge

Experimental **Home Assistant OS app (add-on)** which connects a rooted LG webOS Magic Remote microphone to a Home Assistant Assist pipeline.

> **v0.1.4 experimental** — microphone capture and Polish STT worked with an LG 65NANO863PA and a PowerShell bridge. The HAOS app has not yet undergone on-device integration testing.

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
