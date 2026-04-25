# NiftyShield — TODOs

> Open work only. Completed items and full session history:
> [docs/archive/TODOS_ARCHIVE_2026-04-24.md](docs/archive/TODOS_ARCHIVE_2026-04-24.md)

---

## Priority Key

| Label | Meaning |
|---|---|
| `P1-NEXT` | Do this sprint — unblocked, highest impact |
| `P2-EVAL` | Decision or evaluation required before any code |
| `P3-DEFER` | Explicitly deferred — reason and ETA documented |
| `P5-DEBT` | Technical debt — fix alongside adjacent refactoring only, never standalone |

---

## ~~P1-NEXT — Greeks Capture~~ — DONE 2026-04-25

Story file: `docs/plan/0_2_greeks_capture.md`

Implemented: `src/models/options.py` (OptionLeg, OptionChainStrike, OptionChain), `src/client/upstox_market.py` (parse_upstox_option_chain + _parse_option_leg + _safe_decimal), `src/portfolio/tracker.py` (_extract_greeks_from_chain + real _fetch_greeks), `tests/unit/test_greeks_capture.py` (16 tests, all green). 883 tests total passing.

---

## ~~P1-NEXT — Paper Trading Module~~ — DONE 2026-04-25

Sprint 0.5 from `BACKTEST_PLAN.md`.

Implemented:
- `src/paper/__init__.py`, `src/paper/CLAUDE.md` — package + module invariants doc
- `src/paper/models.py` — `PaperTrade` (frozen Pydantic, `paper_` prefix validator, `is_paper: Literal[True]`), `PaperPosition` (frozen dataclass, `avg_cost` + `avg_sell_price`), `PaperNavSnapshot` (frozen dataclass)
- `src/paper/store.py` — `PaperStore` with `paper_trades` + `paper_nav_snapshots` tables; UNIQUE idempotency; Decimal-as-TEXT invariant
- `src/paper/tracker.py` — `PaperTracker.compute_pnl()` + `record_daily_snapshot()` + `record_all_strategies()`; correct short P&L via `avg_sell_price`
- `scripts/record_paper_trade.py` — CLI mirroring `record_trade.py`; enforces `paper_` prefix; prints position summary post-insert
- Paper trading is standalone — not wired into `daily_snapshot.py`. Use `record_paper_trade.py` to log entries/exits; `PaperTracker.record_daily_snapshot()` for mark-to-market (call manually or via a future `paper_snapshot.py` script).
- `tests/unit/paper/` — 65 tests (20 models, 24 store, 18 tracker, 9 CLI). 948 total passing.

Architecture decision recorded in `DECISIONS.md`: shared SQLite DB + `paper_` prefix convention; `avg_sell_price` tracked separately for short positions.

---

## P2-EVAL — Nuvama Session P&L Alignment

Decision needed before any code changes.

Current `nuvama_intraday_tracker.py` shows "All-time Total P&L" — cumulative sum of all historical `realized_pnl_today` rows via `get_cumulative_realized_pnl()`. This diverges from the Nuvama mobile/web UI which shows "Session P&L" (Unrealized + Today's Realized only), causing a visible mismatch (e.g. system shows +17k, Nuvama shows -17k).

Options:
1. Keep cumulative — true inception P&L; diverges from Nuvama UI intentionally
2. Switch to session-only — matches Nuvama UI; cumulative history still in DB but not displayed

No implementation until Animesh chooses an option.

---

## P3-DEFER — P&L Visualization

Deferred until late May 2026 (need 4+ weeks of snapshot data).

Deliver as a **persistent Cowork artifact** (self-contained HTML page, re-opens with fresh data each session via live DB queries). Four independent panels, each independently viable:

### Panel 1 — Mutual Funds (MF)
- Source: `mf_nav_snapshots` (NAV history) + `mf_transactions` (cost basis: one INITIAL row per scheme with units + amount)
- Data available: 16 days (2026-04-03 → present), 11 schemes
- P&L formula: `(current_nav − avg_cost_per_unit) × units` per scheme per day
- Chart: cumulative rupee P&L curve per scheme + bar chart of current unrealized gain per scheme

### Panel 2 — Dhan ETFs
- Source: `dhan_holdings_snapshots` (avg_cost_price + ltp + total_qty per day)
- Data available: 9 days (2026-04-14 → present); NIFTYIETF (equity) + LIQUIDCASE (bond)
- P&L formula: `(ltp − avg_cost_price) × total_qty` — directly computable, no join needed
- Chart: daily P&L curve per instrument

### Panel 3 — Nuvama Bonds (NCDs, G-Sec, SGB)
- Source: `nuvama_holdings_snapshots` (current_value per ISIN per day) + `nuvama_positions` (static cost basis: avg_price × qty)
- Data available: 8 days (2026-04-15 → present); EFSL NCDs, G-Sec 8.28% 2027, SGB 2023-24
- P&L formula: `current_value − (qty × avg_price)` per ISIN per day
- Chart: daily mark-to-market P&L per bond instrument

### Panel 4 — Nuvama Options (own options book, not FinRakshak)
- Source: `nuvama_options_snapshots` (unrealized_pnl + realized_pnl_today per leg per EOD snapshot)
- Data available: 7 days (2026-04-16 → present); 23–38 open legs per day
- Caveat: closed legs disappear from subsequent snapshots; `realized_pnl_today` captures same-day closures only
- P&L formula: `SUM(unrealized_pnl)` for open legs + `SUM(realized_pnl_today)` cumulated over all historical dates
- Chart: daily total unrealized P&L + cumulative realized P&L line — strategy-level only, not per-leg

### Not yet possible — Zerodha (FinRakshak + ILTS)
- FinRakshak and ILTS both run on Zerodha. No Zerodha table in DB, no integration built. These strategies are a complete blind spot for visualization until Kite Connect is integrated (see P3-DEFER — Zerodha / Kite Connect Integration below).

### Implementation notes
- All four panels can share one artifact; data fetched via `mcp__workspace__bash` → Python → JSON on open
- Render with Chart.js or Recharts (both available in artifact sandbox)
- `PortfolioSummary` dataclass already extracted and queryable; `PLANNER.md` has broader context

---

## P3-DEFER — Zerodha / Kite Connect Integration

Deferred indefinitely — revisit when FinRakshak/ILTS P&L visibility becomes a priority.

FinRakshak and ILTS both run on Zerodha. Currently zero Zerodha data in the DB — positions, avg cost, and P&L for these two strategies are invisible to NiftyShield.

**Feasibility analysis (2026-04-24):**

Zerodha offers two tiers of Kite Connect API:

- **Personal (free):** `positions()`, `holdings()`, `orders()`, `funds()` — full portfolio state, no market data. Enough to capture holdings and avg cost price.
- **Paid (₹500/month):** Everything above + live LTP via REST (`ltp()`, `quote()`) and WebSocket tick streaming + historical candles.

For NiftyShield's use case the practical approach is a **hybrid**: Zerodha free API for position state (instrument, qty, avg cost) + existing Upstox Analytics token for LTP — the same pattern already used in `src/dhan/`. This avoids the ₹500/month charge while giving full P&L computation.

**Auth:** Kite Connect uses the same daily request-token → access-token flow as Upstox. A `src/zerodha/` module mirroring `src/auth/` would be needed, plus a morning login step.

**Implementation scope when ready:**
- `src/zerodha/` — auth + `KiteClient` implementing `BrokerClient` protocol (positions, holdings only; LTP delegated to Upstox)
- `zerodha_holdings_snapshots` table in SQLite (same shape as `dhan_holdings_snapshots`)
- `morning_nav.py` or new script to snapshot Zerodha positions at BOD
- Unblocks Panel 5 in P&L Visualization artifact (FinRakshak + ILTS)

**Note:** Zerodha also launched a **Kite MCP** server (2025) — could enable direct Zerodha queries inside Cowork sessions without building a custom client. Worth evaluating before writing `src/zerodha/` from scratch.

---

## P5-DEBT — Technical Debt

Fix alongside adjacent refactoring. Never worth a standalone commit.

### ~~DEBT-1: `@staticmethod` overuse (TD-1)~~ — DONE 2026-04-24

All 8 `@staticmethod` row-mapper / helper methods promoted to module-level `_private_function()`. No logic changes. 868 tests green.

### DEBT-3: Missing license boilerplate (TD-4)

License decision needed before this can be automated. Every file should carry a header once the license is chosen.

---

## Session Log

| Date | What Changed |
|---|---|
| 2026-04-24 | **DEBT-1 (`@staticmethod` overuse).** Promoted 8 static methods to module-level `_private_function()` across `src/mf/store.py`, `src/portfolio/store.py`, `src/portfolio/tracker.py`, `src/dhan/store.py`, `src/instruments/lookup.py`, `src/client/upstox_market.py`. Added `import sqlite3` to `dhan/store.py`. 868 tests green. |
| 2026-04-24 | **Root markdown cleanup.** Archived all ✅ DONE items (PKG-1–4, DEBT-2,4,5) + session log to TODOS_ARCHIVE_2026-04-24.md. Moved `python-architecture-review.prompt.md` to `docs/`. Updated README.md project structure to actual src/ layout. Wrote `.claude/skills/md-cleanup/SKILL.md`. |
| 2026-04-24 | **P&L Visualization scoping.** Audited DB for all viable data sources. Expanded P3-DEFER with 4 panels (MF, Dhan ETFs, Nuvama Bonds, Nuvama Options), data availability, P&L formulas, and known gap (Zerodha/FinRakshak not integrated). |
| 2026-04-24 | **Zerodha/Kite feasibility + corrections.** Corrected Panel 4 attribution (Nuvama options ≠ FinRakshak; FinRakshak + ILTS run on Zerodha). Added P3-DEFER entry for Kite Connect integration with free/paid tier analysis, hybrid architecture approach, and Kite MCP note. |
| 2026-04-25 | **Greeks capture implemented (task 0.2).** `src/models/options.py` (OptionLeg, OptionChainStrike, OptionChain frozen Pydantic), `src/client/upstox_market.py` (parse_upstox_option_chain + _parse_option_leg + _safe_decimal helper), `src/portfolio/tracker.py` (_extract_greeks_from_chain + real async _fetch_greeks replacing early-return stub), `tests/unit/test_greeks_capture.py` (16 fixture-driven offline tests). Greeks columns in daily_snapshots now populated. 883 tests green. |
| 2026-04-25 | **CSP v1 strategy review.** Underlying switched from NiftyBees options → Nifty 50 index options (liquidity: OI <1000 / spreads >5% on NiftyBees). `docs/strategies/csp_nifty_v1.md` created as successor; `csp_niftybees_v1.md` retained DEPRECATED. Rules revised: R1 time-stop clarified (21 calendar days from entry), R2 loss-stop changed to delta gate −0.45 OR 1.75× mark, R3 IVR filter added (specified, not yet enforced — no VIX ingestion pipeline), R4 event filter added (specified, not yet enforced — pending task 3.3), R5 re-entry revised (IVR-gated after profit exit), R6 kill criterion added (3× avg credit single-cycle stop), R7 slippage model revised (bid-ask based). Lot size documented as 65 (Jan 2026). Paper-trade minimum raised from 2 cycles to 6 cycles. `DECISIONS.md` updated with Strategy Decisions section. `BACKTEST_PLAN.md` updated: tasks 0.4/0.6/0.8/1.1/1.7/1.8/1.11 revised to reflect new underlying and V1/V2/V3 variant backtest structure. Commits: 946e5a5 (strategy + DECISIONS), follow-up commit (plan + TODOS). |
| 2026-04-24 | **Greeks capture design finalized.** Decisions: Upstox-first (Dhan switch at Phase 1.10 for IV source consistency); strike+asset_type lookup not instrument_key; `get_option_chain_sync` return-type bug noted and deferred. Full phase breakdown + 16-test plan written to `docs/plan/0_2_greeks_capture.md`. DECISIONS.md updated with OptionChain model decisions. Implementation not yet started — ready to pick up next session. |

Full log (2026-04-01 → 2026-04-24): [docs/archive/TODOS_ARCHIVE_2026-04-24.md](docs/archive/TODOS_ARCHIVE_2026-04-24.md)
