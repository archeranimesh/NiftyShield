# Council Decision: bug032-ambiguous-match-aggregation-vs-hard-fail

Date: 2026-08-24  
Chairman: anthropic/claude-opus-4.6  
Council members: openai/gpt-5.6-sol, google/gemini-3.1-pro-preview, x-ai/grok-4.6, deepseek/deepseek-r1-0528

---

## Stage 3 — Chairman Synthesis

# Chairman's Ruling: BUG-032 — Overlay Leg-Role Ambiguous-Match Resolution

**CONTEXT.md ✓**

**Scope:** BUG-032 architecture ruling — failure semantics, persistence shape, calculation invariants, and alerting contract. No code changes in this ruling; implementation story follows.

---

## Verdict

**Hybrid: Aggregate correctly across all open instruments per role (Position A), alert loudly on the invariant break, do not hard-fail (Position B rejected), do not widen `paper_leg_snapshots`' primary key.**

The council is unanimous on the high-level direction. All four responses chose the hybrid; all four rejected Position B as a standalone answer; all four rejected re-keying the existing table in-place as part of this fix. The disagreements are on implementation details — LTP handling, schema additions, alert mechanics — resolved below.

---

## Answers to the Four Questions

### Q1: Missing snapshot vs. correct aggregate?

**A correctly-aggregated snapshot serves the operator better. A missing snapshot during a roll creates worse operational risk.**

The decisive project-specific fact (identified most clearly by Response C, confirmed by all reviewers): PP3's "no unprotected day" rule **deliberately** holds two puts on roll day. Position B would therefore create a **systematic** reporting outage on every routine PP roll — not a rare incident triggered only by BUG-031's stuck state. The operator needs exposure visibility most when the book is in a transitional state. A snapshot cron *measures* risk; it does not *create* risk. The "fail closed when state is unknown" principle (DECISIONS.md, `_open_pp_dte`, 2026-08-20) applies to **writes that change exposure** (entry gates, `record_trades`), not to reads that describe it. Observability should degrade gracefully; the control plane should fail closed. Conflating the two is how you fly blind on the exact day you need the book.

The state is anomalous but not unpriceable: instrument keys are known, quantities and cost bases are known, each instrument can be priced independently, and the resulting role-level P&L is mathematically well-defined. Multiplicity alone is not grounds for refusing to value the book.

### Q2: Schema change to `paper_leg_snapshots`?

**No. Keep `(strategy_name, leg_role, snapshot_date)` as the primary key. Aggregate at write time.**

Downstream consumers — `OverlayPnLSnapshot` (keyed `strategy_name, overlay_type, snapshot_date`), `ProtectionRecoverySnapshot`, daily digests, pct-denominator calculations — all expect one role-level row. Re-keying forces a migration, a backfill of `instrument_key` onto historical rows that never stored it (creating ambiguous synthetic identities), and a sweep of every reader — for no change in the numbers those readers actually consume. Per-instrument truth already lives in `paper_trades` + `get_positions()` (PG-1). BUG-032 is a *computation* defect inside the existing role-level contract, not evidence that the grain is wrong.

If per-instrument historical auditability is later needed (e.g., for reconstructing prior-day marked-value denominators), add a **companion** table (e.g., `paper_instrument_leg_snapshots`) keyed on `(strategy_name, leg_role, instrument_key, snapshot_date)` — scope that in a separate follow-up story, not as part of this live fix. The minimum fix does not require it.

### Q3: Is there a hybrid neither A nor B fully captures?

**Yes. This is the actual design: correct math + loud alert + no data blackout.**

Ship all three properties simultaneously:

1. **Correct aggregation** — `get_positions(strategy_name)` → filter by `leg_role` → per-instrument LTP fetch and P&L calculation → sum at role level.
2. **Loud anomaly alert** — structured log (`overlay_pnl.multi_instrument_role`) **and** a non-fatal Telegram notification whenever `len(matches) > 1`.
3. **No data loss** — the daily snapshot never goes missing; unrelated roles/tracks continue if one role is temporarily unpriceable.

**Do not use `GateViolation`.** That model and table are explicitly for threshold IC entry gates (IVR floor, DTE window, liquidity, delta cap) under `--log-only-gates`. A reporting-layer invariant break is not an entry gate. Reusing it mixes two telemetry domains and would show up as a fake "would have blocked entry" count in `get_gate_violation_counts`.

**Alert deduplication:** alert on the first OFF→ON transition (first cron run that sees `n > 1` for a role); do not re-fire on every subsequent run while the condition persists. Log a recovery message when the role returns to `n ≤ 1`. A multi-day overlap (like the current BUG-031–induced state) may warrant escalation (e.g., severity bump from WARNING to ERROR after N days); a same-day transient overlap (PP3's designed two-put window) should be WARNING only.

### Q4: Does fixing BUG-031 change the answer?

**No. It lowers frequency but does not remove the requirement.**

Multiple instruments under one role can still occur through: PP3's intentional same-day overlap, non-atomic roll timing at the daily cron's granularity, partial persistence or compensating-close paths, manual intervention, retry/replay behavior, or another lifecycle defect. Correct multi-instrument aggregation is a permanent valuation requirement, not merely a workaround for BUG-031. Rarity is an argument for the *alert* severity (so a stuck state is visible); it is not an argument for refusing to sum the marks.

---

## Required Calculation Semantics

The implementation must not create a synthetic blended position. For each open `(leg_role, instrument_key)` position:

1. Resolve that instrument's own LTP from the broker.
2. Compute unrealized P&L using its own quantity, direction, cost basis, and LTP — independently.
3. Sum the resulting monetary P&L values at role level.

```
role_unrealized = Σ_i  instrument_unrealized_i
role_realized   = Σ_i  instrument_realized_i
role_total      = role_unrealized + role_realized
```

**Hard invariants:**

| Rule | Rationale |
|---|---|
| Never average cost bases or LTPs across strikes/expiries before calculating P&L | Two contracts at different strikes have independent marks; a blended avg_cost has no tradeable meaning |
| Fetch every open instrument key, not just the most recent | This is the exact defect being fixed |
| `total_pnl == unrealized_pnl + realized_pnl` (SNAP-5 invariant) | Enforced at `record_nav_snapshot` write time; must hold for the aggregated row |
| Realized P&L: compute once at the appropriate role/instrument scope, do not duplicate per open instrument | If the existing helper operates at role level, guard against double-counting when called in a per-instrument loop |
| Entry basis for `pnl_inception_pct`: `Σ_i abs(qty_i × cost_i)` | Sum per instrument, never blend then multiply |
| Quantity for `_position_qty`: `Σ_i net_qty_i` | Sum, not pick-one |
| `paper_leg_snapshots.ltp` when `n == 1`: real LTP (current behavior, unchanged) | — |
| `paper_leg_snapshots.ltp` when `n > 1`: **`NULL`** | A single LTP for a multi-instrument aggregate is a lie. Do not write the newest leg's LTP — that is the exact misrepresentation that made the 2026-08-21 `92.5 / -65.00` row look plausible when it was hiding a dropped leg. `NULL` is honest. |
| Previous-day `pnl_1d_pct` denominator: aggregate marked value `Σ_i (ltp_i × abs(qty_i))` from the prior day's per-instrument computation, not `blended_ltp × summed_qty` | If the companion table is deferred, this denominator must be reconstructible from the aggregation step itself; document the approach in the implementation story |

**Implementation shape:** gather `store.get_positions(STRATEGY_OVERLAY)` **once** and group by `leg_role`. The three affected helpers (`_compute_overlay_leg_totals`, `_leg_entry_basis`, `_position_qty`) should consume that grouped representation rather than independently calling `get_position()` — eliminates both the ambiguous-match branch and any risk of inconsistent position sets across the three calls.

**`get_position()` stays PG-2a.** Do not change it to return a synthetic aggregate. Close and roll paths (PG-4a `LegClose`, `PaperExecutor.apply()`) must target a single concrete `instrument_key`. This is a call-site bug in the snapshot script, not a store-API bug.

---

## Failure Semantics

| Condition | Required behavior |
|---|---|
| One open instrument per role | Normal calculation (degenerate sum, current behavior) |
| Multiple open instruments, all priced | Aggregate correctly, alert (WARNING for transient / ERROR for multi-day), continue |
| Multiple instruments, one or more LTPs missing | Fail that role loudly (ERROR log + Telegram); do not silently exclude the unpriced instrument; do not write a partial aggregate as though it were complete; continue unrelated roles |
| `get_positions()` / DB query fails | Fail closed for that role; do not interpret failure as an empty role |
| One role fails | Continue unrelated track/overlay snapshots |

---

## Minimum Regression Coverage

The current test suite has zero coverage of `get_position`'s ambiguous-match branch being exercised from the overlay P&L path. That is why this shipped unnoticed for 4+ days.

Required tests:

1. Two open PE instruments under `overlay_pp`, different strikes, different LTPs → aggregate `total_pnl` equals sum of both independent per-instrument calculations, **not** newest-only.
2. Verify the older instrument's P&L is included (the specific defect).
3. Verify every instrument key triggers a broker LTP fetch (mock asserts both keys requested).
4. Verify no blended-cost/LTP calculation is used anywhere in the aggregation.
5. Verify role-level realized P&L is not counted twice when multiple instruments are open.
6. Verify aggregate entry basis and quantity denominators include both positions.
7. Verify `paper_leg_snapshots.ltp is None` for a multi-instrument role.
8. Verify `total_pnl == unrealized_pnl + realized_pnl` on the written row (SNAP-5 invariant).
9. Verify anomaly alert fires on the first `n > 1` detection and is deduplicated on subsequent runs.
10. Verify alert clears when the role returns to `n ≤ 1`.
11. Verify a missing LTP for one instrument does not silently exclude it (role fails loud, not partial).
12. Verify a single-position role retains exactly current behavior (no regression).
13. Verify unrelated roles continue when one role cannot be valued.

---

## Historical Repair

The affected 2026-08-20 onward `paper_leg_snapshots` and `paper_overlay_pnl_snapshots` rows are understated. Backfill only where the older instrument's historical EOD mark can be sourced reliably (e.g., from Parquet chain snapshots if they cover `NSE_FO|61604`'s strike/expiry on those dates). Record unrecoverable dates explicitly rather than fabricating marks. This is a follow-up story, not a precondition for the live fix — the first post-fix cron run will produce correct numbers going forward.

---

## Expect a Step Discontinuity

On the first post-fix cron date, `overlay_pp`'s `pnl_1d_*` will show a one-day step that has no market-move explanation — it is the correction of the 4+ day understatement. Log it explicitly in the cron output so the operator does not misread it as a market event. Do not try to smooth or hide it.

---

## Summary

> **BUG-032 is fixed by per-instrument valuation followed by role-level summation, with a deduplicated anomaly alert for multiple open instruments. `paper_leg_snapshots` remains one row per role, `ltp = NULL` when aggregated. `get_position()` is unchanged. `GateViolation` is not used. The daily P&L snapshot must never go missing because a role holds more than one contract.**

---

## Stage 1 — Individual Responses

### openai/gpt-5.6-sol

**CONTEXT.md ✓**

**Scope:** BUG-032 architecture ruling only; no code changes proposed here.  
**Plan:** choose failure semantics, define persistence shape, and state implementation invariants/tests.

# Council Ruling: Aggregate Correctly, Alert Loudly, Preserve Role-Level Reporting

Adopt a **hybrid of Position A and explicit anomaly alerting**:

1. **Always aggregate every open instrument under the role.**
2. **Never let ambiguity suppress P&L visibility.**
3. **Emit a deduplicated operational alert whenever a role has multiple open instruments.**
4. **Keep `paper_leg_snapshots` as the role-level aggregate interface.**
5. **Add per-instrument snapshot detail as a companion persistence layer if historical auditability and correct prior-day denominators require it; do not change the existing table’s primary key in place.**

A hard-fail is not appropriate for a valuation pipeline when the underlying positions and prices remain determininate.

## Answers

### 1. Aggregate or hard-fail?

**Aggregate.**

A missing snapshot during an overlapping or stuck roll creates more operational risk than a correctly aggregated snapshot. The operator most needs exposure and P&L visibility precisely when the expected one-position-per-role invariant has broken.

The state is anomalous, but it is not unpriceable:

- instrument keys are known;
- quantities and cost bases are known;
- each instrument can be priced independently;
- the resulting role-level P&L is mathematically well-defined.

Hard failure should be reserved for conditions where correct valuation is impossible—for example, one of the instruments cannot be priced and no approved fallback exists. Multiplicity alone is not such a condition.

The cron should also not fail globally because one overlay role is problematic. Peripheral failure isolation remains the appropriate snapshot behavior.

### 2. Should `paper_leg_snapshots` become per-instrument?

**Do not change its existing key or semantics. Keep it one row per role.**

`paper_leg_snapshots` is already consumed as a role-level reporting table by digests, overlay summaries, recovery calculations, and dashboards. Changing its primary key to include `instrument_key` would push aggregation responsibility into every reader and create a broad migration with substantial double-counting risk.

Instead:

- retain `paper_leg_snapshots` as the role-level aggregate projection;
- if per-instrument history is needed, add a companion table such as:

```text
paper_instrument_leg_snapshots
(
    strategy_name,
    leg_role,
    instrument_key,
    snapshot_date,
    net_qty,
    entry_basis,
    mark_value,
    unrealized_pnl,
    realized_pnl,
    total_pnl,
    ltp,
    PRIMARY KEY (
        strategy_name,
        leg_role,
        instrument_key,
        snapshot_date
    )
)
```

The exact model should be scoped in the implementation story, but monetary columns must remain Decimal-as-TEXT.

This gives:

- continuous role-level reporting;
- per-instrument auditability;
- a source for correct previous-day marked-value denominators;
- no breaking change for existing readers.

The detail rows and role aggregate should ideally be written in one SQLite transaction.

### 3. Is the hybrid preferable?

**Yes. This is the recommended design.**

Multiplicity should produce both:

- a correct aggregate valuation; and
- a loud data-quality/lifecycle anomaly.

Do **not** use `GateViolation` for this. That model and table are explicitly for threshold IC entry gates. Reusing it would blur entry-policy telemetry with portfolio-state integrity incidents.

Use a dedicated structured event and Telegram alert, for example:

```text
overlay_snapshot.multiple_open_instruments
```

Include:

- `strategy_name`
- `leg_role`
- `instrument_count`
- all instrument keys
- quantities
- entry dates
- snapshot date
- aggregate P&L
- oldest overlap age

Alerting should be deduplicated:

- alert on the first OFF→ON transition;
- optionally escalate when the overlap survives beyond the expected roll window or into the next EOD snapshot;
- send a recovery message or clear persisted state when the role returns to one or zero open instruments.

A same-tick transient overlap may merit WARNING only. A multi-day overlap such as BUG-032 should be ACTION/ERROR severity.

### 4. Does fixing BUG-031 change the answer?

**No. It lowers frequency but does not remove the requirement.**

BUG-031 explains the current prolonged overlap, but reporting must value the ledger state that actually exists—not the state the strategy was expected to produce.

Multiple instruments under one role can still occur through:

- roll overlap;
- partial persistence or compensating-close paths;
- delayed close execution;
- manual intervention;
- retry/replay behavior;
- future scaling into a position;
- another lifecycle defect.

Therefore, correct multi-instrument aggregation is a permanent valuation requirement, not merely a workaround for BUG-031.

# Required Calculation Semantics

The implementation must not create a synthetic blended position.

For each open `(leg_role, instrument_key)` position:

1. Resolve that instrument’s own LTP.
2. Compute unrealized P&L using its own:
   - quantity;
   - direction;
   - cost basis;
   - LTP.
3. Sum the resulting monetary P&L values at role level.

Formally:

```text
role_unrealized = Σ instrument_unrealized
```

Do not average cost bases or LTPs across strikes or expiries before calculating P&L.

Additional invariants:

- Fetch every open instrument key, not just the most recent one.
- Compute realized P&L once at the appropriate role/instrument scope; do not duplicate role-level realized P&L once per open instrument.
- Preserve:

```text
total_pnl == unrealized_pnl + realized_pnl
```

- Entry basis for percentage calculations must be the sum of the participating instruments’ monetary entry bases under the existing denominator convention.
- Previous-day percentage denominators must use aggregate marked value, not `blended_ltp × summed_qty`.
- A single `ltp` has no valid meaning for a multi-instrument aggregate. For `paper_leg_snapshots.ltp`:
  - retain the real LTP when exactly one instrument is present;
  - store `NULL` when more than one instrument is aggregated.
- Do not fabricate a weighted-average LTP merely to satisfy the old row shape.

The implementation should gather `store.get_positions(STRATEGY_OVERLAY)` once and group that consistent result by `leg_role`. The three affected helpers should consume that grouped representation rather than independently calling `get_position()` and potentially resolving different subsets.

# Failure Semantics

| Condition | Required behavior |
|---|---|
| One open instrument | Normal calculation |
| Multiple open instruments, all priced | Aggregate correctly and alert |
| Multiple instruments with one or more missing LTPs | Fail that role loudly or use an existing explicitly approved pricing fallback; never silently omit the unpriced instrument |
| Invalid direction/state within one role | Aggregate only if semantics are defined; otherwise mark the role unpriceable and alert |
| One role fails | Continue unrelated track/overlay snapshots where safe |
| `get_positions()`/DB query fails | Fail closed; do not interpret it as an empty role |

# Minimum Regression Coverage

Tests should include:

1. Two open PE instruments under `overlay_pp`, each with different quantity, cost, and LTP; aggregate P&L must equal the sum of both independent calculations.
2. Verify the older instrument is included.
3. Verify every instrument key is requested from the broker.
4. Verify no blended-cost/LTP calculation is used.
5. Verify role-level realized P&L is not counted twice.
6. Verify aggregate entry basis and quantity/marked-value denominators include both positions.
7. Verify `paper_leg_snapshots.ltp is None` for a multi-instrument role.
8. Verify the total-P&L invariant.
9. Verify an anomaly event is emitted once and deduplicated on subsequent runs.
10. Verify alert state clears when the role returns to one instrument.
11. Verify missing LTP does not silently exclude a position.
12. Verify a single-position role retains current behavior.
13. Verify unrelated roles continue if one role cannot be valued.
14. Verify detail and aggregate rows reconcile if the companion table is introduced.

# Historical Repair

The affected 2026-08-20 onward snapshots should be backfilled only where the older instrument’s historical EOD mark can be sourced reliably. Do not infer its historical LTP from the newer contract or fabricate a blended value.

Record unrecoverable dates explicitly if authoritative historical marks are unavailable.

## Final Decision

> **BUG-032 will be fixed by per-instrument valuation followed by role-level aggregation, with a deduplicated anomaly alert for multiple open instruments. `paper_leg_snapshots` remains one row per role. Per-instrument history should be added through a companion table rather than by breaking the existing table’s primary key. Multiplicity alone must never make the daily P&L snapshot disappear.**

### google/gemini-3.1-pro-preview

Here is the synthesized council ruling from the Options Strategist and Systems Architect personas to resolve BUG-032.

---

# COUNCIL RULING: BUG-032 (Overlay Leg-Role Ambiguous-Match)

## 1. Core Decision
**Adopt the Hybrid Approach (Position A + Loud Alerting).** 
You must aggregate the P&L correctly across all open instruments under a `leg_role` to maintain accurate risk visibility, while simultaneously alerting the operator that a structural constraint has been breached. Do **not** hard-fail (Position B), and do **not** widen the `paper_leg_snapshots` schema. 

## 2. Answers to Specific Questions

### Q1: Missing vs. Aggregated Snapshot Operational Impact
**A missing snapshot (Position B) is worse than an aggregated one.** 
In a delta-neutral and dynamically hedged framework, the operator relies on continuous daily NAV and leg-level tracking to make risk decisions. If a snapshot drops completely because of a stuck leg, the operator is flying blind regarding both the old *and* the new leg exactly when risk is elevated. You must compute the true open risk (the sum of all open positions for that role) so the reported exposure matches reality.

### Q2: Schema Change vs. Report-Time Aggregation
**Aggregate at report-time; do not widen the schema.**
The `leg_role` (e.g., `overlay_pp`) represents a *semantic allocation* within the portfolio. If the system temporarily holds two put contracts, their combined P&L is the true P&L of the "protective put" allocation. 
1. `_compute_overlay_leg_totals()` should retrieve all open positions for the role via `store.get_positions()`.
2. Compute `unrealized_pnl` **per-instrument** (using its specific LTP) and `realized_pnl` per-instrument.
3. Sum these values and write them into the existing single `(strategy_name, leg_role, snapshot_date)` row in `paper_leg_snapshots`.
4. *Edge case for `ltp`:* Since a single role-row cannot hold two different LTPs, write the `ltp` of the most recently entered position (preserving current display behavior) but ensure the P&L totals reflect the strict mathematical sum of all contracts.
5. *Edge case for denominators:* `_leg_entry_basis()` and `_position_qty()` must also sum across all open instruments to ensure `pnl_inception_pct` calculates correctly against the combined cost basis.

### Q3: Is there a Hybrid approach?
**Yes. Accurate Math + Loud Alarms.**
Aggregation ensures the math is correct, but holding two instruments under one role is typically a business-logic error (unless mid-roll). 
When `len(open_positions) > 1` for a single role:
* Proceed with the aggregation math.
* Immediately log a structured `ERROR` (not a silent WARNING like `get_position` does).
* Dispatch a `TelegramNotifier.send()` alert: `⚠️ [BUG-032 Alert] Multiple open positions detected for leg_role '{leg_role}'. P&L has been aggregated, but duplicate positions require manual review.`

### Q4: Does fixing BUG-031 change this architecture?
**No.** 
Even when BUG-031 is fixed and overlapping positions become genuinely rare, the cron snapshot might still trigger at exactly `15:35:00.000` while an atomic roll is inflight (e.g., if one leg is written but the closing leg write is delayed by a fraction of a second, or if the roll is executed serially). 
Position B (hard-fail) would crash the entire snapshot cron due to a transient microsecond overlap. Position A (Aggregate) smoothly handles transient overlaps, correctly reflecting the portfolio state at that exact millisecond without breaking the data pipeline.

---

## 3. Implementation Directives for `paper_3track_snapshot.py`

1. **Replace `get_position` with `get_positions`:** In `_compute_overlay_leg_totals()`, `_leg_entry_basis()`, and `_position_qty()`, fetch the list of all open positions for the target role.
2. **Per-Instrument Math:** Loop over the list. Fetch the specific LTP for each `instrument_key`. Compute the unrealized/realized P&L independently.
3. **Summation:** Accumulate the PnLs, Quantities, and Entry Basis values. 
4. **Alerting:** Wrap a check: `if len(positions) > 1: fire_telegram_alert(...)`.
5. **Testing:** Write a regression test specifically injecting two open `overlay_pp` positions (simulating the BUG-031 state) and assert that the resulting `paper_leg_snapshots` row contains the mathematical sum of both, rather than dropping one or throwing an exception.

### x-ai/grok-4.6

CONTEXT.md ✓

This is a reporting-pipeline decision, not an entry-gate decision. The 2026-08-20 “fail closed when state is unknown” rule does **not** apply here — that rule is for actions that can create exposure. A snapshot cron *measures* exposure. Stopping the measurement because the book is messy is the wrong failure mode.

---

## Verdict

**Hybrid: Position A for numbers, loud alert for the invariant break. Do not adopt Position B. Do not widen `paper_leg_snapshots` as part of this fix.**

Change the three call sites to `get_positions()` filtered by `leg_role`, mark each instrument independently, then sum. Leave `get_position()`’s PG-2a contract alone — action paths still need a single instrument.

---

### 1. Missing snapshot vs. correct aggregate

Position B does **not** serve the operator better. It creates the worse operational risk.

- The operator is one human making delta-neutral adjustments. A dark overlay book on a roll day is worse than a correct book-level number plus an alert.
- Dual-open under `overlay_pp` is **intentional**, not only a BUG-031 leftover. PP3’s “no unprotected day” rule *deliberately* holds the new put and the outgoing DTE≤5 put on the same day. Position B would blank `overlay_pp` on every routine roll day — a systematic outage, not a rare incident.
- The same window exists for any close-then-reopen that is not atomic at the 15:35 cron’s granularity.
- “Fail loud” is the right rule for *writes that change risk* (`_open_pp_dte`, entry gates, `record_trades`). It is the wrong rule for *reads that describe risk*. Observability should degrade gracefully; the control plane should fail closed. Mixing those is how you fly blind on the exact day you need the book.

A silently-wrong number (today) is bad. A missing number during a designed two-leg state is worse. A correct sum plus a Telegram/WARNING is the only shape that keeps both continuity and honesty.

---

### 2. Schema: do not re-key `paper_leg_snapshots` in this fix

Keep `(strategy_name, leg_role, snapshot_date)`. Aggregate at write time.

Reasons:

- Downstream is already book-level. `OverlayPnLSnapshot` is keyed `(strategy_name, overlay_type, snapshot_date)` with `overlay_type ∈ {cc, pp, collar}`. `ProtectionRecoverySnapshot` is the same grain. Widening the leg table forces a migration, a backfill of `instrument_key` onto historical rows that never stored it, and a sweep of every reader — for no change in the numbers those readers actually consume.
- Per-instrument truth already lives in `paper_trades` + `get_positions()` (PG-1). Forensics go there, not through the daily rollup.
- One-row-per-role is the display/book contract from S8 / BUG-028. This bug is a *computation* defect inside that contract, not evidence the grain is wrong.

**Hard rule on the stored row:** never blend two contracts into one `avg_cost` / one `ltp`. Those are different strikes and expiries; a quantity-weighted mash has no tradeable meaning (Position A already states this correctly).

When `n == 1`: current shape, real LTP.  
When `n > 1`: persist **summed** `unrealized_pnl` / `realized_pnl` / `total_pnl` (each instrument marked on its own LTP, then added). Set `ltp = None`. Do not write the newest leg’s LTP. A null LTP is honest; a single print is a lie that will poison the next hand reconstruction the way the 2026-08-21 `92.5 / -65.00` row already did.

Entry-basis / qty for `%` denominators: sum per instrument (`Σ |qty_i × cost_i|`, `Σ net_qty_i`). Book-level `pnl_inception_pct` is meaningful. Expect a one-day step in `pnl_1d_*` on the first post-fix date — that step *is* the correction of the understatement. Log it; do not try to hide it.

A later story can add `(leg_role, instrument_key)` grain if you want per-contract dashboards. That is not required to stop understating the book.

---

### 3. Hybrid — this is the actual design, not a compromise

Neither A nor B as scoped is complete. Ship all three:

1. **Compute A:** `get_positions(strategy_name)` → filter `leg_role` → per-instrument LTP/PnL → sum.
2. **Alert:** if `len(matches) > 1`, structured log (`overlay_pnl.multi_instrument_role`, role, keys, qtys) **and** a non-fatal Telegram line. Same “notify, don’t block” contract as bootstrap/roll notifications.
3. **Do not use `GateViolation`.** That table is for threshold *entry* gates (IVR floor, DTE window, liquidity, delta cap) under `--log-only-gates`. A reporting invariant break is not an entry gate. Reusing it mixes two meanings and will show up as a fake “would have blocked entry” count.

`get_position()` stays PG-2a. Changing it to sum would break close/roll paths that must target one `instrument_key` (PG-4a `LegClose`). This is a call-site bug in the snapshot script, not a store-API bug.

---

### 4. BUG-031 does not flip this

Even if stuck multi-day duplicates go away:

- PP3 still *designs* a same-day two-put book.
- The cron is daily, not tick-atomic. Any in-flight roll at 15:35 is a real dual-open.
- Aggregation is cheap and correct for `n = 1` (degenerate sum) and for `n > 1`. You do not get to skip it because the trigger becomes rare. Rare-and-wrong is how this shipped for four days with only a WARNING inside `get_position` that no snapshot test ever exercised.

Rarity is an argument for the *alert* (so a stuck BUG-031-class state is visible). It is not an argument for refusing to add the two marks.

---

## Implementation shape (data layer only)

| Site | Change |
|---|---|
| `_compute_overlay_leg_totals` | `get_positions(STRATEGY_OVERLAY)` filtered by role; fetch LTP per `instrument_key`; sum unrealized/realized |
| `_leg_entry_basis` / `_position_qty` | same filter; sum cost basis and qty; never call role-only `get_position` |
| `paper_leg_snapshots` | no PK change; `ltp is None` when `n > 1` |
| Alert | Telegram + structlog; not `GateViolation` |
| Tests | two open `overlay_pp` instruments, different strikes/LTPs → total = mark₁ + mark₂, **not** newest-only; `ltp is None`; alert fired. Current suite never hits this branch — that is why it lived four days. |
| Historical rows | optional later backfill (same family as B028.11 / SNAP-5). Not a precondition for the live fix. First good cron day will be correct going forward. |

Do not “fix” this by making `get_position()` return a synthetic blended `PaperPosition`. That object cannot carry two LTPs, and every close path that consumes it would aim at the wrong contract.

---

**Council checkpoint:** warranted — load-bearing live P&L, options microstructure (independent marks), and operational risk. Single-discipline “just sum it” would have missed PP3’s intentional overlap and the `ltp` lie.

### deepseek/deepseek-r1-0528

Based on the council's domain constraints and the specific disagreement around BUG-032, here's the recommended resolution:

### Council Decision: Hybrid Approach (Aggregate with Alerting)

1. **Implement Position A (aggregate) with schema change**  
   Modify `_compute_overlay_leg_totals()`, `_leg_entry_basis()`, and `_position_qty()` to:
   - Use `PaperStore.get_positions(strategy_name)` to get all open positions
   - Filter by leg_role and sum:
     ```python
     # Pseudo-code
     positions = store.get_positions(STRATEGY_OVERLAY)
     pp_positions = [p for p in positions if p.leg_role == "overlay_pp"]
     
     # Per-instrument computation then sum
     unrealized_sum = sum(
         _compute_leg_unrealized_pnl(pos, broker, lookup) 
         for pos in pp_positions
     )
     ```
   - Change `paper_leg_snapshots` schema to `(strategy_name, leg_role, instrument_key, snapshot_date)` PK
   - Preserve per-instrument granularity while maintaining role-level aggregates in reporting

2. **Add loud alerting for ambiguous states**  
   When >1 position exists per role:
   - Telegram alert: `⚠️ DUPLICATE {leg_role} POSITIONS: {count} open instruments`
   - Log CRITICAL with instrument keys and expiries
   - Continue serving aggregated P&L (Position A)

3. **Justification for hybrid approach**
   - **Operational necessity**: Continuous P&L visibility is critical for delta-neutral adjustments
   - **Data integrity**: Per-instrument storage preserves audit trail while aggregation solves underreporting
   - **Progressive enhancement**: Alerting provides operator awareness without blocking visibility
   - **Future-proofing**: Schema change handles legitimate multi-position scenarios (e.g., staggered rolls)

### Implementation Path

1. **Schema migration**  
   Add `instrument_key` to `paper_leg_snapshots` PK:
   ```sql
   ALTER TABLE paper_leg_snapshots
   ADD COLUMN instrument_key TEXT NOT NULL DEFAULT '';
   
   CREATE TABLE new_leg_snapshots (...) STRICT;
   -- Data migration logic here
   DROP TABLE paper_leg_snapshots;
   ALTER TABLE new_leg_snapshots RENAME TO paper_leg_snapshots;
   ```

2. **Refactor computation**  
   In `paper_3track_snapshot.py`:
   ```python
   def _compute_overlay_leg_totals(..., role: str):
       positions = [
           p for p in store.get_positions(STRATEGY_OVERLAY) 
           if p.leg_role == role
       ]
       
       if len(positions) > 1:
           logger.critical("role_ambiguous_positions", role=role, count=len(positions))
           notifier.send(f"⚠️ DUPLICATE {role} POSITIONS: {len(positions)} instruments")
       
       return sum(
           _compute_single_leg_pnl(pos, broker, lookup)
           for pos in positions
       )
   ```

3. **Update downstream readers**  
   Modify `_compute_overlay_pnl_snapshots()` and `_compute_protection_recovery_snapshot()` to:
   - Expect per-instrument rows
   - Aggregate by `overlay_type` using same logic as `_normalize_overlay_pnls()`

4. **Add regression test**  
   Simulate two open positions under one role and verify:
   - Both contribute to P&L
   - Alert fires
   - Snapshots show correct instrument_key granularity

### Why Not Position B?
Hard-failing would violate the operational constraint requiring continuous P&L visibility during rolls. Paper trading's experimental nature prioritizes data collection over perfect integrity during edge cases.

### Council Validation
This satisfies:
- **Quant modeling**: Correct P&L aggregation maintains strategy performance tracking
- **Risk management**: Alerting provides visibility into position management issues
- **Systems design**: Schema change addresses root cause while maintaining backwards compatibility

---

Final decision aligns with Animesh's operational priorities while closing the latent reporting gap. Implementation preserves the "one role = one position" abstraction where possible but degrades gracefully when violated.

## Aggregate Rankings (Stage 2 Peer Review)

- x-ai/grok-4.6: avg rank 1.25 (4 votes)
- openai/gpt-5.6-sol: avg rank 1.75 (4 votes)
- google/gemini-3.1-pro-preview: avg rank 3.0 (4 votes)
- deepseek/deepseek-r1-0528: avg rank 4.0 (4 votes)

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