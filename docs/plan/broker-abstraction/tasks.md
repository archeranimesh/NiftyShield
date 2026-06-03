# Broker Abstraction — Task Checklist

> Priority: LOW — implement only after Phase 0.8 gate passes.
> One task per session. Find the first unchecked item. That is your only task.
> After each task: tick this file, append `| SHA: <sha>`, add one line to TODOS.md session log.
> Full prompt: `docs/plan/broker-abstraction/prompt.md`
> Story specs: `docs/plan/broker-abstraction/stories/<TASK_ID>.md`

---

## Phase 0 — Pre-implementation Research (gates all other phases)

- [ ] BA-0 — Broker data quality analysis: probe scripts + findings doc + decision matrix

## Phase 1 — Parser Protocol + Upstox Conformance

- [ ] BA-1 — Define `MarketDataParser` protocol + move Upstox parser to conform
- [ ] BA-2 — Define `InstrumentKeyAdapter` protocol + Upstox adapter

## Phase 2 — Dhan Integration

- [ ] BA-3 — Dhan `MarketDataParser` implementation (`src/client/parsers/dhan.py`)
- [ ] BA-4 — Dhan `InstrumentKeyAdapter` implementation (`src/client/adapters/dhan.py`)
- [ ] BA-5 — Wire Dhan parsers into `factory.py` + integration smoke test

## Phase 3 — Kite/Zerodha Integration

- [ ] BA-6 — Kite `MarketDataParser` implementation (`src/client/parsers/kite.py`)
- [ ] BA-7 — Kite `InstrumentKeyAdapter` implementation (`src/client/adapters/kite.py`)
- [ ] BA-8 — Wire Kite parsers into `factory.py` + integration smoke test

## Phase 4 — Config + VIX Ingest

- [ ] BA-9 — Add Kite credential block to `src/config.py` + `.env.example`
- [ ] BA-10 — Make VIX ingest broker-agnostic (promote NSE CSV path, deprecate Upstox-specific path)

## Phase 5 — Instrument Master + Market Quote Abstraction

- [ ] BA-11 — `InstrumentMasterLoader` protocol + Upstox BOD adapter + Dhan/Kite stubs
- [ ] BA-12 — `MarketQuoteClient` protocol + constructor injection into `UpstoxLiveClient`
- [ ] BA-13 — Configurable broker prefix in `ChainWriter` / `ChainReader` (default `"upstox"`)

## Phase 6 — Auth Abstraction (Phase 1+ gate — do NOT start before `src/execution/` exists)

- [ ] BA-14 — `BrokerAuthProvider` protocol + Upstox/Dhan providers + Kite stub
- [ ] BA-15 — Remove `upstox_client` SDK direct import from `sandbox_order_lifecycle.py`

---

## Session Log

| Date | Task | Description | SHA |
|------|------|-------------|-----|
