"""A fake osascript and a writable chat.db for send tests. Nothing here touches Messages."""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import uuid
from datetime import datetime

from imessage_mcp import chatdb, dialog, sender


class FakeOsascript:
    """Stands in for subprocess.run. Records every argv; fakes Messages writing the sent row."""

    def __init__(self, db_path=None, *, button="Send", accounts="1", send_rc=0, row=None):
        self.db_path = db_path
        self.button = button  # "Send", "Cancel", "Timeout", or an Exception to raise
        self.accounts = accounts
        self.send_rc = send_rc
        self.row = row  # dict(error=, is_sent=, is_delivered=) to insert on send; None = no row appears
        self.calls: list[list[str]] = []

    def kinds(self):
        return [self._kind(c) for c in self.calls]

    @staticmethod
    def _kind(argv):
        script = argv[2]
        return {sender.SEND_SCRIPT: "send", sender.ACCOUNT_SCRIPT: "account", dialog.DIALOG_SCRIPT: "dialog"}[script]

    def sends(self):
        return [c for c in self.calls if self._kind(c) == "send"]

    def __call__(self, argv, **kwargs):
        assert isinstance(argv, list) and argv[:2] == ["osascript", "-e"], argv
        assert "shell" not in kwargs
        self.calls.append(argv)
        kind = self._kind(argv)
        if kind == "account":
            return subprocess.CompletedProcess(argv, 0, self.accounts + "\n", "")
        if kind == "dialog":
            if isinstance(self.button, BaseException):
                raise self.button
            return subprocess.CompletedProcess(argv, 0, self.button + "\n", "")
        if self.send_rc != 0:
            return subprocess.CompletedProcess(argv, self.send_rc, "", "execution error: Messages got an error (-1700)")
        if self.row is not None:
            insert_sent_row(self.db_path, argv[3], argv[4], argv[5], **self.row)
        return subprocess.CompletedProcess(argv, 0, "", "")


def writable_copy(src, tmp_path):
    dest = tmp_path / "chat.db"
    shutil.copy(src, dest)
    return dest


def insert_sent_row(db_path, phone, text, service, *, error=0, is_sent=1, is_delivered=1):
    """What Messages does after a send: an outgoing row with text NULL (as step 0 showed)."""
    from imessage_mcp import attributed_body

    con = sqlite3.connect(db_path)
    handle = next(r for r in con.execute("SELECT ROWID, id FROM handle") if chatdb.try_normalize(r[1]) == phone)[0]
    chat = con.execute("SELECT chat_id FROM chat_handle_join WHERE handle_id = ?", (handle,)).fetchone()[0]
    when = chatdb.to_apple(datetime.now().astimezone())
    cur = con.execute(
        "INSERT INTO message (guid, text, attributedBody, handle_id, service, date, is_from_me, error, is_sent,"
        " is_delivered) VALUES (?, NULL, ?, ?, ?, ?, 1, ?, ?, ?)",
        (str(uuid.uuid4()).upper(), attributed_body.encode(text), handle, service, when, error, is_sent, is_delivered),
    )
    con.execute("INSERT INTO chat_message_join VALUES (?, ?, ?)", (chat, cur.lastrowid, when))
    con.commit()
    con.close()


class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s
