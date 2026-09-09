# Signals Paper Track — schema

> Sole DDL source for SPT-2 onward. Fixed by the SPT-1 council ruling
> (`docs/archive/council/strategy/2026-09-09_signals-paper-track-execution-layer.md`).
> Do not inline DDL in a `stories.md` spec — edit here.

House rules (`src/paper/store.py` header): monetary values stored as `TEXT` (Decimal
invariant), timestamps as `TEXT` (ISO-8601), `CREATE TABLE IF NOT EXISTS`, `INTEGER PRIMARY
KEY AUTOINCREMENT`, `snake_case` `paper_*` names. All new tables live in
`data/portfolio/portfolio.sqlite` and are created by `PaperStore._ensure_schema` (add to
`DB_REGISTRY.md` in SPT-8).

## Position ledger — no change

The signals paper position persists in the existing **`paper_trades`** table under
`strategy_name = 'paper_signal_track_v1'` (the `paper_` prefix is enforced by `PaperTrade`'s
Pydantic validator). One BUY leg, `leg_role = 'signal_long'`, `quantity = 65`. Exit reuses the
existing close path and **`paper_exit_events`** for the reason + final fill. No parallel
signals-position table — `eod_pt_summary` reads all strategies through
`PaperStore.get_positions()` and must keep seeing this one.

## `paper_signal_entries` — frozen entry metadata (1 row per signal paper trade)

```sql
CREATE TABLE IF NOT EXISTS paper_signal_entries (
    trade_id          INTEGER PRIMARY KEY REFERENCES paper_trades(id),
    signal_date       TEXT NOT NULL,          -- DailySignal.trade_date (YYYY-MM-DD)
    trade_action      TEXT NOT NULL,          -- BUY_CALL | BUY_PUT
    instrument_key    TEXT NOT NULL,
    expiry            TEXT NOT NULL,          -- resolved monthly expiry (YYYY-MM-DD)
    entry_dte         INTEGER NOT NULL,       -- calendar DTE at entry
    entry_ts          TEXT NOT NULL,          -- fill timestamp (ISO-8601, IST)
    entry_premium     TEXT NOT NULL,          -- E, the simulated BUY fill (mid + s)
    entry_bid         TEXT NOT NULL,
    entry_ask         TEXT NOT NULL,
    entry_slippage    TEXT NOT NULL,          -- s applied at entry
    entry_vix         TEXT,                   -- India VIX at entry, NULL if unavailable
    entry_underlying  TEXT NOT NULL,          -- Nifty spot at entry
    signal_confidence INTEGER NOT NULL,       -- DailySignal consensus confidence (1-5)
    sl_pct            TEXT NOT NULL,          -- 0.30 for v1
    tgt_pct           TEXT NOT NULL,          -- 0.50 for v1
    sl_price          TEXT NOT NULL,          -- E * (1 - sl_pct), frozen
    tgt_price         TEXT NOT NULL,          -- E * (1 + tgt_pct), frozen
    ruleset_version   TEXT NOT NULL DEFAULT 'v1'
);
```

`ruleset_version` is the cohort tag. Any recalibrated SL/target ships as `'v2'` and applies
only prospectively — the 6-month gate report groups by this column and never pools v1 with v2.

## `paper_signal_marks` — tick telemetry (many rows per trade)

The Phase 2 dataset and the 6-month gate input. Written every monitor tick while the position
is open (30 s cadence — see the ruling), by SPT-4.

```sql
CREATE TABLE IF NOT EXISTS paper_signal_marks (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id       INTEGER NOT NULL REFERENCES paper_trades(id),
    ts             TEXT NOT NULL,          -- tick evaluation time (ISO-8601, IST)
    quote_ts       TEXT,                  -- broker quote timestamp; NULL if not supplied
    stale          INTEGER NOT NULL DEFAULT 0,  -- 1 if quote_ts > 30 s older than ts
    ltp            TEXT NOT NULL,
    bid            TEXT NOT NULL,
    ask            TEXT NOT NULL,
    mark           TEXT NOT NULL,          -- (bid + ask) / 2, the value compared to sl/tgt
    unrealised_pct TEXT NOT NULL,          -- (mark / E) - 1
    mfe_pct        TEXT NOT NULL,          -- running max favourable excursion, % of E
    mae_pct        TEXT NOT NULL,          -- running max adverse excursion, % of E
    gap_event      INTEGER NOT NULL DEFAULT 0,  -- 1 if |mark - prev_mark| / E > 0.20
    UNIQUE(trade_id, ts)
);

CREATE INDEX IF NOT EXISTS idx_paper_signal_marks_trade
    ON paper_signal_marks(trade_id, ts);
```

Retention: keep for the full evaluation window (no rolling purge — the 6-month gate needs the
whole history). Revisit after the go-live decision.

## Exit-reason enum

`PaperExitEvent.reason` (or the signals-specific exit enum SPT-5 introduces) carries, for
Phase 1: `TARGET`, `STOP_LOSS`, `TIME_EXIT`. **Reserve `TRAILING_STOP` now** so the Phase 2
dynamic exit does not force a schema/enum migration.

## Migration

New tables only — additive, no `ALTER` on `paper_trades`. `PaperStore._ensure_schema` runs the
`CREATE TABLE IF NOT EXISTS` on every open, so a fresh checkout and the live DB converge with
no manual step. SPT-8 adds both tables to `DB_REGISTRY.md`.
