"""Best-effort LG webOS toast feedback, with safe error classification.

Uses only predefined Polish messages, existing authenticated SSH, and a
bounded Luna call. No credentials, voice transcripts, or raw device response
are persisted or returned to the browser. No TV filesystem changes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shlex

LOG = logging.getLogger("shwm_magic_remote")

TOAST_MESSAGES = {
    "TEST": "SHWM Voice: test powiadomień",
    "LISTENING": "SHWM Voice: słucham...",
    "PROCESSING": "SHWM Voice: przetwarzam...",
    "DONE": "SHWM Voice: polecenie przyjęte",
    "DECLINED": "SHWM Voice: brak potwierdzenia wykonania",
    "ANSWER": "SHWM Voice: odpowiedź gotowa",
    "STT_OK": "SHWM Voice: rozpoznano mowę",
    "NO_SPEECH": "SHWM Voice: nie rozpoznano mowy",
    "AI_UNAVAILABLE": "SHWM Voice: asystent AI niedostępny",
    "ERROR": "SHWM Voice: nie udało się",
}
TV_TOAST_URI = "luna://com.webos.notification/createToast"


def tv_toast_command(kind):
    """Use the minimal native luna-send invocation verified on LG webOS."""
    if kind not in TOAST_MESSAGES:
        raise ValueError("Unknown TV toast kind")
    payload = json.dumps(
        {"message": TOAST_MESSAGES[kind]},
        ensure_ascii=True, separators=(",", ":")
    )
    # Do not force an app caller/sourceId: the user's LG confirmed success
    # with the native, caller-neutral invocation below.
    return ("luna-send -n 1 -f " + TV_TOAST_URI +
            " " + shlex.quote(payload))


def _luna_reply(stdout):
    """Find a structured Luna reply, even if luna-send adds harmless chatter.

    No regex guessing of success from output strings. No stdout/stderr is
    written to logs or exposed to the ingress UI.
    """
    data = stdout[:8192].decode("utf-8", "replace")
    decoder = json.JSONDecoder()
    for i, char in enumerate(data):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(data[i:])
        except ValueError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("returnValue"), bool):
            return parsed
    return None


def _service_reason(reply):
    """Allowlist-only classification; never expose the TV's raw error text."""
    value = reply.get("errorText")
    msg = value.lower() if isinstance(value, str) else ""
    if ("permission" in msg and ("denied" in msg or "not" in msg)
            or "denied method call" in msg or "not authorized" in msg):
        return "SERVICE_PERMISSION_DENIED"
    if "unknown source" in msg:
        return "SERVICE_UNKNOWN_SOURCE"
    if "invalid source" in msg:
        return "SERVICE_INVALID_SOURCE"
    if ("unknown method" in msg or "method not found" in msg
            or "no such method" in msg):
        return "SERVICE_METHOD_UNAVAILABLE"
    if "message is not parsed" in msg or "invalid" in msg and "json" in msg:
        return "SERVICE_INVALID_PAYLOAD"
    code = reply.get("errorCode")
    # Structured numeric code is not a secret and helps identify the failure.
    if type(code) is int and 0 <= code <= 99999:
        return "SERVICE_ERROR_" + str(code)
    return "SERVICE_REJECTED"


def _transport_reason(stderr):
    """Classify common SSH errors without logging banners or raw stderr."""
    msg = stderr[:4096].decode("utf-8", "replace").lower()
    if "permission denied" in msg or "publickey" in msg:
        return "SSH_AUTH_FAILED"
    if "host key verification failed" in msg or "host identification has changed" in msg:
        return "SSH_HOST_KEY_ERROR"
    if ("connection refused" in msg or "connection timed out" in msg
            or "no route to host" in msg):
        return "TV_SSH_UNREACHABLE"
    if "luna-send: not found" in msg or "luna-send: command not found" in msg:
        return "LUNA_SEND_NOT_FOUND"
    return "SSH_OR_LUNA_FAILED"


class SessionToast:
    """Generation-scoped, non-blocking TV notifications for one MIC session."""

    def __init__(self, notifier, session_id):
        self.notifier = notifier
        self.session_id = session_id
        self._processing_task = None

    def emit(self, kind):
        if kind != "PROCESSING" and self._processing_task is not None:
            self._processing_task.cancel()
            self._processing_task = None
        self.notifier.emit(kind, session_id=self.session_id)

    def processing_after(self, delay=1.5):
        """Only show processing when Assist has not already finished."""
        if not self.notifier.enabled or self.session_id != self.notifier.session_id:
            return
        if self._processing_task is not None:
            self._processing_task.cancel()

        async def delayed():
            await asyncio.sleep(delay)
            self.notifier.emit("PROCESSING", session_id=self.session_id)

        self._processing_task = asyncio.create_task(delayed())
        self.notifier._track(self._processing_task)


class TvToastNotifier:
    def __init__(self, opts, ssh_args):
        self.opts = opts
        self.ssh_args = ssh_args
        self.enabled = bool(opts.get("tv_toasts_enabled", False))
        self.pending = set()
        self.session_id = 0
        self._send_lock = asyncio.Lock()

    def _track(self, task):
        self.pending.add(task)
        task.add_done_callback(self.pending.discard)

    def new_session(self):
        """Drop stale queued/in-flight notices before starting another MIC."""
        self.session_id += 1
        for task in tuple(self.pending):
            task.cancel()
        return SessionToast(self, self.session_id)

    async def send_diagnostic(self, kind):
        """Return (accepted_by_Luna, safe_reason), no user-supplied content."""
        if not self.enabled:
            return False, "FEATURE_DISABLED"
        command = tv_toast_command(kind)
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.ssh_args(self.opts), command,
                # luna-send on LG can exit silently if SSH closes stdin
                # before the asynchronous Luna reply arrives. Keep it open.
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                # Do NOT use communicate() here: it closes stdin immediately.
                # The fixed toast JSON response is tiny, below pipe capacity.
                await asyncio.wait_for(proc.wait(), timeout=4.0)
                stdout, stderr = await proc.communicate()
            except asyncio.TimeoutError:
                if proc.returncode is None:
                    proc.kill()
                await proc.communicate()
                reason = "TIMEOUT"
                LOG.info("STATUS TV_TOAST_SKIPPED reason=%s kind=%s", reason, kind)
                return False, reason
            # Depending on webOS/luna-send, a structured response can arrive
            # on either channel. Require an actual JSON returnValue boolean.
            reply = _luna_reply(stdout) or _luna_reply(stderr)
            if proc.returncode != 0:
                reason = (_service_reason(reply)
                          if reply is not None and reply.get("returnValue") is False
                          else _transport_reason(stderr))
                LOG.info("STATUS TV_TOAST_SKIPPED reason=%s kind=%s", reason, kind)
                return False, reason
            if reply is None:
                reason = "NO_VALID_LUNA_RESPONSE"
                # Only counts and exit status: never log TV/SSH raw output.
                LOG.info("STATUS TV_TOAST_DIAGNOSTIC kind=%s ssh_exit=%d stdout_bytes=%d stderr_bytes=%d",
                         kind, proc.returncode, len(stdout), len(stderr))
                LOG.info("STATUS TV_TOAST_SKIPPED reason=%s kind=%s", reason, kind)
                return False, reason
            if reply["returnValue"] is not True:
                reason = _service_reason(reply)
                LOG.info("STATUS TV_TOAST_SKIPPED reason=%s kind=%s", reason, kind)
                return False, reason
            LOG.info("STATUS TV_TOAST_SENT kind=%s", kind)
            return True, "ACCEPTED"
        except OSError:
            LOG.info("STATUS TV_TOAST_SKIPPED reason=SSH_UNAVAILABLE kind=%s", kind)
            return False, "SSH_UNAVAILABLE"
        except asyncio.CancelledError:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.communicate()
            raise

    async def send(self, kind):
        """Compatibility: the voice path needs only best-effort boolean result."""
        accepted, _ = await self.send_diagnostic(kind)
        return accepted

    def emit(self, kind, session_id=None):
        """Serialize per-TV toasts; never send a stale session's queued notice.

        Sending is best-effort and never blocks microphone or Home Assistant.
        Session-agnostic emit() is retained for backwards compatibility.
        """
        if not self.enabled:
            return
        if kind not in TOAST_MESSAGES:
            raise ValueError("Unknown TV toast kind")
        if session_id is not None and session_id != self.session_id:
            return

        async def send_when_current():
            async with self._send_lock:
                if session_id is not None and session_id != self.session_id:
                    return
                await self.send(kind)

        self._track(asyncio.create_task(send_when_current()))
