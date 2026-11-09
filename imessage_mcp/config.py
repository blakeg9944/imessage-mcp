"""Environment variables (SPEC §7, §11).

| Variable | Default | Meaning |
|---|---|---|
| `IMESSAGE_MCP_LIVE` | unset | `1` turns on real sending. Anything else is dry-run. |
| `IMESSAGE_MCP_NO_DIALOG` | unset | `1` skips the native dialog. For pytest; honored only in dry-run. |
| `IMESSAGE_MCP_CHAT_DB` | `~/Library/Messages/chat.db` | chat.db to read (tests point it at the synthetic DB). |
| `IMESSAGE_MCP_QUIET_HOURS` | `21:00-08:00` | No sends in this local-time window. |
| `IMESSAGE_MCP_BLOCK_SUNDAY` | `1` | `1` also blocks sends on Sundays. |
| `IMESSAGE_MCP_CONTACTS` | `<project>/contacts.csv` | The allowlist. |
| `IMESSAGE_MCP_LOG` | `<project>/logs/sends.jsonl` | The send log. |
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    live: bool
    no_dialog: bool
    chat_db: Path
    contacts: Path
    log_path: Path
    quiet_start: time
    quiet_end: time
    block_sunday: bool

    @property
    def dry_run(self) -> bool:
        return not self.live


def _parse_hhmm(s: str) -> time:
    h, m = s.strip().split(":")
    return time(int(h), int(m))


def parse_quiet_hours(value: str) -> tuple[time, time]:
    try:
        start, end = value.split("-")
        return _parse_hhmm(start), _parse_hhmm(end)
    except (ValueError, TypeError):
        raise ConfigError(f"IMESSAGE_MCP_QUIET_HOURS must look like 21:00-08:00 (got {value!r})") from None


DEMO_DIR = PROJECT_ROOT / "demo"
EXAMPLE_CONTACTS_NAME = "contacts.example.csv"


def _is_demo_setup(chat_db: Path, contacts: Path) -> bool:
    """True for the synthetic demo files, which must never be used with live sending."""
    return contacts.name == EXAMPLE_CONTACTS_NAME or chat_db.resolve().is_relative_to(DEMO_DIR.resolve())


def load(env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    live = env.get("IMESSAGE_MCP_LIVE", "").strip() == "1"
    no_dialog = env.get("IMESSAGE_MCP_NO_DIALOG", "").strip() == "1"
    if live and no_dialog:
        raise ConfigError(
            "Refusing to start: IMESSAGE_MCP_LIVE=1 and IMESSAGE_MCP_NO_DIALOG=1 are both set. "
            "The native dialog is the send gate and can only be skipped in dry-run."
        )
    block = env.get("IMESSAGE_MCP_BLOCK_SUNDAY", "1").strip()
    if block not in ("0", "1"):
        raise ConfigError(f"IMESSAGE_MCP_BLOCK_SUNDAY must be 0 or 1 (got {block!r})")
    start, end = parse_quiet_hours(env.get("IMESSAGE_MCP_QUIET_HOURS", "21:00-08:00"))
    chat_db = Path(env.get("IMESSAGE_MCP_CHAT_DB") or "~/Library/Messages/chat.db").expanduser()
    contacts = Path(env.get("IMESSAGE_MCP_CONTACTS") or PROJECT_ROOT / "contacts.csv").expanduser()
    if live and _is_demo_setup(chat_db, contacts):
        raise ConfigError(
            "Refusing to start: IMESSAGE_MCP_LIVE=1 is set on a demo setup (synthetic chat.db or "
            "contacts.example.csv). Live sending only runs on the real `imessage` server with the real "
            "chat.db and contacts.csv."
        )
    return Config(
        live=live,
        no_dialog=no_dialog,
        chat_db=chat_db,
        contacts=contacts,
        log_path=Path(env.get("IMESSAGE_MCP_LOG") or PROJECT_ROOT / "logs" / "sends.jsonl").expanduser(),
        quiet_start=start,
        quiet_end=end,
        block_sunday=block == "1",
    )
