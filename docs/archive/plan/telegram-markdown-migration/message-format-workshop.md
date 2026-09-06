# Telegram Message Format Workshop — Reusable Prompt

> Paste this whole file's content (or point Claude at this file path) to start a new session focused on iterating one Telegram message's format to a confirmed target, then recording that target into
> `strategy-rollout/stories.md`. Repeatable — run once per message.

---

## Session protocol

1. Read `CONTEXT.md`, state `CONTEXT.md ✓`.
2. Read `docs/plan/telegram-markdown-migration/README.md` (epic context), `docs/plan/telegram-markdown-migration/backbone/stories.md` (MarkdownV2 escaping rules — MD-1's `mdcode()`/`escape_markdown()`
   design, the reserved-character set, the "static template text needs escaping too" rule), and `docs/plan/telegram-markdown-migration/formatting-rules/stories.md` (decimal/alignment spec — FMT-1's
   table, FMT-3's table-builder designs and the locked-in 1dp leg-table exception). These three files are the ground truth for every formatting decision made in this workshop — do not improvise a rule
   that contradicts them without flagging the contradiction to Animesh first.
3. Check whether `backbone/` (MD-1..MD-5) has shipped yet:
   ```
   search_graph("mdcode")
   search_graph("escape_markdown")
   ```
   - **If shipped:** import `src/notifications/markdown.py` and `src/notifications/formatting.py`
     directly in the scratch script — do not re-derive escaping/formatting logic that already
     exists as real, tested code.
   - **If not shipped yet:** the scratch script inlines its own copies of `mdcode()` /
     `escape_markdown()` / the value formatters, matching the exact signatures and behavior
     specified in `backbone/stories.md` MD-1 and `formatting-rules/stories.md` FMT-2/FMT-3 —
     so the eventual real implementation is a near-verbatim port, not a rewrite. Say explicitly
     in the scratch script's docstring which case you're in.

## What to ask the user for

This workshop covers one message at a time. Ask (unless already given in the prompt that started the session):

- **Which message?** Name it against `strategy-rollout/tasks.md`'s list (ROLL-1 IC audit [done — reference: `scratch/2026-08-07_ic_eod_audit_telegram_format.py`], ROLL-2 comparison report, ROLL-3 the
  7 strategy close/roll notifications, ROLL-4 approval requests) if it matches one of those. If it's a message not on that list, that's fine — note it as a new task to add to
  `strategy-rollout/tasks.md` at the end of this workshop, don't block on it not having a pre-assigned slot.
- **Current ("from") message**, if one exists — paste the actual current rendered text/format, or point at the source function (`get_code_snippet`/`search_graph` it, don't guess).
- **Target ("to") message**, if the user already knows what they want — or **ask for suggestions** if they want you to propose a format. If proposing, ground the proposal in FMT-1's spec table and the
  already-approved IC EOD audit format (bold header line, side-by-side or single kv table as appropriate, fenced leg table only if the message actually has multiple position rows — don't force a table
  onto a single-value message, per `strategy-rollout/stories.md` ROLL-3's explicit "match the format to what the message needs" guidance).

## Build the scratch script

- Path: `scratch/YYYY-MM-DD_<message-name>_format.py` (today's date, kebab-case name matching the message — e.g. `2026-08-08_ic_comparison_report_format.py`).
- Structure: mirror `scratch/2026-08-07_ic_eod_audit_telegram_format.py` — sample data dict, `build_message(d)` pure function, a `main()` that prints then sends via real Telegram credentials from
  `src.config.settings`, non-fatal error handling that surfaces Telegram's actual `description` field on a 400 (don't let `raise_for_status()` swallow it — that exact mistake cost a full debugging
  round-trip in the IC EOD session).
- `parse_mode="MarkdownV2"` per the backbone decision — not legacy `Markdown`, not HTML.
- Apply the formatting rules without re-litigating them: money 2dp (`format_money`), strikes integer, Greeks 2dp signed with `-` for `None` (`format_greek`), LTP/Entry 2dp everywhere **except** inside
  a leg table specifically (1dp there, per the locked-in exception), DTE/qty integer, IVR 2dp, percentages 1dp. Wrap every dynamic identifier-like value (strategy IDs, signal/action codes, instrument
  labels) in `mdcode()`; escape any literal reserved punctuation in static template text with `escape_markdown()` — MarkdownV2's reserved set is `` _*[]()~`>#+-=|{}.! ``, wider than legacy Markdown,
  easy to under-escape if this step is rushed.

## Iterate

Send real messages, look at the actual rendering on-device (not the console `print()` output — that's raw source, not what Telegram renders; this distinction caused confusion in the original session,
don't repeat it). Adjust and resend until the user confirms the target is right.

## Close out: update `strategy-rollout/stories.md`

Once confirmed:

1. Find or create the matching `ROLL-N` task in `docs/plan/telegram-markdown-migration/strategy-rollout/stories.md` (and `tasks.md`'s checklist line) for this message. If it's a new message not
   already listed, append a new `ROLL-N` following the existing numbering and the file/method it targets (`get_code_snippet`/`search_graph` to find the real source function — don't assume a path).
2. Write that task's spec using the now-confirmed scratch script as the reference implementation, same pattern as ROLL-1's existing spec: which real file/function changes, what the confirmed message
   structure is, which formatters/helpers it uses, what tests are needed (happy path + the underscore/reserved-character regression test — every message in this epic carries that regression test
   forward, it's the bug the whole epic started from).
3. If the scratch iteration surfaced a NEW formatting rule not already in `formatting-rules/stories.md` FMT-1's table (e.g. a parameter type that table doesn't cover yet), add it there too — don't let
   a rule live only inside one `ROLL-N` task's spec if it's actually a general rule.
4. Update `docs/plan/telegram-markdown-migration/README.md`'s scope-decision section only if this message's rollout changed something structural (new file added to the "confirmed real callers" list, a
   new coordination point discovered) — most single-message updates won't need this, don't touch it reflexively.
5. Do NOT touch `src/`/`scripts/` in this workshop — this session's output is docs (`stories.md`/`tasks.md`) plus the scratch script, never real code. Real implementation happens later, in the actual
   `backbone/`/`strategy-rollout/` task sessions, following `prompt.md`'s one-task-per-session protocol.

## Commit

Docs + scratch script only, no `.py` files under `src/`/`scripts/`/`tests/` — skip `code-reviewer`, commit directly per root `CLAUDE.md` Step 5c's docs/config-only path. Commit format:
`.claude/skills/commit/SKILL.md`. Execute the commit — do not draft it and stop.

**Known sandbox caveat (2026-08-07):** if committing from a Cowork sandbox session, `.git/HEAD.lock` may fail to clear with "Operation not permitted" — a mount/filesystem quirk, not a real lock
contention. Retry `git commit --no-verify` once or twice before concluding it's actually stuck; it resolved on retry last time without any manual intervention. If truly stuck, hand the exact commit
message to the user to run from their own terminal — do not leave uncommitted work unflagged.

**Verify and record:** append one line to `TODOS.md`'s item 29 (Telegram Markdown migration) noting which message's format was confirmed this session and which `ROLL-N` task now has a concrete spec,
same pattern as this project's other session-log entries.
