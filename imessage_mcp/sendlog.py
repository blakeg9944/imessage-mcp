"""logs/sends.jsonl: one line per confirm_send row (SPEC §7).

The log is the source of truth for "who was asked what, and when." Each record holds `send_id`,
`timestamp` (local ISO-8601, taken just before the send), `name`, normalized `phone`, `text`, `service`,
`dry_run`, `sent` (whether the Messages send was actually called and returned cleanly), the chat.db `guid`
when found, delivery `status`, `error`, and `after_rowid` (the pre-send MAX(ROWID), so the sent row can be
found again later).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path


def new_send_id() -> str:
    return "s_" + uuid.uuid4().hex[:12]


def normalize_text(text: str) -> str:
    """For the duplicate-send guard: case-insensitive, whitespace-collapsed, curly quotes straightened."""
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return " ".join(text.split()).casefold()


def _ts(record: dict) -> datetime:
    dt = datetime.fromisoformat(record["timestamp"])
    return dt.astimezone() if dt.tzinfo is None else dt


class SendLog:
    def __init__(self, path: Path | str):
        self.path = Path(path).expanduser()

    def append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

    def records(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # a torn last line must not break reads
        return out

    def get(self, send_id: str) -> dict | None:
        for r in reversed(self.records()):
            if r.get("send_id") == send_id:
                return r
        return None

    def live_sends(self, phone: str) -> list[dict]:
        """Live rows to `phone` where the Messages send was actually called, oldest first."""
        rows = [r for r in self.records() if r.get("phone") == phone and not r.get("dry_run") and r.get("sent")]
        return sorted(rows, key=_ts)

    def last_live_send_time(self, phone: str) -> datetime | None:
        rows = self.live_sends(phone)
        return _ts(rows[-1]) if rows else None

    def next_live_send_after(self, phone: str, after: datetime, exclude_id: str | None = None) -> datetime | None:
        for r in self.live_sends(phone):
            if r.get("send_id") != exclude_id and _ts(r) > after:
                return _ts(r)
        return None

    def recent_duplicate(self, phone: str, text: str, now: datetime, within: timedelta) -> dict | None:
        """The latest live send of the same normalized text to `phone` within `within`, if any.

        Rows whose delivery check reported `failed` don't count: the member never got that text, and
        SPEC §9 has Claude offer a fresh SMS preview after a failed iMessage.
        """
        want = normalize_text(text)
        for r in reversed(self.live_sends(phone)):
            if r.get("status") == "failed":
                continue
            if normalize_text(r.get("text", "")) == want and now - _ts(r) <= within:
                return r
        return None


def timestamp_of(record: dict) -> datetime:
    return _ts(record)
