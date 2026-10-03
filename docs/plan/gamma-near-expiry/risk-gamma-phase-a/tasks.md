# risk-gamma-phase-a — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session. Tick the box and append the completion tail `| Owner: <Claude|Antigravity|Animesh> | Model: <model-id|n/a> | Review:
> <code-reviewer|none> | SHA: <sha>` when done. Add one line to `TODOS.md` session log. See `docs/plan/README.md` §Conventions. Full story spec for each task:
> `docs/plan/gamma-near-expiry/risk-gamma-phase-a/stories.md`.

**Open: B2.3, B2.4, B2.5.**

---

## Track A — Delta Gate Wiring

- [x] **A** — Wire `src/risk/` delta gate into `record_paper_trade.py` | Owner: Animesh | Model: n/a | Review: none | SHA: b9c00146

---

## Track B — Near-Expiry Gamma Buy (`src/gamma/` + `scripts/pipeline/gamma_daily_watch.py`)

### Phase B1 — Package scaffolding

- [x] **B1** — `src/gamma/` package: models (`GammaChainSnapshot`, `GammaWatchlistEntry`) + `GammaStore` | Owner: Animesh | Model: n/a | Review: none | SHA: d8c2e69

### Phase B2 — `scripts/pipeline/gamma_daily_watch.py` (5 sub-tasks, one session each)

- [x] **B2.1** — Script scaffold: CLI flags + expiry resolution | Owner: Animesh | Model: n/a | Review: none | SHA: b68bb3d
- [x] **B2.2** — Chain fetch + field computation (pure `src/gamma/derive.py::derive_snapshots`; script `_fetch_chain`, `_fetch_and_snapshot`) | Owner: Claude | Model: claude-sonnet-5 | Review:
  greeks-analyst | SHA: <pending>
- [ ] **B2.3** — Snapshot persistence (wire `GammaStore.insert_chain_snapshot` into `_fetch_and_snapshot`; catch `DataFetchError`, not bare `Exception`) | Owner: Claude | Model: claude-sonnet-5 |
  Review: code-reviewer | SHA: —
- [ ] **B2.4** — Watchlist maintenance (pure `src/gamma/watchlist.py::evaluate_watchlist` + script `_update_watchlist`; add / retain / remove / elevate per §5b) | Owner: Claude | Model:
  claude-sonnet-5 | Review: greeks-analyst | SHA: —
- [ ] **B2.5** — Percentile calibration + Telegram summary (`GammaStore.update_percentiles`, `_run_calibration`, `build_notifier` wire-up) | Owner: Claude | Model: claude-sonnet-5 | Review:
  code-reviewer | SHA: —

## Story done when

- **B2.2** — `derive_snapshots` (pure, in `src/gamma/`), `_fetch_chain`, `_fetch_and_snapshot` implemented and unit-tested with no network, no real SQLite; prior-OI lookup batched per expiry.
- **B2.3** — `GammaStore.insert_chain_snapshot` wired into `_fetch_and_snapshot`; per-expiry failure isolation (`DataFetchError`) covered by tests.
- **B2.4** — `evaluate_watchlist` + `_update_watchlist` implement add/retain/remove/elevate per `docs/strategies/near_expiry_buy_v1.md` §5b, unit-tested.
- **B2.5** — `update_percentiles`, `_run_calibration` and Telegram summary wired in; non-fatal notifier failure covered by tests.
- `src/gamma/CLAUDE.md` updated (new modules, script now exists, `src/gamma/` never imports from `scripts/`).
