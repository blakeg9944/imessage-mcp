"""Read-only queries on Messages' chat.db (SPEC §3, §9).

- Opened only with a read-only `file:...?mode=ro` URI.
- Only 1:1 threads: a thread is the set of chats whose only participant is that phone's handle(s).
- Text comes from `message.text`, else from the `attributedBody` blob (copied decoder).
- Tapbacks (associated_message_type 2000–2006) are rendered like `👍 Liked "…"` and linked to the
  message they react to; removals (3000–3006) cancel the matching reaction.
- Phone matching normalizes `handle.id`; email handles never match a phone.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import attributed_body
from .contacts import Allowlist, NotAllowed
from .phones import try_normalize

APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)
OBJ = "￼"  # object replacement char Messages puts where an attachment sits

REACTIONS = {
    2000: ("❤️", "Loved"),
    2001: ("👍", "Liked"),
    2002: ("👎", "Disliked"),
    2003: ("😂", "Laughed at"),
    2004: ("‼️", "Emphasized"),
    2005: ("❓", "Questioned"),
    2006: ("", "Reacted to"),  # custom emoji (newer macOS); emoji in associated_message_emoji
}
REMOVALS = range(3000, 3007)

DEFAULT_LOOKBACK = timedelta(days=7)

FULL_DISK_ACCESS_HELP = (
    "Can't open {path} ({err}). Grant Full Disk Access to the app that runs Claude Code "
    "(Terminal/iTerm, or the Claude desktop app if you use its Code tab): System Settings > "
    "Privacy & Security > Full Disk Access, then restart that app."
)


class ChatDBError(RuntimeError):
    pass


# ---------------------------------------------------------------------------------------------------
# Time


def from_apple(value: int | None) -> datetime | None:
    """chat.db date (ns since 2001-01-01 UTC; seconds on very old databases) → local aware datetime."""
    if not value:
        return None
    seconds = value / 1e9 if abs(value) > 1e11 else float(value)
    return (APPLE_EPOCH + timedelta(seconds=seconds)).astimezone()


def to_apple(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return int((dt - APPLE_EPOCH).total_seconds() * 1_000_000_000)


_RELATIVE = re.compile(r"^\s*(\d+)\s*([mhdw])\s*$", re.IGNORECASE)
_UNITS = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}


def parse_since(value: str | None, now: datetime | None = None) -> datetime | None:
    """ISO-8601 datetime (naive = local time) or relative like "2d", "6h", "30m", "1w"."""
    if value is None or str(value).strip() == "":
        return None
    now = now or datetime.now().astimezone()
    m = _RELATIVE.match(str(value))
    if m:
        return now - timedelta(**{_UNITS[m.group(2).lower()]: int(m.group(1))})
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"Invalid since {value!r}: use ISO-8601 (2026-11-05T18:00) or relative (2d, 6h)") from None
    return dt.astimezone() if dt.tzinfo is None else dt


# ---------------------------------------------------------------------------------------------------
# Connection


@contextmanager
def connect(path: Path | str) -> Iterator[sqlite3.Connection]:
    path = Path(path).expanduser()
    try:
        con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        con.execute("SELECT 1 FROM message LIMIT 1")
    except (sqlite3.Error, OSError) as e:
        raise ChatDBError(FULL_DISK_ACCESS_HELP.format(path=path, err=e)) from None
    con.row_factory = sqlite3.Row
    try:
        yield con
    except sqlite3.Error as e:  # e.g. "database is locked" while Messages writes: never a raw sqlite3 error
        raise ChatDBError(f"Couldn't read {path}: {e}") from None
    finally:
        con.close()


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}


def _qmarks(n: int) -> str:
    return ",".join("?" * n)


# ---------------------------------------------------------------------------------------------------
# Handles and threads


def handles_for(con: sqlite3.Connection, phone: str) -> list[sqlite3.Row]:
    """handle rows whose id normalizes to `phone` (a normalized +1XXXXXXXXXX). Emails never match."""
    rows = con.execute("SELECT ROWID, id, service FROM handle").fetchall()
    return [r for r in rows if "@" not in (r["id"] or "") and try_normalize(r["id"]) == phone]


def _one_to_one_chats(con: sqlite3.Connection, handle_ids: list[int]) -> list[int]:
    if not handle_ids:
        return []
    rows = con.execute(
        f"""SELECT chj.chat_id FROM chat_handle_join chj
            WHERE chj.handle_id IN ({_qmarks(len(handle_ids))})
              AND (SELECT COUNT(*) FROM chat_handle_join x WHERE x.chat_id = chj.chat_id) = 1""",
        handle_ids,
    ).fetchall()
    return sorted({r[0] for r in rows})


def decode_text(row: sqlite3.Row) -> str:
    text = row["text"]
    if not text:
        text, _ = attributed_body.decode(row["attributedBody"])
        text = text or ""
    has_attachment = bool(row["cache_has_attachments"]) or OBJ in text
    text = text.replace(OBJ, "[attachment]").strip()
    if has_attachment and "[attachment]" not in text:
        text = ("[attachment] " + text).strip()
    return text


def _target_guid(assoc: str | None) -> str | None:
    if not assoc:
        return None
    if "/" in assoc:  # "p:0/GUID"
        return assoc.split("/", 1)[1]
    if assoc.startswith("bp:"):
        return assoc[3:]
    return assoc


def _quote(text: str, limit: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass
class Message:
    rowid: int
    guid: str
    from_me: bool
    text: str
    date: datetime
    service: str
    reaction: int | None = None  # 2000–2006 when this row is a tapback
    target_guid: str | None = None
    emoji: str | None = None

    @property
    def is_tapback(self) -> bool:
        return self.reaction is not None

    def to_dict(self) -> dict:
        d = {
            "from": "me" if self.from_me else "them",
            "time": self.date.isoformat(timespec="seconds"),
            "service": self.service,
            "text": self.text,
        }
        if self.is_tapback:
            d["tapback"] = REACTIONS[self.reaction][1].split()[0].lower()
        return d


_MSG_COLS = (
    "m.ROWID, m.guid, m.text, m.attributedBody, m.is_from_me, m.date, m.service, m.cache_has_attachments,"
    " m.associated_message_guid, m.associated_message_type"
)


def _rows_in_thread(
    con: sqlite3.Connection,
    chats: list[int],
    *,
    since: datetime | None,
    until: datetime | None,
    newest_first: bool = False,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    if not chats:
        return []
    extra = ", m.associated_message_emoji" if "associated_message_emoji" in _columns(con, "message") else ""
    where = [f"cmj.chat_id IN ({_qmarks(len(chats))})", "m.item_type = 0"]
    params: list = list(chats)
    if since is not None:
        where.append("m.date > ?")
        params.append(to_apple(since))
    if until is not None:
        where.append("m.date < ?")
        params.append(to_apple(until))
    sql = (
        f"SELECT DISTINCT {_MSG_COLS}{extra} FROM message m JOIN chat_message_join cmj ON cmj.message_id = m.ROWID"
        f" WHERE {' AND '.join(where)} ORDER BY m.date {'DESC' if newest_first else 'ASC'}, m.ROWID"
    )
    if limit:
        sql += f" LIMIT {int(limit)}"
    return con.execute(sql, params).fetchall()


def _build(con: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[Message]:
    """Rows (oldest first) → Messages with tapbacks rendered and removed reactions cancelled."""
    out: list[Message] = []
    for r in rows:
        kind = r["associated_message_type"] or 0
        target = _target_guid(r["associated_message_guid"])
        emoji = r["associated_message_emoji"] if "associated_message_emoji" in r.keys() else None
        if kind in REMOVALS:
            want = kind - 1000
            for i in range(len(out) - 1, -1, -1):
                prev = out[i]
                if prev.reaction == want and prev.target_guid == target and prev.from_me == bool(r["is_from_me"]):
                    if want != 2006 or not emoji or prev.emoji == emoji:
                        del out[i]
                        break
            continue
        msg = Message(
            rowid=r["ROWID"],
            guid=r["guid"],
            from_me=bool(r["is_from_me"]),
            text="" if kind in REACTIONS else decode_text(r),
            date=from_apple(r["date"]),
            service=r["service"] or "",
            reaction=kind if kind in REACTIONS else None,
            target_guid=target if kind in REACTIONS else None,
            emoji=emoji,
        )
        out.append(msg)

    targets = {m.target_guid for m in out if m.is_tapback and m.target_guid}
    texts = target_texts(con, targets)
    for m in out:
        if m.is_tapback:
            icon, verb = REACTIONS[m.reaction]
            if m.reaction == 2006:
                icon = m.emoji or "🙂"
            quoted = texts.get(m.target_guid)
            m.text = f'{icon} {verb} "{_quote(quoted)}"' if quoted is not None else f"{icon} {verb} a message"
    return out


def target_texts(con: sqlite3.Connection, guids: Iterable[str]) -> dict[str, str]:
    guids = list(guids)
    if not guids:
        return {}
    rows = con.execute(
        f"SELECT guid, text, attributedBody, cache_has_attachments FROM message WHERE guid IN ({_qmarks(len(guids))})",
        guids,
    ).fetchall()
    return {r["guid"]: decode_text(r) for r in rows}


def thread(
    con: sqlite3.Connection,
    phone: str,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    include_sent: bool = True,
) -> list[Message]:
    """1:1 messages with `phone` (normalized), oldest first."""
    chats = _one_to_one_chats(con, [h["ROWID"] for h in handles_for(con, phone)])
    msgs = _build(con, _rows_in_thread(con, chats, since=since, until=until))
    return msgs if include_sent else [m for m in msgs if not m.from_me]


def last_message(con: sqlite3.Connection, phone: str) -> Message | None:
    """The latest message in the 1:1 thread, either direction."""
    chats = _one_to_one_chats(con, [h["ROWID"] for h in handles_for(con, phone)])
    rows = _rows_in_thread(con, chats, since=None, until=None, newest_first=True, limit=25)
    msgs = _build(con, list(reversed(rows)))
    return msgs[-1] if msgs else None


# ---------------------------------------------------------------------------------------------------
# Service choice and delivery check


def choose_service(con: sqlite3.Connection, phone: str) -> str:
    """SMS when chat.db shows the number has only ever used SMS; otherwise iMessage (SPEC §9).

    RCS (newer macOS) counts as SMS here, since AppleScript only offers iMessage and SMS accounts.
    """
    handles = handles_for(con, phone)
    services = {(h["service"] or "") for h in handles}
    if handles:
        ids = [h["ROWID"] for h in handles]
        services |= {
            r[0] or ""
            for r in con.execute(
                f"SELECT DISTINCT service FROM message WHERE handle_id IN ({_qmarks(len(ids))})", ids
            )
        }
    services.discard("")
    if services and services <= {"SMS", "RCS"}:
        return "SMS"
    return "iMessage"


def max_rowid(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COALESCE(MAX(ROWID), 0) FROM message").fetchone()[0]


def find_sent_row(con: sqlite3.Connection, phone: str, after_rowid: int) -> sqlite3.Row | None:
    """The first outgoing, non-tapback row to `phone` with ROWID > after_rowid.

    Matched by ROWID, never by text: step 0 showed `message.text` is NULL on rows we send.
    """
    handle_ids = [h["ROWID"] for h in handles_for(con, phone)]
    if not handle_ids:
        return None
    chats = _one_to_one_chats(con, handle_ids)
    in_chat = (
        f" OR m.ROWID IN (SELECT message_id FROM chat_message_join WHERE chat_id IN ({_qmarks(len(chats))}))"
        if chats
        else ""
    )
    return con.execute(
        f"""SELECT m.ROWID, m.guid, m.error, m.is_sent, m.is_delivered, m.service FROM message m
            WHERE m.is_from_me = 1 AND m.ROWID > ? AND m.associated_message_type = 0
              AND (m.handle_id IN ({_qmarks(len(handle_ids))}){in_chat})
            ORDER BY m.ROWID LIMIT 1""",
        [after_rowid, *handle_ids, *chats],
    ).fetchone()


def delivery_status(row: sqlite3.Row | None) -> str:
    """delivered / sent / failed / unknown for a sent row (None = no row found)."""
    if row is None:
        return "unknown"
    if row["error"]:
        return "failed"
    if row["is_delivered"]:
        return "delivered"
    if row["is_sent"]:
        return "sent"
    return "unknown"


# ---------------------------------------------------------------------------------------------------
# get_replies


def get_replies(
    con: sqlite3.Connection,
    allow: Allowlist,
    phones: list,
    *,
    since: datetime | None = None,
    include_sent: bool = False,
    default_since: Callable[[str], datetime | None] = lambda phone: None,
    now: datetime | None = None,
) -> list[dict]:
    """Messages from each allowlisted phone (oldest first). Non-allowlisted phones are refused."""
    now = now or datetime.now().astimezone()
    results = []
    for raw in phones:
        try:
            contact = allow.require(raw)
        except NotAllowed as e:
            results.append({"phone": str(raw), "error": f"Refused: {e}", "messages": []})
            continue
        if since is not None:
            start, source = since, "argument"
        else:
            logged = default_since(contact.phone)
            if logged is not None:
                start, source = logged, "last logged live send"
            else:
                start, source = now - DEFAULT_LOOKBACK, f"no logged live send; last {DEFAULT_LOOKBACK.days} days"
        msgs = thread(con, contact.phone, since=start, include_sent=include_sent)
        results.append(
            {
                "name": contact.name,
                "phone": contact.phone,
                "since": start.isoformat(timespec="seconds"),
                "since_source": source,
                "messages": [m.to_dict() for m in msgs],
            }
        )
    return results
