# Council Decision: overlay-pnl-reporting-track-independence

Date: 2026-08-10  
Chairman: anthropic/claude-opus-4.6  
Council members: openai/gpt-5.6-sol, google/gemini-3.1-pro-preview, x-ai/grok-4.3, deepseek/deepseek-r1-0528

---

## Stage 3 — Chairman Synthesis

# Chairman's Ruling: BUG-028 — Overlay P&L Reporting Pipeline Alignment

**Decision: Position B, implemented as a schema-preserving refactor ("B-lite").**

The council is unanimous: Position A (re-attribution) is rejected. Position B (decouple the pipeline to match the entry layer) is adopted, with the practical constraint that the existing SQLite schema requires no DDL changes — only the values written into `strategy_name` change.

---

## Answers to the Four Questions

### 1. Is it architecturally sound for reporting to reintroduce track coupling?

**No.** All four council members agree without exception.

S2r was a deliberate operator decision (DECISIONS.md 2026-07-29 round 5) to make overlay entry/roll track-independent. Re-coupling at the reporting layer does not solve the problem — it relocates the same ambiguity S2r was written to eliminate. Position A has no defensible attribution rule:

- Showing the overlay under all three tracks triple-counts one economic position.
- Assigning it to one "primary" track is arbitrary and misleading.
- Creating a synthetic aggregate row changes the report shape anyway, effectively converging on Position B while retaining Position A's conceptual confusion.

The existing `compute_overlay_coverage()` (S3r) already demonstrates the correct pattern: shared overlays may be *compared with* a base track at read time without being *persisted as belonging to* that track. Reporting must follow the same principle.

### 2. Can the rework be done incrementally, or is backfill necessary?

**Both — they are separable concerns.**

- **Live path (immediate):** New overlay P&L rows are written under `STRATEGY_OVERLAY`. This requires no schema change — the existing `(strategy_name, overlay_type, snapshot_date)` primary key already supports it. Deploy this first to stop the bleeding (every day since S2r has produced silent false-zero rows).

- **Historical repair (one-off, transaction-safe):** Pre-S2r rows were correctly filed under base-track `strategy_name` values at the time they were written. A backfill script following the project's established pattern (`backfill_nav_total_pnl.py`, `migrate_paper_trades_state.py`) should:
  1. Back up the SQLite database.
  2. Derive the actual cutover date from the trade ledger (first overlay trade written under `STRATEGY_OVERLAY`), not from a hardcoded commit date.
  3. Check for primary-key collisions before any UPDATE — if multiple legacy track rows share the same `(overlay_type, snapshot_date)`, they cannot be blindly collapsed into one `STRATEGY_OVERLAY` row. The council specifically flags this as a real risk that a naive `UPDATE strategy_name = 'paper_nifty_overlay'` would hit.
  4. Where reconstruction is ambiguous, preserve the legacy rows and document the canonical-series start date. An explicit discontinuity is safer than fabricated continuity.
  5. Produce counts (inserted, skipped, ambiguous, unchanged) for audit.

**Do not dual-write** the same economic P&L under both legacy track names and `STRATEGY_OVERLAY`. Dual-writing creates duplicate economic observations, ambiguous downstream aggregation, and a second cleanup migration later.

### 3. Is there a viable third option?

**No useful one beyond what B-lite already provides.**

A "join to whichever track is active" approach fails because multiple tracks may be active simultaneously — it would recreate an implicit primary-track concept that S2r removed. Adding a nullable `track_namespace` column adds schema complexity without demonstrated benefit since the existing `strategy_name` column already distinguishes the overlay book.

The genuinely useful "third option" is already embedded in B-lite: persist overlay P&L canonically under `STRATEGY_OVERLAY`, and produce track-relative or NiftyBees-relative *views* at read time only — clearly labeled as comparisons, never written back into canonical snapshot tables.

### 4. Does the single-operator audience justify simpler design?

**Yes — and that simplicity favors Position B, not Position A.**

The operator's daily question is: *"How much did my protection (CC/PP/Collar) recover against my NiftyBees baseline?"* One unified overlay book compared against one NiftyBees benchmark answers this directly. Per-track overlay breakdowns add cognitive load without trading insight — the overlays are genuinely track-independent by construction since S2r. The digest becomes shorter, clearer, and impossible to misread.

---

## Implementation Mandate

### Phase 1 — Correctness Fix (Immediate)

1. **`_compute_overlay_pnl_snapshots()`** (`paper_3track_snapshot.py`): Query overlay positions from `STRATEGY_OVERLAY`, not from the base-track `strategy_name` loop variable. This is the root cause of BUG-028's silent zero.

2. **`generate_track_snapshot()`** (`track_snapshot.py`): Remove or isolate any overlay-leg discovery from the base-track snapshot path. Base-track snapshots report base-leg P&L only. Overlay P&L is computed once per account-level overlay book, not once per base track.

3. **`_build_recovery_digest()`**: Reframe as "NiftyBees benchmark vs standalone overlay book." Join the NiftyBees row and overlay rows by `snapshot_date`. No "active track" selection needed.

4. **`PaperStore.record_overlay_pnl_snapshot()`**: Write canonical rows with `strategy_name = STRATEGY_OVERLAY`. No DDL change — the column and key already exist.

### Phase 2 — Eliminate Silent False Zeros (Part of BUG-028 DoD)

The most dangerous aspect of this bug is that missing source legs produce a valid-looking `Decimal("0")` indistinguishable from "no P&L movement today." The fix must enforce:

- No matching overlay source data → `None` / "No data," **not** `Decimal("0")`.
- The pipeline logs a WARNING containing strategy, overlay type, and date when source data is absent.
- The digest renders "No data" or "No open position" rather than `₹0.00`.
- A zero P&L is emitted only when source observations exist and the computed value is genuinely zero.

This is not optional hardening — it is the invariant that prevents this class of bug from recurring silently.

### Phase 3 — Historical Repair (One-Off Script)

`scripts/dev/migrate_overlay_pnl_attribution.py`:

1. Back up the database.
2. Identify the actual S2r cutover date from the trade ledger.
3. For each pre-cutover row in `paper_overlay_pnl_snapshots`:
   - Check `(STRATEGY_OVERLAY, overlay_type, snapshot_date)` uniqueness before relabeling.
   - If collision-free, UPDATE `strategy_name` to `STRATEGY_OVERLAY`.
   - If collision exists (multiple tracks wrote the same overlay_type on the same date), skip with a logged WARNING and leave the legacy row intact.
4. Output: counts of migrated, skipped (collision), and unchanged rows.
5. Preserve legacy rows for audit unless downstream consumers are proven not to need them.

---

## Required Invariants

The implementation must enforce these properties:

| # | Invariant |
|---|---|
| 1 | One canonical overlay P&L row per `(STRATEGY_OVERLAY, overlay_type, snapshot_date)` |
| 2 | Overlay trades and canonical overlay snapshots use the same strategy namespace |
| 3 | Shared overlay P&L is never persisted once per base track |
| 4 | Recovery calculations consume canonical overlay rows only |
| 5 | Missing source data never silently becomes zero P&L |
| 6 | Historical migration never merges rows without a verified economic-identity rule |
| 7 | Read-time track comparisons cannot write back into canonical snapshot tables |

---

## What This Ruling Does NOT Change

- The `paper_overlay_pnl_snapshots` table schema (no DDL).
- `compute_overlay_coverage()` (S3r) — already correctly uses `STRATEGY_OVERLAY`.
- The overlay entry/roll path — already writes under `STRATEGY_OVERLAY` since S2r.
- The `paper_leg_snapshots` S7 fix — already uses real leg_role keys from `raw_overlay_pnls`.
- Any base-track P&L computation — base legs are unaffected.

---

*Council confidence: high. All four members selected Position B. The primary variance was in migration safety (where Response A's caution about collision checking and non-silent zeros was recognized as the most rigorous treatment). This ruling adopts A's invariants and migration discipline within B's structural direction.*

---

## Stage 1 — Individual Responses

### openai/gpt-5.6-sol

CONTEXT.md ✓

**Scope:** architecture ruling for BUG-028 only; no implementation proposed here.  
**Plan:** determine the canonical ownership model, separate persistence from display projections, and define a safe historical transition.

# Council ruling: adopt Position B, but as a schema-preserving “B-lite”

`STRATEGY_OVERLAY = "paper_nifty_overlay"` must be the canonical owner of overlay trades, leg snapshots, overlay P&L snapshots, and overlay reporting.

Do **not** attribute the same overlay book back to Spot, Futures, or Proxy for persistence. That would recreate the ambiguity S2r deliberately removed and would invite either triple-counting or an arbitrary “primary track” convention.

However, Position B does **not** require dropping the existing `strategy_name` column or redesigning the entire table. The current key:

```text
(strategy_name, overlay_type, snapshot_date)
```

can remain. New canonical rows should simply use:

```text
strategy_name = STRATEGY_OVERLAY
```

This is both structurally correct and considerably smaller than the full schema rework described in Position B.

## Why Position A is rejected

Position A has no defensible attribution rule:

- Showing the overlay under all three tracks triple-counts one economic position.
- Assigning it to one track is arbitrary.
- Creating a synthetic aggregate row already changes the report shape and effectively converges on Position B.
- Reporting ownership would disagree with trade-ledger ownership.

A reporting layer may create comparisons between independent books, but it must not silently turn a comparison into ownership.

The existing `compute_overlay_coverage()` model demonstrates the correct distinction: shared overlays may be compared with each base track at read time without being persisted as belonging to that track.

# Recommended module boundary

Separate the two concepts explicitly:

## 1. Base-track pipeline

`generate_track_snapshot()` should be responsible for the selected base strategy and its base-leg P&L.

It should not discover or persist shared overlay-book P&L as though those legs belonged to the track.

If existing callers still need an overlay-inclusive display, that should be a separate read-time projection rather than part of the canonical track snapshot.

## 2. Overlay-book pipeline

Add or extract one overlay-book computation path that:

1. Queries `STRATEGY_OVERLAY`.
2. Resolves the real roles:
   - `overlay_cc`
   - `overlay_pp`
   - `overlay_collar_call`
   - `overlay_collar_put`
3. Persists overlay leg snapshots once per EOD run.
4. Computes CC/PP/Collar aggregate P&L once.
5. Writes `paper_overlay_pnl_snapshots` with:
   ```text
   strategy_name = paper_nifty_overlay
   ```
6. Feeds the recovery digest from those canonical rows.

This calculation must run once per account-level overlay book, not once per base track.

## 3. Recovery comparison

The Telegram digest should be framed as:

> NiftyBees benchmark vs standalone overlay book

That is a **benchmark comparison**, not an ownership relationship.

Joining the NiftyBees row and overlay rows by `snapshot_date` is sound. No “active track” needs to be selected.

# Answers to the four questions

## 1. Should reporting reintroduce track coupling?

No.

Doing so would relocate, rather than solve, the confusion addressed by S2r. Canonical reporting and canonical trade ownership should agree.

Track-specific comparisons can still exist as read-time analytics, but they must be labeled as comparisons and must never cause duplicate persistence.

## 2. Is dual-writing appropriate, or is backfill mandatory?

Do not dual-write the same economic P&L under both legacy track names and `STRATEGY_OVERLAY`.

Dual-writing would create:

- duplicate economic observations,
- ambiguous downstream aggregation,
- a risk that consumers sum both forms,
- a second cleanup migration later.

A hard migration of open positions is **not** needed. Current trades already live under `STRATEGY_OVERLAY`; the corrected pipeline should begin reading them directly.

Historical snapshot handling is a separate matter:

1. Deploy the corrected canonical writer.
2. Determine the real cutover from ledger data—the first overlay trade written under `STRATEGY_OVERLAY`—rather than relying only on a commit date.
3. Backfill canonical historical rows only where the old data can be mapped unambiguously.
4. Preserve legacy rows for audit unless there is a compelling reason to delete them.

Before relabeling old rows, verify uniqueness for each:

```text
(snapshot_date, overlay_type)
```

If multiple legacy track rows exist for the same date/type, do not arbitrarily choose one or sum them without proving they represent components of the same economic book.

If reconstruction is ambiguous, preserve the legacy series and document the canonical-series start date. An explicit discontinuity is safer than fabricated continuity.

## 3. Is there a viable third option?

Yes, but not the proposed “join to whichever track is active.”

The recommended B-lite design is effectively the useful third option:

- Persist overlay P&L under `STRATEGY_OVERLAY`.
- Keep the existing table and key shape.
- Produce track-relative or NiftyBees-relative views at read time.
- Never persist those views as ownership records.

“Whichever track is active” is not a stable rule because multiple tracks may be active simultaneously. It would recreate an implicit primary-track concept that S2r removed.

A valid derived view could instead be:

```text
base_strategy_name
base_pnl
shared_overlay_pnl
combined_hypothetical_pnl
```

but it must be clearly labeled as a hypothetical/read-time projection and must not write another overlay snapshot.

## 4. Does the single-operator audience justify something simpler?

Yes.

The system does not currently need a generalized N-strategy allocation engine. The simplest correct model is:

- three independent base books,
- one standalone overlay book,
- one NiftyBees benchmark,
- read-time comparisons among them.

Keep `strategy_name` in the table even if canonical overlay rows currently all use the same value. It preserves provenance, avoids a schema migration, and leaves room for future separate overlay books without committing to a generalized allocation framework today.

# Migration and rollout recommendation

## Phase 1 — correctness fix

- Query overlay positions from `STRATEGY_OVERLAY`.
- Persist overlay leg/P&L snapshots once per day.
- Build the digest from canonical overlay rows.
- Stop producing track-attributed overlay snapshots.
- Preserve the existing SQLite schema.

## Phase 2 — prevent silent false zeros

The current failure is especially dangerous because “missing source legs” becomes a valid-looking zero.

Change the reporting contract so that:

- no matching overlay source data means **missing/not available**, not `Decimal("0")`;
- the pipeline logs a WARNING containing the strategy, overlay type, and date;
- the digest renders “No data” or “No open position” rather than `₹0`;
- a zero is emitted only when source observations exist and the computed P&L is genuinely zero.

This should be treated as part of BUG-028’s Definition of Done, not optional hardening.

## Phase 3 — historical repair

Use a one-off, transaction-safe backfill script:

1. Back up the SQLite database.
2. Inspect legacy rows and corresponding trade/leg snapshots.
3. Recompute from source ledger/leg snapshots where possible.
4. Insert canonical rows under `STRATEGY_OVERLAY`.
5. Abort on key collisions or ambiguous multi-track ownership.
6. Produce counts for inserted, skipped, ambiguous, and unchanged rows.
7. Keep legacy rows for audit unless downstream consumers are proven not to need them.

Do not merely rename `strategy_name` values unless it is proven that each legacy row represents the same standalone overlay book.

# Required invariants

The implementation should enforce these invariants:

1. One canonical overlay P&L row per:
   ```text
   (STRATEGY_OVERLAY, overlay_type, snapshot_date)
   ```
2. Overlay trades and canonical overlay snapshots use the same strategy namespace.
3. Shared overlay P&L is never persisted once per base track.
4. Recovery calculations consume canonical overlay rows only.
5. Missing source data never silently becomes zero P&L.
6. Historical migration never merges rows without a documented economic-identity rule.
7. Read-time track comparisons cannot write back into canonical snapshot tables.

## Final decision

**Choose Position B’s ownership model, implemented as a schema-preserving B-lite refactor.** Keep `paper_overlay_pnl_snapshots.strategy_name`, write canonical rows under `STRATEGY_OVERLAY`, separate overlay computation from `generate_track_snapshot()`, and treat any base-track association as a read-time comparison only.

Do not re-couple reporting to tracks, do not dual-write duplicate economic rows, and do not perform an unconditional historical relabel.

### google/gemini-3.1-pro-preview

**DECISION: Position B (Decouple the pipeline)**

The reporting pipeline must be decoupled to match the entry layer's architecture. Overlays are physically and logically traded as a single unified pool (`STRATEGY_OVERLAY`). The reporting layer must reflect this reality rather than hallucinating per-track relationships that execution explicitly dismantled in S2r. 

Here is the council's direct response to your questions and the implementation mandate:

### 1. Architectural Soundness of Re-coupling (Position A)
Re-coupling at the reporting layer is an architectural anti-pattern and should be rejected. If you attempt Position A, you are forced to either triple-count the P&L (breaking the portfolio-level P&L invariants) or arbitrarily assign the shared overlay to one specific base track (which makes the report misleading). S2r decoupled overlays because they provide generalized portfolio protection. Reporting them as a single, independent strategy book is the only mathematically sound approach.

### 2. Migration Path vs. Incremental Delivery
Do a clean backfill. This codebase has an established pattern of using one-off migration scripts to correct data invariants (e.g., `backfill_nav_total_pnl.py`, `migrate_paper_trades_state.py`). 
Writing a query-time branch to handle a schema discontinuity (i.e., `if date < S2r_date: use base_track else: use STRATEGY_OVERLAY`) will permanently pollute `track_snapshot.py` and `paper_3track_snapshot.py`. Instead, write a quick `scripts/dev/migrate_overlay_attribution.py` to UPDATE the `strategy_name` of all pre-2026-08-04 overlay rows in `paper_overlay_pnl_snapshots` (and `paper_leg_snapshots` if applicable) to `STRATEGY_OVERLAY`.

### 3. Is there a viable third option (Read-time Join)?
No, because read-time joins presuppose that viewing the overlay "through the lens of a specific track" provides analytical value. The operator already confirmed (during S9) that CC/PP/Collar run as live parallel overlays specifically against NiftyBees, and the `OverlayCoverage` metric (S3r) already uses the track-independent `STRATEGY_OVERLAY` namespace. Trying to artificially map the P&L back to Futures or Proxy via a join just adds query complexity without delivering actual trading insight. 

### 4. Audience and Simplicity
The single human operator audience strongly argues for Position B. The operator's primary question at EOD is: *"How much did my protection (CC/PP/Collar) recover against my baseline (NiftyBees)?"* 
Stripping out the legacy per-track breakdown makes the Telegram digest shorter, clearer, and faster to read. 

### Implementation Mandate
1. **Reporting Queries:** Modify `_compute_overlay_pnl_snapshots()` to pull base positions explicitly from `STRATEGY_OVERLAY` rather than inheriting the loop's `strategy_name`. 
2. **Digest Framing:** Update `_build_recovery_digest()` to frame the report as "NiftyBees vs Unified Overlays". Remove all legacy track-iteration logic related to overlays.
3. **Migration:** Write a one-off script to migrate historical data so `paper_overlay_pnl_snapshots` is uniformly keyed to `STRATEGY_OVERLAY` from inception to present. 
4. **Data Model:** No schema changes (DDL) are required. The table already has a `strategy_name` column; we are simply standardizing the string value it holds for overlays.

### x-ai/grok-4.3

**Council recommendation: Position B (Decouple pipeline).**

### Answers to the four questions

1. **Re-coupling via reporting is architecturally unsound.**  
   S2r was an explicit operator decision (DECISIONS.md 2026-07-29 round 5) to make overlay entry/roll track-independent. Re-introducing the coupling only in the reporting layer (Position A) simply moves the mismatch from the write path to the read path. It creates exactly the attribution ambiguity the council already rejected at entry time (which track “owns” a leg that was deliberately written without a track?). This is the definition of technical debt that will surface again the moment anyone tries to add a fourth track, a new overlay type, or automated position sizing.

2. **Incremental dual-write is feasible for the live path; a one-time backfill is still required for history.**  
   - New rows written after the fix can go under `STRATEGY_OVERLAY` (or a new `overlay_type` column) with no schema change beyond a nullable `track_namespace` column that is left NULL for the independent overlay book.  
   - Pre-S2r rows (2026-08-04 and earlier) were correctly filed under a track’s `strategy_name`. A small migration script (`scripts/dev/migrate_overlay_pnl_to_independent.py`) can either:  
     – backfill a synthetic `overlay_type` + set `strategy_name = STRATEGY_OVERLAY` for those rows, or  
     – leave them as-is and document a “legacy” query path that the digest falls back to for dates ≤ S2r cutover.  
   Because the daily digest is consumed by a single human, the discontinuity is acceptable if clearly dated in the Telegram message (“Pre-2026-07-29 rows shown under original track; post-S2r rows shown under independent overlay book”). No hard migration of the entire table is required.

3. **A read-time join (the “third option”) adds complexity without benefit.**  
   It would require either (a) keeping the old keyed rows and joining at query time, or (b) a new mapping table. Both approaches re-create the attribution problem at runtime and make the `paper_overlay_pnl_snapshots` table harder to reason about. Aligning the write model and the read model (Position B) is cleaner.

4. **Single-operator audience argues for Position B, not against it.**  
   The daily digest is the primary monitoring surface. When the data model and the report match, the operator sees one consistent story (“NiftyBees vs the independent overlay book”). Any re-attribution logic (Position A) will eventually produce surprising numbers that the operator has to mentally discount. Consistency reduces cognitive load for the human who actually reads the output every day.

### Concrete next steps (data-architecture view)

- Add an optional `track_namespace` column (nullable) to `paper_overlay_pnl_snapshots` and the corresponding `OverlayPnLSnapshot` dataclass.  
- Change `_compute_overlay_pnl_snapshots` and `_build_recovery_digest` to read from `STRATEGY_OVERLAY` (and fall back to the legacy track-scoped rows only for dates before the S2r cutover).  
- Update `PaperStore.record_overlay_pnl_snapshot` / `get_overlay_pnl_snapshots` to accept an optional `track_namespace` filter (default `None` → independent overlay book).  
- One migration script + a note in DECISIONS.md dated today.  
- No change to `generate_track_snapshot` itself—overlay P&L is no longer its concern.

This keeps the storage layer simple (one strategy_name for the overlay book) while preserving historical queryability. It is the smallest change that respects the S2r architectural boundary.

### deepseek/deepseek-r1-0528


I'll analyze the BUG-028 overlay reporting issue and provide council recommendations based on the project context and architectural constraints.

### Analysis of Options
**Position A (Re-attribute)**
- 👍 Preserves current report format with minimal changes
- 👎 Violates S2r's core decoupling principle by reintroducing track dependence
- 👎 Creates ambiguous attribution logic (triple-counting vs arbitrary assignment)
- 👎 Maintains architectural inconsistency between entry and reporting layers

**Position B (Decouple pipeline)**
- 👍 Aligns reporting with actual architecture post-S2r
- 👍 Resolves attribution ambiguity at its source
- 👎 Requires significant rework (multiple files, schema changes)
- 👎 Needs migration strategy for pre-S2r data discontinuity

### Council Recommendations
1. **Architectural Alignment**  
Position B is architecturally superior. S2r deliberately decoupled overlays from tracks for operational flexibility. Reintroducing coupling in reporting would create a "schizophrenic" system where entry/management is decoupled but reporting is coupled. This violates the principle of single source of truth.

2. **Incremental Implementation**  
The pipeline rework can be implemented incrementally:
- Phase 1: Update `paper_overlay_pnl_snapshots` schema to use `STRATEGY_OVERLAY` exclusively
- Phase 2: Modify `generate_track_snapshot()` to ignore overlay legs (already done post-S2r)
- Phase 3: Rebuild `_compute_overlay_pnl_snapshots()` to source exclusively from `STRATEGY_OVERLAY`
- Phase 4: Refactor `_build_recovery_digest()` to use the new independent overlay stream

3. **Migration Strategy**  
Handle the schema discontinuity with:
```python
# In paper_3track_snapshot.py
def _migrate_leg_snapshot(snapshot):
    if snapshot.strategy_name in BASE_TRACKS and snapshot.leg_role in OVERLAY_ROLES:
        return snapshot._replace(strategy_name=STRATEGY_OVERLAY)
    return snapshot
```
Run this transformation during database initialization. Pre-S2r data retains its original strategy_name but gets reinterpreted in the new context.

4. **Operator Experience**  
The daily digest should evolve to show:
```
🛡️ NiftyShield Protection Performance
-------------------------------------
NiftyBees: +1.2% (+₹5,600)
Overlay Book (all tracks): +0.8% (+₹3,200)
Net Protected: +0.4% (+₹2,400)
```
This maintains simplicity while honoring the architectural reality.

### Verdict
**Adopt Position B (decoupled pipeline)** with the migration strategy above. This preserves architectural integrity while delivering a coherent operator experience. The extra development effort is justified by:
1. Eliminating persistent data inconsistencies
2. Honoring the S2r design intent
3. Creating a foundation for future strategy expansion
4. Maintaining clear separation of concerns

Implementation should begin immediately given the reporting blackout since S2r. The schema migration can be completed within the current sprint.

## Aggregate Rankings (Stage 2 Peer Review)

- openai/gpt-5.6-sol: avg rank 1.0 (4 votes)
- google/gemini-3.1-pro-preview: avg rank 2.0 (4 votes)
- x-ai/grok-4.3: avg rank 3.25 (4 votes)
- deepseek/deepseek-r1-0528: avg rank 3.75 (4 votes)

---

## Prompt Sent (first 3000 chars)

```
=== NIFTYSHIELD PROJECT STATE ===

# NiftyShield — Project Context

> **For AI assistants:** This file is the authoritative state of the codebase.
> Read this before writing any code. Do not rely on session summaries or chat history.
> Repo: https://github.com/archeranimesh/NiftyShield

**Related files:** [MISSION.md](MISSION.md) — immutable mission + grounding principles | [DECISIONS.md](DECISIONS.md) | [REFERENCES.md](REFERENCES.md) | [TODOS.md](TODOS.md) | [PLANNER.md](PLANNER.md) | [BACKTEST_PLAN.md](BACKTEST_PLAN.md) — Phase 0 active tasks only (~300 lines) | [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md) — Phase 1+ tasks (load only after Phase 0.8 gate) | [LITERATURE.md](LITERATURE.md) — concept reference (Kelly, Sharpe, meta-labeling) | [LOGGING.md](LOGGING.md) — logging standard | [docs/plan/](docs/plan/) — one story file per task | [INSTRUCTION.md](INSTRUCTION.md)
---

## Current State (as of 2026-05-25)

### What Exists (committed and working)

Full file-level module tree: **[CONTEXT_TREE.md](CONTEXT_TREE.md)**
Load that file when adding new modules or doing a full structural survey.
Key top-level packages: `src/auth`, `src/client`, `src/models`, `src/portfolio`, `src/paper`, `src/mf`, `src/dhan`, `src/nuvama`, `src/intraday`, `src/instruments`, `src/market_calendar`, `src/notifications`, `src/utils`, `src/backtest`, `src/risk`, `src/gamma`, `src/strategy`, `src/council`, `src/db.py`
`src/risk/` — portfolio-level delta risk controls. `PortfolioDelta` frozen dataclass (`src/risk/models.py`): `options_delta_lots`, `niftybees_delta_lots`, `total_delta_lots`, `warning_breached`, `cap_breached`, `as_of`. `PortfolioDeltaTracker` (`src/risk/delta_tracker.py`): `aggregate_delta(paper_positions, nifty_spot, lot_size, position_deltas=None) → PortfolioDelta`; options-only thresholds warning=0.75/cap=1.0 lots, combined thresholds warning=1.5/cap=2.0 lots; parameterised via constructor. Classification is by `PaperPosition.option_type` (not `instrument_key` substring — fixed in BUG-002/B002.3, real Upstox keys are numeric-only). If `position_deltas` (dict, `instrument_key` → signed delta-in-lots) supplies a chain-derived value for a PE/CE leg, that value is used as-is (B002.4); otherwise falls back to the approximation CE=`net_qty/lot_size`, PE=`-net_qty/lot_size` with a logged WARNING (never silent — module stays pure/zero-I/O per council ruling `docs/council/2026-07-02_paper-delta-source-architecture.md`, caller is responsible for resolving the map). FUT = `net_qty/lot_size`; NiftyBees = `qty×avg_cost/(spot×lot_size)`; unresolved `option_type` → WARNING + zero delta (never misclassified as a future). `check_entry_allowed` (`src/risk/entry_gate.py`): protective entries always allowed; cap → block; warning → allow with message. 33 unit tests in `tests/unit/risk/test_delta_tracker.py` + hypothesis property tests in `tests/unit/risk/test_delta_hypothesis.py`.
`src/gamma/` — scaffolding, data models (`GammaChainSnapshot` and `GammaWatchlistEntry` fr...
```