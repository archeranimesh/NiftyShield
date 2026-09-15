# Unified exit message — prompt

> One shared close-confirmation renderer for every paper strategy whose entry message was unified (`unified-entry-message/` + `overlay-entry-message/`): IC v1/v2, CSP, CC, PP, Collar. Carries
> this-exit / cycle / inception P&L plus win-rate stats, replacing four divergent hand-rolled close f-strings.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

The entry-message stories built `src/notifications/entry_message.py` and unified every entry card. The **close** side was never touched and has drifted into four shapes:

- **IC v1 / v2** (`ic_nifty_v1.py` ~828, `ic_nifty_v2.py` ~2228) — `✅ *IC closed — {signal}*`
  + `Strategy:` / `Action:` / `Net P&L:` lines + a raw `{leg_role}: {action} {qty} @ {price}` list. P&L is inception realized (`get_strategy_realized_pnl`), not this cycle.
- **CSP** (`csp_nifty_v1.py` ~635 `_reentry_notification`, ~469 `⛔ *CSP closed — waiting*`) — text only: instrument key, no prices, no P&L, no legs. `record_paper_trade.py --close` prints `position
  closed` to stdout and sends nothing.
- **CC / PP** (`cc_overlay_v1._send_close_notification` ~374, `pp_overlay_v1` ~393) — one `📤 Closed: {label} @ {exit}` line + `Entry … · Delta … · DTE …`. No P&L at all.
- **Collar** (`collar_overlay_v1._send_close_notification` ~715) — two `📤` leg lines, per-leg `Entry / Delta / DTE`. No P&L.
- **`auto_close.py`** daemon (~302 Collar, ~321 CC, ~350 PP) — a *fifth* shape: per-leg `@ {exit} (entry {e}) → {pnl}` + `Signal:` + `Net P&L:` + `Overlay P&L (total realized):` (via
  `get_strategy_realized_pnl(store, STRATEGY_OVERLAY)`).

Four headline conventions (`✅ closed`, `💰 :`, `⛔ waiting`, `🔄 rolled`), P&L shown in two of five, leg prices absent from CSP entirely. Animesh asked (2026-09-10) to unify the close message and add
cycle + inception P&L and win-rate stats.

## The three P&L levels (all derivable today, all different)

- **This exit** — P&L of the legs closed in *this* action. Equals the cycle for a full close; differs for a partial / single-leg close (CC closing one collar leg).
- **Cycle** — the current round trip. `get_last_cycle_realized_pnl(trades)` for the just-closed one; hold days + the decay figure come from the same `Cycle`
  (`src/paper/cycle_pnl.py::reconstruct_cycles`).
- **Inception** — `get_strategy_realized_pnl(store, strategy_name)`. Use this for the headline number, **not** the sum of cycle `realized_pnl` — cycle reconstruction is an approximation (mid-cycle
  defends not fully captured) and the two drift. Cycles drive the *stats*, the store call drives the *number*.

## Decay basis — gross short premium (decided with Animesh 2026-09-10)

The existing `Cycle.decay_pct` divides by the **net** entry premium (short legs minus hedges), which is `None` for a net-debit entry — it goes unstable for a near-zero collar net and inverts for a
long put. UXM-1 adds a `short_decay_pct` computed against the **gross premium of the short legs only** (hedges / longs excluded): `100 * (short_credit − short_buyback) / short_credit`. This is stable
and carries one meaning — *how much of the premium you sold did you keep* — for IC, CSP, CC and Collar (all have a short leg), and is correctly `None` for PP (a pure long has no premium-capture
story). Every exit card and `cycle_stats` uses `short_decay_pct`; the net `decay_pct` stays on `Cycle` for the report CLI.

Win rate / avg-win / avg-loss / best / worst / avg-hold / avg-decay are a pure helper over `[c for c in reconstruct_cycles(trades) if not c.is_open]`.

## Scope guard

**In bounds:** new `src/notifications/exit_message.py` · `src/notifications/formatting.py` (a new `build_close_leg_table` — the entry table's `build_leg_table` stays untouched) ·
`src/paper/cycle_pnl.py` (new `cycle_stats` helper + a `resolve_target` / `_Group` move from `scripts/dev/cycle_pnl_report.py` so `src/` can import it) · `src/strategy/ic_nifty_v1.py` ·
`ic_nifty_v2.py` · `csp_nifty_v1.py` · `cc_overlay_v1.py` · `pp_overlay_v1.py` · `collar_overlay_v1.py` · `src/strategy/auto_close.py` · `scripts/record/record_paper_trade.py` (extend UEM-2's
`--notify` to also fire on `--close`) · `scripts/pre_market_brief.py` (UXM-7 redesign) · `src/notifications/formatting.py` `STRATEGY_LABELS` (add any `paper_*` id the brief lists that is missing) ·
`scripts/dev/cycle_pnl_report.py` (import path only) · matching `tests/unit/`.

**Out of bounds:** `entry_message.py` / `build_leg_table` (unchanged) · the entry cards shipped by the two entry stories · roll *execution* logic (`csp_roll_executor`, `ic_close_executor`,
`roll_utils`) — this is the *message* only · re-entry *failure* notifications (`_send_reentry_failure_notification`) · any DB schema (no `schema.md` — `paper_exit_events` + the `paper_trades` ledger
already carry everything) · `PaperTracker` P&L math · `TelegramGateway` / `TelegramNotifier` internals · the brief's IVR / position-fetch logic (UXM-7 is the message only).

Changes `src/` and `scripts/` behaviour: every close message switches to the shared card with the P&L footer; CSP gains prices + P&L it never had; `record_paper_trade.py --close --notify` sends an
exit card; the daily pre-market brief switches to a fenced table with the overlay broken into CC / Collar / PP.

## Session-start load hints

- `unified-entry-message/` + `overlay-entry-message/` (sibling sub-stories in this epic) — the `EntryMessage` / `format_entry_message` design and the sign-aware net line (OEM-1) this mirrors.
- `src/notifications/CLAUDE.md` — §"Instrument Label Formatting"; the escaping-boundary contract (fenced block emitted literally, every interpolated value pre-escaped).
- `FORMATTING.md` §3 — `build_leg_table` 1-dp exception; the close table follows the same.
- `src/paper/cycle_pnl.py` + `scripts/dev/cycle_pnl_report.py` — `Cycle`, `reconstruct_cycles`, `get_last_cycle_realized_pnl`, `resolve_target` / `_Group` (moving to `cycle_pnl.py`).
- `src/paper/tracker.py::get_strategy_realized_pnl` — the inception number.
- `docs/bugs/bugs.md` BUG-043 — the `cycle_pnl` helper's shared-consumer history.

## Task overview

- **UXM-1** — gross-short-premium `short_decay_pct` (+ `short_credit_per_unit` / `short_buyback_per_unit`) on `Cycle`; `cycle_stats(trades) -> CycleStats` pure helper in `src/paper/cycle_pnl.py`
  (closed-count, wins, losses, win_rate, avg_win, avg_loss, best, worst, avg_hold_days, avg_decay_pct over `short_decay_pct`); move `resolve_target` + `_Group` there from the report CLI; fix the CLI
  import (CLI output unchanged). `greeks-analyst` gate (`src/paper/`).
- **UXM-2** — `src/notifications/exit_message.py`: `ExitMessage` + `format_exit_message` + `ExitKind` enum; `build_close_leg_table` in `formatting.py`. Renderer + tests only, no callers. Footer:
  this-exit / cycle (+ decay, held) / inception / win-rate (gated `closed_count >= 5`, else omitted) / overlay-total (overlay strategies only).
- **UXM-3** — Migrate IC v1 + v2 `_send_close_notification` to `format_exit_message`.
- **UXM-4** — Migrate CSP (`_reentry_notification` + `⛔ waiting`); extend `record_paper_trade.py --notify` to send an exit card on `--close`.
- **UXM-5** — Migrate CC + PP + Collar strategy-class `_send_close_notification`. `greeks-analyst` gate.
- **UXM-6** — Migrate `auto_close.py` daemon paths (Collar / CC / PP), keeping the `Overlay P&L (total realized)` line as the footer's overlay-total row. `greeks-analyst` gate.
- **UXM-7** — Redesign `scripts/pre_market_brief.py`: drop the broken `<b>` HTML, MarkdownV2 fenced table, `strategy_label()` names, `paper_nifty_overlay` broken into a parent row + CC / Collar / PP
  sub-rows (via UXM-1's `resolve_target`), a portfolio `Total` row.
- **UXM-8** — Sub-story docs close: `CONTEXT.md`, `src/notifications/CLAUDE.md`, `DECISIONS.md`; flip the `unified-exit-message/` row in the epic `README.md` **Stories** table to ✅; `TODOS.md` Session
  Log. No folder archive — `overlay-recovery-digest/` ORD-4 archives the epic.

## Definition of done

`format_exit_message` renders a close card with the Act/Instrument/Entry/Exit/P&L table and the this-exit / cycle / inception / win-rate footer. All six strategies (IC v1/v2, CSP, CC, PP, Collar) and
both paths (strategy-class + `auto_close.py`) emit it; `record_paper_trade.py --close --notify` sends it. No hand-rolled `✅ … closed` / `📤 Closed:` f-string remains in `src/strategy/`. Win rate is
shown only at `closed_count >= 5`. Send failure is logged and never crashes a tick or a recording. `pre_market_brief.py` sends a MarkdownV2 fenced table (no `<b>`) with the overlay split into CC /
Collar / PP and a portfolio total. All unit tests green. Sub-story docs updated and its epic `README.md` Stories-table row flipped to ✅ — the epic folder is archived only after
`overlay-recovery-digest/` ORD-4.

## Perspectives not covered

Whether a 4–5 line P&L footer on *every* close message is signal or clutter for a trader who already gets the EOD digest (`eod_pt_summary.py`) — this story assumes the at-close moment is exactly when
inception + win-rate context is wanted. A per-strategy `verbose_exit_footer` toggle is deferred. Also: win rate over 7–12 cycles is statistically thin; the `>= 5` gate is a blunt guard, not a
confidence interval.
