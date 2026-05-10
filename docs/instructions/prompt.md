# NiftyShield — Ideal Task Prompts

Reference prompts that trigger the full workflow:
`task_protocol.sh` → CONTEXT.md read → council check → plan gate → routing decision →
implementation (test-runner + code-reviewer) → commit skill (SHA confirmed).

**Rule:** Start with the action verb. Never prefix with "can you" — the `UserPromptSubmit`
hook classifies on the first keyword and will skip injection if it matches a query pattern.

---

## Prompt 1 — New module, Antigravity path (3 files, complete spec)

```
implement India VIX ingestion pipeline:
  fetch daily VIX close from Upstox Analytics endpoint,
  store to Parquet partitioned by date under data/market/vix/,
  expose get_vix_history(from_date, to_date) → pd.DataFrame with UTC timestamps.
Phase: BACKTEST_PLAN.md P1-NEXT.
Files: src/paper/vix_fetcher.py (new), src/paper/vix_store.py (new),
       tests/unit/paper/test_vix.py (new).
DoD: ≥4 offline tests (happy path + empty range + store round-trip + bad date raises),
     CONTEXT.md updated, SHA confirmed in git log.
Route: Antigravity.
```

**Triggers:** task verb → hook injection · `src/paper/` → greeks-analyst · 3 files → Antigravity
routing · Phase reference → BACKTEST_PLAN.md load · UTC/Parquet → code-reviewer mandatory ·
explicit DoD + SHA → commit skill proof step.

---

## Prompt 2 — Bug fix, Claude path (1–2 files, graph queries expected mid-impl)

```
fix PaperStore.record_leg_snapshot:
  upsert is silently overwriting total_pnl when unrealized_pnl is None,
  violating the invariant total_pnl == unrealized_pnl + realized_pnl.
Files: src/paper/store.py, tests/unit/paper/test_paper_store.py.
DoD: failing test added first (red), then fix (green), existing 11 tests still pass,
     SHA confirmed in git log.
Route: Claude.
```

**Triggers:** task verb → hook injection · `src/paper/` → greeks-analyst · 2 files + graph
queries likely → Claude routing · Decimal/P&L invariant → code-reviewer mandatory ·
"failing test first" → TDD discipline enforced by DoD, not by hope.

---

## Prompt 3 — Feature addition, council checkpoint likely (design fork present)

```
add delta-neutral rebalancing trigger to PaperTracker:
  when net portfolio delta breaches ±0.10 threshold, emit a Telegram alert
  with the offending leg, current delta, and suggested adjustment (buy/sell N lots).
  Do not auto-execute — alert only.
Phase: BACKTEST_PLAN.md Phase 0 (paper trading).
Files: src/paper/tracker.py, src/notifications/telegram.py,
       tests/unit/paper/test_tracker_alerts.py (new).
DoD: ≥3 offline tests (breach triggers alert + no alert below threshold + Decimal delta path),
     CONTEXT.md updated, SHA confirmed in git log.
Route: Claude.
```

**Triggers:** task verb → hook injection · `src/paper/` + delta/gamma fields → greeks-analyst ·
council check — two defensible designs exist (threshold as config vs hardcoded) so Step 2b
fires · Telegram (non-fatal contract) → notifications invariant enforced · 3 files but
design ambiguity → Claude routing over Antigravity.

---

## Dimensions a prompt must cover

| Dimension | What to include | Example |
|---|---|---|
| **Files** | Name each file + new/existing | `src/paper/vix_fetcher.py (new)` |
| **Phase** | BACKTEST_PLAN.md section | `Phase: P1-NEXT` |
| **Tests** | Count + case names | `≥4 offline tests (happy + bad date + …)` |
| **DoD** | Docs update + SHA | `CONTEXT.md updated, SHA confirmed in git log` |
| **Route** | Explicit fork | `Route: Antigravity` or `Route: Claude` |
