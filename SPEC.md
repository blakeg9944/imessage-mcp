# iMessage MCP Server — Build Spec

Status: **draft — ready for Blake's review**

## 1. Purpose

An MCP server that lets an AI agent (Claude) send and read iMessages/SMS from Blake's Mac.
The main use case is Blake's volunteer work as a ward executive secretary: texting ward
members to schedule interviews with the bishopric, then checking who replied.

Built for Blake's agent engineering class, vibe coded from this spec.

## 2. Project setup

- **Location:** `~/imessage-mcp` (new folder and git repo, separate from `~/imessage-search-project`).
- **Reused code** (copied, not imported) from `~/imessage-search-project`:
  - `imsearch/attributed_body.py` and `tests/test_attributed_body.py` — decodes the `attributedBody`
    blob (via `pytypedstream`), needed because on recent macOS the `message.text` column is often empty.
  - `imsearch/synthetic.py` — generates a fake `chat.db` for tests and demos.
  - `imsearch/sqlite_copy.py` — reviewed as a reference for opening `chat.db` safely.

## 3. Known technical facts

- **Sending works** via AppleScript run through `osascript`:
  ```applescript
  tell application "Messages"
    set svc to 1st account whose service type = iMessage
    send msg to participant phoneNum of svc
  end tell
  ```
- **Reading** comes from `~/Library/Messages/chat.db` (SQLite), opened **read-only**
  (`file:...?mode=ro` URI). The program that launches the server (Terminal, Claude Desktop, etc.)
  needs **Full Disk Access** in System Settings → Privacy & Security, or the open fails with
  "authorization denied".
- **Source of truth for phone numbers is LCR**, not the ward Google Sheet. The Sheet has had wrong
  numbers, which caused two misdirected texts.

## 4. Class requirements

- The assignment requires an **MCP server**. No other graded requirements named (no mandated tests,
  report or demo format).
- Deadline: _not given yet_.

## 5. Stack and clients

- **Python** (>=3.10) with the official `mcp` SDK, using **FastMCP**. Transport: stdio.
- **Client: Claude Code only.** Register with `claude mcp add imessage -- <venv python> -m imessage_mcp`.
  Full Disk Access goes to the terminal app Claude Code runs in (or the Claude desktop app if run
  from its Code tab).

## 6. Tools

All tools take phone numbers in any common format and normalize them (see §8). Where a number is in
`contacts.csv`, results include the member's name. `since` accepts an ISO-8601 datetime or a relative
value like `"2d"` / `"6h"`; times in results are local ISO-8601.

| Tool | Inputs | Returns |
|---|---|---|
| `send_message` | `phone`, `text` | **Does not send.** Validates the number against the allowlist and returns a preview (name, normalized number, text, iMessage/SMS guess) plus a one-time `confirm_token` that expires in 10 minutes. |
| `confirm_send` | `confirm_token` | Actually sends the previewed message via `osascript`, logs it, returns success/failure. Fails if the token is unknown, used, or expired. |
| `get_replies` | `phones: list`, `since` | For each phone: messages **from** that number since `since`, oldest first (text, time, service). Optionally include Blake's own outgoing messages with `include_sent=true` for context. |
| `check_confirmations` | `phones: list`, `since` | For each phone: `status` = `replied` or `no_reply`, the reply texts, and a keyword `guess` (`yes` / `no` / `unclear`). **Claude makes the final yes/no call** from the text; the server's guess is only a hint. No LLM call inside the server. |
| `list_recent_conversations` | `limit=20` | Most recent chats: name (if known), number or chat id, last message preview, time, unread flag. |
| `search_messages` | `query`, `phone=None`, `limit=20` | Keyword search (case-insensitive substring over decoded text), newest first, optionally limited to one contact. |

## 7. Safety

- **Allowlist:** `contacts.csv` (`name,phone`, gitignored) in the project folder, filled by hand from
  **LCR**. `send_message` refuses any number not on it, with a clear error. Reading tools work for any
  number; the allowlist only gates sending.
- **Two-step confirm:** `send_message` → preview + token; `confirm_send(token)` sends. The tool
  descriptions tell Claude to show Blake the preview and wait for his OK before calling `confirm_send`.
  Claude Code's own tool-permission prompt is a second layer.
- **Send log:** every `confirm_send` attempt is appended to `logs/sends.jsonl` (gitignored): timestamp,
  name, normalized phone, text, dry_run flag, result/error.
- **Dry-run mode:** `IMESSAGE_MCP_DRY_RUN=1` makes `confirm_send` log and return success without
  calling `osascript`. Used in tests and the class demo.
- `chat.db` is only ever opened read-only.

## 8. Phone numbers

- Every phone input (tool arguments and `contacts.csv`) is normalized to **`+1XXXXXXXXXX`**: strip
  spaces, dashes, dots, parentheses; accept 10 digits or `1` + 10 digits, with or without `+`.
- Anything else (international, short codes, emails, wrong digit count) is **rejected** with an error
  naming the bad input.
- When matching against `chat.db`, compare normalized `handle.id` values (handles can be stored as
  `+1801...`, bare digits, or an email for iMessage-by-email; email handles are shown but never matched
  to a phone).
- `contacts.csv` rows that fail to normalize are reported at server startup and skipped.

## 9. Message formats

- **Sending:** try **iMessage** first. Use **SMS** instead when `chat.db` shows the number has only
  ever used SMS (`handle.service` / `message.service` = `SMS`), and fall back to SMS if the iMessage
  `osascript` call errors. SMS send uses `1st account whose service type = SMS` and needs iPhone
  Text Message Forwarding enabled. The result reports which service was used.
- **Reading:** both iMessage and SMS; each message is labeled with its service.
- **Text decoding:** use `message.text` when non-empty, otherwise decode `attributedBody` with the
  copied decoder. Skip tapbacks/reactions (`associated_message_type != 0`) or show them as
  "reacted ❤️ to …"; show attachments as `[attachment]`.
- **Dates:** `message.date` is nanoseconds since 2001-01-01 UTC; convert to local time.
- **Group chats:** read-only. Reading tools include group messages labeled with the group name (or
  participant list). `send_message` only sends 1:1.

## 10. Testing and use

No live class demo. The goal is a server Blake actually uses for ward texting, tested thoroughly.

- **pytest on the synthetic `chat.db`** (generator copied from `imessage-search-project`, extended
  with ward-style interview threads: yes, no, "can we do 7:30 instead?", and no reply). Tests cover
  phone normalization, attributedBody decoding, every read tool, allowlist refusal, token expiry/reuse,
  dry-run logging. The DB path comes from `IMESSAGE_MCP_CHAT_DB` (default `~/Library/Messages/chat.db`),
  so tests never touch real data.
- **MCP Inspector** (`npx @modelcontextprotocol/inspector`) to call each tool by hand against the
  synthetic DB.
- **Claude Code in dry-run:** register the server with `IMESSAGE_MCP_DRY_RUN=1` and walk through a full
  scheduling flow (draft texts → preview → confirm → check confirmations).
- **One real send to himself:** put Blake's own number in `contacts.csv`, send for real, reply from his
  phone, and check `get_replies` / `check_confirmations` pick it up.

## 11. Project layout

```
imessage-mcp/
  pyproject.toml          # deps: mcp, pytypedstream; dev: pytest
  README.md               # setup, Full Disk Access, claude mcp add, env vars
  contacts.example.csv    # committed; contacts.csv is gitignored
  imessage_mcp/
    __main__.py           # python -m imessage_mcp → runs FastMCP over stdio
    server.py             # FastMCP tool definitions (thin)
    phones.py             # normalization
    contacts.py           # contacts.csv loading / allowlist
    chatdb.py             # read-only queries on chat.db
    attributed_body.py    # copied decoder
    sender.py             # osascript send, iMessage→SMS fallback, dry-run
    confirm.py            # pending-send tokens
    sendlog.py            # logs/sends.jsonl
  tests/
    synthetic.py          # copied + extended generator
    test_*.py
```

## 12. Build plan

1. `git init`, `pyproject.toml`, `.venv`, `.gitignore` (`contacts.csv`, `logs/`, `*.db`, `.venv`).
2. Copy `attributed_body.py` + its tests and the synthetic DB generator from `imessage-search-project`;
   get those tests passing here.
3. `phones.py` + tests.
4. `contacts.py` (CSV → allowlist with names) + tests.
5. `chatdb.py`: read-only connection, decoded messages, `get_replies`, `list_recent_conversations`,
   `search_messages`, group labeling; extend the synthetic DB with interview threads; tests.
6. `check_confirmations` (built on `get_replies` + keyword guess) + tests.
7. `sender.py`, `confirm.py`, `sendlog.py`: tokens, allowlist check, dry-run, osascript with SMS
   fallback + tests (osascript mocked).
8. `server.py`: wire all tools into FastMCP with clear tool descriptions (including "show Blake the
   preview before `confirm_send`").
9. Try every tool in MCP Inspector against the synthetic DB.
10. `README.md`; register in Claude Code with dry-run on; run a full scheduling flow.
11. Grant Full Disk Access, point at the real `chat.db`, fill `contacts.csv` from LCR, do the one real
    send to Blake's own number.
