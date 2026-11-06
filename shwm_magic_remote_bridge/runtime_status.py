"""In-memory, admin-only voice bridge session diagnostics for SHWM v2 beta.

No audio, transcription, user commands, tokens, SSH keys, or identifiers are
recorded here. No network calls; snapshots are shared within one event loop.
"""
from __future__ import annotations

import math
import time

ALLOWED_TIMINGS = (
    "event_to_mic_seconds", "assist_ready_seconds", "tv_mic_ready_seconds",
    "audio_captured_seconds", "capture_cleanup_seconds",
    "assist_after_audio_seconds", "total_seconds"
)
VALID_OUTCOMES = {
    "OK", "NO_SPEECH", "STT_UNVERIFIED", "INTENT_UNVERIFIED",
    "INTENT_ERROR", "AI_ROUTER_UNAVAILABLE", "AUDIO_ONLY_OK", "ASSIST_ERROR",
    "TV_AUDIO_ERROR", "TIMEOUT", "CANCELLED", "INTERNAL_ERROR"
}
VALID_PHASES = {
    "STARTING", "WAITING_HA", "READY", "WAITING_MANUAL_MIC",
    "ASSIST_CONNECT", "MIC_STARTING", "WAITING_ASSIST", "OFFLINE"
}


class BridgeStatus:
    def __init__(self, *, version="2.0.0", clock=None):
        self.clock = clock or time.monotonic
        self.version = version
        self.boot_at = self.clock()
        self.ready = False
        self.active = False
        self.phase = "STARTING"
        self.sessions = 0
        self.last_result = "NONE"
        self.last_timings = {}
        self.history = []
        self.last_completed_uptime_seconds = None

    def set_ready(self, ready):
        self.ready = bool(ready)
        if not self.active:
            self.phase = "READY" if ready else "WAITING_HA"

    def begin(self, *, manual=False):
        if self.active:
            return False
        self.active = True
        self.sessions += 1
        self.phase = "WAITING_MANUAL_MIC" if manual else "ASSIST_CONNECT"
        return True

    def set_phase(self, phase):
        if phase not in VALID_PHASES:
            raise ValueError("invalid status phase")
        if self.active:
            self.phase = phase

    def complete(self, result, timings=None):
        if result not in VALID_OUTCOMES:
            result = "INTERNAL_ERROR"
        clean = {}
        for k in ALLOWED_TIMINGS:
            v = (timings or {}).get(k)
            if type(v) in (float, int) and math.isfinite(v) and 0 <= v <= 180:
                clean[k] = round(float(v), 3)
        self.last_timings = clean
        self.last_result = result
        self.active = False
        self.phase = "READY" if self.ready else "WAITING_HA"
        self.last_completed_uptime_seconds = round(max(0, self.clock() - self.boot_at), 1)
        self.history.append({
            "session": self.sessions,
            "result": result,
            "timings": clean
        })
        self.history = self.history[-5:]

    def snapshot(self):
        # Return new lists/dicts so callers cannot mutate live state.
        return {
            "version": self.version,
            "ready": self.ready,
            "active": self.active,
            "phase": self.phase,
            "sessions": self.sessions,
            "last_result": self.last_result,
            "last_timings": dict(self.last_timings),
            "last_completed_uptime_seconds": self.last_completed_uptime_seconds,
            "uptime_seconds": round(max(0, self.clock() - self.boot_at), 1),
            "history": [
                {"session": h["session"], "result": h["result"],
                 "timings": dict(h["timings"])}
                for h in self.history
            ]
        }
