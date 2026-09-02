# src/portfolio — Reference Notes

> **Not auto-loaded.** Reference detail relocated out of `CLAUDE.md` (FIX-2,
> `docs/plan/token-efficiency/fixed-overhead/`) so the auto-injected file carries only
> invariants and caller contracts. File-level module tree: `CONTEXT_TREE.md`.

---

## `overlay_coverage.py` — why it lives here

`overlay_coverage.py` (added S3r, 2026-07-29) is **paper-trading** code — it reads
`PaperStore`/`PaperPosition` from `src/paper/`, not this module's `store.py`/`models.py`.
It lives here only because the story called for a query-time join comparable in spirit to
`PortfolioTracker`'s per-strategy joins; it shares no types, tables, or constraints with the
rest of this module.

---

## `apply_trade_positions()` — where it's wired

- `PortfolioTracker._get_overlaid_strategy()` / `_get_all_overlaid_strategies()` — private
  helpers called internally before every `compute_pnl`, `record_daily_snapshot`,
  `record_all_strategies`.
- `daily_snapshot.py _async_main()` and `_historical_main()` — both call it via
  `apply_trade_positions()` after `get_all_strategies()`.

Callers do **not** need to apply it manually for tracker paths — the overlay is internalized.

---

## Models in `models.py`

- `Leg`, `Strategy`, `DailySnapshot`, `Trade`, `TradeAction` — all here
- `Trade` is `frozen=True` with validators: `qty > 0`, `price > 0`
- P&L methods accept `float | Decimal`, always return `Decimal`
- `PortfolioSummary` frozen dataclass — carries combined totals + four day-delta fields (all
  `Decimal | None`)

## Strategy Registry

- `src/portfolio/strategies/__init__.py` — `ALL_STRATEGIES` list
- `src/portfolio/strategies/finideas/ilts.py` — `ILTS` (4 legs: EBBETF0431 + 3 Nifty options)
- `src/portfolio/strategies/finideas/finrakshak.py` — `FinRakshak` (1 leg: protective put)
