---
description: Text one contact the exact words you give, through the live imessage server
argument-hint: <name> [--late] "<message>"
model: claude-haiku-5-5
allowed-tools: Read(./contacts.csv), mcp__imessage__preview_send
---

Send this text for Blake: $ARGUMENTS

Do this quickly, with no drafting and no extra questions unless a step below says to stop:

1. Split the arguments into the recipient, an optional `--late` flag, and the message. The message is the
   quoted part, or, without quotes, everything after the name (and after `--late`). `--late` is never part
   of the message.
2. Read `contacts.csv` in the project root. Match the recipient against the `name` column, ignoring case. A
   first name alone is fine if exactly one row matches. If nothing matches, or more than one row could
   match, stop and say so. Never guess a number, and never use a number that isn't in `contacts.csv`.
3. Send the message **exactly as written**: don't reword it, fix typos, or add a greeting or sign-off.
4. Call `mcp__imessage__preview_send` with that one row (`service` left as `auto`). Pass
   `allow_quiet_hours=true` only if `--late` was given. Never pass `allow_repeat` unless the arguments
   explicitly ask for a repeat. If the preview refuses the row, show the reason in one line and stop. For a
   quiet-hours refusal, add: "Run it again with --late to send anyway."
5. Show the preview table, then call `mcp__imessage__confirm_send` right away with the token and the same
   messages list. Don't wait for a chat reply: Blake approves at the permission prompt and then clicks Send
   in the native dialog. Never try to click the dialog yourself.
6. Reply in one line: who, the status (`delivered` / `sent` / `failed` / `unknown`), and the `send_id`. If
   it's `failed` or `unknown`, don't retry. Say so and offer a fresh preview (for `failed`, maybe with
   `service="SMS"`).
