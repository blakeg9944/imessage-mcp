import dataclasses
from datetime import datetime, timedelta

import pytest

from imessage_mcp import config, contacts
from imessage_mcp.confirm import ConfirmError, TokenStore, preview_send
from imessage_mcp.sendlog import SendLog
from tests.fakes import FakeClock

NOON_THU = datetime(2026, 11, 12, 12, 0).astimezone()
NIGHT_THU = datetime(2026, 11, 12, 22, 0).astimezone()
TEXT = "Could you meet with the bishopric Sunday at 7:00?"


@pytest.fixture
def env(tmp_path, synth_db, allow):
    cfg = config.load({"IMESSAGE_MCP_CHAT_DB": str(synth_db), "IMESSAGE_MCP_LOG": str(tmp_path / "s.jsonl"),
                       "IMESSAGE_MCP_NO_DIALOG": "1"})
    clock = FakeClock()
    return {"cfg": cfg, "allow": allow, "log": SendLog(cfg.log_path), "store": TokenStore(clock=clock), "clock": clock}


def preview(env, messages, now=NOON_THU, **kw):
    return preview_send(messages, cfg=env["cfg"], allow=env["allow"], log=env["log"], store=env["store"], now=now, **kw)


MSGS = [{"phone": "(801) 555-0131", "text": TEXT}, {"phone": "801.555.0133", "text": TEXT, "service": "auto"}]


def test_preview_ok(env):
    r = preview(env, MSGS)
    assert r["ok"] and r["dry_run"] and r["confirm_token"]
    assert [x["name"] for x in r["rows"]] == ["Mark Nelson", "David Tanaka"]
    assert [x["phone"] for x in r["rows"]] == ["+18015550131", "+18015550133"]
    assert [x["service"] for x in r["rows"]] == ["iMessage", "SMS"]  # David's history is SMS-only
    assert r["rows"][0]["last_message"]["text"] == "See you then"
    assert "Mark Nelson" in r["preview_table"] and "DRY RUN" in r["next_step"]


def test_preview_no_prior_messages(env, tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("name,phone\nNew Person,8015550100\n")
    env["allow"] = contacts.load(p)
    r = preview(env, [{"phone": "8015550100", "text": "hi"}])
    assert r["rows"][0]["last_message"] == "no prior messages"


def test_non_allowlisted_row_blocks_the_whole_batch(env):
    r = preview(env, MSGS + [{"phone": "8015550199", "text": TEXT}])
    assert not r["ok"] and "confirm_token" not in r
    assert r["failed_rows"] == [{"row": 3, "phone": "8015550199", "reason": r["failed_rows"][0]["reason"]}]
    assert "not in contacts.csv" in r["failed_rows"][0]["reason"]


@pytest.mark.parametrize(
    "msg,reason",
    [
        ({"phone": "+44 20 7183 8750", "text": "hi"}, "Invalid phone"),
        ({"phone": "8015550131", "text": "  "}, "text is empty"),
        ({"phone": "8015550131", "text": "hi", "service": "WhatsApp"}, "Invalid service"),
        ("not a dict", "must be an object"),
    ],
)
def test_bad_rows(env, msg, reason):
    r = preview(env, [msg])
    assert not r["ok"] and reason in r["failed_rows"][0]["reason"]


def test_same_number_twice_in_batch(env):
    r = preview(env, [{"phone": "8015550131", "text": "a"}, {"phone": "+1 801 555 0131", "text": "b"}])
    assert "appears twice" in r["failed_rows"][0]["reason"]


def test_empty_batch(env):
    assert not preview(env, [])["ok"]


def test_quiet_hours(env):
    r = preview(env, MSGS, now=NIGHT_THU)
    assert not r["ok"] and all("quiet hours" in f["reason"] for f in r["failed_rows"])
    r = preview(env, MSGS, now=NIGHT_THU, allow_quiet_hours=True)
    assert r["ok"] and r["rows"][0]["warnings"] == ["QUIET HOURS"]
    sunday = datetime(2026, 11, 15, 12, 0).astimezone()
    assert preview(env, MSGS, now=sunday)["ok"]  # personal profile: Sundays are fine
    env["cfg"] = dataclasses.replace(env["cfg"], block_sunday=True)  # ward profile default
    assert "Sunday" in preview(env, MSGS, now=sunday)["failed_rows"][0]["reason"]


def test_duplicate_send_guard(env):
    env["log"].append({"send_id": "x", "timestamp": (NOON_THU - timedelta(hours=3)).isoformat(), "name": "Mark Nelson",
                       "phone": "+18015550131", "text": TEXT, "service": "iMessage", "dry_run": False, "sent": True,
                       "status": "delivered"})
    r = preview(env, MSGS)
    assert not r["ok"] and r["failed_rows"][0]["row"] == 1 and "allow_repeat" in r["failed_rows"][0]["reason"]
    r = preview(env, MSGS, allow_repeat=True)
    assert r["ok"] and r["rows"][0]["warnings"] == ["REPEAT of a message sent Thu Nov 12 9:00 AM"]
    assert r["rows"][1]["warnings"] == []


def test_dry_run_sends_dont_trigger_the_guard(env):
    env["log"].append({"send_id": "x", "timestamp": NOON_THU.isoformat(), "phone": "+18015550131", "text": TEXT,
                       "dry_run": True, "sent": False, "status": "dry_run"})
    assert preview(env, MSGS)["ok"]


# --- tokens and the echo check -------------------------------------------------------------------


def token(env, msgs=MSGS, **kw):
    r = preview(env, msgs, **kw)
    assert r["ok"], r
    return r["confirm_token"]


def test_redeem_with_exact_echo(env):
    batch = env["store"].redeem(token(env), MSGS)
    assert [r.phone for r in batch.rows] == ["+18015550131", "+18015550133"]


def test_echo_accepts_other_phone_formats_and_resolved_service(env):
    echo = [{"phone": "+18015550131", "text": TEXT, "service": "auto"},
            {"phone": "8015550133", "text": TEXT, "service": "sms"}]
    env["store"].redeem(token(env), echo)


@pytest.mark.parametrize(
    "echo,why",
    [
        ([MSGS[0] | {"text": TEXT + " "}, MSGS[1]], "row 1 text differs"),
        ([MSGS[0] | {"phone": "8015550132"}, MSGS[1]], "row 1 phone differs"),
        ([MSGS[0] | {"service": "SMS"}, MSGS[1]], "row 1 service differs"),
        ([MSGS[1], MSGS[0]], "row 1 phone differs"),
        ([MSGS[0]], "expected 2 messages, got 1"),
        (MSGS + [MSGS[0]], "expected 2 messages, got 3"),
        ([MSGS[0] | {"phone": "nope"}, MSGS[1]], "Invalid phone"),
        ("not a list", "not a list"),
    ],
)
def test_echo_mismatch_refused(env, echo, why):
    t = token(env)
    with pytest.raises(ConfirmError, match="don't match") as e:
        env["store"].redeem(t, echo)
    assert why in str(e.value)
    with pytest.raises(ConfirmError, match="already used"):  # a mismatch spends the token
        env["store"].redeem(t, MSGS)


def test_token_reuse_refused(env):
    t = token(env)
    env["store"].redeem(t, MSGS)
    with pytest.raises(ConfirmError, match="already used"):
        env["store"].redeem(t, MSGS)


def test_token_expiry(env):
    t = token(env)
    env["clock"].t += 601
    with pytest.raises(ConfirmError, match="expired"):
        env["store"].redeem(t, MSGS)


def test_token_valid_just_under_ten_minutes(env):
    t = token(env)
    env["clock"].t += 599
    env["store"].redeem(t, MSGS)


def test_unknown_token(env):
    with pytest.raises(ConfirmError, match="Unknown"):
        env["store"].redeem("made-up", MSGS)
