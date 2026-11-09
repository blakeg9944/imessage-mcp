from datetime import time

import pytest

from imessage_mcp import config
from imessage_mcp.config import ConfigError


def test_defaults_are_dry_run():
    cfg = config.load({})
    assert cfg.dry_run and not cfg.live and not cfg.no_dialog
    assert str(cfg.chat_db).endswith("Library/Messages/chat.db")
    assert cfg.contacts == config.PROJECT_ROOT / "contacts.csv"
    assert cfg.log_path == config.PROJECT_ROOT / "logs" / "sends.jsonl"
    assert (cfg.quiet_start, cfg.quiet_end, cfg.block_sunday) == (time(21), time(8), True)


@pytest.mark.parametrize("value", ["", "0", "true", "yes", "TRUE", " 2 "])
def test_only_exactly_1_is_live(value):
    assert config.load({"IMESSAGE_MCP_LIVE": value}).dry_run


def test_live():
    assert config.load({"IMESSAGE_MCP_LIVE": "1"}).live


def test_no_dialog_refused_when_live():
    with pytest.raises(ConfigError, match="Refusing to start"):
        config.load({"IMESSAGE_MCP_LIVE": "1", "IMESSAGE_MCP_NO_DIALOG": "1"})
    assert config.load({"IMESSAGE_MCP_NO_DIALOG": "1"}).no_dialog


def test_overrides(tmp_path):
    cfg = config.load({
        "IMESSAGE_MCP_CHAT_DB": str(tmp_path / "c.db"),
        "IMESSAGE_MCP_CONTACTS": str(tmp_path / "x.csv"),
        "IMESSAGE_MCP_LOG": str(tmp_path / "l.jsonl"),
        "IMESSAGE_MCP_QUIET_HOURS": "22:30-07:15",
        "IMESSAGE_MCP_BLOCK_SUNDAY": "0",
    })
    assert cfg.chat_db == tmp_path / "c.db" and cfg.log_path == tmp_path / "l.jsonl"
    assert (cfg.quiet_start, cfg.quiet_end, cfg.block_sunday) == (time(22, 30), time(7, 15), False)


@pytest.mark.parametrize("env", [{"IMESSAGE_MCP_QUIET_HOURS": "9pm-8am"}, {"IMESSAGE_MCP_BLOCK_SUNDAY": "no"}])
def test_bad_values(env):
    with pytest.raises(ConfigError):
        config.load(env)
