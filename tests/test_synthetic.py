import sqlite3

from imessage_mcp import contacts
from tests import synthetic


def test_generator_builds_a_chat_db(tmp_path):
    paths = synthetic.generate(tmp_path)
    con = sqlite3.connect(paths["chat_db"])
    assert con.execute("SELECT COUNT(*) FROM message").fetchone()[0] > 100
    n_handles = len(synthetic.CONTACTS) + len(synthetic.UNKNOWN_HANDLES) + len(synthetic.WARD)
    assert con.execute("SELECT COUNT(*) FROM handle").fetchone()[0] == n_handles


def test_ward_matches_example_contacts():
    allow = contacts.load(synthetic.Path(__file__).resolve().parent.parent / "contacts.example.csv")
    assert {c.phone: c.name for c in allow.by_phone.values()} == {m.phone: m.name for m in synthetic.WARD.values()}


def test_ward_sendlog_has_guids(tmp_path):
    synthetic.generate(tmp_path)
    log = synthetic.ward_sendlog()
    assert all(r["guid"] for r in log if r["send_id"] != "synth-yes-reminder")
