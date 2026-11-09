"""check_replies + the keyword guess (SPEC §6, §9).

For each logged send: the original text, then every reply from that number after the send and before the
next logged live send to that number, including tapbacks. The `guess` is only a hint; Claude makes the
final call from the text. No LLM call happens here.
"""

from __future__ import annotations

import re
import sqlite3

from . import chatdb
from .contacts import Allowlist, NotAllowed
from .sendlog import SendLog, timestamp_of

# Order matters: opt_out wins over everything, then reschedule, then yes / no.
_OPT_OUT = re.compile(
    r"\bstop\b(?!\s+(?:by|in|over|at)\b)|\bunsubscribe\b|\b(?:don'?t|do not) text\b|\bremove me\b",
    re.IGNORECASE,
)
_RESCHEDULE = re.compile(
    r"\binstead\b|\banother (?:time|day)\b|\b(?:a )?different (?:time|day)\b|\bcan'?t make\b|\bcannot make\b"
    r"|\bcan not make\b|\breschedul\w*|\bhow about\b|\bwhat about\b|\bany other (?:time|day)\b",
    re.IGNORECASE,
)
_YES_PHRASES = re.compile(r"\bno (?:problem|worries)\b", re.IGNORECASE)  # "yes" phrases that contain "no"
_YES = re.compile(
    r"\byes\b|\byeah?\b|\byep\b|\byup\b|\bsure\b|\bok(?:ay)?\b|\bsounds good\b|\bthat works\b|\bworks for (?:me|us)\b"
    r"|\b(?:will|we'll|i'll) be there\b|\bsee you\b|\babsolutely\b|\bof course\b|\bperfect\b"
    r"|\bcan (?:both )?(?:come|make it|do (?:it|that))\b|👍",
    re.IGNORECASE,
)
_NO = re.compile(
    r"\bno\b|\bnope\b|\bcan'?t\b|\bcannot\b|\bwon'?t (?:be able|work)\b|\bnot (?:able|available)\b|\bunable\b"
    r"|\bout of town\b|\bdoesn'?t work\b|👎",
    re.IGNORECASE,
)

YES_TAPBACKS = {2000, 2001}  # loved, liked
NO_TAPBACKS = {2002}  # disliked


def _clean(text: str) -> str:
    return text.replace("’", "'").replace("‘", "'")


def guess(texts: list[str], tapbacks_on_sent: list[int] = ()) -> str:
    """yes / no / reschedule / opt_out / unclear from reply texts and tapbacks on the sent message."""
    texts = [_clean(t) for t in texts]
    if any(_OPT_OUT.search(t) for t in texts):
        return "opt_out"
    if any(_RESCHEDULE.search(t) for t in texts):
        return "reschedule"
    yes = any(_YES.search(t) or _YES_PHRASES.search(t) for t in texts) or any(k in YES_TAPBACKS for k in tapbacks_on_sent)
    no = any(_NO.search(_YES_PHRASES.sub("", t)) for t in texts) or any(k in NO_TAPBACKS for k in tapbacks_on_sent)
    if yes and not no:
        return "yes"
    if no and not yes:
        return "no"
    return "unclear"


def check_replies(con: sqlite3.Connection, log: SendLog, allow: Allowlist, send_ids: list) -> list[dict]:
    results = []
    for send_id in send_ids:
        record = log.get(str(send_id))
        if record is None:
            results.append({"send_id": send_id, "error": f"Unknown send_id {send_id!r}: not in the send log."})
            continue
        try:
            contact = allow.require(record["phone"])
        except NotAllowed as e:
            results.append({"send_id": send_id, "error": f"Refused: {e}"})
            continue

        sent_at = timestamp_of(record)
        until = log.next_live_send_after(contact.phone, sent_at, exclude_id=record["send_id"])
        guid = record.get("guid")
        if not guid and record.get("after_rowid") is not None and not record.get("dry_run"):
            row = chatdb.find_sent_row(con, contact.phone, record["after_rowid"])  # found late (was "unknown")
            guid = row["guid"] if row else None

        msgs = chatdb.thread(con, contact.phone, since=sent_at, until=until, include_sent=False)
        replies, texts, tapbacks = [], [], []
        for m in msgs:
            d = m.to_dict()
            d.pop("from")
            if m.is_tapback:
                d["on_sent_message"] = bool(guid) and m.target_guid == guid
                if d["on_sent_message"]:
                    tapbacks.append(m.reaction)
            else:
                texts.append(m.text)
            replies.append(d)

        out = {
            "send_id": record["send_id"],
            "name": contact.name,
            "phone": contact.phone,
            "sent_at": sent_at.isoformat(timespec="seconds"),
            "original_text": record.get("text"),
            "service": record.get("service"),
            "dry_run": bool(record.get("dry_run")),
            "delivery_status": record.get("status"),
            "status": "replied" if replies else "no_reply",
            "guess": guess(texts, tapbacks) if replies else None,
            "replies": replies,
        }
        if until is not None:
            out["window_end"] = until.isoformat(timespec="seconds")
            out["window_note"] = "Replies after the next logged send to this number belong to that send."
        if record.get("dry_run"):
            out["note"] = "DRY RUN: this text was never actually sent, so no reply is expected."
        results.append(out)
    return results
