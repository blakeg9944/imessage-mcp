import sqlite3

from tests import synthetic


def test_generator_builds_a_chat_db(tmp_path):
    paths = synthetic.generate(tmp_path)
    con = sqlite3.connect(paths["chat_db"])
    assert con.execute("SELECT COUNT(*) FROM message").fetchone()[0] > 100
    assert con.execute("SELECT COUNT(*) FROM handle").fetchone()[0] == len(synthetic.CONTACTS) + 1
