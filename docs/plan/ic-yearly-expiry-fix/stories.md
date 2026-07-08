# IC Yearly Expiry Correction — Story Specs

---

## YE-1 — Audit blast radius before changing shared resolution logic

**Problem:**
`InstrumentLookup.get_expiry_candidates()` (`src/instruments/lookup.py:279-371`) defines the
`"yearly"` label as: last expiry of the calendar month, month in `{6, 12}` (June or December),
with DTE in `[201, 420]`. Whichever of June/December first clears that DTE band wins the
`"yearly"` slot.

Observed failure (2026-07-08): IC V1's yearly bucket (`ic_expiry_config.py` `CONFIGS["yearly"]`,
`dte_warn_lo=180`, `dte_warn_hi=270`) resolved to **2027-06-29** (DTE 356) instead of December
2026, because December 2026 (last Tuesday ≈ 2026-12-29, DTE 174) fell below the 201-day floor —
June 2027 was the only Jun/Dec candidate left in the 201–420 window. Per Animesh (2026-07-08,
25+ years NSE options trading): **NSE Nifty's annual/long-dated option is always the last Tuesday
of December.** June is a half-yearly milestone, not an interchangeable "yearly" candidate — the
code's own comment (`lookup.py:351`, "NSE's long-dated options (yearly/half-yearly) expire in
June and December") already draws this distinction; the bug is that the `"yearly"` *label*
doesn't respect it.

**Root cause:** `is_yearly = is_monthly and (d.month in (6, 12))` (`lookup.py:352`) treats June
and December as equally valid "yearly" candidates, gated only by the 201–420 DTE band — a
generic distance filter, not a December-specific rule.

**Why an audit first, not just a fix:** the `"yearly"` label is consumed by 8 call sites, not
just IC V1:
- `scripts/strategies/ic/paper_ic_entry.py` (IC V1 yearly bucket — the one that broke)
- `scripts/monitor_daemon.py`
- `scripts/strategies/three_track/paper_3track_overlay.py`
- `scripts/strategies/three_track/paper_3track_entry.py`
- `scripts/pipeline/upstox_chain_intraday.py`
- `scripts/pipeline/upstox_chain_snapshot.py`
- `tests/unit/instruments/test_expiry_candidates.py` (fixtures)
- `tests/unit/test_upstox_chain_intraday.py`, `tests/unit/test_upstox_chain_snapshot.py` (fixtures)

Changing `get_expiry_candidates()`'s `"yearly"` semantics fixes all 8 at once but changes
behavior for callers that may not have hit the June-selection bug yet (or may not care — chain
snapshot/monitor-daemon callers may just want "the current long-dated contract, whichever it
is," not specifically December). Do not assume; check each one.

**Task:**
1. For each of the 6 non-test call sites above: read the surrounding code and determine whether
   it depends on `"yearly"` meaning specifically December, or whether "whichever Jun/Dec contract
   is currently in the DTE band" is acceptable/intended for that caller's purpose (e.g. chain
   snapshot pipelines may just want continuous far-dated chain coverage regardless of month).
2. Check `tests/unit/instruments/test_expiry_candidates.py` — confirm (already verified in this
   session) that no existing test asserts June winning the `"yearly"` slot; all yearly fixtures
   use December dates incidentally. Confirm the same for the two chain-snapshot test files.
3. Produce a short table: caller → current behavior → would-change-if-December-only (yes/no) →
   recommendation (safe to change / needs its own follow-up / out of scope).
4. **Do not fix anything in this task.** Output is the audit table only, appended to this file
   under a new `### YE-1 findings` heading.

**Files touched:** none (read-only audit). Append findings to this file.

---

## YE-2 — Fix `get_expiry_candidates()`'s `"yearly"` label to mean December, always

**Prerequisite:** YE-1 complete. If YE-1 finds a caller that genuinely needs "whichever of
Jun/Dec is in range" (not confirmed to exist yet, but check), stop and flag it — do not silently
special-case IC V1 while leaving the shared method's contract ambiguous; surface the conflict
before writing code.

**Fix:**
Change `is_yearly` (`lookup.py:352`) so `"yearly"` only ever matches `d.month == 12`. Drop the
201–420 DTE gate for this label specifically — December's DTE naturally ranges from ~1 to ~365
across the year depending on when `today` is; a fixed distance band is the wrong tool for "give
me the nearest December, whatever its current distance is." Instead: find the nearest December
last-Tuesday expiry with `dte >= 1` (today or later), full stop — no upper/lower DTE bound at
the `get_expiry_candidates()` layer. If the current year's December has already passed (or DTE
< 1), roll forward to next year's December. Per-strategy DTE *warnings* (not hard filters) stay
where they already live — `ic_expiry_config.py`'s `dte_warn_lo`/`dte_warn_hi` — as a THRESHOLD
gate under the existing `--log-only-gates` philosophy (DECISIONS.md 2026-07-03 entry). Do not
add a new hard DTE filter to compensate; that would reintroduce the same class of bug (a distance
band silently excluding the one contract that should always resolve).

June's semi-annual expiry is not deleted from the codebase, just no longer eligible for the
`"yearly"` label. If YE-1 finds a caller that actually wants June recognized as a distinct
cadence, that's a new label (e.g. `"half_yearly"`) — out of scope for this fix unless YE-1
surfaces a real need.

**`ic_expiry_config.py` follow-up:** `CONFIGS["yearly"].dte_warn_lo=180` will now legitimately
fire a WARNING (not a block) for roughly 6 months of the year, since December's real DTE swings
from ~365 down to ~1. Confirm this is acceptable (it should be, given the log-only-gates
philosophy already treats DTE as informational) — do not widen `dte_warn_lo`/`dte_warn_hi` to
suppress the warning unless the story owner explicitly decides the warning is noise, not signal.

**Tests required:**
- Nearest-December-found: `today` in Jan/Feb of a year, December of that same year exists in the
  instrument set → resolves to that December, regardless of DTE.
- Roll-forward: `today` in late December (past this year's expiry) or with only next year's
  December available → resolves to next year's December.
- June no longer wins: construct a fixture where June clears an old-style DTE band and December
  does not (the exact 2026-07-08 scenario from this session, DTE 174 for Dec / 356 for Jun) →
  assert result is still December, not June.
- Existing `test_expiry_candidates.py` yearly fixtures remain green (they're already
  December-only, per YE-1 audit).

**Files touched:** `src/instruments/lookup.py`, `tests/unit/instruments/test_expiry_candidates.py`

---

## YE-3 — Fix affected callers (per YE-1 findings)

**Prerequisite:** YE-2 merged and green.

Apply whatever YE-1's audit table recommended for each of the 6 call sites. If YE-1 found all 6
callers are compatible with December-only `"yearly"` (expected outcome, given none of them
appeared to assert June-specific behavior), this task may be a no-op confirmation pass — add a
regression test per caller proving it still resolves the expected expiry-label pairing it did
before, so a future change to `get_expiry_candidates()` doesn't silently break them again.

If YE-1 found a genuine need for June recognition somewhere, implement the new label from YE-2's
note (`"half_yearly"` or similar) for that caller only — do not reintroduce June into the
`"yearly"` label to accommodate it.

**Files touched:** determined by YE-1's audit — do not pre-list.

---

## YE-4 — Docs close

**No code.** Targeted `Edit` calls only — never `Write` on existing files.

1. `TODOS.md` — mark YE-1 through YE-4 complete, session log entry with SHAs.
2. `DECISIONS.md` — new entry: `"yearly"` expiry label corrected to mean nearest December
   last-Tuesday expiry only (previously matched June or December, whichever cleared a 201–420
   DTE band — caused IC V1's yearly bucket to silently resolve June 2027 instead of December
   2026 on 2026-07-08, since December's DTE at the time, 174, fell just under the 201 floor).
   Rationale: per Animesh, NSE Nifty's annual contract is always December's last Tuesday; June is
   a half-yearly milestone, not an alternate "yearly" candidate. Cite this story's YE-1 audit
   table for the caller-impact assessment.
3. `CONTEXT.md` — update `InstrumentLookup.get_expiry_candidates()` description if its docstring
   summary changed materially (DTE band removed for the yearly label).
