"""Duplicate-send guard and quiet hours (SPEC §7)."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from .sendlog import SendLog, timestamp_of

REPEAT_WINDOW = timedelta(hours=24)


def quiet_reason(now: datetime, start: time, end: time, block_sunday: bool) -> str | None:
    """Why `now` (local) is in quiet hours, or None. The window may wrap midnight (21:00-08:00)."""
    t = now.time()
    if start == end:
        inside = False
    elif start < end:
        inside = start <= t < end
    else:
        inside = t >= start or t < end
    if inside:
        return f"quiet hours ({start:%H:%M}-{end:%H:%M})"
    if block_sunday and now.weekday() == 6:
        return "Sunday"
    return None


def repeat_of(log: SendLog, phone: str, text: str, now: datetime) -> str | None:
    """Local time of a live send of the same text to `phone` in the last 24 hours, or None."""
    r = log.recent_duplicate(phone, text, now, REPEAT_WINDOW)
    return timestamp_of(r).strftime("%a %b %-d %-I:%M %p") if r else None
