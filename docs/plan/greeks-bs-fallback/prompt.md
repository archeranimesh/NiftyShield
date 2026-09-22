# Greeks BS Fallback — prompt

> Compute delta ourselves via Black-Scholes inversion when Upstox returns all-zero Greeks, so yearly IC entry stops hard-blocking on a data gap.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `docs/plan/greeks-bs-fallback/tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full
spec in `stories.md` (same task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

`filter_strikes_by_delta()` (`src/instruments/strike_selector.py`) selects IC entry strikes by target `|delta|` against Upstox's `option_greeks.delta` field. Confirmed 2026-07-22 (Cowork session, live
diagnostic scripts in `scratch/`): for the yearly IC bucket (Dec 2026 expiry, DTE 160 at the time), Upstox returns `delta`/`gamma`/`theta`/`vega`/`iv` as `0.0` on every single strike, both PE and CE —
not missing/`None`, just zero — despite every strike having real, liquid `ltp`/`bid`/`ask`/`oi`/`volume` (confirmed via full chain dump, `scratch/2026-07-22_ic_yearly_full_chain_dump.py`). This is a
data gap in Upstox's Greeks computation for far-dated contracts, not an illiquid/unquoted market. It hard-blocks yearly IC entry (`ic_entry.leg_resolution_failed`) regardless of the expiry-resolution
fix in `DECISIONS.md` BUG-015 — no strike can ever match a nonzero delta band against an all-zero field. Re-confirmed 2026-08-06, still persistent 3+ weeks later — not a transient outage.

**Decision (Animesh, 2026-07-22):** compute Greeks ourselves rather than substitute a cruder points/percentage-OTM strike-selection heuristic. We have real spot (`NSE_INDEX|Nifty 50`), strike, DTE,
and real mid prices — back out implied vol via Black-Scholes inversion (Newton-Raphson), then compute delta from that IV. This keeps every strategy's actual entry criteria (target `|δ|`) intact
instead of quietly redefining what "0.12 delta" means for one bucket.

## Scope guard

In scope: a new `src/pricing/` module (Black-Scholes pricer + IV solver), wiring the fallback into `filter_strikes_by_delta()` in `src/instruments/strike_selector.py`, and a validation gate before any
live-capital-adjacent use. Out of scope: substituting a points/percentage-OTM heuristic (explicitly rejected above), changing the expiry-resolution logic covered by `DECISIONS.md` BUG-015, and
resolving the three open modeling decisions below — those are Animesh's calls, not this story's to guess. This story changes `src/` behavior (GF-2 through GF-4); GF-1, GF-5, GF-6 are
audit/validation/docs only.

**Open decisions the story deliberately leaves to the story owner (do not silently pick):**
1. Risk-free rate source — flat assumption (e.g. ~6.5% INR) vs. a config value vs. deriving one.
2. Time-to-expiry convention — calendar days/365 vs. trading days/252 — must match whatever convention, if any, `src/backtest/ivr.py` or other existing vol code in this repo already uses, to stay
   internally consistent. Check before assuming.
3. Delta tolerance for GF-5's validation gate (how close must our computed delta be to Upstox's own on a known-good chain to trust the fallback on a chain where Upstox gives us nothing).

See GF-1's audit findings in `stories.md` for the current state of these three decisions — surface for a decision before GF-2 starts, don't guess.

## Session-start load hints

- `DECISIONS.md` BUG-015 (expiry-resolution fix this story sits behind).
- `src/instruments/CLAUDE.md` if present, for `strike_selector.py` invariants.
- `LOGGING.md` before any `logger.*()` call in GF-3/GF-4.
- `Graph-before-Read rule`: never call `Read` on `src/` or `scripts/` without first using the graph. Order: `git log` → graph query (`search_graph`/`get_code_snippet`/`trace_path`) → `search_code` →
  `sed -n` → `Read` (state why the graph was insufficient).
- **Before writing any test helper that constructs a domain model:** run `get_code_snippet('<ModelClassName>')` first — do not write fixtures from memory.

## Task overview

- **GF-1** — Audit scope: confirm which expiry buckets hit all-zero Greeks, pick GF-5's validation ground truth, surface the three open modeling decisions.
- **GF-2** — Black-Scholes pricer + delta formula, `src/pricing/black_scholes.py`.
- **GF-3** — Implied-vol solver, `src/pricing/implied_vol.py`.
- **GF-4** — Wire the fallback into `filter_strikes_by_delta()`.
- **GF-5** — Validation gate against a known-good live chain (blocking).
- **GF-6** — Docs close (`CONTEXT.md`, `DECISIONS.md`, `TODOS.md`).

## Definition of done

All six tasks shipped: the fallback computes delta only when Upstox's own Greeks are all-zero, every returned row is tagged with its delta origin, GF-5's validation shows the computed delta within
Animesh's confirmed tolerance of Upstox's own delta on a known-good chain, and docs reflect the new module and validation results.

**This is quant-correctness work, not a mechanical fix.** GF-2/GF-3 need real financial-math literacy (Black-Scholes, Newton-Raphson convergence behavior, sane bounds/guards). Do not implement from a
half-remembered formula — cite the reference used (e.g. Hull's textbook formula) in the module docstring, and GF-5's validation-against-known-good-chain gate is mandatory, not optional, before this
touches anything that could reach live capital.

**Test gate — blocking:** `python -m pytest tests/unit/ --tb=no -q`. All must be green before committing. GF-2/GF-3 need their own unit tests using static/synthetic fixtures — no network in tests, per
project standard.

**Financial-logic gate:** every task in this story touches option chain Greeks computation feeding real strike selection for paper trades. Per `CLAUDE.md`'s AutoTrigger table, both the real
`@code-reviewer` subagent AND `@greeks-analyst` subagent must run clean against `git diff HEAD` before committing any of GF-2 through GF-4 — inline self-review does not satisfy this gate. Resolve
CRITICAL/ERROR findings before commit; WARNING may be deferred with a documented reason in the commit message. On surfaces that cannot spawn these subagents, follow `CLAUDE.md`'s human-review fallback
— do not skip the gate silently.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft it and stop.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.

## Perspectives not covered

This story treats the zero-Greeks pattern as purely a data-availability problem solved by computing our own Greeks. It does not evaluate whether Upstox's zero-Greeks response for far-dated contracts
reflects a genuine pricing-model limitation on their end (e.g. their vendor may intentionally suppress low-confidence Greeks on thin far-dated order books) that a self-computed Black-Scholes delta —
which assumes a liquid, efficiently-priced market — could be less accurate than, not more, in that specific regime. GF-5's validation gate only checks against a near-dated, liquid chain; it does not
directly validate accuracy on the actual far-dated yearly bucket where Upstox itself has no ground truth to compare against.
