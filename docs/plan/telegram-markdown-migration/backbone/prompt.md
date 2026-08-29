# Telegram Markdown Migration — Backbone — prompt

> Switch the Telegram transport to `parse_mode=MarkdownV2` and make every existing caller's message text safe under it — no format changes yet.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

`TelegramNotifier.send()` currently HTML-escapes and `<pre>`-wraps everything, which makes real bold + copyable fenced tables impossible — the entire point of the epic. Removing that safety net (MD-2)
means every caller that interpolates a dynamic value is now responsible for making it MarkdownV2-safe. MD-1 provides the `escape_markdown()` / `mdcode()` helpers; MD-3/MD-4/MD-7 apply them everywhere
they are currently missing; MD-6 adds a static-scan guard so new call sites cannot regress silently. The original `DELTA_WARN` bug (a lone `_` opening an unclosed italic entity and 400-ing the send)
is the failure mode this story exists to eliminate structurally.

## Scope guard

`src/notifications/` (`markdown.py` new, `telegram.py`, `telegram_gateway.py`), the 7 strategy close/roll notification methods, and the reporting / entry / cron scripts that send Telegram messages.
**This story changes the transport and makes existing text safe — it does not change how any message looks.** Message wording and structure are `strategy-rollout/`'s job. `formatting.py` value
formatters and table builders are `formatting-rules/`'s job.

## Session-start load hints

- Epic `README.md` — the global parse-mode decision, the confirmed-callers list, and the **MD-2 live-risk window** cross-cutting constraint (land MD-2 with MD-3/MD-4, never alone).
- `src/notifications/CLAUDE.md` — the non-fatal send contract.
- No `schema.md` — this story changes no DB schema.

## Hard constraints

- **Non-fatal send contract** (`src/notifications/CLAUDE.md`): `TelegramNotifier.send()` is called from `try/except` throughout the strategy layer. Nothing here may change that — a message that fails
  to send after the migration must still return `False` / log a warning, never raise.
- **Graph-before-Read:** never `Read` a `src/` / `scripts/` file without first trying `git log` → `search_graph` / `get_code_snippet` → `search_code` → `sed -n`. State why the graph was insufficient
  if you fall through to `Read`.
- **Test helpers:** run `get_code_snippet('<ModelClassName>')` before writing any fixture that constructs a domain model — do not write from memory.
- **Test gate (blocking):** `python -m pytest tests/unit/ --tb=no -q` — all green before committing.
- **Financial-logic review:** MD-3, MD-4.3, MD-7.3 touch close-notification / auth paths — run the real `@code-reviewer` subagent against `git diff HEAD` before committing those, per root `CLAUDE.md`
  AutoTrigger rules, not a persona approximation.

## Task overview

One line per task id (detail in `stories.md`): MD-1 escaping helpers · MD-2 parse-mode switch · MD-3 strategy close/roll audit · MD-4 (4.1 gateway flip / 4.2 five callers / 4.3 approval request) ·
MD-6 static-scan guard · MD-7 (7.1 pre_market_brief / 7.2 IC-entry `_gate_alert` / 7.3 auto_close+overlay_closer) · MD-5 docs close.

## Definition of done

Mirrors `tasks.md` §"Story done when". In short: MarkdownV2 is the transport for `send()` and `send_notification`, the escaping helpers exist and are applied at every confirmed call site, the
static-scan guard passes with a documented baseline, and the non-fatal contract is unchanged.

## Perspectives not covered

- **Backslash-in-code-span escaping.** `mdcode()`'s fallback assumes the code-span backslash rule but MD-1 flagged it as "confirm against Telegram's current API docs"; BUG-038 later noted
  `escape_markdown()` does not escape literal backslashes. Whether that gap can bite a real caller was never fully run down.
- **Whether the 7-strategy close-notification list is still complete.** It was a 2026-08-07 graph sweep; a strategy class added since would not be covered by MD-3 and only caught by MD-6's guard if it
  uses a recognised `send(` pattern.
