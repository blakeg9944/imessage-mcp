"""Phone normalization (SPEC §10).

Every phone input is normalized to `+1XXXXXXXXXX`. Spaces, dashes, dots and parentheses are
stripped; 10 digits, or `1` + 10 digits, with or without a leading `+`, are accepted. Anything
else (international numbers, short codes, emails, wrong digit count) is rejected.
"""

from __future__ import annotations

import re

_STRIP = re.compile(r"[\s\-.()]")


class PhoneError(ValueError):
    """Raised when a phone input can't be normalized. The message names the bad input."""


def normalize(raw: object) -> str:
    if not isinstance(raw, str):
        raise PhoneError(f"Invalid phone number {raw!r}: expected a string")
    s = _STRIP.sub("", raw)
    plus = s.startswith("+")
    digits = s[1:] if plus else s
    if not digits.isdigit() or not digits.isascii():
        raise PhoneError(f"Invalid phone number {raw!r}: only US numbers like (801) 555-0142 are accepted")
    if len(digits) == 10 and not plus:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    raise PhoneError(
        f"Invalid phone number {raw!r}: expected 10 digits or 1 + 10 digits (US numbers only)"
    )


def try_normalize(raw: object) -> str | None:
    """Normalize, or return None. Used for chat.db handles, which may be emails."""
    try:
        return normalize(raw)
    except PhoneError:
        return None
