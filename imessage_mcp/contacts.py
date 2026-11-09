"""contacts.csv → allowlist (SPEC §7, §10).

`contacts.csv` (`name,phone`) is filled by hand from LCR with only the people being scheduled. It gates
both sending and reading. Rows whose phone won't normalize are skipped. If two rows normalize to the same
phone (households often share one in LCR), both are reported and that number is neither sendable nor
readable until the file is fixed.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .phones import PhoneError, normalize


@dataclass(frozen=True)
class Contact:
    name: str
    phone: str  # normalized


class NotAllowed(ValueError):
    """The phone isn't usable: invalid, not on the allowlist, or a duplicate in contacts.csv."""


@dataclass
class Allowlist:
    by_phone: dict[str, Contact] = field(default_factory=dict)
    duplicates: dict[str, list[str]] = field(default_factory=dict)  # phone -> names of the clashing rows
    problems: list[str] = field(default_factory=list)  # reported at startup

    def __len__(self) -> int:
        return len(self.by_phone)

    def require(self, raw_phone: object) -> Contact:
        """Normalize and look up a phone, or raise NotAllowed with the reason."""
        try:
            phone = normalize(raw_phone)
        except PhoneError as e:
            raise NotAllowed(str(e)) from None
        if phone in self.duplicates:
            names = ", ".join(self.duplicates[phone])
            raise NotAllowed(
                f"{phone} appears more than once in contacts.csv ({names}). "
                "Fix the file (e.g. one row named 'Smith household') before using this number."
            )
        contact = self.by_phone.get(phone)
        if contact is None:
            raise NotAllowed(f"{phone} is not in contacts.csv (the allowlist). Add it by hand from LCR first.")
        return contact


def load(path: Path) -> Allowlist:
    path = Path(path).expanduser()
    allow = Allowlist()
    if not path.exists():
        allow.problems.append(f"{path} not found: the allowlist is empty, so no number can be sent to or read.")
        return allow

    rows: dict[str, list[str]] = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = [h.strip().lower() for h in (reader.fieldnames or [])]
        if "name" not in fields or "phone" not in fields:
            allow.problems.append(f"{path}: header must be 'name,phone' (got {reader.fieldnames!r}).")
            return allow
        for lineno, raw in enumerate(reader, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k is not None}
            name, phone_raw = row.get("name", ""), row.get("phone", "")
            if not name and not phone_raw:
                continue
            if not name:
                allow.problems.append(f"{path.name} line {lineno}: missing name, row skipped.")
                continue
            try:
                phone = normalize(phone_raw)
            except PhoneError as e:
                allow.problems.append(f"{path.name} line {lineno} ({name}): {e}. Row skipped.")
                continue
            rows.setdefault(phone, []).append(name)

    for phone, names in rows.items():
        if len(names) > 1:
            allow.duplicates[phone] = names
            allow.problems.append(
                f"{path.name}: {phone} is shared by {', '.join(names)}. "
                "Neither row can be sent to or read until only one remains."
            )
        else:
            allow.by_phone[phone] = Contact(names[0], phone)
    return allow
