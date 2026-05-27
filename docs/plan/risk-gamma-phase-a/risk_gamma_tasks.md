# risk-gamma-phase-a — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md` session log.
> Full story spec for each task: `docs/plan/risk-gamma-phase-a/risk_gamma_stories.md`.

---

## Track A — Delta Gate Wiring

- [x] **A** — Wire `src/risk/` delta gate into `record_paper_trade.py` | SHA: b9c00146e2bb268aa0d8449a295e0d92c17cfab1

---

## Track B — Near-Expiry Gamma Buy (`src/gamma/` + `scripts/gamma_daily_watch.py`)

### Phase B1 — Package scaffolding

- [x] **B1** — `src/gamma/` package: models (`GammaChainSnapshot`, `GammaWatchlistEntry`) + `GammaStore` | SHA: d8c2e69

### Phase B2 — `scripts/gamma_daily_watch.py` (5 sub-tasks, one session each)

- [x] **B2.1** — Script scaffold: CLI flags + expiry resolution | SHA: b68bb3d
- [ ] **B2.2** — Chain fetch + field computation (`_fetch_chain`, `_compute_snapshots`, `_fetch_and_snapshot`)
- [ ] **B2.3** — Snapshot persistence (wire `GammaStore.insert_chain_snapshot` into `_fetch_and_snapshot`)
- [ ] **B2.4** — Watchlist maintenance (`_update_watchlist`: add / retain / remove / elevate logic per §5b)
- [ ] **B2.5** — Percentile calibration + Telegram summary (`_run_calibration`, `build_notifier` wire-up)
