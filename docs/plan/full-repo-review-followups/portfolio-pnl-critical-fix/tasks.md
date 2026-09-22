# Portfolio P&L Critical Fix — Tasks

> Find the first unchecked box below. That is the only task for this session.

- [x] **T1** — Fix `get_position()` in `src/portfolio/store.py` to use the weighted SELL price as `average_price` when `buy_qty == 0` (short-first leg), matching the BUY-side weighted-average logic
  already used when `buy_qty > 0`. Add a realized-P&L computation path to `src/portfolio/tracker.py` (or a new helper module) mirroring `src/paper/tracker.py`'s `_compute_realized_pnl_by_leg` pattern,
  and wire it into `apply_trade_positions()` so closed legs contribute realized P&L to the returned `Strategy` instead of vanishing. Add regression tests for: (a) a short-first leg (sell-only trades,
  no BUY), (b) a fully round-tripped leg (BUY then SELL closing it), (c) the existing BUY-first happy path unchanged. | Owner: Claude | Model: claude-opus-5 | Review: code-reviewer | SHA: 63c857a

---

**Source:** `docs/plan/full-repo-review/findings/FR-7_synthesis.md`, FR-7 row 1 (CRITICAL) — FR-2 F1, F2.
