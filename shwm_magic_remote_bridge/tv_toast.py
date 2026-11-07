"""Best-effort LG webOS toast feedback, with safe error classification.

Uses only predefined Polish messages, existing authenticated SSH, and a
bounded Luna call. No credentials, voice transcripts, or raw device response
are persisted or returned to the browser. Only optional PNG icons are written to TV /tmp (never system partitions).
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import shlex
import unicodedata

from tv_icons import KINDS, icon_png

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
TV_ICON_DIR = "/tmp/shwm_magic_remote_icons"
TV_OVERLAY_APP_ID = "com.smarthomewithme.voiceoverlay"
TV_OVERLAY_URI = "luna://com.webos.applicationManager/launch"
DYNAMIC_PREFIX = {
    "HEARD": "Usłyszałem: ",
    "ACTION_DETAIL": "Assist: ",
    "ANSWER_DETAIL": "Odpowiedź: ",
}
ICON_KIND = {
    "TEST": "listen", "LISTENING": "listen", "HEARD": "listen",
    "PROCESSING": "processing",
    "DONE": "done", "ANSWER": "done", "ANSWER_DETAIL": "done",
    "STT_OK": "done", "ACTION_DETAIL": "done",
    "DECLINED": "error", "NO_SPEECH": "error",
    "AI_UNAVAILABLE": "error", "ERROR": "error",
}


def toast_message(kind, text=None):
    """Keep every on-screen string <=60 chars; no terminal/RTL controls."""
    if kind in TOAST_MESSAGES and text is None:
        return TOAST_MESSAGES[kind]
    if kind not in DYNAMIC_PREFIX or not isinstance(text, str):
        raise ValueError("Unknown TV toast kind or unexpected text")
    cleaned = unicodedata.normalize("NFC", text)
    cleaned = "".join(
        " " if unicodedata.category(ch).startswith("C") else ch for ch in cleaned
    )
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        raise ValueError("Empty TV toast text")
    prefix = DYNAMIC_PREFIX[kind]
    limit = 60 - len(prefix)
    if len(cleaned) > limit:
        cleaned = cleaned[:limit - 1].rstrip() + "…"
    return prefix + cleaned


def tv_toast_command(kind, text=None, icon_url=None):
    """Caller-neutral Luna invocation. User text is JSON + shell quoted."""
    payload_obj = {"message": toast_message(kind, text)}
    if icon_url is not None:
        if icon_url not in {
            "file://" + TV_ICON_DIR + "/" + name + ".png" for name in KINDS
        }:
            raise ValueError("Unapproved TV icon path")
        payload_obj["iconUrl"] = icon_url
        # webOS 6.x standard toasts have a zero-width icon slot.
        # "light" renders an icon in the top-right toast on LG C1/6.5.x.
        # If icons are not enabled/prepared, keep proven standard layout.
        payload_obj["type"] = "light"
    payload = json.dumps(
        payload_obj,
        ensure_ascii=True, separators=(",", ":")
    )
    # Do not force an app caller/sourceId: the user's LG confirmed success
    # with the native, caller-neutral invocation below.
    return ("luna-send -n 1 -f " + TV_TOAST_URI +
            " " + shlex.quote(payload))


def tv_overlay_command(kind, text=None, icons=True):
    """Launch optional transparent webOS overlay with display-safe params.

    No custom shell, URL, or app ID from user input; app uses textContent.
    """
    message = toast_message(kind, text)
    icon = ICON_KIND.get(kind)
    if icon is None:
        raise ValueError("Unrecognized overlay status")
    payload = json.dumps({
        "id": TV_OVERLAY_APP_ID,
        "params": {
            "message": message,
            "kind": icon,
            "icons": bool(icons),
        },
    }, ensure_ascii=True, separators=(",", ":"))
    return "luna-send -n 1 -f " + TV_OVERLAY_URI + " " + shlex.quote(payload)


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

    def emit_detail(self, kind, value):
        """Send opted-in detail; a terminal result cancels pending PROCESSING."""
        if kind in ("ACTION_DETAIL", "ANSWER_DETAIL") and self._processing_task is not None:
            self._processing_task.cancel()
            self._processing_task = None
        if isinstance(value, str) and value.strip():
            self.notifier.emit(kind, session_id=self.session_id, text=value)

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
        self.icons_enabled = self.enabled and bool(opts.get("tv_toast_icons_enabled", False))
        self.overlay_enabled = self.enabled and bool(opts.get("tv_overlay_enabled", False))
        self.icons_ready = False
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

    async def prepare_icons(self):
        """Write only four tiny PNGs under TV /tmp. Failure => text-only toasts."""
        if not self.icons_enabled or self.overlay_enabled:
            return
        commands = [
            "set -eu", "umask 022",
            "test ! -L " + TV_ICON_DIR,
            "mkdir -p " + TV_ICON_DIR,
            "chmod 0755 " + TV_ICON_DIR,
        ]
        for kind in KINDS:
            encoded = base64.b64encode(icon_png(kind)).decode("ascii")
            commands.append("test ! -L " + TV_ICON_DIR + "/" + kind + ".png")
            commands.append(
                "printf %s " + shlex.quote(encoded) + " | base64 -d > "
                + TV_ICON_DIR + "/" + kind + ".png"
            )
            commands.append("chmod 0644 " + TV_ICON_DIR + "/" + kind + ".png")
        commands.append("test -s " + TV_ICON_DIR + "/done.png")
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.ssh_args(self.opts), "; ".join(commands),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                await asyncio.wait_for(proc.communicate(), timeout=12.0)
            except asyncio.TimeoutError:
                if proc.returncode is None:
                    proc.kill()
                await proc.communicate()
                LOG.info("STATUS TV_ICONS_SKIPPED reason=TIMEOUT")
                return
            if proc.returncode != 0:
                LOG.info("STATUS TV_ICONS_SKIPPED reason=TV_COMMAND_FAILED")
                return
            self.icons_ready = True
            LOG.info("STATUS TV_ICONS_READY count=%d location=TV_TMP", len(KINDS))
        except OSError:
            LOG.info("STATUS TV_ICONS_SKIPPED reason=SSH_UNAVAILABLE")
        except asyncio.CancelledError:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.communicate()
            raise

    async def send_diagnostic(self, kind, text=None):
        """Try the opt-in overlay; fall back to proven text-only native toast."""
        if not self.enabled:
            return False, "FEATURE_DISABLED"
        if self.overlay_enabled:
            accepted, reason = await self._send_luna(
                tv_overlay_command(kind, text, self.icons_enabled), kind,
                mode="overlay"
            )
            if accepted:
                return True, reason
            LOG.info("STATUS TV_OVERLAY_FALLBACK kind=%s reason=%s", kind, reason)
            return await self._send_luna(
                tv_toast_command(kind, text=text), kind, mode="native"
            )
        icon = (ICON_KIND.get(kind) if self.icons_ready else None)
        icon_url = ("file://" + TV_ICON_DIR + "/" + icon + ".png") if icon else None
        return await self._send_luna(
            tv_toast_command(kind, text=text, icon_url=icon_url),
            kind, mode="native", icon_url=icon_url
        )

    async def _send_luna(self, command, kind, *, mode, icon_url=None):
        """One bounded SSH/Luna request; no raw command output logged."""
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
                LOG.info("STATUS TV_%s_SKIPPED reason=%s kind=%s", "OVERLAY" if mode == "overlay" else "TOAST", reason, kind)
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
            if mode == "overlay":
                LOG.info("STATUS TV_OVERLAY_LAUNCH_ACCEPTED kind=%s", kind)
            else:
                LOG.info("STATUS TV_TOAST_SENT kind=%s icon=%s",
                         kind, "requested" if icon_url else "none")
            return True, "ACCEPTED"
        except OSError:
            LOG.info("STATUS TV_TOAST_SKIPPED reason=SSH_UNAVAILABLE kind=%s", kind)
            return False, "SSH_UNAVAILABLE"
        except asyncio.CancelledError:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.communicate()
            raise

    async def send(self, kind, text=None):
        """Compatibility with existing fixed-status, best-effort send()."""
        if text is None:
            accepted, _ = await self.send_diagnostic(kind)
        else:
            accepted, _ = await self.send_diagnostic(kind, text=text)
        return accepted

    def emit(self, kind, session_id=None, text=None):
        """Serialize per-TV toasts; never send a stale session's queued notice.

        Sending is best-effort and never blocks microphone or Home Assistant.
        Session-agnostic emit() is retained for backwards compatibility.
        """
        if not self.enabled:
            return
        # Validate kind/text before queuing anything on a real TV.
        toast_message(kind, text)
        if session_id is not None and session_id != self.session_id:
            return

        async def send_when_current():
            async with self._send_lock:
                if session_id is not None and session_id != self.session_id:
                    return
                if text is None:
                    await self.send(kind)
                else:
                    await self.send(kind, text=text)

        self._track(asyncio.create_task(send_when_current()))
