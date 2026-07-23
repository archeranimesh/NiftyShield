Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/greeks-bs-fallback/tasks.md` and find the first unchecked box. That is your **only
task** for this session. Do not look at any other unchecked item. One task. Complete it fully.
Stop.

**Story spec:** Read the matching story in `docs/plan/greeks-bs-fallback/stories.md` for the
full spec.

**Background:** `filter_strikes_by_delta()` (`src/instruments/strike_selector.py`) selects IC
entry strikes by target `|delta|` against Upstox's `option_greeks.delta` field. Confirmed
2026-07-22 (Cowork session, live diagnostic scripts in `scratch/`): for the yearly IC bucket
(Dec 2026 expiry, DTE 160 at the time), Upstox returns `delta`/`gamma`/`theta`/`vega`/`iv` as
`0.0` on every single strike, both PE and CE — not missing/`None`, just zero — despite every
strike having real, liquid `ltp`/`bid`/`ask`/`oi`/`volume` (confirmed via full chain dump,
`scratch/2026-07-22_ic_yearly_full_chain_dump.py`). This is a data gap in Upstox's Greeks
computation for far-dated contracts, not an illiquid/unquoted market. It hard-blocks yearly IC
entry (`ic_entry.leg_resolution_failed`) regardless of the expiry-resolution fix in
`DECISIONS.md` BUG-015 — no strike can ever match a nonzero delta band against an all-zero field.

**Decision (Animesh, 2026-07-22):** compute Greeks ourselves rather than substitute a cruder
points/percentage-OTM strike-selection heuristic. We have real spot (`NSE_INDEX|Nifty 50`),
strike, DTE, and real mid prices — back out implied vol via Black-Scholes inversion
(Newton-Raphson), then compute delta from that IV. This keeps every strategy's actual entry
criteria (target `|δ|`) intact instead of quietly redefining what "0.12 delta" means for one
bucket.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first using the
graph. Order: `git log` → graph query (`search_graph`/`get_code_snippet`/`trace_path`) →
`search_code` → `sed -n` → `Read` (state why the graph was insufficient).

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` first — do not write fixtures from memory.

**This is quant-correctness work, not a mechanical fix.** GF-2/GF-3 need real financial-math
literacy (Black-Scholes, Newton-Raphson convergence behavior, sane bounds/guards). Do not
implement from a half-remembered formula — cite the reference used (e.g. Hull's textbook
formula) in the module docstring, and GF-5's validation-against-known-good-chain gate is
mandatory, not optional, before this touches anything that could reach live capital.

**Open decisions the story deliberately leaves to the story owner (do not silently pick):**
1. Risk-free rate source — flat assumption (e.g. ~6.5% INR) vs. a config value vs. deriving one.
2. Time-to-expiry convention — calendar days/365 vs. trading days/252 — must match whatever
   convention, if any, `src/backtest/ivr.py` or other existing vol code in this repo already
   uses, to stay internally consistent. Check before assuming.
3. Delta tolerance for GF-5's validation gate (how close must our computed delta be to Upstox's
   own on a known-good chain to trust the fallback on a chain where Upstox gives us nothing).
See GF-1's audit — surface these for a decision before GF-2 starts, don't guess.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing. GF-2/GF-3 need their own unit tests using static/synthetic
fixtures — no network in tests, per project standard.

**Financial-logic gate:** every task in this story touches option chain Greeks computation
feeding real strike selection for paper trades. Per `CLAUDE.md`'s AutoTrigger table, both the
real `@code-reviewer` subagent AND `@greeks-analyst` subagent must run clean against
`git diff HEAD` before committing any of GF-2 through GF-4 — inline self-review does not
satisfy this gate. Resolve CRITICAL/ERROR findings before commit; WARNING may be deferred with
a documented reason in the commit message. On surfaces that cannot spawn these subagents,
follow `CLAUDE.md`'s human-review fallback — do not skip the gate silently.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft
it and stop.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.
