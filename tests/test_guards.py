from datetime import datetime, time, timedelta

import pytest

from imessage_mcp import guards
from imessage_mcp.sendlog import SendLog

Q = (time(21), time(8))
THU = datetime(2026, 11, 5).astimezone().replace(hour=0)  # a Thursday
SUN = datetime(2026, 11, 8).astimezone().replace(hour=0)


@pytest.mark.parametrize(
    "when,quiet",
    [
        (THU.replace(hour=7, minute=59), True),
        (THU.replace(hour=8), False),
        (THU.replace(hour=12), False),
        (THU.replace(hour=20, minute=59), False),
        (THU.replace(hour=21), True),
        (THU.replace(hour=23, minute=30), True),
        (THU.replace(hour=0, minute=5), True),
    ],
)
def test_wrapping_window(when, quiet):
    assert bool(guards.quiet_reason(when, *Q, block_sunday=True)) is quiet


def test_sunday_blocking():
    assert guards.quiet_reason(SUN.replace(hour=12), *Q, block_sunday=True) == "Sunday"
    assert guards.quiet_reason(SUN.replace(hour=12), *Q, block_sunday=False) is None


def test_non_wrapping_and_empty_window():
    assert guards.quiet_reason(THU.replace(hour=13), time(12), time(14), False)
    assert not guards.quiet_reason(THU.replace(hour=15), time(12), time(14), False)
    assert not guards.quiet_reason(THU.replace(hour=3), time(0), time(0), False)


def test_repeat_of(tmp_path):
    log = SendLog(tmp_path / "s.jsonl")
    now = THU.replace(hour=12)
    log.append({"send_id": "a", "timestamp": (now - timedelta(hours=2)).isoformat(), "phone": "+18015550131",
                "text": "Hi there", "dry_run": False, "sent": True, "status": "delivered"})
    assert guards.repeat_of(log, "+18015550131", "hi  there", now) == "Thu Nov 5 10:00 AM"
    assert guards.repeat_of(log, "+18015550131", "hi there", now + timedelta(hours=23)) is None
