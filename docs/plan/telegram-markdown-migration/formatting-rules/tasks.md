# Telegram Markdown Migration — Formatting Rules — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task.
Each task = one commit. See `prompt.md` for why the story exists; see `stories.md` for the
per-task spec — each shipped line carries an **As-built** paragraph there.

**Open: none — `formatting-rules/` is complete (closing SHA `75cc123`). FMT-1 shipped as root
`FORMATTING.md` (`c252bf3`) — read it before adding or changing any formatting rule.**

> **Routing:** `Owner` = who implements (`Claude` = judgment-call, `Antigravity` = mechanical
> with an unambiguous spec). `Model` = model the owner ran at. `Review` = the AutoTrigger gate
> per root `CLAUDE.md`.

## Tasks

- [x] **FMT-1** — Per-parameter-type decimal / alignment / sign spec (money, strikes, Greeks, %, expiry) — docs only, shipped as root `FORMATTING.md` | Owner: Claude | Model: claude-opus-5 |
      Review: none | SHA: c252bf3
- [x] **FMT-1f** — Spec `format_money(signed=True)` + Contango/Backwardation vs. Debit/Credit spread labels — docs only | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: bb95a54
- [x] **FMT-1b** — Spec `pnl_emoji` / `alert_emoji` status helpers (presence/sign-based) — docs only; code promoted in ROLL-1a | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: bb95a54
- [x] **FMT-1c** — Spec the IC EOD audit timeframe color/emoji header + `#IC_{Timeframe}_{Version}` hashtag — docs only; code promoted in ROLL-1b | Owner: Claude | Model: claude-sonnet-5 | Review:
      none | SHA: bb95a54
- [x] **FMT-1d** — Spec the multi-strategy summary-table money exception + `Flt`/`Bkd` terminology + bucket-grouping / totals-first convention — docs only | Owner: Claude | Model: claude-sonnet-5
      | Review: none | SHA: bb95a54
- [x] **FMT-1e** — Spec the monospace-table emoji-presentation-glyph risk (double-width inside a fence) — docs only | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: bb95a54
- [x] **FMT-2** — `src/notifications/formatting.py` value formatters (`format_money`, `format_greek`, `format_strike`, `format_pct`) + tests | Owner: Antigravity | Model: n/a | Review: none | SHA:
      166531b
- [x] **FMT-3** — Table-builder helpers (`build_kv_table`, `build_side_by_side_kv_table`, `build_leg_table`) + tests; widths from content, never a constant | Owner: Claude | Model: claude-sonnet-5
      | Review: none | SHA: 17cbeb6
- [x] **FMT-4** — Docs close: `src/notifications/CLAUDE.md`, `CONTEXT.md`, `TODOS.md` | Owner: Antigravity | Model: n/a | Review: none | SHA: 75cc123

## Story done when

Acceptance criteria — prose, no checkboxes. Verified at story close.

- **FMT-1** — root `FORMATTING.md` states the per-parameter-type decimal / alignment /
  sign-display rules and the expiry format; it governs every downstream formatter.
- **FMT-1b–1f** — the dynamic status-emoji, timeframe-header, summary-table money-exception,
  emoji-presentation-glyph, and signed-money / spread-label rules are recorded in
  `FORMATTING.md` (§§ 3, 4, 7, 10, 11).
- **FMT-2** — `format_money` / `format_greek` / `format_strike` / `format_pct` exist in
  `src/notifications/formatting.py` with happy-path + edge-case tests; `format_money` rejects
  `float`.
- **FMT-3** — the three table builders exist in the same module with every column width from
  `max(len(...))`, `build_leg_table`'s 1dp LTP/Entry exception documented in its own docstring,
  and mismatched-row-count / single-leg / empty-input tests.
- **FMT-4** — `src/notifications/CLAUDE.md` and `CONTEXT.md` record the `formatting.py` module.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Update the epic
`README.md` **Stories** table status column and add one line to `TODOS.md` Session Log.
