from pathlib import Path

import pytest

from imessage_mcp import contacts
from imessage_mcp.contacts import NotAllowed

ROOT = Path(__file__).resolve().parent.parent


def write(tmp_path, text):
    p = tmp_path / "contacts.csv"
    p.write_text(text, encoding="utf-8")
    return p


def test_loads_and_normalizes(tmp_path):
    allow = contacts.load(write(tmp_path, "name,phone\nJake Morales,(801) 555-0142\nSam Chen,385.555.0178\n"))
    assert allow.problems == []
    assert allow.require("801-555-0142") == contacts.Contact("Jake Morales", "+18015550142")
    assert allow.require("+13855550178").name == "Sam Chen"


def test_header_case_whitespace_and_bom(tmp_path):
    allow = contacts.load(write(tmp_path, "﻿Name , Phone\n  Jake  , 8015550142 \n\n"))
    assert allow.require("8015550142").name == "Jake"
    assert allow.problems == []


def test_duplicate_phones_block_both_rows(tmp_path):
    allow = contacts.load(
        write(tmp_path, "name,phone\nJohn Smith,801-555-0160\nJane Smith,(801) 555 0160\nSam,3855550178\n")
    )
    assert "+18015550160" not in allow.by_phone
    assert allow.duplicates == {"+18015550160": ["John Smith", "Jane Smith"]}
    assert any("John Smith" in p and "Jane Smith" in p for p in allow.problems)
    with pytest.raises(NotAllowed, match="more than once"):
        allow.require("8015550160")
    assert allow.require("3855550178").name == "Sam"


def test_bad_rows_reported_and_skipped(tmp_path):
    allow = contacts.load(
        write(tmp_path, "name,phone\nIntl,+44 20 7183 8750\n,8015550142\nEmail,a@b.com\nOk,8015550199\n")
    )
    assert list(allow.by_phone) == ["+18015550199"]
    assert len(allow.problems) == 3
    assert any("line 2" in p and "Intl" in p for p in allow.problems)


def test_not_on_allowlist_and_invalid_input(tmp_path):
    allow = contacts.load(write(tmp_path, "name,phone\nJake,8015550142\n"))
    with pytest.raises(NotAllowed, match="not in contacts.csv"):
        allow.require("8015550199")
    with pytest.raises(NotAllowed, match="Invalid phone"):
        allow.require("hello")


def test_missing_file_is_empty_allowlist(tmp_path):
    allow = contacts.load(tmp_path / "nope.csv")
    assert len(allow) == 0
    assert "not found" in allow.problems[0]


def test_bad_header(tmp_path):
    allow = contacts.load(write(tmp_path, "who,number\nJake,8015550142\n"))
    assert len(allow) == 0
    assert "header" in allow.problems[0]


def test_example_file_is_clean():
    allow = contacts.load(ROOT / "contacts.example.csv")
    assert allow.problems == []
    assert len(allow) == 8
