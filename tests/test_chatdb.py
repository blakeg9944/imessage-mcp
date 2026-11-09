import sqlite3
from datetime import datetime, timedelta

import pytest

from imessage_mcp import chatdb, contacts
from tests import synthetic
from tests.synthetic import INVITE, WARD_SEND_AT


@pytest.fixture
def con(synth_db):
    with chatdb.connect(synth_db) as c:
        yield c


def test_connection_is_read_only(con):
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        con.execute("DELETE FROM message")


def test_missing_db_gives_full_disk_access_help(tmp_path):
    with pytest.raises(chatdb.ChatDBError, match="Full Disk Access"):
        with chatdb.connect(tmp_path / "nope.db"):
            pass


def test_apple_time_round_trip():
    dt = datetime(2026, 11, 5, 18, 30).astimezone()
    assert chatdb.from_apple(chatdb.to_apple(dt)) == dt
    assert chatdb.from_apple(0) is None


def test_parse_since():
    now = datetime(2026, 11, 8, 12, 0).astimezone()
    assert chatdb.parse_since("2d", now) == now - timedelta(days=2)
    assert chatdb.parse_since("6h", now) == now - timedelta(hours=6)
    assert chatdb.parse_since(None) is None
    assert chatdb.parse_since("2026-11-05T18:00").hour == 18
    assert chatdb.parse_since("2026-11-05T18:00:00Z").utcoffset() == timedelta(0)
    with pytest.raises(ValueError, match="Invalid since"):
        chatdb.parse_since("yesterday")


def test_handles_match_normalized_ids_and_never_emails(con):
    assert len(chatdb.handles_for(con, "+18015550132")) == 1  # stored as bare "8015550132"
    assert chatdb.handles_for(con, "+18015550199")  # synthetic friend, stored as +1
    for h in con.execute("SELECT id FROM handle WHERE id LIKE '%@%'"):
        assert chatdb.try_normalize(h[0]) is None


def test_decodes_attributed_body_when_text_is_null(con, ward):
    msgs = chatdb.thread(con, ward["yes"].phone, since=WARD_SEND_AT - timedelta(seconds=1))
    sent = [m for m in msgs if m.from_me]
    assert sent[0].text == INVITE  # text column NULL, decoded from attributedBody
    assert con.execute("SELECT text FROM message WHERE guid = ?", (sent[0].guid,)).fetchone()[0] is None


def test_thread_is_one_to_one_only(con, ward):
    texts = [m.text for m in chatdb.thread(con, ward["yes"].phone)]
    assert "Yes, that works!" in texts
    assert "Yes I'll bring the rolls" not in texts  # group chat message ignored


def test_tapback_rendered_and_linked(con, ward):
    msgs = chatdb.thread(con, ward["tapback"].phone, include_sent=False)
    assert len(msgs) == 1
    tb = msgs[0]
    assert tb.reaction == 2001
    assert tb.target_guid == synthetic.WARD_SENT_GUIDS["tapback"]
    assert tb.text == f'👍 Liked "{INVITE}"'
    assert tb.to_dict()["tapback"] == "liked"


def test_removed_reaction_cancels(con, ward):
    msgs = chatdb.thread(con, ward["no_reply"].phone, since=WARD_SEND_AT, include_sent=False)
    assert msgs == []


class _Row(dict):
    """Stands in for sqlite3.Row in unit tests."""


class _NoTargets:
    def execute(self, *args):
        return self

    def fetchall(self):
        return []


def _reaction(rowid, kind, assoc, emoji=None):
    return _Row(ROWID=rowid, guid=f"g{rowid}", text=None, attributedBody=None, is_from_me=0, date=10**18,
                service="iMessage", cache_has_attachments=0, associated_message_guid=assoc,
                associated_message_type=kind, associated_message_emoji=emoji)


def test_reaction_variants_and_removal():
    rows = [
        _reaction(1, 2006, "p:0/X", emoji="🙏"),  # custom emoji
        _reaction(2, 2002, "p:0/X"),
        _reaction(3, 3002, "p:0/X"),  # removes the dislike
        _reaction(4, 2005, "bp:Y"),
    ]
    msgs = chatdb._build(_NoTargets(), rows)
    assert [m.text for m in msgs] == ["🙏 Reacted to a message", "❓ Questioned a message"]
    assert msgs[1].target_guid == "Y"


def test_attachments_rendered():
    class R(dict):
        pass

    r = R(text="￼look", attributedBody=None, cache_has_attachments=1)
    assert chatdb.decode_text(r) == "[attachment]look"
    assert chatdb.decode_text(R(text=None, attributedBody=None, cache_has_attachments=1)) == "[attachment]"


def test_last_message(con, ward):
    last = chatdb.last_message(con, ward["yes"].phone)
    assert last.text == "See you then"
    assert chatdb.last_message(con, "+18015550100") is None


def test_service_choice(con, ward):
    assert chatdb.choose_service(con, ward["reschedule"].phone) == "SMS"  # SMS-only history
    assert chatdb.choose_service(con, ward["yes"].phone) == "iMessage"
    assert chatdb.choose_service(con, "+18015550100") == "iMessage"  # no history


def test_delivery_lookup_by_rowid(con, ward):
    guid = synthetic.WARD_SENT_GUIDS["yes"]
    rowid = con.execute("SELECT ROWID FROM message WHERE guid = ?", (guid,)).fetchone()[0]
    row = chatdb.find_sent_row(con, ward["yes"].phone, rowid - 1)
    assert row["guid"] == guid
    assert chatdb.delivery_status(row) == "delivered"
    assert chatdb.find_sent_row(con, ward["yes"].phone, chatdb.max_rowid(con)) is None


@pytest.mark.parametrize("key,status", [("yes", "delivered"), ("reschedule", "sent"), ("failed", "failed")])
def test_delivery_status_from_synthetic_rows(con, ward, key, status):
    guid = synthetic.WARD_SENT_GUIDS[key]
    rowid = con.execute("SELECT ROWID FROM message WHERE guid = ?", (guid,)).fetchone()[0]
    assert chatdb.delivery_status(chatdb.find_sent_row(con, ward[key].phone, rowid - 1)) == status


def test_delivery_status_unknown():
    assert chatdb.delivery_status(None) == "unknown"
    assert chatdb.delivery_status({"error": 0, "is_delivered": 0, "is_sent": 0}) == "unknown"


def test_get_replies_allowlist_only(con, allow, ward):
    res = chatdb.get_replies(con, allow, ["(801) 555-0131", "8015550199", "nope"], since=WARD_SEND_AT)
    assert res[0]["name"] == "Mark Nelson"
    assert [m["text"] for m in res[0]["messages"]] == ["Yes, that works!", "See you then"]
    assert all(m["from"] == "them" for m in res[0]["messages"])
    assert "not in contacts.csv" in res[1]["error"] and res[1]["messages"] == []
    assert "Invalid phone" in res[2]["error"]


def test_get_replies_refuses_duplicate_household(con, tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("name,phone\nJohn Smith,8015550137\nJane Smith,801-555-0137\n")
    res = chatdb.get_replies(con, contacts.load(p), ["8015550137"], since=WARD_SEND_AT)
    assert "more than once" in res[0]["error"]


def test_get_replies_since_defaults(con, allow, ward):
    phone = ward["no"].phone
    res = chatdb.get_replies(con, allow, [phone], default_since=lambda p: WARD_SEND_AT)
    assert res[0]["since_source"] == "last logged live send"
    assert [m["text"] for m in res[0]["messages"]] == ["No sorry, we'll be out of town this weekend"]
    res = chatdb.get_replies(con, allow, [phone], now=WARD_SEND_AT + timedelta(days=30))
    assert res[0]["messages"] == [] and "7 days" in res[0]["since_source"]


def test_get_replies_include_sent(con, allow, ward):
    res = chatdb.get_replies(con, allow, [ward["no"].phone], since=WARD_SEND_AT - timedelta(seconds=1), include_sent=True)
    assert [m["from"] for m in res[0]["messages"]] == ["me", "them"]
