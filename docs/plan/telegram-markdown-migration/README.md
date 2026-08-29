# Telegram Markdown Migration — epic index

> Switch every NiftyShield Telegram message from HTML `<pre>` parse_mode to `parse_mode=MarkdownV2` — a global transport change, then a canonical formatting layer, then a per-message-family migration
> staged by risk. It is one epic rather than three stories because the middle and last stories cannot begin until the transport switch and its codebase-wide escaping audit have landed, and every
> message family shares the one escaping contract the first story defines.

## Why this epic exists

Spawned from a Cowork session (2026-08-07) prototyping a nicer IC EOD audit Telegram message. The prototype (`scratch/2026-08-07_ic_eod_audit_telegram_format.py`) proved Markdown parse_mode gets real
bold **and** a copyable fenced code block in the same message — something HTML parse_mode cannot do (nested `<b>` inside `<pre>` is not reliably rendered by Telegram's HTML parser; see that script's
module docstring for the full elimination trail across HTML / plain / raw-HTML attempts). That prototype also surfaced a real bug class: a lone `_` in dynamic text (`DELTA_WARN`) opens an unclosed
`_italic_` entity in Markdown and 400s the send — silently, since `TelegramNotifier.send()` swallows exceptions by contract (non-fatal notifications).

**Revised 2026-08-07 — target is `parse_mode=MarkdownV2`, not legacy `Markdown` v1.** The prototype used legacy Markdown; `backbone/stories.md`'s MD-2 spec explains the switch. MarkdownV2's larger
reserved-character set removes the "smart" entity-pairing ambiguity that caused the `DELTA_WARN` bug in the first place, and it is Telegram's actively-recommended mode. This also widens `backbone/`
MD-3/MD-4's audit-and-fix pass: MarkdownV2 reserves ordinary prose punctuation (`.` `(` `)` `-` `!`) in addition to markup characters, so static message *templates* need escaping too, not just dynamic
values.

## Scope decisions

**Replace `TelegramNotifier`'s default parse mode globally — not an opt-in second method** (confirmed with Animesh, 2026-08-07). This is the higher-blast-radius option: every existing caller of
`send_plain_message()` / `TelegramNotifier.send()` was written for HTML + `<pre>` (auto-escaped, wrapped) and has never been audited for Markdown special characters in its dynamic content.

**All Telegram messages migrate, not just IC** (confirmed with Animesh). `strategy-rollout/` sequences the actual format migration by risk tier; `backbone/` only changes the transport (parse mode) and
makes existing plain-text messages safe under it — it does not change how any message looks yet.

Confirmed real callers, via the code graph (not assumed):

- 7 strategy classes' `_send_close_notification` — `src/strategy/auto_close.py`, `csp_nifty_v1.py`, `cc_overlay_v1.py`, `collar_overlay_v1.py`, `ic_nifty_v1.py`, `ic_nifty_v2.py`, `pp_overlay_v1.py`
- `TelegramGateway.send_approval_request` — interactive keyboard, auth-sensitive
- `scripts/strategies/ic/paper_ic_snapshot.py` — the EOD audit cron
- `scripts/strategies/ic/paper_ic_monthly_comparison.py` — its hand-counted-width table bug was **already fixed** (`telegram-ic-comparison-formatting/` TGFMT-1, SHA `a69d817`); ROLL-2 builds on that
  fix, does not redo it
- `scripts/strategies/three_track/paper_3track_snapshot.py`
- `scripts/eod_summary.py` — **added 2026-08-08** (message-format-workshop.md session): sends the daily "NiftyShield EOD Paper Summary" via raw HTML parse_mode directly (not
  `TelegramNotifier.send()`), so it fell outside the original audit scope. Now in scope — `strategy-rollout/` ROLL-6 covers its migration. `backbone/`'s audit-and-fix pass should be re-checked against
  this file if it landed before ROLL-6 started.
- ~~`scripts/reporting/paper_pnl_report.py`~~ — **removed 2026-08-12, miscategorized.** CLI-only (stdout, `--json` / plain-text); no `TelegramNotifier` / `TelegramGateway` call exists anywhere in its
  history (single commit `04687f1`, SNAP-4). Never a real confirmed caller — see the "Correction (2026-08-12)" section in the archived `../../archive/plan/telegram-markdown-migration/TODO.md`.

## Stories

| Story | Purpose | Status | Depends on | Closing SHA |
|---|---|---|---|---|
| `backbone/` | MarkdownV2 parse_mode switch + escape every existing caller's dynamic values so nothing silently 400s | ✅ Done | — | `57c1c3c` |
| `formatting-rules/` | Canonical per-type decimal / alignment / sign spec (`FORMATTING.md`) + tested `formatting.py` value + table helpers | ✅ Done | `backbone/` | `75cc123` |
| `strategy-rollout/` | Migrate each message family to the bold / table format, staged by risk (IC audit first, approval requests last) | 🔄 In progress | `backbone/` + `formatting-rules/` | — |

Status: ⬜ Not started · 🔄 In progress · ✅ Done. This column is the epic's progress view — per-task checkboxes live only in each sub-story's `tasks.md`.

Story order is fixed and is the row order above. Do not start `formatting-rules/` before `backbone/`'s escaping helper exists — every formatting helper that interpolates a dynamic value needs it. Do
not start `strategy-rollout/` before both `backbone/` and `formatting-rules/` are complete.

## Cross-cutting constraints

- **Non-fatal send contract** (`src/notifications/CLAUDE.md`) — `TelegramNotifier.send()` is called from `try/except` throughout the strategy layer; notification failures must never raise into
  strategy logic. Nothing in this epic may change that. A message that fails to send after the migration must still return `False` / log a warning, never raise.
- **Escape every dynamic value** — every interpolated value in any `send()` / `send_plain_message()` / `send_notification()` call passes through `escape_markdown()` / `mdcode()` before it reaches a
  MarkdownV2 parser. Static template punctuation (`.` `(` `)` `-` `!`) needs escaping too. `backbone/` MD-6 adds a static-scan guard test that enforces this on every call site added afterward;
  `MD-6`'s `_BASELINE_UNESCAPED` (`tests/unit/notifications/test_escaping_guard.py`) is the documented won't-fix list.
- **MD-2 live-risk window** (added 2026-08-18, Cowork review) — MD-2 (switch the global parse_mode) is blocked only by MD-1, while MD-3/MD-4 (the escaping audit-and-fix for every existing caller) are
  blocked *by* MD-2 rather than bundled with it. If MD-2 merges alone, every unescaped dynamic value in every existing caller is live against MarkdownV2's reserved-character set — the same failure
  shape as the original `DELTA_WARN` bug, across the whole notification surface. The non-fatal contract keeps this from crashing strategy logic, but it also means notifications — including close/roll
  alerts relevant to delta-neutral adjustment decisions — can silently stop arriving for as long as the gap lasts. **Land MD-2 and MD-3/MD-4 together, never MD-2 on its own.** (History: MD-2 did land
  alone, SHA `721daf9`, 2026-08-24 — Animesh chose the one-task-per-session protocol over bundling, aware of the window; MD-3/MD-4 followed as urgent, not routine backlog.)
- **Live-format iteration** — `message-format-workshop.md` (epic root) is a reusable prompt, not tied to one task. Use it every time you iterate a specific message's format: paste a before/after or
  ask for a suggestion, confirm on-device via a scratch script, then have the confirmed result written back into `strategy-rollout/stories.md` / `tasks.md`. This is how ROLL-1 was produced; use it for
  ROLL-2 onward instead of writing a message's final format directly into `stories.md` without a live-confirmed reference script.

## Supersession / coordination

**`telegram-ic-comparison-formatting/`** — TGFMT-1 (the `build_comparison_report()` alignment fix) is shipped and stays as history. **TGFMT-2 through TGFMT-9 are superseded by this epic**, marked as
such in that folder's `tasks.md` (2026-08-07) — they planned the same generalized table-helper + `auto_close.py` retrofit + CLAUDE.md standard this epic's `formatting-rules/` and `strategy-rollout/`
already cover, just under the old HTML parse_mode. Two still-open feature asks from that story (TGFMT-2's Legs row, TGFMT-3's Bkd/Flt month-inception P&L split) are carried into `strategy-rollout/`
ROLL-2's scope, not dropped — see ROLL-2's spec.

**`full-repo-review-followups/telegram-approval-auth-fix/`** — touches `TelegramGateway.send_approval_request`, the same method `strategy-rollout/` ROLL-4 touches. Checked 2026-08-07: its only task
(T1) is already shipped (SHA `5cafc3c`) — the outer `docs/plan/README.md` epic-summary line was stale; `tasks.md` inside the story folder is the source of truth. Re-check `tasks.md` there before
starting ROLL-4 in case new tasks were added since.

**Missing-messages queue — completed and archived (2026-08-29, RDO-17.4).** The one-time gap list of un-migrated Telegram call sites (`TODO.md` + `missing-message-workshop-prompt.md`) was worked
through 2026-08-08..11 — all 10 items confirmed on-device and written back as `strategy-rollout/` `ROLL-7..ROLL-16`. Both files now live in `../../archive/plan/telegram-markdown-migration/`.

## Improvement backlog (added 2026-08-12, Cowork design-review session)

Four process / design improvements identified during a plan review, sequenced by urgency — not listed order. Each has a model recommendation for the owning agent. Re-read this section before picking
up any of the four; do not assume listed order is execution order.

1. **MD-6 (task) — static-scan escaping guard.** Owner: Claude, Model: Sonnet. Closes the only real correctness gap of the four: `backbone/`'s escaping discipline was hand-maintained with no compiler
   / CI check — the same failure shape as the original `DELTA_WARN` bug. A test walks `src/` / `scripts/` for `notifier.send(` / `send_plain_message(` call sites and asserts every interpolated value
   passed through the escaping helpers somewhere upstream. Resequenced to land right after MD-2, not after MD-5, so it catches mistakes as they are introduced. **Status: done (SHA `ce95bbd`).**
2. **FMT-1 design-gate treatment.** Owner: Claude, Model: Opus (for the spec-writing pass itself, not just a post-hoc review). FMT-1 is the highest-leverage doc in the epic — every downstream
   formatter and roughly half of `strategy-rollout/` inherits its decisions — so it gets the stronger model at write-time. **Status: done (SHA `c252bf3`, shipped as root `FORMATTING.md`).**
3. **ROLL-7–16 parallelization restructure.** Owner: Claude, Model: Sonnet. `ROLL-7` through `ROLL-16` are each blocked only on "`backbone/` + `formatting-rules/` complete," not on each other
   (`ROLL-15`/`ROLL-16` are the one pair that must stay sequential — both touch `paper_3track_snapshot.py`). Dependency notes are annotated inline in `strategy-rollout/tasks.md`; formalizing explicit
   parallel "waves" for multi-session execution is lower urgency. **Status: dependency notes recorded, wave-grouping restructure not yet done.**
4. **FMT-1b–1e session bundle.** Owner: Claude or Antigravity, Model: Sonnet. Pure session-count housekeeping — collapse four already-specced non-overlapping doc-only tasks into one session. **Status:
   done — FMT-1b/1c/1d/1e/1f all shipped.**

## Epic done when

- **`backbone/`** — `TelegramNotifier.send()` and `TelegramGateway.send_notification` are on MarkdownV2 parse_mode; `escape_markdown()` / `mdcode()` exist in `src/notifications/` with tests; every
  confirmed caller's dynamic values and static punctuation are escaped; MD-6's static-scan guard passes with a documented `_BASELINE_UNESCAPED`; the non-fatal send contract is unchanged.
- **`formatting-rules/`** — root `FORMATTING.md` states the per-parameter-type decimal / alignment / sign rules and the monospace-table safety rules; `src/notifications/formatting.py` carries the
  value formatters (`format_money`, `format_greek`, `format_strike`, `format_pct`), the dynamic status-emoji helpers, and the table builders (`build_kv_table`, `build_side_by_side_kv_table`,
  `build_leg_table`, `build_compare_table`) with every column width computed from content, never a hand-counted constant.
- **`strategy-rollout/`** — every message family in `tasks.md` is migrated to the confirmed MarkdownV2 format (IC EOD audit, IC monthly comparison, strategy close/roll for all 7 classes, approval
  requests, EOD Paper Summary, and the ten missing-message call sites ROLL-7..ROLL-16), each with a live-confirmed reference and passing tests; ROLL-17 (IC entry confirmation) design is closed via a
  workshop session before implementation; the docs-close task records the final state.

## Conventions

Same as `docs/plan/README.md` §Conventions. This is an epic root: `prompt.md` here is the **router** (`/work` loads it, not a sub-story `prompt.md`) and picks P0 `backbone/` → P1 `formatting-rules/` →
P2 `strategy-rollout/`, first unchecked box, with the Owner / Model / Review routing check built in. Each sub-story folder carries `prompt.md` (session entry point), `tasks.md` (first-unchecked-box
protocol, one canonical `| Owner | Model | Review | SHA` line per task), and `stories.md` (per-task implementation spec). `message-format-workshop.md` is a shared reusable prompt (no task checkboxes)
used across `strategy-rollout/` tasks.
