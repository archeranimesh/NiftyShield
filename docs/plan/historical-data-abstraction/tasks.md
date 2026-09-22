# Historical Data Abstraction — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation spec.

> Priority: LOW — implement after Phase 0.8 gate. HD-0 (cost evaluation) runs first and gates all implementation.

**Open: HD-0, HD-1, HD-2, HD-3, HD-4, HD-5, HD-6, HD-7, HD-8, HD-9, HD-10.**

## Phase 0 — Vendor Evaluation (gates all implementation phases)

- [ ] **HD-0** — Historical data vendor cost + quality evaluation: probe scripts + cost matrix + decision doc | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>

## Phase 1 — Canonical Models

- [ ] **HD-1** — `CandleRecord` Pydantic model + `CandleInterval` enum (replaces `Candle = dict[str, Any]`) | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **HD-2** — `CandleRequest` Pydantic model (replaces `CandleRequest = dict[str, Any]`, resolves TD-7) | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>

## Phase 2 — Fetcher Protocol + Upstox Implementation

- [ ] **HD-3** — `HistoricalCandleFetcher` protocol (`src/backtest/fetchers/protocol.py`) | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **HD-4** — `UpstoxCandleFetcher` — wraps existing `ingest_vix_from_api` + `fetch_vix_latest` logic | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: <—>
- [ ] **HD-5** — Wire `UpstoxCandleFetcher` into `VixIngestPipeline`; deprecation shims on module-level functions | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>

## Phase 3 — Alternative Vendor Implementations (gated on HD-0 decision matrix)

- [ ] **HD-6** — `DhanCandleFetcher` (implement only if HD-0 recommends Dhan for OHLC) | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: <—>
- [ ] **HD-7** — `KiteCandleFetcher` (implement only if HD-0 recommends Kite for OHLC) | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: <—>
- [ ] **HD-8** — `NseCsvCandleFetcher` — broker-agnostic NSE CSV path (VIX only; already partially exists) | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: <—>

## Phase 4 — Wire into `BrokerClient` Protocol

- [ ] **HD-9** — Implement `get_historical_candles` in `UpstoxLiveClient` (currently raises `NotImplementedError`) | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **HD-10** — Factory function `build_historical_fetcher()` in `src/client/factory.py` | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>

## Story done when

- **HD-0** — probe scripts run against at least Upstox and Dhan; `hd_analysis.md` and `hd_decision_matrix.md` committed; `DECISIONS.md` records the vendor assignments; HD-6/HD-7 marked
  implement-or-skip.
- **HD-1** — `CandleRecord` + `CandleInterval` exist in `src/models/candles.py`; `Candle` stub in `src/client/protocol.py` resolved (TD-7 half closed).
- **HD-2** — `CandleRequest` exists in `src/models/candles.py`; stub in `src/client/protocol.py` resolved (TD-7 fully closed).
- **HD-3** — `HistoricalCandleFetcher` runtime-checkable protocol defined in `src/backtest/fetchers/protocol.py`.
- **HD-4** — `UpstoxCandleFetcher` implemented, async, conforms to the protocol, covered by fixture-driven tests.
- **HD-5** — `VixIngestPipeline` accepts an injected fetcher; `ingest_vix_from_api` / `fetch_vix_latest` become deprecation shims with all 5 existing callers unchanged.
- **HD-6** — `DhanCandleFetcher` implemented (or explicitly marked skipped per the HD-0 decision matrix).
- **HD-7** — `KiteCandleFetcher` implemented (or explicitly marked skipped per the HD-0 decision matrix).
- **HD-8** — `NseCsvVixFetcher` wraps the existing `ingest_vix_from_csv` logic as a zero-cost fallback fetcher.
- **HD-9** — `UpstoxLiveClient.get_historical_candles` no longer raises `NotImplementedError`; delegates to `UpstoxCandleFetcher`.
- **HD-10** — `build_historical_fetcher()` is the sole composition root for fetcher selection in `src/client/factory.py`.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then add one line to `TODOS.md` Session Log. When the whole story is done, follow `docs/plan/README.md` §Conventions *Completion →
archive* — do not leave a done story half-archived. </content>
