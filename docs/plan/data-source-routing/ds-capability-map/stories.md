# DS Capability Map — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

---

## DSM-1 — Roll-critical verification

**Files to change / create:**
- `docs/plan/data-source-routing/ds-capability-map/roll_checks.md` — the findings. No checkboxes.
- `scratch/data_probes/<date>_<topic>.py` — only for checks needing live data; follow `SCRATCH.md`, extract rather than re-derive, read-only calls only.

**Before any code:**
- Read `docs/archive/council/data_architecture/2026-10-07_data-source-routing.md` Stage 3 §Q5 and the Dissenting Notes for Q1.
- Reuse existing probes in `scratch/data_probes/`; `search_graph("InstrumentLookup")`, `get_code_snippet("InstrumentLookup")` for how the BOD file is loaded.

**What to produce (three checks, in this order — the first can block the roll):**

1. **Upstox BOD coverage.** Does the Upstox instrument master list NIFTY Dec 2027 option contracts (CE and PE across the strike range the yearly strategies select), as of the date checked? Use
   `InstrumentLookup.get_all_option_expiries("NIFTY")` and a strike count. State the date of the BOD file. If Dec 2027 is absent, say when Upstox typically lists a new December series (look at how Dec
   2026 appeared in earlier BOD files if any are kept) and flag that the council requires a separate architectural decision before the roll (ledger key cannot be written).
2. **Dhan failure shapes.** The exact response for error 806 ("Data APIs not subscribed") and for a missing, expired or invalid access token, plus the 805 shape already seen. Needed by DSC-3 / DSN-1
   to classify failures. If a live trigger is impractical (it would need a lapsed plan or a bad token), mark `unverified — owner Animesh` and record where the primary docs state it.
3. **Upstox Greeks flip, second expiry.** DDP-5 measured Dec 2026 (zero at DTE 91, non-zero at DTE 90). Confirm on one more expiry from stored chains, or mark unverified. The council set the
   source-switch trigger as 2 consecutive trading days of non-zero delta on held contracts, not a DTE value, so this is context for the dual-read band, not a gate.

Primary Dhan doc pages may be unreachable from a cloud session; if so, mark those cells `unverified — owner Animesh` instead of filling from a summary.

**Tests:** none (docs and read-only probes).

**Commit:** `docs(plan): roll-critical data source checks`

---

## DSM-2 — Run the council (done)

Council ran 2026-10-07; output added in `1cc4c30` and archived to `docs/archive/council/data_architecture/2026-10-07_data-source-routing.md` by DSM-3.

---

## DSM-3 — Absorb the ruling (done)

`DECISIONS.md` row added; `docs/council/README.md` topic row added (archived); `ds-chain-seam/` and `ds-chain-monitoring/` specced from the Summary Table; the broader capability matrix re-homed as
`ds-router-migration/` DSR-0; epic README open decisions amended. Q4 clarified by Animesh on 2026-10-07 (action-class split, delta-independent backstop, freshness bound tied to cadence).
