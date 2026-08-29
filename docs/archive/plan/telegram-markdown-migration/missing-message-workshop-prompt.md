# Missing-Message Workshop — Reusable Prompt

> **ARCHIVED 2026-08-29 (RDO-17.4).** The `TODO.md` queue this prompt drove is exhausted
> (all 10 items confirmed and written back as `strategy-rollout/` `ROLL-7..ROLL-16`).
> For iterating any *other* Telegram message's format, use the still-live
> `message-format-workshop.md` at the epic root — this file is kept for history only.

> Paste this whole file's content (or point Claude at this file path) to run the next queued
> message from `docs/plan/telegram-markdown-migration/TODO.md` through the format workshop.
> Repeatable — run once per session, same "first unchecked box" protocol as `tasks.md`.

---

## Step 1 — Pick the message

Read `docs/plan/telegram-markdown-migration/TODO.md`. Find the **first unchecked `- [ ]` line**
under "Confirmed missing" — that is this session's only message. Do not skip ahead to a later
item and do not batch multiple items in one session, even if a later one looks more urgent;
if priorities have genuinely changed, say so and get confirmation before deviating from the
queue order.

Confirm the exact current source before building anything — `get_code_snippet`/`search_graph`
the real function named in that TODO.md line, don't work from the grep excerpt alone. If the
line notes the message body wasn't fully read yet (e.g. item 7, the three-track entry
confirmations), read it in full now and flag anything that changes its place in the queue
(e.g. it turns out more/less complex than the simplicity-first ordering assumed).

## Step 2 — Build the scratch script

Path: `scratch/YYYY-MM-DD_<message-name>_format.py` (today's date, kebab-case name matching the
message). Structure: mirror `scratch/2026-08-07_ic_eod_audit_telegram_format.py` — sample data
dict, pure `build_message(d)` function, a `main()` that prints then sends via real Telegram
credentials from `src.config.settings`, non-fatal error handling that surfaces Telegram's actual
`description` field on a 400 (don't let `raise_for_status()` swallow it).

## Step 3 — Run the format workshop

Follow `docs/plan/telegram-markdown-migration/message-format-workshop.md` in full:

1. Read `CONTEXT.md` (state `CONTEXT.md ✓`), this epic's `README.md`, `backbone/stories.md`
   (MarkdownV2 escaping rules), `formatting-rules/stories.md` (decimal/alignment spec).
2. Check whether `backbone/` (MD-1..MD-5) has shipped: `search_graph("mdcode")`,
   `search_graph("escape_markdown")`. If shipped, import the real
   `src/notifications/markdown.py` / `formatting.py` helpers in the scratch script. If not,
   inline matching copies (say explicitly which case you're in, in the script's docstring).
3. `parse_mode="MarkdownV2"`. Apply the locked formatting rules (money 2dp, strikes integer,
   Greeks 2dp signed, LTP/Entry 2dp except 1dp inside a leg table, DTE/qty integer, IVR 2dp,
   percentages 1dp) — wrap dynamic identifier-like values in `mdcode()`, escape reserved
   punctuation in static template text with `escape_markdown()`.
4. Iterate live: send real test messages, look at the actual on-device rendering (not the
   console `print()` output), adjust and resend until Animesh confirms the target format.
   If this message doesn't obviously need a table (most single-line/plain-text messages in the
   queue won't) — don't force one; match the format to what the message needs, per
   `strategy-rollout/stories.md` ROLL-3's explicit guidance.

## Step 4 — Close out

1. Add or update the matching `ROLL-N` entry in `strategy-rollout/stories.md` +
   `tasks.md`'s checklist, following the existing numbering (ROLL-1 through ROLL-6 already
   exist — this is a new `ROLL-N`, find the next free number, don't guess it's ROLL-7 without
   checking what's already there). Spec it the way ROLL-1 is specced: real file/function,
   confirmed message structure, formatters used, tests needed (happy path + the
   underscore/reserved-character regression test carried through every message in this epic).
2. If a new formatting rule surfaced that isn't in `formatting-rules/stories.md` FMT-1's table,
   add it there too.
3. **Tick this message's box in `docs/plan/telegram-markdown-migration/TODO.md`** — but only
   once the docs write-back (the new `ROLL-N` spec + scratch script) is actually committed.
   Append `| SHA: <sha>` after the checkbox line, same convention as `backbone/tasks.md` /
   `strategy-rollout/tasks.md`. Do not tick the box for a real `src/`/`scripts/` implementation
   landing — that's a separate, later step; ticking here only means "format confirmed and
   written back as a ROLL-N spec."
4. Do NOT touch `src/`/`scripts/` in this session — output is docs (`TODO.md`, `stories.md`,
   `tasks.md`) plus the scratch script only. Real implementation happens later in the actual
   `ROLL-N` task session.

## Step 5 — Commit

Docs + scratch script only — skip `code-reviewer` (no `.py` files under `src/`/`scripts/`/
`tests/` in the diff), commit directly per root `CLAUDE.md` Step 5c's docs/config-only path.
Commit format: `.claude/skills/commit/SKILL.md`. **Execute the commit — do not draft it and
stop.** Confirm with `git log --oneline -1` and use that SHA for `TODO.md`'s checkbox line.

**Known sandbox caveat:** if committing from a Cowork sandbox session, `.git/HEAD.lock` may
fail to clear with "Operation not permitted" — retry `git commit --no-verify` once or twice
before concluding it's actually stuck.

Append one line to `TODOS.md` noting which message's format was confirmed this session and
which `ROLL-N` task now has a concrete spec — same pattern as this project's other session-log
entries.

---

## If anything is unclear

Ask before proceeding rather than guessing, especially on: which message is actually "first
unchecked" if `TODO.md` has been edited since this prompt was written, what the target format
should look like if Animesh hasn't stated a preference, and which `ROLL-N` number is next free.
