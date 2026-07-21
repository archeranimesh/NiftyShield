# 3-Track Consolidation & Automation — Epic Prompt

> One task per session. Find the first unchecked item in `stories.md`. That is your only task.
> This epic **reverses part of the documented research design** in `docs/instructions/3track.md`
> and `docs/strategies/nifty_track_comparison_v1.md` — read the Decision Log below before
> touching anything.

---

## Why this epic exists

Operator (2026-07-20) requested four changes to the 3-Track Nifty Long Comparison framework:

1. 3-Track must run fully automated (no human-in-the-loop approval).
2. Spot (NiftyBees) / Futures / Proxy (DITM) remain three ways to answer "should I go long via
   ETF, futures, or a synthetic deep-ITM call?" — this research question (RQ1) is unchanged.
3. Overlays (CC, PP, Collar) exist **only** on the NiftyBees base. Futures and Proxy no longer
   carry their own overlay positions.
4. Exactly one live copy of each overlay leg in the DB. 3-track comparison P&L uses the
   NiftyBees (overlay-adjusted) figure only.

## Decision Log (confirmed with operator 2026-07-20, no council run — operator overrode the
council-checkpoint per CLAUDE.md Step 2b, explicitly accepting the automation risk)

| # | Question | Answer |
|---|---|---|
| 1 | Does this abandon RQ2 ("which overlay works best on which base")? | **Yes, explicitly.** Futures and Proxy report raw, unprotected base P&L only, forever. RQ2 is retired, not deferred — do not resurrect duplicate overlay legs on Futures/Proxy in any future story without a fresh decision. |
| 2 | What happens to the ~18 existing duplicate overlay rows already in `paper_trades` for `paper_nifty_futures` and `paper_nifty_proxy` (collar_call 65900, collar_put 65894, pp 58627/63848 — see S1)? | Deferred to story-writing time. **This document's recommendation: close them out with an explicit synthetic exit trade, not a hard delete** — paper P&L history should stay reconstructable, and a silent delete would make the 2026-05 to 2026-07 realized P&L numbers already reported to the operator (e.g. proxy realized +30,985.18) irreproducible. Flagged as **S1 — requires explicit operator go-ahead before running**, separate from the rest of the epic, because it mutates trade history operators have already seen reported numbers from. |
| 3 | Automate `NiftyTrackComparisonV1` (currently `auto_execute=False` by design)? | **Yes, operator has decided. Council pass explicitly skipped at operator's instruction.** Do not re-litigate this in a future session; if a future agent is tempted to add a council step here, that instruction has already been overridden once by the person who owns the capital risk being modeled. |

## Scope boundary — what this epic does NOT touch

- Base-instrument roll logic (`get_next_contract_in_band`, futures roll) — unchanged.
- `paper_nifty_futures` standalone-CC hard block — stays; irrelevant now since CC only exists
  on NiftyBees anyway, but the guard in `_check_futures_cc_block` should not be deleted (defense
  in depth if a future story re-adds futures overlays).
- CSP (`paper_csp_nifty_v1`), Iron Condor V1/V2 — untouched, different strategy family.
- `PortfolioDeltaTracker` combined-delta caps — untouched; still applies at the account level.

## Files most likely touched (confirm exact set at each story's start)

- `src/strategy/nifty_track_comparison_v1.py` — auto_execute flip, per-track overlay gating
- `src/strategy/exit_signals.py` — no signal-rule changes expected, only which tracks call them
- `src/paper/store.py` / `src/paper/models.py` — if overlay leg ownership needs a schema marker
- `scripts/strategies/three_track/paper_3track_overlay.py`, `paper_3track_overlay_entry.py` — restrict entry to NiftyBees
- `scripts/strategies/three_track/paper_3track_snapshot.py` — P&L aggregation change
- `docs/instructions/3track.md`, `docs/strategies/nifty_track_comparison_v1.md` — rewrite to match new design
- `DECISIONS.md` — log the RQ2 retirement and automation flip as formal decisions
- `tests/unit/strategies/`, `tests/unit/scripts/` — per-story

**Before any code, every story:** run the CLAUDE.md Rule 0 graph checks (`git log --oneline -10
<file>`, `search_graph`, `trace_path`) before `Read`. Do not skip this because the epic is
pre-scoped — the graph will surface any drift between this doc (written 2026-07-20) and the
current code state.
