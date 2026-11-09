"""preview_send + pending-send tokens and the echo check (SPEC §6, §7).

`preview_send` never sends. It checks every row (allowlist, duplicate guard, quiet hours), and only when
every row passes does it issue one `confirm_token` for the whole batch, valid for 10 minutes and usable
once. `confirm_send` must echo the same messages back; any difference in normalized phone, text or
service is refused.
"""

from __future__ import annotations

import secrets
import time as _time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from . import chatdb, guards
from .config import Config
from .contacts import Allowlist, NotAllowed
from .phones import PhoneError, normalize
from .sendlog import SendLog

TOKEN_TTL_SECONDS = 600
SERVICES = {"auto": "auto", "imessage": "iMessage", "sms": "SMS"}


class ConfirmError(ValueError):
    pass


@dataclass(frozen=True)
class Row:
    name: str
    phone: str
    text: str
    service_requested: str  # auto / iMessage / SMS
    service: str  # what will be used: iMessage / SMS
    repeat_of: str | None = None  # local time of the earlier identical send, when allow_repeat was used


@dataclass
class Batch:
    token: str
    rows: list[Row]
    issued_at: float
    allow_repeat: bool
    allow_quiet_hours: bool
    quiet: str | None = None  # quiet-hours reason at preview time, when allow_quiet_hours was used
    used: bool = False


@dataclass
class TokenStore:
    ttl: float = TOKEN_TTL_SECONDS
    clock: Callable[[], float] = _time.monotonic
    _batches: dict[str, Batch] = field(default_factory=dict)

    def issue(self, rows: list[Row], *, allow_repeat: bool, allow_quiet_hours: bool, quiet: str | None) -> Batch:
        token = secrets.token_urlsafe(16)
        batch = Batch(token, rows, self.clock(), allow_repeat, allow_quiet_hours, quiet)
        self._batches[token] = batch
        return batch

    def redeem(self, token: str, messages: list) -> Batch:
        """Check the token and the echoed messages. The token is spent by any attempt that names it."""
        batch = self._batches.get(str(token))
        if batch is None:
            raise ConfirmError("Unknown confirm_token. Run preview_send again.")
        if batch.used:
            raise ConfirmError("This confirm_token was already used. Run preview_send again.")
        batch.used = True
        if self.clock() - batch.issued_at > self.ttl:
            raise ConfirmError("This confirm_token expired (10 minutes). Run preview_send again.")
        mismatch = echo_mismatch(batch.rows, messages)
        if mismatch:
            raise ConfirmError(
                f"Refused: messages don't match the preview ({mismatch}). The token is now spent; "
                "run preview_send again with the exact messages."
            )
        return batch


    def spend(self, token: str) -> None:
        """Mark a token used without checking it (a refused confirm_send still spends its token)."""
        batch = self._batches.get(str(token))
        if batch is not None:
            batch.used = True


def parse_service(value: object) -> str:
    key = str(value if value is not None else "auto").strip().lower()
    if key not in SERVICES:
        raise ValueError(f"Invalid service {value!r}: use auto, iMessage or SMS")
    return SERVICES[key]


def echo_mismatch(rows: list[Row], messages: list) -> str | None:
    if not isinstance(messages, list) or len(messages) != len(rows):
        n = len(messages) if isinstance(messages, list) else "not a list"
        return f"expected {len(rows)} messages, got {n}"
    for i, (row, msg) in enumerate(zip(rows, messages), start=1):
        if not isinstance(msg, dict):
            return f"row {i} is not an object"
        try:
            phone = normalize(msg.get("phone"))
            service = parse_service(msg.get("service", "auto"))
        except (PhoneError, ValueError) as e:
            return f"row {i}: {e}"
        if phone != row.phone:
            return f"row {i} phone differs"
        if msg.get("text") != row.text:
            return f"row {i} text differs"
        if service not in (row.service_requested, row.service):
            return f"row {i} service differs"
    return None


def _table(rows: list[dict]) -> str:
    lines = ["| # | Name | Phone | Service | Text | Last message in thread |", "|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, start=1):
        last = r["last_message"]
        last_s = last if isinstance(last, str) else f'{last["from"]} {last["time"]}: {last["text"]}'
        warn = f' **{"; ".join(r["warnings"])}**' if r.get("warnings") else ""
        cells = [str(i), r["name"], r["phone"], r["service"], r["text"] + warn, last_s]
        lines.append("| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells) + " |")
    return "\n".join(lines)


def preview_send(
    messages: list,
    *,
    cfg: Config,
    allow: Allowlist,
    log: SendLog,
    store: TokenStore,
    allow_repeat: bool = False,
    allow_quiet_hours: bool = False,
    now: datetime | None = None,
    db_path: Path | None = None,
) -> dict:
    now = now or datetime.now().astimezone()
    db_path = db_path or cfg.chat_db
    if not isinstance(messages, list) or not messages:
        return {"ok": False, "dry_run": cfg.dry_run, "error": "messages must be a non-empty list", "rows": []}

    quiet = guards.quiet_reason(now, cfg.quiet_start, cfg.quiet_end, cfg.block_sunday)
    rows: list[dict] = []
    failed: list[dict] = []
    seen: set[str] = set()
    good: list[tuple[int, Row]] = []
    for i, msg in enumerate(messages, start=1):
        raw_phone = msg.get("phone") if isinstance(msg, dict) else None
        try:
            if not isinstance(msg, dict):
                raise ValueError("each message must be an object with phone and text")
            text = msg.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("text is empty")
            requested = parse_service(msg.get("service", "auto"))
            contact = allow.require(raw_phone)
            if contact.phone in seen:
                raise ValueError(f"{contact.phone} appears twice in this batch")
            seen.add(contact.phone)
        except (NotAllowed, ValueError) as e:
            failed.append({"row": i, "phone": str(raw_phone), "reason": str(e)})
            continue
        good.append((i, Row(contact.name, contact.phone, text, requested, requested)))

    final: list[Row] = []
    if good:
        try:
            with chatdb.connect(db_path) as con:
                for i, row in good:
                    service = chatdb.choose_service(con, row.phone) if row.service_requested == "auto" else row.service_requested
                    last = chatdb.last_message(con, row.phone)
                    warnings, reasons = [], []
                    rep = guards.repeat_of(log, row.phone, row.text, now)
                    if rep and not allow_repeat:
                        reasons.append(f"the same text went to this number on {rep} (pass allow_repeat=true only if Blake wants a repeat)")
                    elif rep:
                        warnings.append(f"REPEAT of a message sent {rep}")
                    if quiet and not allow_quiet_hours:
                        reasons.append(f"it is {quiet} (pass allow_quiet_hours=true only if Blake asks)")
                    elif quiet:
                        warnings.append("QUIET HOURS")
                    entry = {
                        "row": i,
                        "name": row.name,
                        "phone": row.phone,
                        "service": service,
                        "text": row.text,
                        "last_message": last.to_dict() if last else "no prior messages",
                        "warnings": warnings,
                    }
                    if reasons:
                        failed.append({"row": i, "phone": row.phone, "name": row.name, "reason": "; ".join(reasons)})
                    rows.append(entry)
                    final.append(Row(row.name, row.phone, row.text, row.service_requested, service, rep if allow_repeat else None))
        except chatdb.ChatDBError as e:
            return {"ok": False, "dry_run": cfg.dry_run, "error": str(e), "rows": []}

    result = {"ok": not failed, "dry_run": cfg.dry_run, "rows": rows, "preview_table": _table(rows)}
    if failed:
        result["failed_rows"] = sorted(failed, key=lambda f: f["row"])
        result["error"] = "No confirm_token issued: every row must pass. Fix or drop the failed rows and preview again."
        return result
    batch = store.issue(final, allow_repeat=allow_repeat, allow_quiet_hours=allow_quiet_hours,
                        quiet=quiet if allow_quiet_hours else None)
    result["confirm_token"] = batch.token
    result["expires_at"] = (now + timedelta(seconds=store.ttl)).isoformat(timespec="seconds")
    result["next_step"] = (
        "Show Blake this full preview table in chat. Only if Blake approves, call confirm_send with this token "
        "and the exact same messages list. A native macOS dialog will then ask Blake to click Send."
        + (" DRY RUN: nothing will actually be sent." if cfg.dry_run else "")
    )
    return result
