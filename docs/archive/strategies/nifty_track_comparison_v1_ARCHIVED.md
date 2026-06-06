# Archived — nifty_track_comparison_v1.md

**Archived:** 2026-06-06
**Superseded by:** `docs/plan/council-refactor/stories_overlay.md` (NT-1, NT-2, CR2, CR3)

---

## What was absorbed into council-refactor stories

| Strategy doc section | Absorbed into |
|---|---|
| Proxy Early Exit Trigger (δ<0.40 for 3 days) | NT-1 — `evaluate_proxy_delta()` + `PaperStore` breach counter |
| Proxy Premium Decay Kill (mark<₹0.50, DTE≥5) | NT-1 — `PROXY_PREMIUM_DECAY` signal |
| Proxy Delta Warning (δ<0.65) | NT-1 — `PROXY_DELTA_WARN` signal |
| Futures + standalone CC blocked combination | NT-2 — `_check_futures_cc_block()` runtime guard |
| Overlay DTE ≤ 5 roll signal | CR2 — `evaluate_roll_overlay()` |
| Base-DTE guard (do not roll overlay before base) | CR2 — `ROLL_BASE_FIRST` WARN |
| Wire overlay roll into NiftyTrackComparisonV1 | CR3 |
| NT-1/NT-2 DECISIONS.md + CONTEXT.md entries | CR4 — `stories_close.md` |

---

## What is NOT in any story (operational reference — preserved here)

The following sections are **not implemented in code** — they are human-operated procedures
and research framework rules. Read this file (or the council source doc) for these:

- **Entry rules**: base leg entry timing (first Wednesday after expiry, 10:00–10:30 AM),
  Proxy delta ≥ 0.85 gate, `find_strike_by_delta.py` invocation for Proxy, Futures front-month
  roll, Spot NEE qty formula `floor((lot_size × nifty_spot) / niftybees_ltp)`.
- **Overlay expiry selection**: spread_pct ≤ 3% gate for quarterly/yearly vs monthly fallback;
  collar must use same expiry for both legs.
- **Monthly roll procedure**: roll all three tracks same day (Wednesday after expiry); re-run
  `find_strike_by_delta.py` for Proxy at each roll; never defer.
- **Annual Spot reset**: January each year — SELL at current NiftyBees LTP, re-BUY at new NEE qty.
- **Framework-level kill criteria**: 5 criteria (5% NEE loss in 30 days, Futures uncovered short,
  Proxy data gap ≥3 days, three consecutive roll failures, regulatory block). See original doc.
- **Position sizing and slippage model**: NEE = nifty_spot × 65; slippage tiers; transaction
  cost schedule.
- **Comparison conclusion gate**: 6 complete cycles, ≥1 high-VIX event (India VIX>18), full
  P&L attribution, Greeks logged ≥80% of days.
- **P&L report schema**: per-track base + overlay breakdown, net Greeks, cycle max drawdown,
  Return on NEE. Used by `paper_snapshot.py`.
- **Approved overlay menu**: PP (all tracks), CC (Spot + Proxy only), Collar (all). Futures +
  standalone CC permanently blocked. Redundant but not blocked: Proxy+PP, Futures+PP.
- **Regime and fail-mode analysis**: trending bull, range-bound collar, high-IV entry, crash
  scenarios, low-IV flat market.

---

## Primary source

`docs/council/2026-05-02_nifty-long-instrument-comparison-protection.md` Stage 3 — the council
ruling is the ultimate authority on overlay menu decisions (especially the Futures+CC block).
