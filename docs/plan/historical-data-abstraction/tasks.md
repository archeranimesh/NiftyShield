# Historical Data Abstraction — Task Checklist

> Priority: LOW — implement after Phase 0.8 gate. HD-0 (cost evaluation) runs first and gates all implementation.
> One task per session. Find the first unchecked item. That is your only task.
> After each task: tick this file, append `| SHA: <sha>`, add one line to TODOS.md session log.
> Full prompt: `docs/plan/historical-data-abstraction/prompt.md`
> Story specs: `docs/plan/historical-data-abstraction/stories/<TASK_ID>.md`

---

## Phase 0 — Vendor Evaluation (gates all implementation phases)

- [ ] HD-0 — Historical data vendor cost + quality evaluation: probe scripts + cost matrix + decision doc

## Phase 1 — Canonical Models

- [ ] HD-1 — `CandleRecord` Pydantic model + `CandleInterval` enum (replaces `Candle = dict[str, Any]`)
- [ ] HD-2 — `CandleRequest` Pydantic model (replaces `CandleRequest = dict[str, Any]`, resolves TD-7)

## Phase 2 — Fetcher Protocol + Upstox Implementation

- [ ] HD-3 — `HistoricalCandleFetcher` protocol (`src/backtest/fetchers/protocol.py`)
- [ ] HD-4 — `UpstoxCandleFetcher` — wraps existing `ingest_vix_from_api` + `fetch_vix_latest` logic
- [ ] HD-5 — Wire `UpstoxCandleFetcher` into `VixIngestPipeline`; deprecation shims on module-level functions

## Phase 3 — Alternative Vendor Implementations (gated on HD-0 decision matrix)

- [ ] HD-6 — `DhanCandleFetcher` (implement only if HD-0 recommends Dhan for OHLC)
- [ ] HD-7 — `KiteCandleFetcher` (implement only if HD-0 recommends Kite for OHLC)
- [ ] HD-8 — `NseCsvCandleFetcher` — broker-agnostic NSE CSV path (VIX only; already partially exists)

## Phase 4 — Wire into `BrokerClient` Protocol

- [ ] HD-9 — Implement `get_historical_candles` in `UpstoxLiveClient` (currently raises `NotImplementedError`)
- [ ] HD-10 — Factory function `build_historical_fetcher()` in `src/client/factory.py`

---

## Session Log

| Date | Task | Description | SHA |
|------|------|-------------|-----|
