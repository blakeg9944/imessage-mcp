import os
from pathlib import Path

import pytest

from imessage_mcp import contacts
from tests import synthetic

ROOT = Path(__file__).resolve().parent.parent

# Tests must never send, show a real dialog, or touch real data. Strip anything inherited.
for _var in ("IMESSAGE_MCP_LIVE", "IMESSAGE_MCP_CHAT_DB", "IMESSAGE_MCP_CONTACTS", "IMESSAGE_MCP_LOG"):
    os.environ.pop(_var, None)
os.environ["IMESSAGE_MCP_NO_DIALOG"] = "1"


@pytest.fixture(scope="session")
def synth_db(tmp_path_factory) -> Path:
    return synthetic.generate(tmp_path_factory.mktemp("synth"))["chat_db"]


@pytest.fixture(scope="session")
def ward() -> dict:
    return synthetic.WARD


@pytest.fixture
def allow() -> contacts.Allowlist:
    return contacts.load(ROOT / "contacts.example.csv")


@pytest.fixture(autouse=True)
def no_real_subprocess(monkeypatch):
    """Any real osascript call (send or dialog) fails the test. Tests pass a fake runner instead."""
    import subprocess

    def refuse(*args, **kwargs):
        raise AssertionError(f"real subprocess.run called in a test: {args!r}")

    monkeypatch.setattr(subprocess, "run", refuse)
