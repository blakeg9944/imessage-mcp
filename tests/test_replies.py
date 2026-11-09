import pytest

from imessage_mcp import chatdb, contacts, replies
from imessage_mcp.sendlog import SendLog
from tests import synthetic


@pytest.fixture
def log(tmp_path, synth_db):
    log = SendLog(tmp_path / "sends.jsonl")
    for r in synthetic.ward_sendlog():
        log.append(r)
    return log


@pytest.fixture
def con(synth_db):
    with chatdb.connect(synth_db) as c:
        yield c


def check(con, log, allow, key):
    return replies.check_replies(con, log, allow, [f"synth-{key}"])[0]


@pytest.mark.parametrize(
    "key,status,guess",
    [
        ("yes", "replied", "yes"),
        ("no", "replied", "no"),
        ("reschedule", "replied", "reschedule"),
        ("tapback", "replied", "yes"),
        ("opt_out", "replied", "opt_out"),
        ("no_reply", "no_reply", None),
        ("household", "replied", "yes"),
        ("failed", "no_reply", None),
    ],
)
def test_each_ward_thread(con, log, allow, key, status, guess):
    r = check(con, log, allow, key)
    assert (r["status"], r["guess"]) == (status, guess)
    assert r["original_text"] == synthetic.INVITE


def test_ignores_replies_before_the_send(con, log, allow):
    r = check(con, log, allow, "no_reply")
    assert r["replies"] == []  # the older "Happy to help" and the cancelled heart are both excluded
    assert any(m.text == "Happy to help, anytime" for m in chatdb.thread(con, synthetic.WARD["no_reply"].phone))


def test_stops_at_the_next_logged_send(con, log, allow):
    r = check(con, log, allow, "yes")
    assert [x["text"] for x in r["replies"]] == ["Yes, that works!"]
    assert "window_end" in r
    second = replies.check_replies(con, log, allow, ["synth-yes-reminder"])[0]
    assert [x["text"] for x in second["replies"]] == ["See you then"]


def test_tapback_on_sent_message(con, log, allow):
    r = check(con, log, allow, "tapback")
    assert r["replies"] == [
        {"time": r["replies"][0]["time"], "service": "iMessage", "text": f'👍 Liked "{synthetic.INVITE}"',
         "tapback": "liked", "on_sent_message": True}
    ]


def test_guid_recovered_from_after_rowid(con, tmp_path, allow):
    rec = next(r for r in synthetic.ward_sendlog() if r["send_id"] == "synth-tapback")
    rowid = con.execute("SELECT ROWID FROM message WHERE guid = ?", (rec["guid"],)).fetchone()[0]
    log = SendLog(tmp_path / "s.jsonl")
    log.append(rec | {"guid": None, "status": "unknown", "after_rowid": rowid - 1})
    r = replies.check_replies(con, log, allow, ["synth-tapback"])[0]
    assert r["guess"] == "yes" and r["replies"][0]["on_sent_message"] is True


def test_unknown_send_id_and_allowlist(con, log, tmp_path):
    allow = contacts.load(tmp_path / "missing.csv")
    res = replies.check_replies(con, log, allow, ["nope", "synth-yes"])
    assert "Unknown send_id" in res[0]["error"]
    assert "not in contacts.csv" in res[1]["error"]


def test_dry_run_send_is_labeled(con, tmp_path, allow):
    log = SendLog(tmp_path / "s.jsonl")
    log.append({"send_id": "d1", "timestamp": "2026-11-08T10:00:00-07:00", "name": "Mark Nelson",
                "phone": "+18015550131", "text": "hi", "service": "iMessage", "dry_run": True, "sent": False,
                "guid": None, "status": None, "error": None})
    r = replies.check_replies(con, log, allow, ["d1"])[0]
    assert r["dry_run"] is True and "DRY RUN" in r["note"]


@pytest.mark.parametrize(
    "texts,taps,expected",
    [
        (["Yes, that works!"], [], "yes"),
        (["Sure thing"], [], "yes"),
        (["No problem, see you then"], [], "yes"),
        (["No sorry"], [], "no"),
        (["We can't, out of town"], [], "no"),
        (["can we do 7:30 instead?"], [], "reschedule"),
        (["Yes but can't make 7, another time?"], [], "reschedule"),
        (["please stop texting me"], [], "opt_out"),
        (["Yes. Actually STOP. Unsubscribe"], [], "opt_out"),
        (["Don’t text me"], [], "opt_out"),
        (["Yes I'll stop by at 7"], [], "yes"),
        (["Who is this?"], [], "unclear"),
        (["yes", "no"], [], "unclear"),
        ([], [2001], "yes"),
        ([], [2000], "yes"),
        ([], [2002], "no"),
        ([], [2003], "unclear"),
        (["No"], [2001], "unclear"),
    ],
)
def test_guess(texts, taps, expected):
    assert replies.guess(texts, taps) == expected
