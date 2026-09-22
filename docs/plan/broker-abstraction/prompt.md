# Broker Abstraction — prompt

> Introduce multi-broker `MarketDataParser` / `InstrumentKeyAdapter` / auth abstractions so Dhan and Kite can be added without touching the frozen canonical models.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

**Priority: LOW** — implement only after the Phase 0.8 gate passes.

## Why this story exists

Today the codebase only speaks Upstox. Adding Dhan or Kite means duplicating the fetch/parse layer with no seam. This story introduces `MarketDataParser`, `InstrumentKeyAdapter`,
`InstrumentMasterLoader`, `MarketQuoteClient`, and `BrokerAuthProvider` protocols so each new broker is a bounded implementation, never a change to the canonical `OptionChain` / `OptionChainStrike` /
`OptionLeg` models or the frozen Parquet/SQLite schemas.

BA-0 gates everything else — a probe pass across Upstox, Dhan, and Kite assigns each data category (Greeks, LTP, historical OHLC, VIX, instrument master, streaming) to its best-suited broker before
any protocol code is written, so the abstraction is built around real data quality differences instead of assumptions.

## Scope guard

**In bounds:** `src/client/parsers/`, `src/client/adapters/`, `src/client/protocol.py` extensions, `factory.py` wiring, `src/config.py` Kite credential block, VIX ingest path, `ChainWriter` /
`ChainReader` broker prefix, `src/execution/` auth provider abstraction (Phase 6 only, gated on `src/execution/` existing).

**Out of bounds:** the canonical domain models in `src/models/options.py` (frozen — fetch/parse layer only changes), the Parquet schema, the SQLite schema, and any downstream consumer (paper trading,
backtests, Telegram formatting).

## Session-start load hints

- `REFERENCES.md` — instrument keys for NIFTY index, India VIX, NIFTYBEES before writing any probe or parser (BA-0 especially).
- `src/client/CLAUDE.md` — existing `BrokerClient` protocol pattern to mirror for the new parser/adapter protocols.
- `DECISIONS.md` — BA-0 must record its broker data source assignments here before BA-1 starts.

## Task overview

- **BA-0** — probe scripts across Upstox/Dhan/Kite + findings doc + decision matrix; gates every other task.
- **BA-1 / BA-2** — `MarketDataParser` + `InstrumentKeyAdapter` protocols, Upstox conformance.
- **BA-3 / BA-4 / BA-5** — Dhan parser, adapter, and `factory.py` wiring + smoke test.
- **BA-6 / BA-7 / BA-8** — Kite parser, adapter, and `factory.py` wiring + smoke test.
- **BA-9 / BA-10** — Kite config block; broker-agnostic VIX ingest.
- **BA-11 / BA-12 / BA-13** — `InstrumentMasterLoader`, `MarketQuoteClient`, configurable Parquet broker prefix.
- **BA-14 / BA-15** — `BrokerAuthProvider` protocol (Phase 1+ gate) + remove the direct `upstox_client` SDK import from `sandbox_order_lifecycle.py`.

## Definition of done

Every `BrokerClient`, `MarketDataParser`, and `InstrumentKeyAdapter` implementation exists for Upstox, Dhan, and Kite; `factory.py` constructs a working client for any of the three from config alone;
the canonical models and stored schemas are unchanged throughout.

## Perspectives not covered

Whether Dhan and Kite are still the right second/third brokers to integrate as of today — this story assumes BA-0's probe will confirm or revise that, but the phase ordering (Dhan before Kite)
predates BA-0 and is not re-justified here.

## Graph-before-Read rule

Never call `Read` on `src/` or `scripts/` without first trying the graph. Order: `git log --oneline -10 <file>` → `search_graph` / `get_code_snippet` → `trace_path` → `search_code` → `bash sed -n
'N,Mp' <file>` → `Read` only if all above are insufficient.

## Before writing any test helper

Run `get_code_snippet('<ModelClassName>')` to get the exact current field list. Never write model constructors from memory.

## Implementation rules

Follow all rules in `CLAUDE.md` and `REVIEW.md`. Every public function needs one happy-path test and one edge/error test. No network calls in tests. Monetary fields always `Decimal`, stored as TEXT in
SQLite — never float.

## Test gate — blocking

After implementation, before touching anything else: `python -m pytest tests/unit/ --tb=no -q`. All tests must be green. Fix failures before proceeding.

## Code-reviewer gate — blocking

Run the `code-reviewer` agent against `git diff HEAD` for every task except BA-0 (docs/scripts only). Address any `CRITICAL` or `ERROR` findings before committing. `WARNING` may be deferred with a
documented reason.

## Commit

Use the format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft it.

```bash
git add <files>
git commit -m '<message>'
git log --oneline -1
```

## Verify and record

Copy the SHA from `git log --oneline -1`. Open `tasks.md`, change `- [ ]` to `- [x]` on the completed line, and set `SHA:` to the real commit SHA. Then add one line to `TODOS.md` under the session
log.

**Stop.** Do not proceed to the next unchecked item.
