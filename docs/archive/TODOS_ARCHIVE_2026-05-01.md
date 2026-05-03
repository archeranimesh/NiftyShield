# NiftyShield — Completed Work Archive

> Archived: 2026-05-01. Contains all completed TODO items and session log through 2026-04-30.
> Active open work lives in [TODOS.md](../../TODOS.md).

---

## Session Log (2026-04-27 → 2026-04-30)

| Date | What Changed |
|---|---|
| 2026-04-27 | **Story 0.1 closed (nuvama test debt).** No code changes. Verified all acceptance criteria already met from prior AR-3/AR-7 sessions: 101 tests across `test_models.py` + `test_options_reader.py` + `test_store.py` (100 pass, 1 skip); full `tests/unit/nuvama/` 154 passed. `docs/plan/0_1_nuvama_tests.md` status updated NOT STARTED → DONE. |
| 2026-04-27 | **BACKTEST_PLAN + PLANNER restructure.** Added task 1.3a (Upstox OHLC ingest, free, prerequisite for swing Tier 1 + all investment backtesting); updated 1.12 gate. Added Phase 2 Track A (swing pipeline, 2.S0–2.S7) + Track B (investment pipeline, 2.I0–2.I5) with CODE/STRATEGY/GATE labels and data-cost notes; 3.5 overlap note; calendar-vs-swing Open Question. Updated PLANNER.md Medium/Long-Term with stage sequences and data cost notes for both research docs. Commit a880256. |
| 2026-04-27 | **Data source decision: TrueData + DhanHQ rejected; Stockmock + NSE Bhavcopy adopted.** TrueData rejected (EOD-only historical; DhanHQ rejected (1-min data only 5 days deep, not 5 years as documented). Stockmock adopted for calibration backtests (manual UI, already subscribed). NSE F&O Bhavcopy adopted for programmatic pipeline (free, 2016–present, covers COVID Mar 2020 + IL&FS Sep-Oct 2018). Upstox confirmed as sole live Greeks source. TimescaleDB deferred indefinitely (EOD Bhavcopy ~4M rows fits Parquet+SQLite). BACKTEST_PLAN.md tasks 1.1/1.2/1.3/1.6a/1.8/1.9a/1.10/1.11/1.12/2.S3b updated. DECISIONS.md new section added. PLANNER.md backtesting engine section updated. |
| 2026-04-30 | **IV Reconstruction + Slippage council decisions documented.** IV Reconstruction: Black '76 + Nifty Futures forward, stepped RBI Repo Rate, quadratic smile fit, 30-DTE ATM IV percentile series. Slippage: absolute INR, VIX-regime-aware (₹1.0/1.5/3.0/4.0), OI liquidity multiplier (1.0×–2.5×), exit trigger propagation required. Both pre-submitted manually via llm-council web UI. DECISIONS.md + BACKTEST_PLAN.md updated (tasks 1.4 slippage bullet, 1.6a full rewrite). Commits by user (HEAD.lock issue in sandbox). |
| 2026-04-30 | **llm-council integrated as tools/llm-council submodule.** `scripts/ask_council.py` — dual-mode CLI (submits if server running, saves to docs/council/pending/ if offline); 3 domain templates (backtest_methodology, strategy_parameters, data_architecture) encode settled decisions to prevent re-litigation; `docs/council/README.md` with workflow and archived decision index. 33 offline unit tests (test_ask_council.py). Commit 324a320 (docs); feat commit pending user rm of HEAD.lock. |

---

Full log (2026-04-01 → 2026-04-26): [TODOS_ARCHIVE_2026-04-27.md](TODOS_ARCHIVE_2026-04-27.md)

---

## Completed Items — archived 2026-05-03

### ✅ P1-NEXT — `scripts/find_strike_by_delta.py`

**Completed:** 2026-05-03

Paper trading entry workflow script. Given an underlying + expiry, fetches the live option chain, filters strikes by a delta range, and prints matching strikes with premium and instrument key — ready to pipe directly into `record_paper_trade.py`.

Delivered:
- `scripts/find_strike_by_delta.py` — CLI with `--underlying`, `--expiry`, `--option-type`, `--delta-min`, `--delta-max`; fixed-width table (strike/IV/ltp/mid/bid/ask/OI/key); `--dry-run` emits ready-to-paste `record_paper_trade.py` command
- Three importable helpers: `filter_strikes_by_delta`, `format_table`, `build_record_command`; internal `_infer_leg` / `_safe_float`
- Works directly on raw Upstox chain data to preserve `instrument_key` (stripped by parsed `OptionChain` model)
- 30 offline unit tests in `tests/unit/test_find_strike_by_delta.py` using existing `nifty_chain_2026-04-07.json` fixture

---

### ✅ P2-EVAL — Nuvama Session P&L Alignment

**Resolved:** 2026-05-03 — decision: **keep cumulative (Option 1)**. True inception P&L is preferred over matching the Nuvama UI session view. The divergence from the Nuvama mobile/web "Session P&L" display is intentional — NiftyShield tracks all-time realized P&L via `get_cumulative_realized_pnl()`. No code changes required.
