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

Grain column lists the unique key; cardinality is 1 row per that key unless noted.
Lettered notes below the table carry the per-table detail that does not fit a cell.

| Table | Writer (method → script) | Cron cadence | Grain | Purpose |
|---|---|---|---|---|
| `paper_nav_snapshots` | `record_nav_snapshot()` → `paper_snapshot.py` | `36 15`+`35 15` Mon–Fri | `(strategy_name, snapshot_date)` | **Strategy-level** daily MTM, all strategies — note A |
| `paper_leg_snapshots` | `record_leg_snapshot()` → `paper_3track_snapshot.py` **only** | `35 15 * * 1-5` | `(strategy_name, leg_role, snapshot_date)` | **Per-leg** daily P&L, 3-track only — note B |
| `paper_track_comparison_snapshots` | `record_track_comparison_snapshot()` (→ 3track) | `35 15 * * 1-5` | `(strategy_name, snapshot_date)` | 3-track base-leg RQ1 comparison — note C |
| `paper_overlay_pnl_snapshots` | `record_overlay_pnl_snapshot()` (→ 3track) | `35 15 * * 1-5` | `(strategy_name, overlay_type, snapshot_date)` | Daily P&L for CC/PP/Collar overlays — note D |
| `paper_protection_recovery_snapshots` | `record_protection_recovery_snapshot()` (→ 3track) | `35 15 * * 1-5` | `snapshot_date` | NiftyBees-anchored spot + recovery series — note E |
| `daily_snapshots` | `PortfolioStore` → `scripts/portfolio/daily_snapshot.py` | `45 15 * * 1-5` | `(leg_id, snapshot_date)` | **Live** option Greeks/LTP/OI snapshot, joins `legs` — note F |
| `dhan_{holdings,margin,options}_snapshots` | `src/dhan/store.py` → `dhan_intraday_tracker.py` | intraday `*/5 9-15 * * 1-5` | varies | Dhan-side live holdings/margin/options mirror — note G |
| `nuvama_{intraday,options,holdings}_snapshots` | `src/nuvama/store.py` → Nuvama polling scripts | intraday | varies | Nuvama-side live positions/holdings mirror — note H |
| `intraday_market_snapshots` | `src/intraday/market_store.py` → `intraday_tracker` | `*/5 9-15 * * 1-5` | timestamp | Nifty spot + India VIX tick snapshots, market hours only. |
| `mf_nav_snapshots` | `MFStore.upsert_nav_snapshot()` / `upsert_nav_snapshots_bulk()` → AMFI NAV fetcher | daily (see `scripts/mf/`) | `(amfi_code, snapshot_date)` | MF NAV history, AMFI-sourced. |

**Note A — `paper_nav_snapshots`:** writers are `PaperTracker.record_nav_snapshot()` → `scripts/portfolio/paper_snapshot.py` (all strategies)
and `scripts/strategies/three_track/paper_3track_snapshot.py` (3-track only).
Cron: `36 15 * * 1-5` (paper_snapshot); `35 15 * * 1-5` (3track).
Fields: `realized_pnl`, `unrealized_pnl`, `total_pnl`, `underlying_price`.
Covers **all** paper strategies including every IC variant and CSP.
This is the table for "daily P&L graph" / "realized since inception" / "unrealized since inception" questions unless you specifically need per-leg detail.

**Note B — `paper_leg_snapshots`:** writer is `PaperStore.record_leg_snapshot()` → `scripts/strategies/three_track/paper_3track_snapshot.py` **only**.
As of 2026-08-07: populated **only** for `paper_nifty_futures` / `paper_nifty_proxy` / `paper_nifty_spot` (3-track).
**Zero rows for every IC variant and CSP/overlay strategy** —
`paper_ic_snapshot.py` computes the same per-leg numbers for its Telegram report but never persists them (see `docs/plan/paper-ic-daily-snapshot/`).
Do not assume this table is populated for a strategy just because `paper_nav_snapshots` is.
**2026-08-24 (BUG-036):** gained a `net_qty INTEGER` column (nullable) —
the leg's net open quantity as of `snapshot_date`, used so day-over-day P&L% math uses the quantity that was actually open then, not today's live quantity.
`NULL` on rows written before the fix until `scripts/dev/backfill_leg_snapshot_net_qty.py` is run against them.

**Note C — `paper_track_comparison_snapshots`:** writer is `PaperStore.record_track_comparison_snapshot()` → `scripts/strategies/three_track/paper_3track_snapshot.py`.
3-track-only base-leg RQ1 comparison (1-day + inception P&L %, tracking error vs. Nifty spot).
Includes a synthetic `"nifty_index"` row. Never includes overlay legs.

**Note D — `paper_overlay_pnl_snapshots`:** writer is `PaperStore.record_overlay_pnl_snapshot()` → `scripts/strategies/three_track/paper_3track_snapshot.py`.
Daily P&L for CC/PP/Collar overlays (`overlay_type ∈ {cc, pp, collar}`), sourced from `paper_leg_snapshots`' real leg roles, not the collapsed display dict.

**Note E — `paper_protection_recovery_snapshots`:** writer is `PaperStore.record_protection_recovery_snapshot()` → `scripts/strategies/three_track/paper_3track_snapshot.py`.
Single NiftyBees-anchored series combining spot P&L with cc/pp/collar recovery framing. No `strategy_name` column by design.

**Note F — `daily_snapshots`:** **Live** (non-paper) portfolio option Greeks/LTP/OI snapshot — joins to `legs`.
This is the live-book counterpart to `paper_leg_snapshots`, not paper data.

**Note G — `dhan_{holdings,margin,options}_snapshots`:** the three tables are `dhan_holdings_snapshots`, `dhan_margin_snapshots`, `dhan_options_snapshots`.
Writer: `src/dhan/store.py` → `scripts/intraday/dhan_intraday_tracker.py` and related dhan scripts.
Cron: intraday (`*/5 9-15 * * 1-5`, see `scripts.intraday.*`). Grain varies (see schema).
Dhan-side live holdings/margin/options mirror. Separate broker surface from Upstox/paper.

**Note H — `nuvama_{intraday,options,holdings}_snapshots`:** the three tables are `nuvama_intraday_snapshots`, `nuvama_options_snapshots`, `nuvama_holdings_snapshots`.
Nuvama-side live positions/holdings mirror. Third broker surface — do not conflate with `dhan_*` or `paper_*`.

## Event / audit tables (written on occurrence, not on a schedule)

| Table | Writer | Purpose |
|---|---|---|
| `paper_trades` | `PaperStore` → `record_paper_trade.py`, entry/roll/exit scripts | Append-only paper trade ledger. Source of truth for positions — see note below. |
| `paper_exit_events` | `PaperStore.create_exit_event()` → exit-signal check scripts | One row per detected exit signal per trade, `status` OPEN/ACKNOWLEDGED/ACTED/DISMISSED. |
| `paper_action_audit` | `PaperStore` → adjustment/roll scripts | Append-only audit trail of executed adjustment actions (price, qty, rationale). |
| `gate_violations` | `PaperStore.record_gate_violation()` → `paper_ic_entry.py` / `_v2.py`, `ic_entry_gates.py` | THRESHOLD entry-gate violations under `--log-only-gates` — see note below. |
| `warn_signal_state` | `PaperStore` | Dedup/state tracking so a WARN-severity signal doesn't re-fire every cron tick. |
| `paper_margin_snapshots` | `PaperStore` → IC entry scripts, `capture_entry_margin()` | One row per `(strategy_name, entry_date)` — margin at entry. **IC-only** — see note below. |
| `paper_proxy_delta_log` | `PaperStore` → 3-track proxy monitoring | Daily log of Proxy deep-ITM-call delta breach state. |
| `paper_strategies` | `PaperStore` | One row per strategy — mutable state (breach counts, profit-lock zone flags, active wing widths, `cycle_id`). Not snapshot history; current state only. |
| `pending_approvals` / `council_outputs` | `PaperStore` | Council-gated action approval workflow (Telegram approve/reject) and the raw per-persona LLM responses behind each approval. |
| `daemon_heartbeat` | `PaperStore` → `start_monitor`/`stop_monitor` daemon | Single-row (`id=1`) liveness beacon for the monitor daemon. |
| `cron_heartbeats` | `PortfolioStore` | Per-service last-run/status beacon, keyed by `service` name — used by `healthcheck.py`. |
| `strategies` / `legs` / `trades` | `PortfolioStore` | **Live** strategy/leg/trade tables — real-money counterpart to `paper_strategies` / `paper_trades` (not the `paper_*` tables). |
| `nuvama_positions` | `src/nuvama/store.py` → `scripts/seed_nuvama_positions.py` (seed-once, not daily cron) | Static cost-basis reference, keyed by `isin`. Not a snapshot history. |
| `mf_transactions` | `MFStore` | Append-only MF buy/sell ledger, keyed `(amfi_code, transaction_date, transaction_type)`. |

**Note — `paper_trades`:** `paper_nav_snapshots` / `paper_leg_snapshots` are derived from `paper_trades`, not the reverse.
The full writer set is `PaperStore` → `scripts/record/record_paper_trade.py` plus the entry/roll/exit scripts.

**Note — `gate_violations`:** the four THRESHOLD gates logged are IVR floor, DTE window, liquidity floor, delta cap.
STRUCTURAL gates never write here — they hard-block instead.

**Note — `paper_margin_snapshots`:** **IC-only** — 3-track futures notional is computed separately (`qty * 1.0`), never from this table.

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
