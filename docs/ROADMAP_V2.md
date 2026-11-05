# SHWM Magic Remote Assist Bridge — v2.0 development gates

Status: **development roadmap**; not a claim that v2.0 is released.

## Verified reference hardware and evidence

- LG 65NANO863PA, rooted webOS 6.5.3, original Magic Remote.
- Home Assistant OS app v0.1.7: public-key onboarding and SSH check verified;
  Glasshouse MIC event triggered audio capture; PCM16 was sent to Assist;
  Polish STT succeeded; the owner independently confirmed commands work.
- One observed fixed-window session: 9.33s total, ~8s recording.
- One observed VAD session: 5.86s total, 2.10s captured audio, but
  STT only returned the tail of the phrase. Approx. 1.77s elapsed between
  MIC_DETECTED and TV_MIC_READY, during which early words can be missed.
- Other TV hardware and newer speed optimizations: not yet validated.

## Phase 1: measure, do not guess — v0.1.9

- CAPTURE_TIMING breaks down SSH/voiceinput startup, captured audio and
  post-VAD cleanup. SESSION_TIMING adds Assist setup, Assist response and
  total latency.
- Empty STT results are NO_SPEECH rather than misleading generic errors.
- Keep logs without raw microphone audio, saved WAVs, or private credentials.
- Ask the tester to send logs for one event *after waking the remote* and
  another event *after five minutes of idle*. In the latter case, if the
  initial MIC does not produce MIC_DETECTED, the missing event is upstream
  of this add-on.

## Phase 2: latency and wake behavior

- Compare event-to-voiceinput time on warm/cold SSH connection and verify
  whether ControlMaster actually reduces it on the physical TV.
- Verify that TV_STOP_REQUESTED after VAD does not leave Luna subscriptions,
  stuck audio sockets or zombie SSH subprocesses.
- Treat Magic Remote Bluetooth power saving separately from network SSH
  setup: the add-on currently has no proven safe way to wake a sleeping
  Bluetooth Magic Remote.
- Do not alter Glasshouse or claim the ability to wake a powered-off TV
  without a real hardware test.

## Phase 3: capture quality

- Compare VAD OFF with ON (250 RMS / 1500ms quiet) under normal room noise.
- Log and troubleshoot clipped first words. No automatic retries once any
  audio or intent has been submitted; duplicates can repeat a home action.
- Explicit indication of TV_MIC_READY on the Home Assistant side might be
  added after confirming an existing supported UX channel.
- Ensure all mute/standby tests use non-mutating STT-only mode.

## Phase 4: compatibility and safety

- First-time pairing must never require changes to Glasshouse. Current
  one-click key setup is conditional on a *previously enabled*, owner
  accessible rooted-TV admin shell (or existing authorized SSH).
- Never auto-enable Telnet, use shared/default passwords, bypass host-key
  checks, edit TV system partitions, or expose secrets in UI.
- Validate backup/restore and document safe removal of SHWM's own key.
- Validate another rooted LG model/webOS version before describing support
  as broad rather than experimental.

## Release gate for v2.0

- Repeated full-phrase STT success with and without VAD, before enabling
  commands for selected harmless HA devices.
- At least three press-to-completion runs after idle and three from an
  awake remote, with timings reported as observations, not marketing.
- Test after TV restart and HA restart, including SSH ControlMaster
  cleanup and recovery.
- Confirm no duplicate home actions and no credential leakage.
- Update installation docs/screenshots, preserve rollback path to a
  known-working add-on version, and then decide on release.

## Blog publication gate

WordPress draft #988 must remain unpublished until v2.0 is actually
released and confirmed, real screenshots replace placeholders, and
Pre-Publication Guardian reports no blockers. A separate article can
explain rooted webOS prerequisites and Glasshouse MQTT setup, linking to
the bridge article without implying that any LG can be rooted.
