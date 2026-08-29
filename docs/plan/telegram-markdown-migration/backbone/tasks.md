# Telegram Markdown Migration — Backbone — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task.
Each task = one commit. See `prompt.md` for why the story exists; see `stories.md` for the
per-task spec — each shipped line carries an **As-built** paragraph there with the split
rationale, scope-expansion history, and review-gate detail collapsed out of this file.

**Open: none — `backbone/` is complete (closing SHA `57c1c3c`).**

> **Routing:** `Owner` = who implements (`Claude` = judgment-call, `Antigravity` = mechanical
> with an unambiguous spec). `Model` = model the owner ran at. `Review` = the AutoTrigger gate;
> where `stories.md` says "real `@code-reviewer`, Opus" the real subagent is mandatory, not a
> persona approximation (financial-logic close-notification paths).

## Tasks

- [x] **MD-1** — `escape_markdown()` / `mdcode()` MarkdownV2 escaping helpers in `src/notifications/markdown.py` + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA:
      786e8096
- [x] **MD-2** — Switch `TelegramNotifier.send()` to MarkdownV2 parse_mode (no `<pre>`, no auto-escape); rewrite the HTML tests + entity-parse regression | Owner: Claude | Model: claude-sonnet-5 |
      Review: code-reviewer | SHA: 721daf9
- [x] **MD-3** — Audit + escape the 7 strategy close/roll `_send_close_notification` paths (dynamic values + static template punctuation) | Owner: Antigravity | Model: n/a | Review: code-reviewer
      | SHA: 62d0172
- [x] **MD-4** — Umbrella: reporting scripts + approval requests; gateway HTML→MarkdownV2 flip + 2 entry scripts folded in (2026-08-25). See MD-4.1/4.2/4.3. | SHA: aa58f44
- [x] **MD-4.1** — Flip `TelegramGateway.send_notification` HTML → MarkdownV2; lands with MD-4.2 | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: cd1e554
- [x] **MD-4.2** — Escape dynamic values + static punctuation in the 5 reporting/entry scripts calling `send_notification` | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: cd1e554
- [x] **MD-4.3** — Escape `TelegramGateway.send_approval_request` (auth keyboard path; coordination-check vs. `telegram-approval-auth-fix`) | Owner: Claude | Model: claude-sonnet-5 | Review:
      code-reviewer | SHA: aa58f44
- [x] **MD-6** — Static-scan escaping guard: `test_escaping_guard.py` walks `send(` call sites, asserts every interpolated value is escaped upstream, with a maintained `_BASELINE_UNESCAPED` |
      Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: ce95bbd
- [x] **MD-7** — Umbrella: escape gaps MD-6's guard surfaced that no prior MD-*/ROLL-* task named. See MD-7.1/7.2/7.3. | SHA: 04b469d
- [x] **MD-7.1** — Escape both `gateway.send_plain_message()` calls in `scripts/pre_market_brief.py` | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: 39993bf
- [x] **MD-7.2** — Escape `_gate_alert` in `paper_ic_entry.py` + `paper_ic_entry_v2.py` (separate path from MD-4.2's calls) | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: adfae40
- [x] **MD-7.3** — Escape `auto_close.py` + `overlay_closer.py` close/monetize paths outside MD-3's scope | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 04b469d
- [x] **MD-5** — Docs close: `src/notifications/CLAUDE.md`, `DECISIONS.md`, `CONTEXT.md`, `TODOS.md` — record the migration + escaping contract + MD-6 guard | Owner: Antigravity | Model: n/a |
      Review: none | SHA: 57c1c3c

## Story done when

Acceptance criteria — prose, no checkboxes. Verified at story close; per-task status lives
only in the working list above.

- **MD-1** — `escape_markdown()` / `mdcode()` exist in `src/notifications/markdown.py` with
  tests covering every reserved char, prose punctuation, the `mdcode` backtick fallback, empty
  string, and the 2026-08-11 non-reserved-Unicode / realistic-`=` regression cases.
- **MD-2** — `TelegramNotifier.send()` sends `{"text": text, "parse_mode": "MarkdownV2"}`
  verbatim; the HTML-specific tests are replaced; the entity-parse-error regression test
  asserts `send()` returns `False` without raising (non-fatal contract intact).
- **MD-3** — all 7 strategy `_send_close_notification` paths escape their dynamic values and
  static template punctuation; one underscore-survival test per method; real `@code-reviewer`
  (Opus) ran.
- **MD-4** — `send_notification` is on MarkdownV2; all 5 reporting/entry callers escaped in the
  same commit as the flip; `send_approval_request` escaped with the auth coordination-check.
- **MD-6** — the static-scan guard passes with a documented `_BASELINE_UNESCAPED`; the two
  baseline-maintenance tests enforce that downstream tasks clear their entry on fix.
- **MD-7** — the three gap sets (`pre_market_brief`, IC-entry `_gate_alert`, `auto_close` /
  `overlay_closer` non-close paths) are escaped and their baseline entries removed.
- **MD-5** — `src/notifications/CLAUDE.md`, `DECISIONS.md`, `CONTEXT.md` record the migration,
  the caller-responsibility escaping contract (dynamic values **and** static punctuation), and
  the MD-6 guard.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Update the epic
`README.md` **Stories** table status column and add one line to `TODOS.md` Session Log.
