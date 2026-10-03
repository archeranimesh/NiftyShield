# Gamma Scan Phase B — prompt

> `scripts/gamma_scan.py`: the 5-minute intraday signal scan for the Near-Expiry Gamma Buy strategy, built as pure `src/gamma/` rule modules plus a thin orchestration script.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

Phase A (`../risk-gamma-phase-a/`) captures the daily chain snapshot and maintains the watchlist. Phase B is the live half of `docs/strategies/near_expiry_buy_v1.md` §6: every 5 minutes on DTE 0–1 it
evaluates each candidate strike against the four-layer signal stack, writes every evaluation to `gamma_signal_log` (failed filters are as valuable as passed ones for calibration), and — when a signal
fires with no open position in that direction — records one paper trade and watches the exit conditions E1/E2/E3. It is a separate story because it starts only after at least 5 days of Phase A data
exist and needs the Dhan Data API for L2 depth.

## Scope guard

In bounds: the `gamma_signal_log` table + store methods; `src/gamma/` signal, ranking, exit and depth modules; `scripts/gamma_scan.py`; the cron entry; the `--dry-run` validation. Out of bounds: any
change to Phase A's snapshot/watchlist logic beyond reading it; `src/risk/` internals; live-order placement (paper trades only, via the existing `record_paper_trade` path); strategy tuning (Stage 1
thresholds are taken as written in §6 — calibration is a later, data-driven step).

**Blocked by:** `risk-gamma-phase-a` complete (B2.2–B2.5 closed) **and** ≥ 5 trading days of `gamma_chain_snapshots` rows (strategy doc Phase B gate). Do not start GS-1 before both hold.

## Design review

Run against `docs/refactor/design-principles.md` and `code-deduplication-and-taxonomy.md` before drafting any task. Outcome:

- **Prior-art / reuse:** the derived-field maths (`src/gamma/derive.py`), `GammaStore` (incl. `get_active_watchlist` for the `watchlist_hit` tag) and the percentile columns that Layer 3 reads all come
  from Phase A. Phase B must import them, never re-derive in `gamma_scan.py`.
- **Open/closed:** Layers 0–4 are an ordered `SignalStack` of small predicates, each returning a reason code, evaluated in a loop. Adding a layer or condition adds a predicate; it never adds an `elif`
  to a decision method. Thresholds live in a frozen config dataclass (env overrides from §12 are applied once at the script edge).
- **Dependency inversion:** `ChainSource` and `DepthSource` are Protocols injected into the scan; `NullDepth` implements reduced mode when `DHAN_DATA_API_KEY` is unset. The paper-entry step is an
  injected adapter around the existing `record_paper_trade` functions — never a subprocess shell-out.
- **One-way dependencies:** `src/gamma/*` never imports from `scripts/`. Ranking and exit rules are pure functions; only `gamma_scan.py` touches I/O.
- **Council checkpoint (Step 2b):** not triggered — thresholds and layers come from an already-decided strategy spec; no new load-bearing two-way decision.

## Session-start load hints

- `src/gamma/CLAUDE.md` before touching `src/gamma/`; `docs/strategies/near_expiry_buy_v1.md` §6 (signal stack), §11 (DDL), §12 (env vars) and the "gamma_scan.py responsibilities" block.
- `DB_REGISTRY.md` first for GS-1 (new table in `portfolio.sqlite`); `src/dhan/CLAUDE.md` for GS-3; `src/paper/CLAUDE.md` for GS-5.
- Greeks / gamma-gearing fields are involved — `greeks-analyst` review per `CLAUDE.md` AutoTrigger rules on GS-2 and GS-4.

## Task overview

- **GS-1** — `gamma_signal_log` model, DDL and `GammaStore` methods.
- **GS-2** — `src/gamma/signals.py`: Layers 0–4 as predicates in an ordered `SignalStack`.
- **GS-3** — `DepthSource` Protocol, Dhan L2 adapter, `NullDepth`.
- **GS-4** — `ranking.py` (§6 candidate-ranking formula) and `exits.py` (E1/E2/E3), both pure.
- **GS-5** — `scripts/gamma_scan.py`: thin orchestration, lock + atomic "no open position" check, paper-entry adapter.
- **GS-6** — cron entry `*/5 9-15 * * 3,4` and the first-qualifying-Wednesday `--dry-run` validation.

## Definition of done

`gamma_scan.py` runs unattended every 5 minutes on DTE 0–1: every candidate strike's evaluation is logged to `gamma_signal_log` with the reason codes of the first failing layer, a qualifying signal
opens exactly one paper trade (a double cron fire cannot open two), and open positions are closed on E1/E2/E3. All rule modules are unit-tested offline; the script is covered by an end-to-end test
with all collaborators mocked.

## Perspectives not covered

Execution and data-quality risk of a 5-minute cadence: chain freshness, Upstox/Dhan rate limits, stale OI, cron overlap and market-close edge cases. GS-5 covers overlap (lock) and duplicate entry;
freshness and rate-limit handling need live observation during GS-6's dry-run, and the strategy's profitability is out of scope until the calibration milestones in the strategy doc.
