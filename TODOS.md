# NiftyShield — TODOs

> Open work only. Completed items and session history through 2026-04-26:
> [docs/archive/TODOS_ARCHIVE_2026-04-27.md](docs/archive/TODOS_ARCHIVE_2026-04-27.md)

---

## Priority Key

| Label | Meaning |
|---|---|
| `P1-NEXT` | Do this sprint — unblocked, highest impact |
| `P2-EVAL` | Decision or evaluation required before any code |
| `P3-DEFER` | Explicitly deferred — reason and ETA documented |
| `P5-DEBT` | Technical debt — fix alongside adjacent refactoring only, never standalone |

---

## P1-NEXT — `scripts/find_strike_by_delta.py`

Paper trading entry workflow: given an underlying + expiry, fetch the live option chain, filter strikes by a delta range, and print matching strikes with premium and instrument key — ready to pipe directly into `record_paper_trade.py`.

**Scope:**
- `scripts/find_strike_by_delta.py` — new script, no `src/` changes
- CLI: `--underlying NIFTY --expiry 2026-05-29 --option-type PE --delta-min -0.30 --delta-max -0.15 --expiry-date <today>` (defaults to today for spot)
- Uses `UpstoxLiveClient.get_option_chain()` + `parse_upstox_option_chain` (both exist in `src/client/upstox_market.py`)
- Output: table of matching strikes showing strike, delta, IV, bid, ask, LTP, instrument_key
- `--dry-run` prints the first match as a ready-to-run `record_paper_trade.py` command

**Dependencies already in place:** `OptionChainStrike` (delta/iv fields), `parse_upstox_option_chain`, `UPSTOX_ANALYTICS_TOKEN` in `.env`

**Tests:** offline fixture-driven (reuse `tests/fixtures/responses/nifty_chain_2026-04-07.json`); no new fixtures needed

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

### DEBT-3: Missing license boilerplate (TD-4)

License decision needed before this can be automated. Every file should carry a header once the license is chosen.

---

## Session Log

| Date | What Changed |
|---|---|
| 2026-04-27 | **Story 0.1 closed (nuvama test debt).** No code changes. Verified all acceptance criteria already met from prior AR-3/AR-7 sessions: 101 tests across `test_models.py` + `test_options_reader.py` + `test_store.py` (100 pass, 1 skip); full `tests/unit/nuvama/` 154 passed. `docs/plan/0_1_nuvama_tests.md` status updated NOT STARTED → DONE. |
| 2026-04-27 | **BACKTEST_PLAN + PLANNER restructure.** Added task 1.3a (Upstox OHLC ingest, free, prerequisite for swing Tier 1 + all investment backtesting); updated 1.12 gate. Added Phase 2 Track A (swing pipeline, 2.S0–2.S7) + Track B (investment pipeline, 2.I0–2.I5) with CODE/STRATEGY/GATE labels and data-cost notes; 3.5 overlap note; calendar-vs-swing Open Question. Updated PLANNER.md Medium/Long-Term with stage sequences and data cost notes for both research docs. Commit a880256. |

Full log (2026-04-01 → 2026-04-26): [docs/archive/TODOS_ARCHIVE_2026-04-27.md](docs/archive/TODOS_ARCHIVE_2026-04-27.md)
