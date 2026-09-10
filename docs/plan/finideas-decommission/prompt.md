# Finideas decommission — prompt

> Fully remove the Finideas strategies (`finideas_ilts`, `finrakshak`) from NiftyShield —
> the strategy-provider code, the portfolio-snapshot reporting, the seed data, and every
> Finideas row in `portfolio.sqlite` — after Animesh decided (2026-09-10) the Finideas
> product is not worth running.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else.
Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task.
Read that task's full spec in `stories.md` (same task id) before writing any code.
One task per session. Complete it fully. Stop.

## Why this story exists

Animesh has wound down the Finideas product and is no longer running `finideas_ilts` (ILTS
overlay + its ETF legs `EBBETF0431` / `LIQUIDBEES`) or `finrakshak` (the MF hedge). The daily
portfolio snapshot still reports all of it — the `├ Finideas P&L` line, its share of the
`Derivatives` subtotal and `💰 Total`, the entire `🛡 Hedge (FinRakshak)` block, and the ETF
value under `Equity`. Requested 2026-09-10: remove every Finideas-derived value from the
message and clean the underlying data.

`finideas` is the **only** strategy provider in `src/portfolio/strategies/` —
`ALL_STRATEGIES = [*FINIDEAS_STRATEGIES]` and `create_strategy_instance` hard-codes
`["finideas"]`. Every current `trades` row and all `etf_value` belong to `finideas_ilts`.
So a full exit removes the options / hedge / ETF half of the portfolio snapshot and the
whole `src/portfolio/strategies/` layer, leaving MF + Nuvama bonds + Nuvama options + Dhan.

**History decision (Animesh, 2026-09-10): option A — hard-delete every Finideas row.**
`strategies` / `legs` / `trades` / `daily_snapshots` rows for `finideas_ilts` and `finrakshak`
are deleted outright. No archive table, no export. Consequence, accepted: the all-time
`Total P&L` figure drops the realized Finideas P&L that was in the closed history, and that
history is not recoverable from the DB afterwards. Because it is a straight `DELETE` with no
new table, this story carries **no `schema.md`**.

## Scope guard

**In bounds:** `src/portfolio/strategies/` (whole `finideas/` package + registry
`__init__.py`) · `src/models/portfolio.py` (`HedgeStrategy`, the `["finideas"]` provider list
in `create_strategy_instance`, `finrakshak_day_delta` on `PortfolioSummary` if that type
lives here) · `src/portfolio/summary.py` (`_build_portfolio_summary`, `PortfolioSummary`) ·
`src/portfolio/formatting.py` (`_format_combined_summary` waterfall + fallback,
`_format_protection_stats`) · `src/portfolio/store.py` (docstring examples only) ·
`src/dhan/reader.py` + `src/nuvama/reader.py` (the `finideas_ilts` / `LIQUIDBEES` dedup
comments and any ISIN-tracking coupling) · `scripts/seed/seed_trades.py` ·
`scripts/seed/seed_mf_holdings.py` · `scripts/record/record_trade.py` ·
`scripts/portfolio/roll_leg.py` · `scripts/lookup/instrument_lookup.py` (example strings) ·
a new `scripts/dev/decommission_finideas.py` CLI · `tests/unit/**` for every file above ·
`REFERENCES.md` / `CONTEXT.md` / `CONTEXT_TREE.md` / `DB_REGISTRY.md` / `DECISIONS.md` /
`src/portfolio/CLAUDE.md` / `src/portfolio/NOTES.md`.

**Out of bounds:** the paper-trading engine (`src/paper/`, `src/strategy/`) — Finideas is a
`src/portfolio/` live-tracking concept only · `telegram-message-unification/` and any paper
strategy entry/exit card · the MF / Nuvama bond / Nuvama options / Dhan snapshot paths beyond
removing their coupling to Finideas strategy legs · `paper_trades` / any paper table · the
`daily_snapshot.py` cron schedule · the live broker clients.

Changes `src/` and `scripts/` behaviour: the daily portfolio snapshot stops reporting
options, the FinRakshak hedge, and the ETF; `get_all_strategies()` returns `[]`; the
all-time `Total P&L` is recomputed without Finideas.

## Session-start load hints

- `src/portfolio/CLAUDE.md` — auto-loads; the strategy-layer + snapshot invariants.
- `REFERENCES.md` §"Finideas ILTS" / §"Finideas FinRakshak" / §"FinRakshak Protected MF
  Portfolio" — the position definitions being deleted; remove these sections at FD-7.
- `DB_REGISTRY.md` — the `strategies` / `legs` / `trades` / `daily_snapshots` rows; update
  at FD-5 with the post-delete row counts.
- `CONTEXT.md` lines ~99–106 — the trade-seed + manual-close history for `finideas_ilts` /
  `finrakshak`; this is the data FD-5 deletes.
- `DECISIONS.md` §"P&L & Reporting" and §"daily_snapshot.py Design" — where the FD-7
  decision row goes.
- No council file. No `schema.md` (straight `DELETE`).

## Task overview

- **FD-1** — Pre-delete audit: confirm no open Finideas legs / broker positions remain and
  record the exact rows (`strategies` / `legs` / `trades` / `daily_snapshots` counts + ids)
  that FD-5 will delete, plus the current all-time `Total P&L` for a before/after check.
- **FD-2** — Delete the `src/portfolio/strategies/finideas/` package; drop `HedgeStrategy`
  (nothing else hedges); remove the `["finideas"]` provider list + `ALL_STRATEGIES` wiring;
  `create_strategy_instance` returns the base `Strategy` for any unknown name.
- **FD-3** — Remove `options_pnl` / `options_day_delta` / `finrakshak_day_delta` / the
  Finideas-ETF terms from `_build_portfolio_summary` + `PortfolioSummary`; `total_value` /
  `total_pnl` recompute from MF + bonds + Nuvama options + Dhan only.
- **FD-4** — Rework `_format_combined_summary`: drop the `├ Finideas P&L` line, the
  `Derivatives` parent (keep Nuvama options where it reads best), the `🛡 Hedge (FinRakshak)`
  block, `_format_protection_stats`, and the fallback `Finideas ETF` line.
- **FD-5** — `scripts/dev/decommission_finideas.py`: a tested CLI that hard-deletes every
  `finideas_ilts` / `finrakshak` row from `strategies` / `legs` / `trades` /
  `daily_snapshots` in one transaction (`--dry-run` default, `--apply` to commit); update
  `DB_REGISTRY.md`.
- **FD-6** — Seed / example cleanup: `seed_trades.py`, `seed_mf_holdings.py`,
  `record_trade.py`, `roll_leg.py`, `instrument_lookup.py`, and the `LIQUIDBEES` /
  `finideas_ilts` dedup comments in `src/dhan/reader.py` + `src/nuvama/reader.py`.
- **FD-7** — Docs close: `CONTEXT.md`, `REFERENCES.md`, `CONTEXT_TREE.md`, `DECISIONS.md`,
  `src/portfolio/CLAUDE.md`, `src/portfolio/NOTES.md`, `docs/plan/README.md`, `TODOS.md`;
  archive the folder.

## Definition of done

`get_all_strategies()` returns `[]` and the daily portfolio snapshot (waterfall and fallback
paths) renders with no `Finideas P&L`, no `Derivatives` options line, no `🛡 Hedge
(FinRakshak)` block, and no ETF value — MF + Nuvama bonds + Nuvama options + Dhan only. No
`finideas` / `finrakshak` / `ilts` / `HedgeStrategy` reference remains in `src/` or
`scripts/` outside a historical-note context. `scripts/dev/decommission_finideas.py --apply`
has removed every Finideas row from the four tables and `DB_REGISTRY.md` reflects the new
counts. All unit tests green. Docs updated and the folder archived per §Conventions
*Completion → archive*.

## Perspectives not covered

A P&L-accounting perspective on whether hard-deleting the closed Finideas realized P&L is the
right call for a solo trader's long-term track record — option A was chosen deliberately by
Animesh over an export-first (B) or archive-table (C) path; FD-1 still captures the
before/after all-time number so the delta is at least recorded in the story. Also
unaddressed: whether `EBBETF0431` / `LIQUIDBEES` are genuinely liquidated at the broker or
merely no longer tracked here — FD-1 must confirm before FD-5 deletes their trade rows.
