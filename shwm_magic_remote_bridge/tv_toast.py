"""Optional, bounded system-toast notifications on an owner-rooted LG webOS TV.

No Glasshouse changes, recordings, transcript, arbitrary text/commands or
privileged filesystem writes. Toasts are deliberately best-effort: failure
must never delay or change the Assist result.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shlex

LOG = logging.getLogger("shwm_magic_remote")

# Only static status messages; no user speech or model-generated text.
TOAST_MESSAGES = {
    "TEST": "SHWM Voice: powiadomienia dzialaja",
    "LISTENING": "SHWM Voice: Slucham...",
    "DONE": "SHWM Voice: polecenie przyjete",
    "ANSWER": "SHWM Voice: odpowiedz gotowa",
    "STT_OK": "SHWM Voice: rozpoznano mowe",
    "NO_SPEECH": "SHWM Voice: nie rozpoznano mowy",
    "AI_UNAVAILABLE": "SHWM Voice: asystent AI niedostepny",
    "ERROR": "SHWM Voice: polecenie niepowodzenie",
}

TV_TOAST_URI = "luna://com.webos.notification/createToast"


def tv_toast_command(kind):
    """Build exactly one shell-quoted, fixed payload for the LG luna-send."""
    if kind not in TOAST_MESSAGES:
        raise ValueError("Unknown TV toast kind")
    payload = json.dumps({
        "sourceId": "webosbrew",
        "message": TOAST_MESSAGES[kind]
    }, ensure_ascii=True, separators=(",", ":"))
    return ("luna-send -a webosbrew -f -n 1 " + TV_TOAST_URI +
            " " + shlex.quote(payload))


class TvToastNotifier:
    def __init__(self, opts, ssh_args):
        self.opts = opts
        self.ssh_args = ssh_args
        self.enabled = bool(opts.get("tv_toasts_enabled", False))
        self.pending = set()

    async def send(self, kind):
        """Return True only if the TV's Luna service confirms its request."""
        if not self.enabled:
            return False
        command = tv_toast_command(kind)
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.ssh_args(self.opts), command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                output, _ = await asyncio.wait_for(proc.communicate(), timeout=4.0)
            except asyncio.TimeoutError:
                if proc.returncode is None:
                    proc.kill()
                await proc.communicate()
                LOG.info("STATUS TV_TOAST_SKIPPED reason=TIMEOUT kind=%s", kind)
                return False
            if proc.returncode != 0:
                LOG.info("STATUS TV_TOAST_SKIPPED reason=SSH_OR_LUNA_FAILED kind=%s", kind)
                return False
            try:
                data = json.loads(output.decode("utf-8", "replace").strip())
            except (ValueError, UnicodeError):
                LOG.info("STATUS TV_TOAST_SKIPPED reason=INVALID_RESPONSE kind=%s", kind)
                return False
            if not isinstance(data, dict) or data.get("returnValue") is not True:
                LOG.info("STATUS TV_TOAST_SKIPPED reason=NOT_CONFIRMED kind=%s", kind)
                return False
            LOG.info("STATUS TV_TOAST_SENT kind=%s", kind)
            return True
        except OSError:
            LOG.info("STATUS TV_TOAST_SKIPPED reason=SSH_UNAVAILABLE kind=%s", kind)
            return False
        except asyncio.CancelledError:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.communicate()
            raise

    def emit(self, kind):
        """Non-blocking status request. Never await from MIC/PCM/Assist path."""
        if not self.enabled:
            return
        if kind not in TOAST_MESSAGES:
            raise ValueError("Unknown TV toast kind")
        task = asyncio.create_task(self.send(kind))
        self.pending.add(task)
        task.add_done_callback(self.pending.discard)
