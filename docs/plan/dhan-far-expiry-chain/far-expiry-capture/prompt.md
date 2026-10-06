# Far-Expiry Capture — prompt

> One Dhan chain snapshot per trading day for the far expiries, stored so liquidity history exists, plus a daily report on the target-delta strikes.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

Dhan's chain is a snapshot with no history. The only way to know whether Dec 2027 has enough liquidity before the Dec 2026 roll is to record it every day from now. The report turns the raw capture
into the numbers the gate needs: is the target-delta strike quoted, how wide is the spread, how much OI.

## Scope guard

Capture and report only. No thresholds, no gate, no strategy change. Calendar pressure: the plan lapses 2026-11-04, so FC-2 and FC-3 should land early even if FC-5 waits.

## Design review

SRP: capture entrypoint orchestrates, a writer persists, a pure function reduces a chain to a liquidity row. Storage is decided in FC-1 (Parquet `ChainWriter` versus SQLite) before any DDL;
`schema.md` is added to this folder only if SQLite is chosen.

## Session-start load hints

`DB_REGISTRY.md` (first, before any storage choice), `LOGGING.md`, `SCRATCH.md`, `src/backtest` `ChainWriter`/`ChainReader`, `src/market_calendar/` (`guard_trading_day`), `healthcheck.py` heartbeat
pattern.

## Task overview

FC-1 storage decision → FC-2 writer → FC-3 capture entrypoint → FC-4 cron + healthcheck (Animesh) → FC-5 liquidity report.

## Definition of done

One capture per trading day for Dec 2026 and the next yearly expiry, spaced 4 s, with a heartbeat; the report prints per-expiry liquidity at target deltas from stored data only.

## Perspectives not covered

Intraday variation: one end-of-day snapshot misses spread widening at the open and close; the capture time is a judgement (after 15:30 IST for settled quotes) and not otherwise tested.
