# Broker Abstraction — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation spec.

> Priority: LOW — implement only after Phase 0.8 gate passes.

**Open: BA-0, BA-1, BA-2, BA-3, BA-4, BA-5, BA-6, BA-7, BA-8, BA-9, BA-10, BA-11, BA-12, BA-13, BA-14, BA-15.**

## Phase 0 — Pre-implementation Research (gates all other phases)

- [ ] **BA-0** — Broker data quality analysis: probe scripts + findings doc + decision matrix | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>

## Phase 1 — Parser Protocol + Upstox Conformance

- [ ] **BA-1** — Define `MarketDataParser` protocol + move Upstox parser to conform | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **BA-2** — Define `InstrumentKeyAdapter` protocol + Upstox adapter | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>

## Phase 2 — Dhan Integration

- [ ] **BA-3** — Dhan `MarketDataParser` implementation (`src/client/parsers/dhan.py`) | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **BA-4** — Dhan `InstrumentKeyAdapter` implementation (`src/client/adapters/dhan.py`) | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **BA-5** — Wire Dhan parsers into `factory.py` + integration smoke test | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>

## Phase 3 — Kite/Zerodha Integration

- [ ] **BA-6** — Kite `MarketDataParser` implementation (`src/client/parsers/kite.py`) | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **BA-7** — Kite `InstrumentKeyAdapter` implementation (`src/client/adapters/kite.py`) | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **BA-8** — Wire Kite parsers into `factory.py` + integration smoke test | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>

## Phase 4 — Config + VIX Ingest

- [ ] **BA-9** — Add Kite credential block to `src/config.py` + `.env.example` | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **BA-10** — Make VIX ingest broker-agnostic (promote NSE CSV path, deprecate Upstox-specific path) | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>

## Phase 5 — Instrument Master + Market Quote Abstraction

- [ ] **BA-11** — `InstrumentMasterLoader` protocol + Upstox BOD adapter + Dhan/Kite stubs | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **BA-12** — `MarketQuoteClient` protocol + constructor injection into `UpstoxLiveClient` | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **BA-13** — Configurable broker prefix in `ChainWriter` / `ChainReader` (default `"upstox"`) | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>

## Phase 6 — Auth Abstraction (Phase 1+ gate — do NOT start before `src/execution/` exists)

- [ ] **BA-14** — `BrokerAuthProvider` protocol + Upstox/Dhan providers + Kite stub | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **BA-15** — Remove `upstox_client` SDK direct import from `sandbox_order_lifecycle.py` | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>

## Story done when

Acceptance criteria — prose, no checkboxes. Per-task status lives only in the working list above; this list is verified at story close.

- Every `BrokerClient`, `MarketDataParser`, and `InstrumentKeyAdapter` implementation exists for Upstox, Dhan, and Kite, conforming to their respective protocols.
- The canonical `OptionChain` / `OptionChainStrike` / `OptionLeg` models and the Parquet/SQLite schemas are unchanged — no broker-specific field name crosses the parser boundary.
- `factory.py` can construct a working client for any of the three brokers from config alone.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update `docs/plan/README.md` and add one line to `TODOS.md` Session Log. When the whole story is done, follow
`docs/plan/README.md` §Conventions *Completion → archive*.
