# CC Delta-Based Strike Selector — Story Spec

> Part of the 3-track-consolidation epic (CC is the NiftyBees-only overlay this epic's S1/S2/S4
> restrict and automate). Kept in its own file rather than folded into `stories.md`'s S1–S6 —
> this doesn't touch any of that sequencing or those files, so it's tracked separately to avoid
> confusion with the S1–S6 numbering, but lives in this folder since it's the same epic.
>
> Context: `scripts/lookup/find_strike_by_delta.py` already does everything needed for a
> delta-targeted, multi-expiry (monthly/quarterly/yearly), liquidity-gated strike search —
> but it is CSP-only under the hood. Confirmed via live run (2026-07-28, `--option-type CE
> --delta-min 0.20 --delta-max 0.35 --strategy paper_covered_call_v1`): the printed
> comparison table honors the user's `--delta-min`/`--delta-max` flags, but the actual
> auto-selected strike (the one that generates the `record_paper_trade` command) does not —
> it re-filters against a hardcoded module-level `DELTA_CANDIDATES = [0.22, 0.25, 0.20]`,
> which is CSP's short-put target ladder, regardless of what the caller asked for. For CC
> this is silently wrong: the CLI accepted CE + a CC-appropriate delta range and then handed
> back a strike chosen against CSP's target deltas anyway.

---

## CC1 — Per-strategy delta candidate ladder, CC gets its own

**Problem:** `DELTA_CANDIDATES` (module-level constant in `find_strike_by_delta.py`) is used
unconditionally in `main()`'s auto-select loop, regardless of `--strategy`/`--option-type`.
There is no `CC_DELTA_CANDIDATES` — CC either silently inherits CSP's ladder (current, wrong
behavior) or has to bypass auto-select entirely and read the printed table by hand (current
workaround).

**Files to change:**
- `scripts/lookup/find_strike_by_delta.py` — add `CC_DELTA_CANDIDATES`, select the ladder
  based on `--option-type` (CE → CC ladder, PE → existing CSP ladder) or an explicit
  `--overlay-type cc` flag if that reads more clearly than inferring from side
- `src/instruments/strike_selector.py` — `rank_strikes()`'s docstring says "CSP entry
  preference" but the ranking tuple itself (round-strike preference, spread bucket, OI,
  exact spread) isn't actually CSP-specific — confirm this before assuming it needs to
  change; likely just a docstring fix, not a logic change
- `tests/unit/test_find_strike_by_delta.py` — new tests for CC ladder selection
- `src/strategy/cc_overlay_v1.py` — `reentry_script_hint` currently points to
  `find_overlay_strikes.py --overlay-type cc` (the %OTM tool); decide whether this story's
  output should update that hint to the delta-based tool instead (see CC2 below — this
  can't be decided independently of CC2)

**Before any code:**
```
get_code_snippet("find_strike_by_delta.main")           # confirm auto-select loop location, already reviewed above
get_code_snippet("DELTA_CANDIDATES")                      # confirm current CSP values, already reviewed above
search_code("DEFAULT_STRATEGY")                           # confirm all CSP-specific defaults that need a CC sibling
git log --oneline -10 scripts/lookup/find_strike_by_delta.py
```

**Tests:**
- `test_cc_ladder_used_for_ce_option_type` — `--option-type CE` selects from
  `CC_DELTA_CANDIDATES`, not `DELTA_CANDIDATES`
- `test_csp_ladder_unchanged_for_pe_option_type` — regression guard, PE path untouched
- `test_selected_strike_respects_requested_delta_range` — the auto-selected row's delta
  actually falls near the CC ladder, not CSP's, when `--option-type CE`

**Commit:** `feat(instruments): CC-specific delta candidate ladder, decouple from CSP's`

---

## CC2 — Open decision (needs operator input before CC1 can pick real numbers)

**What `CC_DELTA_CANDIDATES` should actually contain is not a mechanical choice — it's a
live strategy-parameter decision, and there's a real tension to resolve first:**

The CC overlay's current *production* entry path (`find_overlay_strikes.py
--overlay-type cc`) targets a fixed 4% OTM strike — confirmed 2026-07-28 experiment: for
monthly (2026-08-25), 4% OTM lands near strike 24950 (delta ≈0.135, quite far OTM / low
delta). A delta-targeted search at 0.20–0.24 (this session's test run) instead picked strike
24700 (≈2.4% OTM, delta 0.2191) — a **closer, higher-delta, higher-premium, higher-assignment-
risk strike than the current live default.** These are not the same strike and not a rounding
difference — they represent two different entry philosophies (fixed %OTM vs. fixed-delta),
and CC's existing exit rules (`DELTA_STOP` 0.55, `DELTA_WARN` 0.45) were presumably calibrated
against whatever entry delta the %OTM approach has historically produced, not against a
0.20–0.24 entry target.

**This qualifies for the CLAUDE.md council checkpoint** (load-bearing: changes what strike
real paper trades get entered at; two materially different approaches with different P&L/
assignment-risk profiles; spans strategy design + NSE microstructure). Recommend template
`strategy_parameters`, draft question:

> "CCOverlayV1's current production entry uses a fixed 4% OTM strike via
> find_overlay_strikes.py. A delta-targeted alternative (using the existing
> find_strike_by_delta.py engine, generalized for CC) would instead target a fixed delta
> band (e.g. 0.20–0.30). These produce materially different strikes — 4% OTM is
> ~0.135 delta on the current monthly chain, versus 0.20–0.24 landing 1.6 percentage
> points closer to the money. Should CC entry move to a delta-targeted approach, and if so
> what delta band, given DELTA_STOP fires at 0.55 and DELTA_WARN at 0.45 — is there a
> preferred cushion between entry delta and the stop, and does moving closer to the money
> change the appropriate PROFIT_TARGET/TIME_STOP calibration too?"

**Until this is answered, CC1 can ship as an experimentation/comparison tool only** (parallel
to `find_overlay_strikes.py`, not replacing it) — `CC_DELTA_CANDIDATES` gets a reasonable
placeholder (e.g. matching the 0.20–0.24 band already validated in this session's test run)
with an explicit code comment that the values are provisional pending this decision, and
`cc_overlay_v1.py`'s `reentry_script_hint` stays pointed at the %OTM tool until the operator
decides otherwise.

**Commit:** none — this is a decision-gate note, not an implementation story. Resolve via
council or direct operator decision, then update `DECISIONS.md` and CC1's ladder values.

---

## Suggested pick-up order

CC1 can be implemented now as a provisional/parallel tool (placeholder ladder, clearly
labeled experimental) — it doesn't need to wait on CC2 to exist and be useful for
comparison purposes, exactly as it was used in this session. It does need to wait on CC2
before its output is treated as a live trading recommendation that supersedes
`find_overlay_strikes.py`.
