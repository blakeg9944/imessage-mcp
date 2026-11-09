"""The native confirmation dialog: the real send gate (SPEC §7).

`osascript` shows `display dialog` with Cancel (the default) and Send, giving up after 120 seconds. The
dialog text is passed as an argument (`on run argv`), never pasted into the script. Claude can't click
it, so a confirm token alone can never send. A timeout, Cancel, or any error counts as Cancel.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

GIVE_UP_SECONDS = 120

DIALOG_SCRIPT = f"""on run argv
  set msg to item 1 of argv
  set ttl to item 2 of argv
  try
    set r to display dialog msg with title ttl buttons {{"Cancel", "Send"}} default button "Cancel" cancel button "Cancel" with icon caution giving up after {GIVE_UP_SECONDS}
  on error number -128
    return "Cancel"
  end try
  if gave up of r then return "Timeout"
  return button returned of r
end run"""

TITLE = "iMessage MCP: confirm send"


def build_text(rows, *, dry_run: bool, quiet: str | None) -> str:
    """Dialog body: warnings in caps, then every row (name, number, service, text)."""
    head = []
    if dry_run:
        head.append("DRY RUN: nothing will actually be sent.")
    if quiet:
        head.append(f"QUIET HOURS: it is {quiet}.")
    n = len(rows)
    head.append(f"Send {n} message{'s' if n != 1 else ''}?")
    body = []
    for i, r in enumerate(rows, start=1):
        lines = [f"{i}. {r.name}  {r.phone}  ({r.service})"]
        if r.repeat_of:
            lines.append(f"   REPEAT of a message sent {r.repeat_of}")
        lines.append(f"   “{r.text}”")
        body.append("\n".join(lines))
    return "\n".join(head) + "\n\n" + "\n\n".join(body)


def ask(text: str, *, runner: Callable | None = None) -> tuple[bool, str]:
    """Show the dialog. Returns (approved, outcome) where outcome is Send / Cancel / Timeout / error text."""
    runner = runner or subprocess.run
    try:
        proc = runner(
            ["osascript", "-e", DIALOG_SCRIPT, text, TITLE],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=GIVE_UP_SECONDS + 15,
        )
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except OSError as e:
        return False, f"dialog failed: {e}"
    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return False, f"dialog failed: {(proc.stderr or '').strip() or proc.returncode}"
    return out == "Send", out or "Cancel"
