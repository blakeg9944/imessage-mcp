"""confirm_send: echo check → guards → Mac state → native dialog → argv send → delivery check → log.

Dry-run is the default: unless IMESSAGE_MCP_LIVE=1, the Messages send is never called and every row
returns `sent: false, dry_run: true`. The phone and text always travel as osascript arguments
(`on run argv`), never inside the script string. There is no automatic SMS fallback (SPEC §9).
"""

from __future__ import annotations

import subprocess
import time as _time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from . import chatdb, dialog, guards
from .config import Config
from .confirm import Batch, ConfirmError, TokenStore
from .sendlog import SendLog, new_send_id

SEND_SCRIPT = """on run argv
  set phoneNum to item 1 of argv
  set msg to item 2 of argv
  set svcType to item 3 of argv -- "iMessage" or "SMS"
  tell application "Messages"
    if svcType is "SMS" then
      set svc to 1st account whose service type = SMS
    else
      set svc to 1st account whose service type = iMessage
    end if
    send msg to participant phoneNum of svc
  end tell
end run"""

ACCOUNT_SCRIPT = """on run argv
  set svcType to item 1 of argv
  tell application "Messages"
    if svcType is "SMS" then
      set accts to every account whose service type = SMS and enabled is true
    else
      set accts to every account whose service type = iMessage and enabled is true
    end if
    return (count of accts) as text
  end tell
end run"""

DELIVERY_TIMEOUT = 15.0
POLL_INTERVAL = 1.0

ACCOUNT_HELP = {
    "iMessage": "Messages has no enabled iMessage account: is Messages signed in? (Messages > Settings > iMessage)",
    "SMS": "Messages has no enabled SMS account: is Text Message Forwarding on? "
    "(iPhone: Settings > Apps > Messages > Text Message Forwarding)",
}


def _osascript(runner: Callable, script: str, *args: str, timeout: float = 30) -> subprocess.CompletedProcess:
    return runner(["osascript", "-e", script, *args], capture_output=True, text=True, encoding="utf-8", timeout=timeout)


def check_account(service: str, runner: Callable) -> str | None:
    """None when Messages has an enabled account for `service`, else a clear error."""
    try:
        proc = _osascript(runner, ACCOUNT_SCRIPT, service)
    except (subprocess.TimeoutExpired, OSError) as e:
        return f"Couldn't check Messages accounts: {e}"
    if proc.returncode != 0:
        return f"Couldn't check Messages accounts ({(proc.stderr or '').strip()}). {ACCOUNT_HELP[service]}"
    try:
        count = int((proc.stdout or "0").strip() or 0)
    except ValueError:
        count = 0
    return None if count > 0 else ACCOUNT_HELP[service]


def wait_for_delivery(
    db_path: Path,
    phone: str,
    after_rowid: int,
    *,
    timeout: float = DELIVERY_TIMEOUT,
    interval: float = POLL_INTERVAL,
    clock: Callable[[], float] = _time.monotonic,
    sleep: Callable[[float], None] = _time.sleep,
) -> tuple[str, dict | None]:
    """Poll chat.db for the outgoing row (matched by ROWID > after_rowid, never by text).

    Stops early on delivered/failed; otherwise reports what it saw at the deadline (sent or unknown).
    """
    deadline = clock() + timeout
    row = None
    while True:
        with chatdb.connect(db_path) as con:
            found = chatdb.find_sent_row(con, phone, after_rowid)
            row = dict(found) if found else None
        status = chatdb.delivery_status(row)
        if status in ("delivered", "failed") or clock() >= deadline:
            return status, row
        sleep(interval)


def confirm_send(
    token: str,
    messages: list,
    *,
    cfg: Config,
    store: TokenStore,
    log: SendLog,
    runner: Callable | None = None,
    now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
    clock: Callable[[], float] = _time.monotonic,
    sleep: Callable[[float], None] = _time.sleep,
) -> dict:
    runner = runner or subprocess.run
    if cfg.live and cfg.no_dialog:  # config.load already refuses this; never trust a single check
        raise RuntimeError("IMESSAGE_MCP_NO_DIALOG is not allowed with IMESSAGE_MCP_LIVE=1")
    try:
        batch = store.redeem(token, messages)
    except ConfirmError as e:
        return {"ok": False, "sent": False, "dry_run": cfg.dry_run, "error": str(e)}

    problem = _recheck(batch, cfg, log, now())
    if problem:
        return {"ok": False, "sent": False, "dry_run": cfg.dry_run, "error": problem}

    if cfg.live:
        for service in sorted({r.service for r in batch.rows}):
            err = check_account(service, runner)
            if err:
                return {"ok": False, "sent": False, "dry_run": False, "error": err}

    if cfg.dry_run and cfg.no_dialog:
        approved, outcome = True, "skipped (IMESSAGE_MCP_NO_DIALOG=1, dry-run only)"
    else:
        text = dialog.build_text(batch.rows, dry_run=cfg.dry_run, quiet=batch.quiet)
        approved, outcome = dialog.ask(text, runner=runner)
    if not approved:
        return {"ok": False, "sent": False, "dry_run": cfg.dry_run, "dialog": outcome,
                "error": f"Not sent: the confirmation dialog returned {outcome}."}

    results = [_send_row(r, batch, cfg, log, runner, now, clock, sleep) for r in batch.rows]
    out = {"ok": all(r["status"] != "failed" for r in results), "dry_run": cfg.dry_run, "dialog": outcome,
           "results": results}
    if cfg.dry_run:
        out["note"] = "DRY RUN: nothing was sent. Set IMESSAGE_MCP_LIVE=1 and restart the server to send for real."
    return out


def _recheck(batch: Batch, cfg: Config, log: SendLog, at: datetime) -> str | None:
    """Re-run the guards at confirm time: the 10-minute token can outlive the preview's checks."""
    quiet = guards.quiet_reason(at, cfg.quiet_start, cfg.quiet_end, cfg.block_sunday)
    if quiet and not batch.allow_quiet_hours:
        return f"Not sent: it is now {quiet}. Preview again with allow_quiet_hours=true only if Blake asks."
    if not batch.allow_repeat:
        for r in batch.rows:
            rep = guards.repeat_of(log, r.phone, r.text, at)
            if rep:
                return f"Not sent: the same text went to {r.name} on {rep}. Preview again."
    return None


def _send_row(row, batch, cfg, log, runner, now, clock, sleep) -> dict:
    send_id = new_send_id()
    record = {
        "send_id": send_id,
        "timestamp": now().isoformat(),
        "name": row.name,
        "phone": row.phone,
        "text": row.text,
        "service": row.service,
        "dry_run": cfg.dry_run,
        "sent": False,
        "attempted": False,  # the Messages send was called (it may have sent even if osascript timed out)
        "guid": None,
        "status": "dry_run" if cfg.dry_run else "unknown",
        "error": None,
        "after_rowid": None,
        "allow_repeat": bool(row.repeat_of),
        "allow_quiet_hours": bool(batch.quiet),
    }
    if cfg.live:
        try:
            with chatdb.connect(cfg.chat_db) as con:
                record["after_rowid"] = chatdb.max_rowid(con)
            record["timestamp"] = now().isoformat()
            record["attempted"] = True
            proc = _osascript(runner, SEND_SCRIPT, row.phone, row.text, row.service)
        except chatdb.ChatDBError as e:
            record.update(status="failed", error=f"not sent: {e}")
        except (subprocess.TimeoutExpired, OSError) as e:
            record.update(status="unknown", error=f"osascript did not finish: {e}")  # may have sent: don't retry
        else:
            if proc.returncode != 0:
                record.update(status="failed", error=f"osascript failed: {(proc.stderr or '').strip()}")
            else:
                record["sent"] = True
                try:
                    status, found = wait_for_delivery(cfg.chat_db, row.phone, record["after_rowid"], clock=clock, sleep=sleep)
                except chatdb.ChatDBError as e:
                    status, found = "unknown", None
                    record["error"] = f"sent, but couldn't read chat.db to check delivery: {e}"
                record["status"] = status
                if found:
                    record["guid"] = found["guid"]
                    if found.get("error"):
                        record["error"] = f"Messages reported error {found['error']} (Not Delivered)"
                elif status == "unknown" and not record["error"]:
                    record["error"] = "No outgoing row appeared in chat.db within 15 seconds. Is the Mac online?"
    log.append(record)
    return {
        "send_id": send_id,
        "name": row.name,
        "phone": row.phone,
        "service": row.service,
        "status": record["status"],
        "sent": record["sent"],
        "dry_run": cfg.dry_run,
        "error": record["error"],
    }
