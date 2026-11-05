# SHWM Magic Remote Assist Bridge

Experimental **Home Assistant OS app (add-on)** which connects a rooted LG webOS Magic Remote microphone to a Home Assistant Assist pipeline.

> **v0.1.0 experimental** — microphone capture and Polish STT worked with an LG 65NANO863PA and a PowerShell bridge. The HAOS app has not yet undergone on-device integration testing.

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
