import subprocess
from datetime import datetime, timedelta

import pytest

from imessage_mcp import config, dialog, sender
from imessage_mcp.confirm import TokenStore, preview_send
from imessage_mcp.sendlog import SendLog
from tests.fakes import FakeClock, FakeOsascript, writable_copy

NOON_THU = datetime(2026, 11, 12, 12, 0).astimezone()
TEXT = "Could you meet with the bishopric Sunday at 7:00?"
TRICKY = 'O\'Neil said "yes" \\ back\\slash; end tell -- & $(rm -rf ~) `x` \n second line'


def make(tmp_path, db, allow, *, live=False, no_dialog=True):
    env = {"IMESSAGE_MCP_CHAT_DB": str(db), "IMESSAGE_MCP_LOG": str(tmp_path / "sends.jsonl")}
    if live:
        env["IMESSAGE_MCP_LIVE"] = "1"
    if no_dialog:
        env["IMESSAGE_MCP_NO_DIALOG"] = "1"
    cfg = config.load(env)
    clock = FakeClock()
    ctx = {"cfg": cfg, "allow": allow, "log": SendLog(cfg.log_path), "store": TokenStore(clock=clock), "clock": clock}
    return ctx


def preview(ctx, msgs, **kw):
    r = preview_send(msgs, cfg=ctx["cfg"], allow=ctx["allow"], log=ctx["log"], store=ctx["store"], now=NOON_THU, **kw)
    assert r["ok"], r
    return r["confirm_token"]


def confirm(ctx, tok, msgs, runner, now=NOON_THU):
    return sender.confirm_send(tok, msgs, cfg=ctx["cfg"], store=ctx["store"], log=ctx["log"], runner=runner,
                               now=lambda: now, clock=ctx["clock"], sleep=ctx["clock"].sleep)


MSGS = [{"phone": "8015550131", "text": TEXT}, {"phone": "8015550134", "text": TEXT}]


# --- dry-run ----------------------------------------------------------------------------------------


def test_dry_run_is_the_default_and_never_calls_messages(tmp_path, synth_db, allow):
    ctx = make(tmp_path, synth_db, allow)
    assert ctx["cfg"].dry_run
    fake = FakeOsascript()
    r = confirm(ctx, preview(ctx, MSGS), MSGS, fake)
    assert fake.calls == []  # NO_DIALOG in dry-run: no dialog, no account check, no send
    assert r["dry_run"] is True and "DRY RUN" in r["note"]
    assert [(x["sent"], x["dry_run"], x["status"]) for x in r["results"]] == [(False, True, "dry_run")] * 2
    assert "success" not in str(r).lower()
    logged = ctx["log"].records()
    assert [(x["name"], x["dry_run"], x["sent"]) for x in logged] == [("Mark Nelson", True, False), ("Grace Whitfield", True, False)]
    assert {x["send_id"] for x in logged} == {x["send_id"] for x in r["results"]}


def test_dry_run_still_shows_the_dialog_labeled_dry_run(tmp_path, synth_db, allow):
    ctx = make(tmp_path, synth_db, allow, no_dialog=False)
    fake = FakeOsascript(button="Send")
    r = confirm(ctx, preview(ctx, MSGS), MSGS, fake)
    assert fake.kinds() == ["dialog"]
    body = fake.calls[0][3]
    assert body.startswith("DRY RUN") and "Mark Nelson  +18015550131  (iMessage)" in body and TEXT in body
    assert fake.calls[0][4] == dialog.TITLE
    assert r["results"][0]["status"] == "dry_run"


@pytest.mark.parametrize("button", ["Cancel", "Timeout", "", subprocess.TimeoutExpired("osascript", 135)])
def test_cancel_or_timeout_sends_nothing(tmp_path, synth_db, allow, button):
    ctx = make(tmp_path, writable_copy(synth_db, tmp_path), allow, live=True, no_dialog=False)
    fake = FakeOsascript(ctx["cfg"].chat_db, button=button, row={})
    r = confirm(ctx, preview(ctx, MSGS), MSGS, fake)
    assert not r["ok"] and r["sent"] is False and "Not sent" in r["error"]
    assert fake.sends() == [] and ctx["log"].records() == []


def test_dialog_script_has_cancel_default_and_gives_up():
    s = dialog.DIALOG_SCRIPT
    assert 'default button "Cancel"' in s and "giving up after 120" in s and 'buttons {"Cancel", "Send"}' in s
    assert "item 1 of argv" in s


def test_dialog_warnings():
    from imessage_mcp.confirm import Row

    rows = [Row("Mark", "+18015550131", "hi", "auto", "iMessage", repeat_of="Thu Nov 12 9:00 AM")]
    text = dialog.build_text(rows, dry_run=True, quiet="Sunday")
    assert "DRY RUN" in text and "QUIET HOURS: it is Sunday" in text and "REPEAT of a message sent Thu Nov 12 9:00 AM" in text


def test_dialog_nonzero_exit_is_cancel():
    def runner(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, "", "not authorized")

    assert dialog.ask("x", runner=runner) == (False, "dialog failed: not authorized")


# --- live (osascript mocked) ----------------------------------------------------------------------


@pytest.fixture
def live(tmp_path, synth_db, allow):
    return make(tmp_path, writable_copy(synth_db, tmp_path), allow, live=True, no_dialog=False)


def test_live_send_passes_phone_and_text_as_argv(live, tmp_path):
    msgs = [{"phone": "(801) 555-0131", "text": TRICKY}]
    fake = FakeOsascript(live["cfg"].chat_db, row={})
    r = confirm(live, preview(live, msgs), msgs, fake)
    assert fake.kinds() == ["account", "dialog", "send"]
    argv = fake.sends()[0]
    assert argv == ["osascript", "-e", sender.SEND_SCRIPT, "+18015550131", TRICKY, "iMessage"]
    assert TRICKY not in sender.SEND_SCRIPT and "O'Neil" not in argv[2]
    assert r["results"][0]["status"] == "delivered" and r["results"][0]["sent"] is True


def test_send_script_matches_spec():
    s = sender.SEND_SCRIPT
    for line in ["set phoneNum to item 1 of argv", "set msg to item 2 of argv", "set svcType to item 3 of argv",
                 "send msg to participant phoneNum of svc", "1st account whose service type = SMS"]:
        assert line in s


@pytest.mark.parametrize(
    "row,status,has_guid",
    [
        ({"is_sent": 1, "is_delivered": 1}, "delivered", True),
        ({"is_sent": 1, "is_delivered": 0}, "sent", True),
        ({"error": 22, "is_sent": 0, "is_delivered": 0}, "failed", True),
        ({"is_sent": 0, "is_delivered": 0}, "unknown", True),
        (None, "unknown", False),
    ],
)
def test_every_delivery_status(live, row, status, has_guid):
    msgs = MSGS[:1]
    fake = FakeOsascript(live["cfg"].chat_db, row=row)
    r = confirm(live, preview(live, msgs), msgs, fake)
    res = r["results"][0]
    assert res["status"] == status
    rec = live["log"].records()[0]
    assert rec["status"] == status and rec["dry_run"] is False and rec["attempted"] is True
    assert bool(rec["guid"]) is has_guid and rec["after_rowid"] > 0
    if status in ("sent", "unknown"):
        assert sum(live["clock"].sleeps) >= sender.DELIVERY_TIMEOUT  # waited the full 15 s
    else:
        assert live["clock"].sleeps == []  # terminal status: stop polling right away
    if status == "failed":
        assert "Not Delivered" in res["error"] and r["ok"] is False
    if row is None:
        assert "15 seconds" in res["error"]


def test_osascript_error_is_failed_and_no_fallback(live):
    msgs = MSGS[:1]
    fake = FakeOsascript(live["cfg"].chat_db, send_rc=1)
    r = confirm(live, preview(live, msgs), msgs, fake)
    assert r["results"][0]["status"] == "failed" and "osascript failed" in r["results"][0]["error"]
    assert len(fake.sends()) == 1  # no automatic SMS retry


def test_explicit_sms_service(live):
    msgs = [{"phone": "8015550131", "text": TEXT, "service": "SMS"}]
    fake = FakeOsascript(live["cfg"].chat_db, row={"is_delivered": 0})
    confirm(live, preview(live, msgs), msgs, fake)
    assert fake.calls[0] == ["osascript", "-e", sender.ACCOUNT_SCRIPT, "SMS"]
    assert fake.sends()[0][5] == "SMS"


def test_mac_state_check_blocks_send(live):
    msgs = MSGS[:1]
    fake = FakeOsascript(live["cfg"].chat_db, accounts="0", row={})
    r = confirm(live, preview(live, msgs), msgs, fake)
    assert not r["ok"] and "signed in" in r["error"]
    assert fake.kinds() == ["account"] and live["log"].records() == []


def test_live_with_no_dialog_is_refused(tmp_path, synth_db, allow):
    with pytest.raises(config.ConfigError):
        make(tmp_path, synth_db, allow, live=True, no_dialog=True)
    cfg = config.Config(**{**config.load({}).__dict__, "live": True, "no_dialog": True})
    with pytest.raises(RuntimeError, match="NO_DIALOG"):
        sender.confirm_send("t", [], cfg=cfg, store=TokenStore(), log=SendLog(tmp_path / "s"), runner=FakeOsascript())


def test_bad_token_never_reaches_dialog(live):
    fake = FakeOsascript(live["cfg"].chat_db, row={})
    r = confirm(live, "nope", MSGS, fake)
    assert not r["ok"] and fake.calls == []


def test_echo_mismatch_never_reaches_dialog(live):
    tok = preview(live, MSGS)
    fake = FakeOsascript(live["cfg"].chat_db, row={})
    r = confirm(live, tok, [MSGS[0] | {"text": "something else"}, MSGS[1]], fake)
    assert "don't match" in r["error"] and fake.calls == []


def test_quiet_hours_rechecked_at_confirm(live):
    tok = preview(live, MSGS)
    fake = FakeOsascript(live["cfg"].chat_db, row={})
    r = confirm(live, tok, MSGS, fake, now=NOON_THU.replace(hour=21, minute=5))
    assert "quiet hours" in r["error"] and fake.calls == []


def test_live_send_then_repeat_is_guarded(live):
    msgs = MSGS[:1]
    confirm(live, preview(live, msgs), msgs, FakeOsascript(live["cfg"].chat_db, row={}))
    r = preview_send(msgs, cfg=live["cfg"], allow=live["allow"], log=live["log"], store=live["store"],
                     now=NOON_THU + timedelta(minutes=5))
    assert not r["ok"] and "allow_repeat" in r["failed_rows"][0]["reason"]


def test_osascript_timeout_counts_as_attempted(live):
    msgs = MSGS[:1]

    class Hang(FakeOsascript):
        def __call__(self, argv, **kw):
            if self._kind(argv) == "send":
                self.calls.append(argv)
                raise subprocess.TimeoutExpired("osascript", 30)
            return super().__call__(argv, **kw)

    r = confirm(live, preview(live, msgs), msgs, Hang(live["cfg"].chat_db))
    assert r["results"][0]["status"] == "unknown"
    assert live["log"].live_sends("+18015550131")  # so the duplicate guard still sees it
