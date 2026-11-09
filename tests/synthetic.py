"""Generate a fake chat.db + AddressBook that mimic Apple's schemas.

Used for development, tests, and the on-screen demo, so no real messages are ever needed
outside the user's own Mac. The data mixes planted "findable" storylines (a wifi password,
a restaurant recommendation, a goat incident...) with lots of realistic filler chatter.

Copied from ~/imessage-search-project and extended for imessage-mcp with ward interview threads
(`_ward_threads`, SPEC §11) and the delivery columns (`error`, `is_sent`, `is_delivered`). Run
`python -m tests.synthetic OUT_DIR` to write a demo chat.db plus a matching demo send log.
"""

from __future__ import annotations

import random
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from imessage_mcp import attributed_body

TZ = ZoneInfo("America/Denver")
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=ZoneInfo("UTC"))
OBJ = "￼"  # object replacement char Messages puts where an attachment sits


@dataclass(frozen=True)
class Contact:
    key: str
    first: str
    last: str | None
    handle: str  # phone (E.164) or email


CONTACTS = [
    Contact("jake", "Jake", "Morales", "+18015550142"),
    Contact("sam", "Sam", "Chen", "+13855550178"),
    Contact("priya", "Priya", "Patel", "priya.patel@example.com"),
    Contact("tyler", "Tyler", "Brooks", "+18015550199"),
    Contact("emma", "Emma", "Larsen", "+18015550123"),
    Contact("mom", "Mom", None, "+14355550111"),
    Contact("dad", "Dad", None, "+14355550112"),
    Contact("lily", "Lily", "Grant", "+14355550113"),
]
# Handles that are NOT saved in Contacts, so they show up as raw numbers.
UNKNOWN_HANDLES = {"dentist": "+18015550987"}

# chat key -> (display_name, member keys). 1:1 chats have no display name.
CHATS = {
    **{c.key: (None, [c.key]) for c in CONTACTS},
    "dentist": (None, ["dentist"]),
    "apt": ("Apartment Hunt 🏠", ["emma", "tyler"]),
    "fam": ("Fam", ["mom", "dad", "lily"]),
    "crew": (None, ["jake", "sam", "tyler"]),
}

# Planted storylines: (chat, local start time, [(speaker, text), ...]). "me" = the phone owner.
STORIES: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("jake", "2026-03-12 19:05", [
        ("jake", "ok you HAVE to try sabor oaxaqueño on 4th street"),
        ("jake", "the mole negro is unreal"),
        ("jake", "go on a weeknight tho, weekends the wait is like an hour"),
        ("me", "adding it to the list"),
    ]),
    ("sam", "2026-05-20 21:40", [
        ("sam", "so i did it"),
        ("sam", "put in my two weeks today"),
        ("me", "WAIT what"),
        ("me", "at the firm??"),
        ("sam", "yeah. couldn't do another year of 70 hour weeks"),
        ("sam", "starting at a nonprofit in july, way less money but i'm actually excited"),
        ("me", "dude that's huge, proud of you"),
    ]),
    ("emma", "2026-08-24 16:12", [
        ("me", "what's the wifi again"),
        ("emma", "network is LarsenNet 5G"),
        ("emma", "password BlueHeron_2291"),
        ("me", "ty"),
    ]),
    ("priya", "2026-06-02 11:20", [
        ("priya", "address for saturday is 1847 W Canyon Rd apt 12"),
        ("priya", "park on the street, the lot is permit only"),
        ("me", "perfect see you then"),
    ]),
    ("tyler", "2026-04-07 13:02", [
        ("tyler", "dude a goat got loose in the parking lot at work"),
        ("tyler", "it ATE part of my windshield wiper"),
        ("tyler", "like chewed it right off"),
        ("me", "😂😂 im crying"),
        ("tyler", "animal control took 2 hours to show up"),
    ]),
    ("jake", "2026-09-30 12:15", [
        ("jake", "we should grab tacos friday"),
        ("jake", "that place by campus"),
        ("me", "down, 7?"),
        ("jake", "7 works"),
    ]),
    ("apt", "2026-02-03 20:30", [
        ("emma", "ok the one on 900 E was $1650 but no washer"),
        ("tyler", "no washer is a dealbreaker for me"),
        ("me", "agreed, the maple st one had in-unit laundry"),
        ("emma", "landlord for the maple st place wants first + last + deposit"),
        ("tyler", "oof that's like 5k upfront"),
    ]),
    ("apt", "2026-02-10 18:45", [
        ("emma", "they accepted our application!!"),
        ("me", "LETS GO"),
        ("emma", "lease signing is the 15th at 4pm at their office"),
        ("tyler", "i'll be there"),
    ]),
    ("mom", "2026-10-05 09:30", [
        ("mom", "Are you coming home for Thanksgiving?"),
        ("mom", "Dad wants to know if he should buy you a ticket"),
        ("me", "yes! fly in wednesday if that works"),
        ("mom", "Done. Confirmation is QX7RTP, Delta, lands at 3:40"),
        ("me", "thank you!! ❤️"),
    ]),
    ("fam", "2026-04-18 15:10", [
        ("lily", "I GOT IN"),
        ("lily", "the nursing program at weber accepted me"),
        ("mom", "SO proud of you sweetheart!!"),
        ("dad", "Way to go kiddo"),
        ("me", "LILY!!! congrats"),
    ]),
    ("dentist", "2026-11-01 10:00", [
        ("dentist", "Reminder: your appointment with Dr. Hale is Tue Nov 10 at 9:30 AM. Reply C to confirm."),
        ("me", "C"),
    ]),
    ("priya", "2026-09-10 14:05", [
        ("priya", "here's the doc for the group project https://docs.example.com/d/8f2k-group-proposal"),
        ("priya", "can you take the methods section?"),
        ("me", "yep on it"),
    ]),
    ("tyler", "2026-07-14 22:10", [
        ("tyler", "you'd love this podcast about a guy who sailed around the world solo"),
        ("tyler", "it's called Alone At Sea, episode 4 is the craziest"),
        ("me", "downloading now"),
    ]),
    ("emma", "2026-09-03 19:22", [
        ("emma", "can you venmo me 42.18 for groceries"),
        ("me", "sent!"),
    ]),
    ("crew", "2026-08-07 20:00", [
        ("jake", "hike saturday?"),
        ("sam", "im in"),
        ("tyler", "trailhead at 6am, bring headlamps"),
        ("me", "6am is criminal but ok"),
    ]),
]

FILLER_SHORT = [
    "lol", "omw", "haha", "yeah", "same", "😂", "no way", "ugh", "ty!", "np", "k", "wait really?",
    "i'm down", "ok sounds good", "100%", "lmao", "yep", "nice", "hahaha", "true", "ok", "👍",
]
FILLER_LONG = [
    "did you see the game last night", "i'm so tired today", "running 10 min late sorry",
    "can you call me when you get a sec", "this class is killing me", "what time is the thing tonight",
    "lmk when you're home", "just got out of class", "can't tonight sorry, too much homework",
    "good luck on your exam!", "made it home", "did you eat yet", "send me that pic", "ill check and get back to you",
    "are you going to the devotional", "my car is making that noise again", "we need more paper towels",
    "how was your weekend", "that midterm was brutal", "want to study at the library later",
    "i'm at the store, need anything?", "happy birthday!! 🎉", "miss you guys", "call you after work",
    "the parking situation on campus is so bad", "did you finish the reading", "free for lunch tomorrow?",
]
FILLER_FAMILY = [
    "Call me when you can", "Love you!", "How is school going?", "Don't forget to call grandma",
    "Did you get the package?", "We're so proud of you", "Drive safe", "Sunday dinner at 5?",
]


def _apple_ns(dt: datetime) -> int:
    return int((dt - APPLE_EPOCH).total_seconds() * 1_000_000_000)


def _create_chat_db(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE handle (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL, service TEXT,
            uncanonicalized_id TEXT);
        CREATE TABLE chat (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, guid TEXT UNIQUE NOT NULL, style INTEGER,
            chat_identifier TEXT, service_name TEXT, display_name TEXT);
        CREATE TABLE message (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, guid TEXT UNIQUE NOT NULL, text TEXT,
            attributedBody BLOB, handle_id INTEGER DEFAULT 0, service TEXT, date INTEGER, date_read INTEGER,
            is_from_me INTEGER DEFAULT 0, cache_has_attachments INTEGER DEFAULT 0, item_type INTEGER DEFAULT 0,
            associated_message_guid TEXT, associated_message_type INTEGER DEFAULT 0,
            thread_originator_guid TEXT, balloon_bundle_id TEXT, error INTEGER DEFAULT 0,
            is_sent INTEGER DEFAULT 0, is_delivered INTEGER DEFAULT 0, date_delivered INTEGER DEFAULT 0,
            associated_message_emoji TEXT);
        CREATE TABLE chat_handle_join (chat_id INTEGER, handle_id INTEGER, UNIQUE(chat_id, handle_id));
        CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER, message_date INTEGER DEFAULT 0,
            PRIMARY KEY (chat_id, message_id));
        CREATE TABLE attachment (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, guid TEXT UNIQUE NOT NULL,
            filename TEXT, mime_type TEXT, transfer_name TEXT);
        CREATE TABLE message_attachment_join (message_id INTEGER, attachment_id INTEGER,
            UNIQUE(message_id, attachment_id));
        """
    )
    return con


def _create_addressbook(root: Path) -> None:
    source = root / "Sources" / str(uuid.UUID(int=0x5EED))
    source.mkdir(parents=True, exist_ok=True)
    db = source / "AddressBook-v22.abcddb"
    db.unlink(missing_ok=True)
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE ZABCDRECORD (Z_PK INTEGER PRIMARY KEY, ZFIRSTNAME TEXT, ZLASTNAME TEXT, ZNICKNAME TEXT,
            ZORGANIZATION TEXT);
        CREATE TABLE ZABCDPHONENUMBER (Z_PK INTEGER PRIMARY KEY, ZOWNER INTEGER, ZFULLNUMBER TEXT);
        CREATE TABLE ZABCDEMAILADDRESS (Z_PK INTEGER PRIMARY KEY, ZOWNER INTEGER, ZADDRESS TEXT);
        """
    )
    for pk, c in enumerate(CONTACTS, start=1):
        con.execute("INSERT INTO ZABCDRECORD VALUES (?, ?, ?, NULL, NULL)", (pk, c.first, c.last))
        if "@" in c.handle:
            con.execute("INSERT INTO ZABCDEMAILADDRESS (ZOWNER, ZADDRESS) VALUES (?, ?)", (pk, c.handle))
        else:
            # Contacts stores numbers the way the user typed them.
            d = c.handle[-10:]
            con.execute(
                "INSERT INTO ZABCDPHONENUMBER (ZOWNER, ZFULLNUMBER) VALUES (?, ?)",
                (pk, f"({d[:3]}) {d[3:6]}-{d[6:]}"),
            )
    con.commit()
    con.close()


class _Writer:
    def __init__(self, con: sqlite3.Connection, rng: random.Random):
        self.con = con
        self.rng = rng
        self.handle_ids: dict[str, int] = {}
        self.chat_ids: dict[str, int] = {}

    def setup(self) -> None:
        handles = {c.key: c.handle for c in CONTACTS} | UNKNOWN_HANDLES
        for key, h in handles.items():
            cur = self.con.execute(
                "INSERT INTO handle (id, service, uncanonicalized_id) VALUES (?, 'iMessage', ?)", (h, h)
            )
            self.handle_ids[key] = cur.lastrowid
        for key, (name, members) in CHATS.items():
            group = len(members) > 1
            ident = f"chat{self.rng.randrange(10**17, 10**18)}" if group else handles[members[0]]
            cur = self.con.execute(
                "INSERT INTO chat (guid, style, chat_identifier, service_name, display_name)"
                " VALUES (?, ?, ?, 'iMessage', ?)",
                (f"iMessage;{'+' if group else '-'};{ident}", 43 if group else 45, ident, name or ""),
            )
            self.chat_ids[key] = cur.lastrowid
            for m in members:
                self.con.execute("INSERT INTO chat_handle_join VALUES (?, ?)", (cur.lastrowid, self.handle_ids[m]))

    def message(
        self,
        chat: str,
        speaker: str,
        text: str | None,
        when: datetime,
        *,
        item_type: int = 0,
        assoc: tuple[int, str] | None = None,
        attachment: bool = False,
    ) -> str:
        guid = str(uuid.UUID(int=self.rng.getrandbits(128))).upper()
        from_me = speaker == "me"
        # Mimic how storage changed across macOS versions: mostly attributedBody-only or both,
        # occasionally the old text-only layout.
        roll = self.rng.random()
        if text is None:
            col_text, body = None, None
        elif roll < 0.45:
            col_text, body = None, attributed_body.encode(text)
        elif roll < 0.95:
            col_text, body = text, attributed_body.encode(text)
        else:
            col_text, body = text, None
        cur = self.con.execute(
            "INSERT INTO message (guid, text, attributedBody, handle_id, service, date, is_from_me,"
            " cache_has_attachments, item_type, associated_message_guid, associated_message_type)"
            " VALUES (?, ?, ?, ?, 'iMessage', ?, ?, ?, ?, ?, ?)",
            (
                guid,
                col_text,
                body,
                0 if from_me else self.handle_ids[speaker],
                _apple_ns(when),
                int(from_me),
                int(attachment),
                item_type,
                f"p:0/{assoc[1]}" if assoc else None,
                assoc[0] if assoc else 0,
            ),
        )
        self.con.execute(
            "INSERT INTO chat_message_join VALUES (?, ?, ?)", (self.chat_ids[chat], cur.lastrowid, _apple_ns(when))
        )
        if attachment:
            a = self.con.execute(
                "INSERT INTO attachment (guid, filename, mime_type, transfer_name) VALUES (?, ?, 'image/jpeg', ?)",
                (f"at_{guid}", f"~/Library/Messages/Attachments/xx/{guid}/IMG.jpeg", "IMG.jpeg"),
            )
            self.con.execute("INSERT INTO message_attachment_join VALUES (?, ?)", (cur.lastrowid, a.lastrowid))
        return guid

    def turn(self, chat: str, speaker: str, text: str, when: datetime) -> None:
        guid = self.message(chat, speaker, text, when)
        if self.rng.random() < 0.08:  # tapback reaction from someone else
            members = ["me", *CHATS[chat][1]]
            reactor = self.rng.choice([m for m in members if m != speaker])
            kind, verb = self.rng.choice([(2000, "Loved"), (2001, "Liked"), (2003, "Laughed at")])
            self.message(chat, reactor, f"{verb} “{text}”", when + timedelta(seconds=40), assoc=(kind, guid))


def _session(w: _Writer, chat: str, start: datetime, lines: list[tuple[str, str]]) -> None:
    t = start
    for speaker, text in lines:
        w.turn(chat, speaker, text, t)
        t += timedelta(seconds=w.rng.randint(15, 240))


def _filler_lines(rng: random.Random, chat: str) -> list[tuple[str, str]]:
    members = CHATS[chat][1]
    family = chat in ("mom", "dad", "fam")
    speakers = ["me", *members]
    lines = []
    for _ in range(rng.randint(2, 10)):
        r = rng.random()
        if family and r < 0.35:
            text = rng.choice(FILLER_FAMILY)
        elif r < 0.55:
            text = rng.choice(FILLER_SHORT)
        else:
            text = rng.choice(FILLER_LONG)
        lines.append((rng.choice(speakers), text))
    return lines


# ---------------------------------------------------------------------------------------------------
# Ward interview threads (added for imessage-mcp, SPEC §11). Every name and number here is fake; the
# numbers are in the 555-01xx range reserved for fiction. contacts.example.csv lists the same people.

INVITE = "Could you meet with the bishopric Sunday at 7:00?"
REMINDER = "Reminder: Sunday at 7:00 with the bishopric. See you then!"
WARD_SEND_AT = datetime(2026, 11, 5, 18, 30, tzinfo=TZ)
WARD_SECOND_SEND_AT = datetime(2026, 11, 6, 12, 0, tzinfo=TZ)


@dataclass(frozen=True)
class WardMember:
    key: str
    name: str
    phone: str  # normalized
    handle_id: str  # how chat.db stores it
    service: str = "iMessage"


WARD = {
    m.key: m
    for m in [
        WardMember("yes", "Mark Nelson", "+18015550131", "+18015550131"),
        WardMember("no", "Ruth Okafor", "+18015550132", "8015550132"),  # stored as bare digits
        WardMember("reschedule", "David Tanaka", "+18015550133", "+18015550133", "SMS"),  # SMS-only
        WardMember("tapback", "Grace Whitfield", "+18015550134", "+18015550134"),
        WardMember("opt_out", "Paul Ferreira", "+18015550135", "+18015550135"),
        WardMember("no_reply", "Anna Lindqvist", "+18015550136", "+18015550136"),
        WardMember("household", "Smith household", "+18015550137", "+18015550137"),
        WardMember("failed", "Lucy Abara", "+18015550138", "+18015550138"),
    ]
}

# member key -> [(minutes after WARD_SEND_AT, text)]
WARD_REPLIES = {
    "yes": [(12, "Yes, that works!")],
    "no": [(40, "No sorry, we'll be out of town this weekend")],
    "reschedule": [(5, "can we do 7:30 instead?")],
    "opt_out": [(90, "please stop texting me")],
    "household": [(25, "This is Jane, John and I can both come")],
}


def _ward_threads(w: _Writer) -> None:
    con = w.con
    sent_guids: dict[str, str] = {}
    ward_handles: dict[str, int] = {}
    for m in WARD.values():
        cur = con.execute(
            "INSERT INTO handle (id, service, uncanonicalized_id) VALUES (?, ?, ?)", (m.handle_id, m.service, None)
        )
        ward_handles[m.key] = cur.lastrowid
        chat = con.execute(
            "INSERT INTO chat (guid, style, chat_identifier, service_name, display_name) VALUES (?, 45, ?, ?, '')",
            (f"{m.service};-;{m.handle_id}", m.handle_id, m.service),
        )
        con.execute("INSERT INTO chat_handle_join VALUES (?, ?)", (chat.lastrowid, cur.lastrowid))
        w.chat_ids[f"ward:{m.key}"] = chat.lastrowid

    def put(key, from_me, text, when, *, error=0, sent=1, delivered=1, assoc=None, text_col=None):
        m = WARD[key]
        guid = str(uuid.UUID(int=w.rng.getrandbits(128))).upper()
        cur = con.execute(
            "INSERT INTO message (guid, text, attributedBody, handle_id, service, date, is_from_me, error, is_sent,"
            " is_delivered, date_delivered, associated_message_guid, associated_message_type)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                guid,
                text_col,
                attributed_body.encode(text),
                ward_handles[key],
                m.service,
                _apple_ns(when),
                int(from_me),
                error,
                int(from_me and sent),
                int(from_me and delivered),
                _apple_ns(when) if from_me and delivered else 0,
                f"p:0/{assoc[1]}" if assoc else None,
                assoc[0] if assoc else 0,
            ),
        )
        con.execute(
            "INSERT INTO chat_message_join VALUES (?, ?, ?)", (w.chat_ids[f"ward:{key}"], cur.lastrowid, _apple_ns(when))
        )
        return guid

    # An older, unrelated exchange before the send: must not count as a reply.
    put("no_reply", True, "Thanks for helping with the move!", WARD_SEND_AT - timedelta(days=9))
    put("no_reply", False, "Happy to help, anytime", WARD_SEND_AT - timedelta(days=9, minutes=-30), text_col="Happy to help, anytime")
    put("yes", False, "Do you know when the ward party is?", WARD_SEND_AT - timedelta(days=3))

    for i, key in enumerate(WARD):
        when = WARD_SEND_AT + timedelta(seconds=i)
        if key == "failed":
            # A send that Messages accepted and then failed ("Not Delivered").
            sent_guids[key] = put(key, True, INVITE, when, error=22, sent=0, delivered=0)
        elif WARD[key].service == "SMS":
            sent_guids[key] = put(key, True, INVITE, when, delivered=0)  # SMS: sent, no delivery receipt
        else:
            sent_guids[key] = put(key, True, INVITE, when)

    for key, replies in WARD_REPLIES.items():
        for minutes, text in replies:
            put(key, False, text, WARD_SEND_AT + timedelta(minutes=minutes), text_col=text if key == "no" else None)

    # 👍 tapback only.
    put("tapback", False, f"Liked “{INVITE}”", WARD_SEND_AT + timedelta(minutes=3), assoc=(2001, sent_guids["tapback"]))
    # Loved, then removed the love: cancels out, so still no reply.
    put("no_reply", False, f"Loved “{INVITE}”", WARD_SEND_AT + timedelta(minutes=8), assoc=(2000, sent_guids["no_reply"]))
    put("no_reply", False, f"Removed a heart from “{INVITE}”", WARD_SEND_AT + timedelta(minutes=9),
        assoc=(3000, sent_guids["no_reply"]))

    # A second logged send to Mark, with its own reply: the first send's replies stop here.
    put("yes", True, REMINDER, WARD_SECOND_SEND_AT)
    put("yes", False, "See you then", WARD_SECOND_SEND_AT + timedelta(minutes=4))

    # A ward group chat: Mark and Ruth reply there too, which 1:1 reads must ignore.
    group = con.execute(
        "INSERT INTO chat (guid, style, chat_identifier, service_name, display_name)"
        " VALUES ('iMessage;+;chat777', 43, 'chat777', 'iMessage', 'Ward council')"
    ).lastrowid
    for key in ("yes", "no"):
        con.execute("INSERT INTO chat_handle_join VALUES (?, ?)", (group, ward_handles[key]))
    for key, text, minutes in (("yes", "Yes I'll bring the rolls", 20), ("no", "No problem", 21)):
        guid = str(uuid.UUID(int=w.rng.getrandbits(128))).upper()
        when = WARD_SEND_AT + timedelta(minutes=minutes)
        cur = con.execute(
            "INSERT INTO message (guid, text, handle_id, service, date, is_from_me) VALUES (?, ?, ?, 'iMessage', ?, 0)",
            (guid, text, ward_handles[key], _apple_ns(when)),
        )
        con.execute("INSERT INTO chat_message_join VALUES (?, ?, ?)", (group, cur.lastrowid, _apple_ns(when)))

    WARD_SENT_GUIDS.clear()
    WARD_SENT_GUIDS.update(sent_guids)


WARD_SENT_GUIDS: dict[str, str] = {}  # filled by generate(): member key -> guid of the INVITE row


def ward_sendlog() -> list[dict]:
    """Send-log records matching the synthetic sends (call after generate())."""
    records = []
    for i, (key, m) in enumerate(WARD.items()):
        status = "failed" if key == "failed" else ("sent" if m.service == "SMS" else "delivered")
        records.append({
            "send_id": f"synth-{key}",
            "timestamp": (WARD_SEND_AT + timedelta(seconds=i)).isoformat(),
            "name": m.name, "phone": m.phone, "text": INVITE, "service": m.service, "dry_run": False,
            "sent": True, "guid": WARD_SENT_GUIDS.get(key), "status": status,
            "error": "chat.db error 22" if key == "failed" else None,
        })
    m = WARD["yes"]
    records.append({
        "send_id": "synth-yes-reminder", "timestamp": WARD_SECOND_SEND_AT.isoformat(), "name": m.name,
        "phone": m.phone, "text": REMINDER, "service": "iMessage", "dry_run": False, "sent": True, "guid": None,
        "status": "delivered", "error": None,
    })
    return records

def generate(out_dir: Path, seed: int = 7, sessions_per_chat: int = 45) -> dict[str, Path]:
    """Write `chat.db` and an `AddressBook/` tree into out_dir. Returns their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    chat_db = out_dir / "chat.db"
    chat_db.unlink(missing_ok=True)
    rng = random.Random(seed)
    con = _create_chat_db(chat_db)
    w = _Writer(con, rng)
    w.setup()

    sessions: list[tuple[datetime, str, list[tuple[str, str]]]] = []
    for chat, start, lines in STORIES:
        sessions.append((datetime.strptime(start, "%Y-%m-%d %H:%M").replace(tzinfo=TZ), chat, lines))
    span_start = datetime(2026, 1, 2, tzinfo=TZ)
    span_days = 300
    for chat in CHATS:
        if chat == "dentist":
            continue
        for _ in range(sessions_per_chat if chat not in ("dad", "lily") else sessions_per_chat // 3):
            when = span_start + timedelta(days=rng.randrange(span_days), hours=rng.uniform(8, 23))
            sessions.append((when, chat, _filler_lines(rng, chat)))
    sessions.sort(key=lambda s: s[0])

    for when, chat, lines in sessions:
        _session(w, chat, when, lines)
        if rng.random() < 0.06:  # photo, sometimes with a caption
            speaker = rng.choice(["me", *CHATS[chat][1]])
            caption = rng.choice(["", "", "look at this view", "this is the one i was talking about"])
            w.message(chat, speaker, OBJ + caption, when + timedelta(minutes=20), attachment=True)

    # A group rename event (non-message row that extraction must skip).
    w.message("crew", "jake", None, datetime(2026, 8, 7, 19, 55, tzinfo=TZ), item_type=2)
    _ward_threads(w)
    con.commit()
    con.close()

    ab_root = out_dir / "AddressBook"
    _create_addressbook(ab_root)
    return {"chat_db": chat_db, "addressbook": ab_root}


if __name__ == "__main__":
    import json
    import sys

    out = Path(sys.argv[1] if len(sys.argv) > 1 else "demo")
    paths = generate(out)
    log = out / "sends.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in ward_sendlog()))
    print(f"wrote {paths['chat_db']} and {log}")
