# risk-gamma-phase-a — Session Orientation

> **What this story covers:** Two parallel tracks shipped in one phase:
> (A) wiring `src/risk/` delta gate into `record_paper_trade.py`, and
> (B) the Near-Expiry Gamma Buy strategy scaffolding + `gamma_daily_watch.py` script.
>
> Track A is complete. Track B is in progress at B2.2.

---

## Context

- `src/risk/` — fully implemented: `PortfolioDeltaTracker`, `check_entry_allowed`, 20 unit tests green.
- `src/gamma/` — scaffolding complete: `GammaChainSnapshot`, `GammaWatchlistEntry`, `GammaStore`, `gamma_daily_watch.py` skeleton (CLI + expiry resolution).
- Full strategy spec for the gamma buy strategy: `docs/strategies/near_expiry_buy_v1.md`.

---

## Session start protocol

> Antigravity: find the first unchecked `- [ ]` line in `risk_gamma_tasks.md`. That is your only task.
> Do not look at any other unchecked item. One task. Complete it fully. Stop.

1. Read this file + `CONTEXT.md` + `src/gamma/CLAUDE.md` (if present).
2. Check `risk_gamma_tasks.md` — first unchecked item only.
3. For each task: read story spec in `risk_gamma_stories.md` before writing any code.
4. After task: tick `risk_gamma_tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md`.

---

## Task overview

| Task | Status | SHA |
|------|--------|-----|
| A — Wire delta gate into `record_paper_trade.py` | ✅ Done | b9c00146 |
| B1 — `src/gamma/` models + GammaStore | ✅ Done | d8c2e69 |
| B2.1 — Script scaffold: CLI + expiry resolution | ✅ Done | b68bb3d |
| B2.2 — Chain fetch + field computation | ⬜ Next | — |
| B2.3 — Snapshot persistence | ⬜ | — |
| B2.4 — Watchlist maintenance | ⬜ | — |
| B2.5 — Percentile calibration + Telegram summary | ⬜ | — |

**Next task:** B2.2 — chain fetch + field computation in `scripts/gamma_daily_watch.py`.
