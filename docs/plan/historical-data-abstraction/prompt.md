# Historical Data Abstraction — prompt

> Introduce a broker-agnostic `HistoricalCandleFetcher` protocol so OHLC candle fetching (VIX, NIFTY spot, equity ETFs) can move between Upstox, Dhan, Kite, and offline NSE CSV without touching the
> frozen Parquet storage layer.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

**Priority: LOW** — HD-0 (vendor cost evaluation) runs first and gates all implementation phases.

## Why this story exists

`Candle = dict[str, Any]` and `CandleRequest = dict[str, Any]` are untyped TODO stubs (TD-7) in `src/client/protocol.py`, and `UpstoxLiveClient.get_historical_candles()` raises `NotImplementedError`.
Today only Upstox's VIX-fetch path (`ingest_vix_from_api` / `fetch_vix_latest` in `src/backtest/vix_ingest.py`) actually fetches historical OHLC data, using synchronous `requests.get` with no typed
request/response shape and no seam for a second vendor.

This story defines the canonical `CandleRecord` / `CandleRequest` models, a `HistoricalCandleFetcher` protocol, and per-vendor implementations (Upstox, optionally Dhan and Kite per the HD-0 decision
matrix, and a zero-cost offline NSE CSV fallback), then wires the whole thing through `VixIngestPipeline`, `UpstoxLiveClient`, and a `factory.py` composition root — mirroring the pattern already
established for market-data parsing.

## Scope guard

**In bounds:** `src/models/candles.py`, `src/backtest/fetchers/` (new package), `src/backtest/vix_ingest.py`, `src/client/protocol.py`, `src/client/upstox_live.py`, `src/client/factory.py`,
`scripts/dev/historical_probe/` (HD-0 probe scripts only). Src behaviour changes only in the fetch layer.

**Out of bounds:** the frozen Parquet schema (`date`/`open`/`high`/`low`/`close` float64 columns — no migration, no column renames), the SQLite schema, and any downstream consumer (paper trading,
backtests, `compute_ivr`, Telegram formatting). Candle price fields stay `float` to match the existing Parquet schema — `Decimal` conversion does not apply here.

## Session-start load hints

- `REFERENCES.md` — `NSE_INDEX|India VIX` instrument key and NIFTYBEES key, needed by HD-0 probes and HD-1/HD-8 models.
- `src/client/CLAUDE.md` — existing `BrokerClient` protocol pattern; `build_market_data_parser()` in `factory.py` is the pattern HD-10 mirrors exactly.
- `DECISIONS.md` — HD-0 must record the vendor assignment decision here before HD-1 starts.
- If `broker-abstraction/` (BA-*) has shipped by the time this story starts: `VixIngestPipeline` and instrument-key adapters (`DhanInstrumentKeyAdapter`, `KiteInstrumentKeyAdapter`) may already exist
  — HD-5/HD-6/HD-7 reuse them rather than duplicating.

## Task overview

- **HD-0** — vendor cost/quality evaluation across Upstox, Dhan, Kite, NSE CSV; cost-bounded probe scripts + decision matrix; gates every other task.
- **HD-1 / HD-2** — `CandleRecord` + `CandleInterval` + `CandleRequest` Pydantic models in `src/models/candles.py`, resolving the TD-7 stubs.
- **HD-3** — `HistoricalCandleFetcher` runtime-checkable protocol.
- **HD-4 / HD-5** — `UpstoxCandleFetcher` implementation; wire into `VixIngestPipeline` with deprecation shims on the two legacy module-level functions.
- **HD-6 / HD-7 / HD-8** — `DhanCandleFetcher` / `KiteCandleFetcher` (conditional on the HD-0 decision matrix) and `NseCsvVixFetcher` (zero-cost offline fallback).
- **HD-9 / HD-10** — implement `get_historical_candles` in `UpstoxLiveClient`; `build_historical_fetcher()` factory composition root.

## Definition of done

`HistoricalCandleFetcher` has a working Upstox implementation wired through `VixIngestPipeline` and `UpstoxLiveClient`; `Candle` / `CandleRequest` TD-7 stubs are fully resolved; `factory.py` builds
the correct fetcher for the active broker environment; Dhan and Kite implementations exist or are explicitly marked skipped per the HD-0 decision matrix; the Parquet schema is unchanged throughout.

## Perspectives not covered

Whether Dhan or Kite are still the right second/third vendors for historical OHLC by the time this story is picked up — HD-0 re-evaluates this against current pricing and API behaviour rather than
assuming the phase ordering baked into HD-6/HD-7 is still correct.

---

## Core Design Constraint

**Storage format is frozen. Only the fetch layer changes.**

Canonical storage:
- VIX: Parquet at `data/historical/ohlc/india_vix/`, daily closes, columns `date/open/high/low/close`
- OHLC candles: Parquet at `data/historical/ohlc/<instrument>/`, same schema
- Bhavcopy: Parquet at `data/offline/options_ohlcv/`, `BhavRecord` schema from `src/backtest/bhavcopy_ingest.py`

None of these schemas change. The `HistoricalCandleFetcher` protocol produces rows that feed the existing Parquet writers unchanged.

**Cost discipline — mandatory for HD-0 (evaluation) and HD-1 (probe scripts):** Every API call to a paid historical data source must be preceded by a dry-run check. Probe scripts must accept
`--dry-run` to print what would be fetched without calling the API. Probe scripts must print estimated cost (calls × rate) before any paid fetch. Never run paid probes against a full date range —
probe with a 5-day window only.

## Graph-before-Read rule

`git log --oneline -10 <file>` → `search_graph` → `trace_path` → `search_code` → `bash sed -n 'N,Mp' <file>` → `Read` only if all above insufficient.

## Before writing any test helper

`get_code_snippet('<ModelClassName>')` — never write model constructors from memory.

## Implementation rules

`CLAUDE.md` + `REVIEW.md` apply. Every public function: one happy-path + one edge/error test. No network calls in tests. Monetary/price fields always `Decimal`, stored as TEXT in SQLite. Parquet price
columns use `float64` (existing schema — do not change to Decimal in Parquet).

## Agent routing

Each story opens with `> Assigned to: Claude` or `> Assigned to: Antigravity`.

## Test gate — blocking

`python -m pytest tests/unit/ --tb=no -q` — all green before proceeding.

## Code-reviewer gate — blocking

`code-reviewer` agent against `git diff HEAD`. CRITICAL/ERROR must resolve before commit.

## Commit

Format from `.claude/skills/commit/SKILL.md`. Execute — do not draft.

```bash
git add <files>
git commit -m '<message>'
git log --oneline -1
```

## Verify and record

Set `SHA:` to the real commit SHA on the task line and tick the box in `tasks.md`. Add one line to `TODOS.md` session log.

**Stop.** </content>
