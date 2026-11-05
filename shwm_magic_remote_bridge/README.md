# SHWM Magic Remote Assist Bridge

Experimental HAOS app. Glasshouse provides the button event, LG webOS provides raw PCM through the voiceinput service, and this app streams it to Home Assistant Assist.

Read [DOCS.md](DOCS.md) before installation. **Commands are disabled by default.** No model or TTS runs on the television.

## v0.1.1 manual test

In a separate test HA, enable `manual_test_enabled: true`, configure its own Assist STT, then fire the `shwm_magic_remote_test` event in Developer Tools → Events. Hold MIC immediately after firing. The test does not require Glasshouse MQTT on that HA and will not execute home-automation commands.
