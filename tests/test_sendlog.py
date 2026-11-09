from datetime import datetime, timedelta

from imessage_mcp.sendlog import SendLog, new_send_id, normalize_text

NOW = datetime(2026, 11, 8, 12, 0).astimezone()


def rec(phone="+18015550131", text="Could you meet Sunday at 7:00?", minutes_ago=60, **kw):
    base = {"send_id": new_send_id(), "timestamp": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
            "name": "Mark", "phone": phone, "text": text, "service": "iMessage", "dry_run": False, "sent": True,
            "status": "delivered"}
    return base | kw


def test_append_and_read_back(tmp_path):
    log = SendLog(tmp_path / "logs" / "sends.jsonl")
    assert log.records() == []
    r = rec()
    log.append(r)
    assert log.get(r["send_id"]) == r
    assert log.get("missing") is None
    assert log.path.parent.name == "logs"


def test_torn_line_is_skipped(tmp_path):
    log = SendLog(tmp_path / "s.jsonl")
    log.append(rec())
    with log.path.open("a") as f:
        f.write('{"send_id": "torn"')
    assert len(log.records()) == 1


def test_live_sends_ignore_dry_run_and_unsent(tmp_path):
    log = SendLog(tmp_path / "s.jsonl")
    live = rec(minutes_ago=30)
    log.append(rec(minutes_ago=10, dry_run=True, sent=False))
    log.append(rec(minutes_ago=5, sent=False, status="unknown"))
    log.append(live)
    log.append(rec(phone="+18015550132", minutes_ago=1))
    assert [r["send_id"] for r in log.live_sends("+18015550131")] == [live["send_id"]]
    assert log.last_live_send_time("+18015550131") == NOW - timedelta(minutes=30)
    assert log.last_live_send_time("+18015550100") is None


def test_next_live_send_after(tmp_path):
    log = SendLog(tmp_path / "s.jsonl")
    a, b = rec(minutes_ago=120), rec(minutes_ago=30)
    log.append(a)
    log.append(b)
    assert log.next_live_send_after(a["phone"], NOW - timedelta(minutes=120), exclude_id=a["send_id"]) == NOW - timedelta(minutes=30)
    assert log.next_live_send_after(a["phone"], NOW - timedelta(minutes=30), exclude_id=b["send_id"]) is None


def test_recent_duplicate(tmp_path):
    log = SendLog(tmp_path / "s.jsonl")
    log.append(rec(text="Could you  meet Sunday at 7:00?", minutes_ago=60))
    day = timedelta(hours=24)
    assert log.recent_duplicate("+18015550131", "could you meet sunday at 7:00?", NOW, day)
    assert log.recent_duplicate("+18015550131", "Could you meet Sunday at 8:00?", NOW, day) is None
    assert log.recent_duplicate("+18015550131", "Could you meet Sunday at 7:00?", NOW + day, day) is None
    assert log.recent_duplicate("+18015550132", "Could you meet Sunday at 7:00?", NOW, day) is None


def test_failed_and_dry_run_sends_are_not_duplicates(tmp_path):
    log = SendLog(tmp_path / "s.jsonl")
    log.append(rec(status="failed"))
    log.append(rec(dry_run=True, sent=False))
    assert log.recent_duplicate("+18015550131", "Could you meet Sunday at 7:00?", NOW, timedelta(hours=24)) is None


def test_normalize_text():
    assert normalize_text("  Don’t   FORGET ") == "don't forget"
