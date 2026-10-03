
# Gamma Near-Expiry Buy — epic index

> The Near-Expiry Gamma Buy strategy (`docs/strategies/near_expiry_buy_v1.md`) delivered as two stories that share one `src/gamma/` package: Phase A captures daily chain snapshots and maintains the
> strike watchlist; Phase B runs the 5-minute intraday signal scan on top of it. They are one epic because Phase B reuses Phase A's derived-field, store and watchlist seams and is gated on Phase A's
> data.

## Why this epic exists

Phase A was scaffolded alone, with `gamma_scan.py` noted as "a separate story" in a footer. A design review against `docs/refactor/` (2026-10-03) showed Phase A would trap shared logic in a script and
that Phase B would then duplicate it. Grouping both under one epic makes the shared seams and the ordering explicit.

## Scope decisions

- Paper trades only; no live-order placement anywhere in this epic.
- Phase B starts only after Phase A is closed **and** ≥ 5 trading days of `gamma_chain_snapshots` exist (strategy doc Phase B gate).
- Stage 1 thresholds are taken as written in the strategy doc; calibration is a later, data-driven step.

## Architecture and design review

Run against `docs/refactor/design-principles.md` and `code-deduplication-and-taxonomy.md` on 2026-10-03. Shared seams, owned by Phase A and consumed by Phase B: `src/gamma/derive.py` (pure
derived-field maths), `GammaStore` (snapshots, watchlist, percentile columns), `ChainSource`-style chain fetch. Rules live in pure `src/gamma/` modules (`watchlist.py`; Phase B's `signals.py`,
`ranking.py`, `exits.py`); scripts are thin orchestration only. Dependencies are one-way: `src/gamma/` never imports from `scripts/`. Per-story outcomes are in each story's `prompt.md` Design review
section.

## Stories

| Story | Purpose | Status | Depends on | Closing SHA |
|---|---|---|---|---|
| `risk-gamma-phase-a/` | Delta gate (done) + `gamma_daily_watch.py`: snapshots, watchlist, percentile calibration | 🔄 In progress — next B2.4 | — | — |
| `gamma-scan-phase-b/` | `gamma_scan.py`: 5-min signal stack, `gamma_signal_log`, paper entry, exits | ⬜ Not started | `risk-gamma-phase-a` + ≥ 5 days of data | — |

Status: ⬜ Not started · 🔄 In progress · ✅ Done. This column is the epic's progress view — per-task checkboxes live only in each sub-story's `tasks.md`.

## Cross-cutting constraints

Offline-first tests; `Decimal` for all money and Greeks; every entrypoint script follows `LOGGING.md` (`scripts.<subdir>.<module>` logger name, `setup_logging()`); every Telegram send is non-fatal.

## Supersession / coordination

Independent of every other epic. Supersedes the standalone `risk-gamma-phase-a/` plan folder (moved here 2026-10-03). The old `docs/archive/plan/story_risk_gamma_phase_a.md` is history only.

## Epic done when

- **risk-gamma-phase-a** — `gamma_daily_watch.py` runs end to end, all tasks closed.
- **gamma-scan-phase-b** — `gamma_scan.py` live on cron with one reviewed dry-run, all tasks closed.
