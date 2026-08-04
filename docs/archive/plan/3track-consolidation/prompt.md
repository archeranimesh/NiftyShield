# 3-Track Consolidation & Automation — Epic Prompt

> One task per session. Find the first unchecked `- [ ]` item in `tasks.md` (the checklist —
> `stories.md` holds the full spec per open task ID, read the matching section there once the
> task ID is known; completed stories are archived at
> `docs/archive/plan/3track-consolidation-completed.md`, not in `stories.md` anymore). That is
> your only task.
> This epic **reverses part of the documented research design** in `docs/instructions/3track.md`
> and `docs/strategies/nifty_track_comparison_v1.md` — read the Decision Log below before
> touching anything.
>
> **On completion:** confirm the commit SHA via `git log --oneline -1`, then open `tasks.md` and
> check the completed line — if it does not already end with `| SHA: <sha>`, tick `- [x]` and
> append it; if a SHA is already present (e.g. checked off in an earlier partial session), leave
> it untouched rather than overwriting. Log the session in `docs/archive/TODOS_ARCHIVE.md`'s
> Session Log (create today's dated section if none exists yet), not in `TODOS.md` directly —
> `TODOS.md` itself says new entries belong in the archive since the 2026-07-27 reorg.

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
| 4 | (2026-07-28, supersedes S3's original synthetic-attribution design) Should the daily 3-track comparison use an overlay-adjusted NiftyBees figure, with Futures/Proxy shown via synthetic attribution? | **No — reversed.** Operator wants a fully independent, apples-to-apples base-instrument comparison: all three tracks (Spot/Futures/DITM) compared on base-leg P&L only, persisted daily so performance can be queried over time. Overlay is **display/analysis only, never trade-linked to Futures/Proxy (already true via S2) and now also never math-linked to the comparison** — no overlay-adjusted NiftyBees number, no synthetic attribution to Futures/Proxy, for any track. Overlay P&L continues to be tracked and reported, just in its own separate place, never blended into the RQ1 comparison. See revised S3. |
| 5 | (2026-07-28) Automated base-leg roll for Futures/DITM — quarterly-first to reduce cost-of-carry roll frequency? | **No.** Considered and rejected — NSE index F&O lists only 3 monthly serials (near/next/far); there is no separately-liquid quarterly instrument. A quarterly-first rule would deliberately pick the least liquid available serial every roll. Keep the existing `["monthly","quarterly","yearly"]` band preference in `get_expiry_candidates()`/`get_next_contract_in_band()` unchanged. |
| 6 | (2026-07-28) Roll trigger and liquidity-gate behavior for S5's base-leg roll automation? | **Corrected same day — trigger is per-leg, not a single shared threshold.** `base_futures`: **DTE ≤ 1** (roll on expiry day or the day before — operator preference, prioritizing capital efficiency over the liquidity-crunch concern originally raised for this leg). `base_ditm_call`: **DTE < 20** (band_min+5 buffer, ~1 week ahead — operator's stated reasoning was margin increasing near expiry; more material driver is this leg's much thinner options liquidity far from front-month, same conclusion either way). **Gate: warn-only, always roll** for both legs — matches existing `PROXY_OI_MIN`/`PROXY_SPREAD_MAX` pattern in `paper_3track_entry.py`; operator explicitly declined a hard block for this story. **Futures liquidity check: relative OI ≥ 10% of near-month contract's OI** (chosen over an absolute floor — futures OI operates on a different scale than option OI and a fixed number would need periodic re-tuning). Note: Nifty options are cash-settled, not physically delivered, so there's no delivery-margin spike near expiry the way single-stock options can have — flagged as a factual correction, doesn't change the DITM trigger decision. |
| 7 | (2026-07-28) Should initial entry (base + overlay), not just maintenance actions, also be automated? | **Yes, but as a one-time bootstrap, not recurring — corrected same day.** Initial answer ("fixed cadence, independent of position state") was struck after a lifecycle walkthrough surfaced it assumed a "periodic new cycle" model that isn't the operator's intent: NiftyBees is never closed, and "roll" (Futures/DITM) means contract maintenance on one continuous position, not cycle renewal. There is no cycle to re-enter periodically. Automate entry only for the case of no open position existing yet (first-ever entry); no cadence, no overlap logic needed — there's no second cycle to overlap with. See S6. |
| 8 | (2026-07-28) What's the visibility mechanism once there's no approval gate left anywhere in the pipeline? | **Telegram notification on every trade event** — base-leg roll (S5, build the notify call in from the start), overlay entry/open (currently silent, new), base-leg initial entry (currently silent, new). Overlay close is already implemented (`cc_overlay_v1.py`/`pp_overlay_v1.py`/`collar_overlay_v1.py`) and unchanged. See S6. |

## Scope boundary — what this epic does NOT touch

- Base-instrument roll logic (`get_next_contract_in_band`, futures roll) — unchanged.
- `paper_nifty_futures` standalone-CC hard block — stays; irrelevant now since CC only exists
  on NiftyBees anyway, but the guard in `_check_futures_cc_block` should not be deleted (defense
  in depth if a future story re-adds futures overlays).
- CSP (`paper_csp_nifty_v1`), Iron Condor V1/V2 — untouched, different strategy family.
- `PortfolioDeltaTracker` combined-delta caps — untouched; still applies at the account level.

## Which files a story touches

Each story in `stories.md` states its own "Files to change" section — that is the authoritative,
per-story list; do not reconstruct it here, it goes stale the moment a story's actual
implementation diverges from its plan (it already has, twice, for S1r/S3). Confirm the exact set
at each story's start via the graph, not by memory of this doc.

**Story count has grown past the original 7** (S1/S2 superseded by S1r/S2r/S3r per the
2026-07-29 revision; CC1–3, PP1–3, Collar1–3, S7, S8, S9 added as independent sub-threads) — the
epic prompt's "one task per session, find the first unchecked item in `tasks.md`" instruction
still applies regardless of count; several stories are independent of each other (see ordering
notes in `stories.md` and `tasks.md`), so which one is "first unchecked" depends on what's
already landed. **Completed stories (S1r, S2r, S3, plus the original superseded S1/S2) are
archived in full at `docs/archive/plan/3track-consolidation-completed.md`** — `stories.md` now
holds only open/pending story specs.

**Before any code, every story:** run the CLAUDE.md Rule 0 graph checks (`git log --oneline -10
<file>`, `search_graph`, `trace_path`) before `Read`. Do not skip this because the epic is
pre-scoped — the graph will surface any drift between this doc (written 2026-07-20) and the
current code state.
