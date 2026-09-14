# Unified exit message — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

Sub-story 3 of the `telegram-message-unification/` epic. Depends on `unified-entry-message/` + `overlay-entry-message/` — do not start UXM-1 before every UEM and OEM box is ticked (both Stories-table
rows in the epic `README.md` are ✅). UXM-8 is a sub-story close only — `overlay-recovery-digest/` ORD-4 archives the epic.

**Open: UXM-5, UXM-6, UXM-7, UXM-8.**

- [x] **UXM-1** — gross-short-premium `short_decay_pct` (+ `short_credit_per_unit` /
      `short_buyback_per_unit`) on `Cycle`; `cycle_stats(trades) -> CycleStats` (win_rate,
      avg_win/loss, best/worst, avg_hold_days, avg_decay_pct); move `resolve_target` +
      `LegGroup` in from `scripts/dev/cycle_pnl_report.py`; fix the CLI import (output unchanged).
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer + greeks-analyst | SHA: 51d546c
- [x] **UXM-2** — `src/notifications/exit_message.py` (`ExitMessage` / `ExitKind` /
      `format_exit_message`) + `build_close_leg_table` in `formatting.py`. Renderer + tests
      only, no callers. Win-rate row gated at `closed_count >= 5`.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: e9d830d
- [x] **UXM-3** — Migrate IC v1 + v2 `_send_close_notification` to `format_exit_message`.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 22359bf
- [x] **UXM-4** — Migrate CSP (`_reentry_notification` + `⛔ waiting`); extend
      `record_paper_trade.py --notify` to send an exit card on `--close`.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 21a8449
- [ ] **UXM-5** — Migrate CC + PP + Collar strategy-class `_send_close_notification`.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer + greeks-analyst | SHA: —
- [ ] **UXM-6** — Migrate `auto_close.py` daemon paths (Collar / CC / PP); keep the
      `Overlay P&L (total realized)` line as the footer's overlay-total row.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer + greeks-analyst | SHA: —
- [ ] **UXM-7** — Redesign `scripts/pre_market_brief.py`: drop the broken `<b>` HTML, fenced
      house-style table, `strategy_label()` names, `paper_nifty_overlay` broken into CC /
      Collar / PP sub-rows (via UXM-1's `resolve_target`), portfolio total row.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **UXM-8** — Sub-story docs close: `CONTEXT.md` / `src/notifications/CLAUDE.md` / `DECISIONS.md`;
      flip the `unified-exit-message/` row in the epic `README.md` **Stories** table to ✅ with the
      closing SHA; `TODOS.md` Session Log line. No folder archive — `overlay-recovery-digest/` ORD-4
      archives the epic.
      | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —

## Story done when

- **UXM-1** — `Cycle.short_decay_pct` is the gross-short-premium ratio (defined for IC/CSP/CC/Collar, `None` for PP), net `decay_pct` unchanged; `cycle_stats` returns correct win_rate / avg / best /
  worst / avg_decay_pct for a mixed closed-cycle list and all-zero / `None` for an empty one; `resolve_target` imported from `src.paper.cycle_pnl` gives the CLI its unchanged output; tests green;
  `greeks-analyst` clean.
- **UXM-2** — `format_exit_message` renders the Act/Instrument/Entry/Exit/P&L table + the this-exit / cycle / inception footer; the cycle line carries entry-credit → exit-cost → decay% for a credit
  cycle and drops that segment for a net-debit one; win-rate row appears only at `closed_count >= 5` and carries avg decay% when available; this-exit and cycle rows collapse when equal; negative P&L
  renders `-₹` not `₹-`; tests green.
- **UXM-3** — IC v1 and v2 closes emit `✅ *IC v1/v2 Closed*` with the 4-leg table and the footer; no hand-rolled close f-string remains in either module; notify failure non-fatal; tests green.
- **UXM-4** — CSP close emits the shared card (`✅` / `⛔ waiting`); `record_paper_trade.py --close --notify` sends an exit card and `--close` alone stays stdout-only; tests green.
- **UXM-5** — CC / PP / Collar strategy-class closes emit the shared card with the `Overlay P&L (total realized)` line; PP crash path renders `state_line`; tests green; `greeks-analyst` clean.
- **UXM-6** — the three `auto_close.py` daemon branches emit the shared card; the overlay total matches `get_strategy_realized_pnl(store, STRATEGY_OVERLAY)`; tests green; `greeks-analyst` clean.
- **UXM-7** — `pre_market_brief.py` sends a MarkdownV2 fenced table (no `<b>`), strategy labels not raw ids, `paper_nifty_overlay` shown as a parent row + CC / Collar / PP sub-rows (empty sub-group →
  `—`), and a portfolio `Total` row that counts the overlay once; tests green.
- **UXM-8** — `CONTEXT.md`, `src/notifications/CLAUDE.md`, `DECISIONS.md` reflect the shared exit renderer + `cycle_stats` + the brief redesign; the `unified-exit-message/` row in the epic `README.md`
  **Stories** table is ✅ with the closing SHA; `TODOS.md` Session Log line added. The epic folder is **not** archived here — `overlay-recovery-digest/` ORD-4 does that.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then flip this sub-story's row in the epic `README.md` **Stories** table and add one line to `TODOS.md` Session Log. The epic
folder is archived only after the last sub-story (`overlay-recovery-digest/` ORD-4) — see the epic `prompt.md` Step 4.
