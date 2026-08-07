# DB_REGISTRY.md — SQLite Table Registry

> **Check this file before writing to `data/portfolio/portfolio.sqlite` or adding a new table.**
> Purpose: prevent the "which table has this data?" confusion (2026-08-07 session — went
> looking for daily IC P&L in `paper_leg_snapshots`, found it was actually already landing in
> `paper_nav_snapshots` via a different cron/writer). One table can look empty for a strategy
> while a sibling table already has exactly the data you need. Check here first.

**DB file:** `data/portfolio/portfolio.sqlite` (single shared SQLite DB — no per-domain
databases; `data/portfolio.sqlite` and `data/portfolio.sqlite-wal` at repo root are a stray/stale
copy, not live — do not write to them, and consider deleting after confirming staleness).

**Convention:** find the write path for any table below via `search_code("record_<x>")` or
`search_code("INSERT INTO <table>")` before assuming a call shape — this registry names the
writer method/script, but the exact signature must still come from the graph (`get_code_snippet`),
per `CLAUDE.md`'s test-helper rule.

---

## Daily-write tables (cron-driven)

| Table | Writer (method → script) | Cron cadence | Grain | Purpose |
|---|---|---|---|---|
| `paper_nav_snapshots` | `PaperTracker.record_nav_snapshot()` → `scripts/portfolio/paper_snapshot.py` (all strategies) and `scripts/strategies/three_track/paper_3track_snapshot.py` (3-track only) | `36 15 * * 1-5` (paper_snapshot); `35 15 * * 1-5` (3track) | 1 row / `(strategy_name, snapshot_date)` | **Strategy-level** daily mark-to-market: `realized_pnl`, `unrealized_pnl`, `total_pnl`, `underlying_price`. Covers **all** paper strategies including every IC variant and CSP. This is the table for "daily P&L graph" / "realized since inception" / "unrealized since inception" questions unless you specifically need per-leg detail. |
| `paper_leg_snapshots` | `PaperStore.record_leg_snapshot()` → `scripts/strategies/three_track/paper_3track_snapshot.py` **only** | `35 15 * * 1-5` | 1 row / `(strategy_name, leg_role, snapshot_date)` | **Per-leg** daily P&L. As of 2026-08-07: populated **only** for `paper_nifty_futures` / `paper_nifty_proxy` / `paper_nifty_spot` (3-track). **Zero rows for every IC variant and CSP/overlay strategy** — `paper_ic_snapshot.py` computes the same per-leg numbers for its Telegram report but never persists them (see `docs/plan/paper-ic-daily-snapshot/`). Do not assume this table is populated for a strategy just because `paper_nav_snapshots` is. |
| `paper_track_comparison_snapshots` | `PaperStore.record_track_comparison_snapshot()` → `scripts/strategies/three_track/paper_3track_snapshot.py` | `35 15 * * 1-5` | 1 row / `(strategy_name, snapshot_date)` | 3-track-only base-leg RQ1 comparison (1-day + inception P&L %, tracking error vs. Nifty spot). Includes a synthetic `"nifty_index"` row. Never includes overlay legs. |
| `paper_overlay_pnl_snapshots` | `PaperStore.record_overlay_pnl_snapshot()` → `scripts/strategies/three_track/paper_3track_snapshot.py` | `35 15 * * 1-5` | 1 row / `(strategy_name, overlay_type, snapshot_date)` | Daily P&L for CC/PP/Collar overlays (`overlay_type ∈ {cc, pp, collar}`), sourced from `paper_leg_snapshots`' real leg roles, not the collapsed display dict. |
| `paper_protection_recovery_snapshots` | `PaperStore.record_protection_recovery_snapshot()` → `scripts/strategies/three_track/paper_3track_snapshot.py` | `35 15 * * 1-5` | 1 row / `snapshot_date` | Single NiftyBees-anchored series combining spot P&L with cc/pp/collar recovery framing. No `strategy_name` column by design. |
| `daily_snapshots` | `PortfolioStore` → `scripts/portfolio/daily_snapshot.py` | `45 15 * * 1-5` | 1 row / `(leg_id, snapshot_date)` | **Live** (non-paper) portfolio option Greeks/LTP/OI snapshot — joins to `legs`. This is the live-book counterpart to `paper_leg_snapshots`, not paper data. |
| `dhan_holdings_snapshots` / `dhan_margin_snapshots` / `dhan_options_snapshots` | `src/dhan/store.py` → `scripts/intraday/dhan_intraday_tracker.py` and related dhan scripts | intraday (`*/5 9-15 * * 1-5`, see `scripts.intraday.*`) | varies (see schema) | Dhan-side live holdings/margin/options mirror. Separate broker surface from Upstox/paper. |
| `nuvama_intraday_snapshots` / `nuvama_options_snapshots` / `nuvama_holdings_snapshots` | `src/nuvama/store.py` → Nuvama polling scripts | intraday | varies | Nuvama-side live positions/holdings mirror. Third broker surface — do not conflate with `dhan_*` or `paper_*`. |
| `intraday_market_snapshots` | `src/intraday/market_store.py` → `scripts.intraday.intraday_tracker` | `*/5 9-15 * * 1-5` | 1 row / timestamp | Nifty spot + India VIX tick snapshots, market hours only. |
| `mf_nav_snapshots` | `MFStore.upsert_nav_snapshot()` / `upsert_nav_snapshots_bulk()` → AMFI NAV fetcher | daily (see `scripts/mf/`) | 1 row / `(amfi_code, snapshot_date)` | Mutual fund NAV history, AMFI-sourced. |

## Event / audit tables (written on occurrence, not on a schedule)

| Table | Writer | Purpose |
|---|---|---|
| `paper_trades` | `PaperStore` → `scripts/record/record_paper_trade.py`, entry/roll/exit scripts | Append-only paper trade ledger. Source of truth for positions; `paper_nav_snapshots`/`paper_leg_snapshots` are derived from this, not the reverse. |
| `paper_exit_events` | `PaperStore.create_exit_event()` → exit-signal check scripts | One row per detected exit signal per trade, `status` OPEN/ACKNOWLEDGED/ACTED/DISMISSED. |
| `paper_action_audit` | `PaperStore` → adjustment/roll scripts | Append-only audit trail of executed adjustment actions (price, qty, rationale). |
| `gate_violations` | `PaperStore.record_gate_violation()` → `paper_ic_entry.py`/`_v2.py`, `ic_entry_gates.py` | THRESHOLD entry-gate violations under `--log-only-gates` (IVR floor, DTE window, liquidity floor, delta cap). STRUCTURAL gates never write here — they hard-block instead. |
| `warn_signal_state` | `PaperStore` | Dedup/state tracking so a WARN-severity signal doesn't re-fire every cron tick. |
| `paper_margin_snapshots` | `PaperStore` → IC entry scripts, `capture_entry_margin()` | One row per `(strategy_name, entry_date)` — margin at entry. **IC-only** — 3-track futures notional is computed separately (`qty * 1.0`), never from this table. |
| `paper_proxy_delta_log` | `PaperStore` → 3-track proxy monitoring | Daily log of Proxy deep-ITM-call delta breach state. |
| `paper_strategies` | `PaperStore` | One row per strategy — mutable per-strategy state (breach counts, profit-lock zone flags, active wing widths, `cycle_id`). Not a snapshot history table — always current state only. |
| `pending_approvals` / `council_outputs` | `PaperStore` | Council-gated action approval workflow (Telegram approve/reject) and the raw per-persona LLM responses behind each approval. |
| `daemon_heartbeat` | `PaperStore` → `start_monitor`/`stop_monitor` daemon | Single-row (`id=1`) liveness beacon for the monitor daemon. |
| `cron_heartbeats` | `PortfolioStore` | Per-service last-run/status beacon, keyed by `service` name — used by `healthcheck.py`. |
| `strategies` / `legs` / `trades` | `PortfolioStore` | **Live** (non-paper) strategy/leg/trade tables — the real-money counterpart to `paper_strategies`/`paper_trades`. Do not confuse with the `paper_*` equivalents. |
| `nuvama_positions` | `src/nuvama/store.py` → `scripts/seed_nuvama_positions.py` (seed-once, not daily cron) | Static cost-basis reference, keyed by `isin`. Not a snapshot history. |
| `mf_transactions` | `MFStore` | Append-only MF buy/sell ledger, keyed `(amfi_code, transaction_date, transaction_type)`. |

---

## Adding a new table

1. Check this file first — the data you want may already exist under a different table name
   (strategy-level vs. per-leg vs. per-overlay are three separate tables for paper P&L alone).
2. If genuinely new: add the `CREATE TABLE` in the relevant `src/<module>/store.py` (never a
   bare script-level `CREATE TABLE`), add a `record_*`/`get_*` method pair, and add a row to the
   appropriate section above in the same commit.
3. Monetary fields: `Decimal` stored as `TEXT`, per `CLAUDE.md`. Timestamps: UTC, IST only at
   display layer.
4. Cross-reference `src/paper/CLAUDE.md` if the table lives in the `paper_` namespace — it has
   the fuller per-table invariant list (e.g. `total_pnl == unrealized_pnl + realized_pnl`).

*Last synced against live schema: 2026-08-07. Table list and writers verified via
`sqlite_master` + `search_code`, not from memory — re-verify before trusting an entry that looks
stale relative to `git log`.*
