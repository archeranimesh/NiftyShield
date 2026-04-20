# 0.3 — June 2026 Finideas roll cycle

**Status:** NOT STARTED
**Owner:** Animesh (execution decisions) + Cowork (pre-roll validation via agent)
**Phase:** 0
**Blocks:** 0.8 (Phase 0 gate)
**Blocked by:** —
**Estimated effort:** S (≤1 day of active work, but fixed calendar deadline)
**Literature:** none
**HARD DEADLINE: 2026-06-30**

## Problem statement

`NIFTY_JUN_CE` and `NIFTY_JUN_PE` legs in the `finideas_ilts` strategy expire on the last Tuesday of June 2026 (2026-06-30 per `REFERENCES.md`). Finideas will issue roll instructions before expiry; the system must execute them cleanly via `scripts/roll_leg.py` and produce no orphaned positions or broken P&L reporting.

This is the first production use of `roll_leg.py` since it was built in 2026-04-15. `record_roll()` was tested in unit tests but never run against the live DB. Latent bugs in atomicity, UNIQUE constraint handling, or position aggregation will surface here.

Missing this roll = a real options expiry event with real P&L consequence. There is no dry-run for the calendar.

## Acceptance criteria

- [ ] **No later than 2026-06-23** (1 week before expiry): `roll-validator` agent invoked. Agent reports on (a) current net position for each expiring leg per `trades` table, (b) integrity of `Trade` model for the planned roll, (c) DB atomicity test — simulated rollback on second insert failure leaves DB in original state.
- [ ] **Upon receipt of Finideas roll instructions**: both legs' new strikes, quantities, and expiries recorded in a session log entry in `TODOS.md` before execution.
- [ ] `roll_leg.py --dry-run` run for each leg. Output verified by human — quantity, strike, direction, key all match Finideas instructions.
- [ ] `roll_leg.py` run without `--dry-run`. Both Trade rows inserted in a single transaction per `record_roll()` atomicity guarantee.
- [ ] `daily_snapshot.py` run same day (either at 3:45 PM cron or manually). P&L continues uninterrupted. New JUL/SEP leg prices reflected in mark-to-market.
- [ ] `get_position()` for both old and new legs returns expected values (old leg: 0 net, new leg: full quantity at entry price).
- [ ] Session log entry appended in `TODOS.md` with: date, old instrument keys, new instrument keys, quantities, any anomalies, commit SHA of any fix commits.

## Definition of Done

- [ ] Roll executed successfully before 2026-06-30 market close.
- [ ] Post-roll snapshot runs cleanly for at least one subsequent trading day.
- [ ] If bugs discovered: fix committed in a separate `fix(...)` commit with tests regression-guarding the specific bug. Do not bundle bug fixes into unrelated work.
- [ ] `REFERENCES.md` updated with new instrument keys for JUL/SEP legs.
- [ ] `CONTEXT.md` "Live Data" section updated with roll date and outcome.
- [ ] `BACKTEST_PLAN.md` task 0.3 checkbox ticked with commit SHA of the roll execution trade records.

## Technical notes

- **Finideas may issue roll as a single instruction for both legs, or two separate instructions.** Treat each leg as an independent roll transaction.
- The `--old-action BUY` convention: BUY to cover a short (most option legs in ILTS are short puts/calls paying premium out). SELL to exit a long. Check the direction of each leg before composing the command.
- Commands follow the format documented in `README.md` under "Roll an option leg":
  ```bash
  python -m scripts.roll_leg \
    --strategy finideas_ilts \
    --date 2026-06-30 \
    --old-leg NIFTY_JUN_CE \
    --old-key "NSE_FO|37799" \
    --old-action SELL \
    --old-qty 65 \
    --old-price <actual-exit-price> \
    --new-leg NIFTY_SEP_CE \
    --new-key "NSE_FO|<new-token>" \
    --new-action BUY \
    --new-qty 65 \
    --new-price <actual-entry-price> \
    --notes "JUN→SEP expiry roll per Finideas"
  ```
- Actual exit and entry prices: take the fill price from the broker's execution confirmation, not the pre-trade LTP. Reconcile after execution.
- If dry-run output looks wrong in any way — stop. Do not run without --dry-run. Find the bug or ask for clarification first.
- Verification query after the roll:
  ```sql
  SELECT leg_role, SUM(CASE WHEN action='BUY' THEN qty ELSE -qty END) AS net_qty
  FROM trades WHERE strategy_name='finideas_ilts' GROUP BY leg_role;
  ```

## Non-goals

- Does NOT change strategy logic. Finideas decides strikes and quantities; we execute.
- Does NOT redesign `roll_leg.py` — bugs fixed in place.
- Does NOT add new instruments to `strategies/finideas/ilts.py`. Strategy leg definitions are conceptual roles; physical roll is captured in `trades` via the overlay pattern.

## Follow-up work

- Post-roll, add a short post-mortem entry to `TODOS.md` noting any operational friction. Patterns across multiple rolls (by Dec 2026 there will be 2-3) inform future `roll_leg.py` refinements.
- If Finideas sends instructions for both legs as a single "roll the ILTS" instruction, consider adding a higher-level `roll_strategy.py` CLI in Phase 2+ that takes multiple leg pairs atomically.

---

## Session log

_(append-only, dated entries)_
