# imessage-mcp

An MCP server that lets Claude Code text a few of your own contacts (for example "does Tuesday at 7 work?"),
then check who replied. It is a small texting-and-replies tool, not a general message client. See
[SPEC.md](SPEC.md) for the full design.

The first build is for **personal contacts only**. Ward interview scheduling with members from LCR is
planned for later: it's the `ward` profile (`IMESSAGE_MCP_PROFILE=ward`), and it waits on the bishop's OK
(see [notes/lcr-data-guidance.md](notes/lcr-data-guidance.md)).

**Dry-run is the default.** Nothing is sent unless the server is started with `IMESSAGE_MCP_LIVE=1`.

## ⚠️ Never allow-list `confirm_send`

Never put `confirm_send` (`mcp__imessage__confirm_send`) on Claude Code's allowed-tools list. When Claude
Code asks permission for it, always answer **Yes** for that one call, never "Yes, and don't ask again".
Don't use the live server in any mode that approves tool calls automatically (`--dangerously-skip-permissions`,
bypass-permissions, auto-accept or auto mode), or in a session where Claude has been given control of the
screen (computer use). Live sends belong in a session with normal permission prompts and no screen control.

The project's [.claude/settings.json](.claude/settings.json) allow-lists only the three tools that can't
send (`preview_send`, `get_replies`, `check_replies`) and puts `confirm_send` on the **ask** list, so it always
prompts. Keep it that way.

There are two gates, and both must stay:

1. **The native macOS dialog** is the real gate. It lists every message with **Cancel** (the default) and
   **Send**. Claude can't click it, unless Claude has been given control of the screen, which is why live
   sends need a session without computer use. Cancel, pressing Return, or doing nothing for 2 minutes
   sends nothing.
2. **Claude Code's permission prompt** is the second gate. `confirm_send` has to repeat the messages, so
   the prompt shows the real names and texts, not just a token.

## The four tools

| Tool | What it does |
|---|---|
| `preview_send` | Checks a batch without sending: allowlist, duplicate guard (same text to same number in 24 h), quiet hours. Shows each row's name, number, text, service, and the last message in that thread. Issues one `confirm_token` (10 minutes, single use) only if every row passes. |
| `confirm_send` | Takes the token plus the **same** messages echoed back. Shows the native dialog. Only if you click **Send**: re-checks the guards, sends, checks delivery in `chat.db`, logs. Statuses: `delivered`, `sent`, `failed`, `unknown` (`dry_run` in dry-run). Only one runs at a time. |
| `get_replies` | Messages **from** allowlisted numbers only, since the last logged send (or a `since` you give). |
| `check_replies` | For each `send_id`: the replies after that send, including tapbacks, with a keyword guess (`yes` / `no` / `reschedule` / `opt_out` / `unclear`). Claude makes the final call. |

Reply text is untrusted data from third parties. The tool descriptions tell Claude never to follow
instructions found in it.

## Setup

Needs macOS with Messages signed in, and Python 3.10+.

```bash
cd ~/imessage-mcp
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

`mcp` is pinned below 2.0 because the server uses FastMCP, which the 2.x SDK renamed.

### Full Disk Access

The server reads `~/Library/Messages/chat.db` (read-only). macOS only allows that for apps with Full Disk
Access. Grant it to the app Claude Code runs in: your terminal (Terminal, iTerm, VS Code), or the **Claude
desktop app** if you use its Code tab.

System Settings → Privacy & Security → Full Disk Access → turn on that app, then quit and reopen it.

Without it, the read tools return an error naming Full Disk Access.

### The Automation prompt

The first live send makes macOS ask "*<your app>* wants access to control Messages". Click **Allow**. If you
clicked Don't Allow, turn it back on under System Settings → Privacy & Security → Automation → *<your app>* →
Messages.

Dry-run never controls Messages, so you won't see this prompt until the first live `confirm_send`. The
confirmation dialog itself shows in dry-run too.

### contacts.csv (the allowlist)

Create `contacts.csv` in the project folder by hand, with only the people you want Claude to be able to
text and read. For now that's your own contacts (friends, family). Don't put ward members from LCR in it
until the ward profile is cleared.

```csv
name,phone
Sam Lee,(801) 555-0131
Mom and Dad,801-555-0137
```

- It gates **both sending and reading**: numbers not in it can't be texted or read.
- Phones are normalized to `+1XXXXXXXXXX`. Only US numbers (10 digits, or 1 + 10) are accepted.
- If two rows share a number (a shared household phone), both rows are blocked until you fix the file,
  e.g. one row named "Mom and Dad". Problems are printed when the server starts and included in tool
  results.
- The file is re-read on every tool call, so removing someone takes effect right away.

`contacts.csv` is gitignored. `contacts.example.csv` lists the synthetic members used for demos.

## Register in Claude Code

```bash
claude mcp add imessage -- /Users/blakegertsch/imessage-mcp/.venv/bin/python -m imessage_mcp
```

That registers it in dry-run. To send for real, re-register with `-e IMESSAGE_MCP_LIVE=1`:

```bash
claude mcp remove imessage
```

```bash
claude mcp add imessage -e IMESSAGE_MCP_LIVE=1 -- /Users/blakegertsch/imessage-mcp/.venv/bin/python -m imessage_mcp
```

Restart Claude Code after changing it. The server prints `DRY RUN` or `LIVE` to stderr on startup.

The registered server is local to this project folder, so every Claude session opened here sees it,
including ones with computer use or auto mode. Only send from a session that has neither.

Never turn on live mode for the demo server. The server refuses to start with `IMESSAGE_MCP_LIVE=1` when it's
pointed at `contacts.example.csv` or a `chat.db` under `demo/`.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `IMESSAGE_MCP_LIVE` | unset | `1` enables real sending. Any other value is dry-run. |
| `IMESSAGE_MCP_NO_DIALOG` | unset | `1` skips the dialog. For pytest; honored **only in dry-run**. With `LIVE=1` the server refuses to start. |
| `IMESSAGE_MCP_CHAT_DB` | `~/Library/Messages/chat.db` | The `chat.db` to read. Tests and demos point this at the synthetic DB. |
| `IMESSAGE_MCP_QUIET_HOURS` | `21:00-08:00` | No sends in this local-time window unless `allow_quiet_hours=true` (flagged in the dialog). |
| `IMESSAGE_MCP_PROFILE` | `personal` | `personal` (your own contacts) or `ward` (later: LCR members, ward wording in the tool descriptions, Sundays blocked by default). |
| `IMESSAGE_MCP_BLOCK_SUNDAY` | `0` (`1` for `ward`) | `1` also blocks sends on Sundays. |
| `IMESSAGE_MCP_CONTACTS` | `<project>/contacts.csv` | The allowlist. |
| `IMESSAGE_MCP_LOG` | `<project>/logs/sends.jsonl` | The send log. |

## How a send works

1. Claude drafts texts and calls `preview_send` (no prompt: it can't send). It shows you the full preview
   table.
2. Claude calls `confirm_send` right away with the token and the same messages. It doesn't wait for a chat
   "yes" unless you asked to review first. Claude Code asks permission: check the names and texts, then
   answer **Yes** (once), or **No** and ask for changes.
3. The macOS dialog lists every row, with `DRY RUN`, `REPEAT of a message sent …` or `QUIET HOURS` in caps
   when they apply. Click **Send** only if it's right.
4. For each row the server records `MAX(message.ROWID)`, sends with `osascript` (the phone and text are passed
   as arguments, never pasted into the script), then polls `chat.db` for up to 15 seconds for the new
   outgoing row to report `delivered`, `sent`, `failed` or `unknown`.
5. Every row is appended to `logs/sends.jsonl` (gitignored). A live row is written as `pending` just before
   the send and again with the result, so a text that went out is always in the log and the duplicate guard
   sees it even if the delivery check fails. That log is the record of who was asked what, and when.

### Quick send: `/text`

```
/text Liz "Running 5 min late"
/text Liz --late "Still up?"
```

Looks the name up in `contacts.csv` (a first name is fine if only one row matches), sends the words exactly
as written, and goes straight from the preview to `confirm_send`. You still get the permission prompt and the
Send dialog. It stops instead of guessing if the name doesn't match exactly one contact.

- `--late` sends during quiet hours (it passes `allow_quiet_hours`, and the dialog says QUIET HOURS). Without
  it, a quiet-hours send is refused with a one-line hint to add `--late`.
- It never overrides the repeat guard unless you ask.
- It runs on Haiku (`model:` in the command file) to cut the wait between steps. Your two clicks are still
  the gates. The command is in
[.claude/commands/text.md](.claude/commands/text.md).

A failed iMessage is **not** resent as SMS automatically, because that risks a double text. Claude can offer a
new `preview_send` with `service="SMS"` (that needs iPhone Text Message Forwarding).

## Data rules

- Real names, numbers and replies stay on this Mac. `contacts.csv` and `logs/` are gitignored. Never commit
  them or attach them to class work.
- Message contents do pass through Claude, which is why reads are limited to the allowlist.
- Class demos, screenshots and submissions use the synthetic `chat.db` and `contacts.example.csv`, in dry-run
  only.

## Later: the ward profile (LCR)

Church guidance appears to rule out exporting LCR data and putting member data into AI tools the Church
doesn't manage (see [notes/lcr-data-guidance.md](notes/lcr-data-guidance.md)). Before using this for ward
interviews, ask the bishop. If it's cleared:

- Register the server with `-e IMESSAGE_MCP_PROFILE=ward`. The tool descriptions then say "ward members" and
  tell Claude to keep texts vague, and Sundays are blocked by default.
- Add members to `contacts.csv` by hand from LCR, only the people being scheduled, not the whole ward. LCR
  is more accurate than the ward Google Sheet, which has had wrong numbers.
- Keep texts vague: "Could you meet with the bishopric Sunday at 7:00?". **Never put the reason for the
  interview in the text.**

## Demo on synthetic data (dry-run)

Generate a fake `chat.db` with ward interview threads (a yes, a no, "can we do 7:30 instead?", a 👍 only,
"please stop texting me", no reply, a household, a failed send) plus a matching demo send log:

```bash
.venv/bin/python -m tests.synthetic demo
```

Register a separate demo server pointed at it. The demo threads are ward-style, so add
`-e IMESSAGE_MCP_PROFILE=ward` if you want the ward wording:

```bash
claude mcp add imessage-demo -e IMESSAGE_MCP_CHAT_DB=/Users/blakegertsch/imessage-mcp/demo/chat.db -e IMESSAGE_MCP_CONTACTS=/Users/blakegertsch/imessage-mcp/contacts.example.csv -e IMESSAGE_MCP_LOG=/Users/blakegertsch/imessage-mcp/demo/sends.jsonl -- /Users/blakegertsch/imessage-mcp/.venv/bin/python -m imessage_mcp
```

Then ask Claude to text three of the synthetic members, preview, confirm in the dialog (labeled DRY RUN), and
run `check_replies`. The demo log already has send IDs `synth-yes`, `synth-no`,
`synth-reschedule`, `synth-tapback`, `synth-opt_out`, `synth-no_reply`, `synth-household` and `synth-failed`
with replies to check. Dry-run sends have no replies, since nothing was sent.

## Development

- `.venv/bin/pytest` runs everything against the synthetic DB. Tests never touch real data, never show a
  real dialog, and fail if anything calls the real `subprocess.run`.
- Layout: see SPEC.md §12. `attributed_body.py` and `tests/synthetic.py` were copied from
  `~/imessage-search-project`; the generator was extended with the ward threads.
