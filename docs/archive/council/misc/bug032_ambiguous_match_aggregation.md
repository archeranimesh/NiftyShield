# BUG-032: Overlay Leg-Role Ambiguous-Match — Aggregate vs. Hard-Fail

## System Context

NiftyShield's overlay P&L snapshot pipeline (`paper_3track_snapshot.py`'s
`_compute_overlay_leg_totals()`, `_leg_entry_basis()`, `_position_qty()`) all call
`PaperStore.get_position(strategy_name, leg_role)` with no `instrument_key`. Per
`get_position`'s PG-2a ambiguous-match resolution (`src/paper/store.py:844-911`), when more than
one open position shares a `leg_role`, the call silently picks the position with the most recent
`entry_date` and logs a WARNING — the other open position's contribution is dropped from the
return value entirely, not merged, not double-counted, just gone.

This has been live since 2026-08-20: an old `NSE_FO|61604` leg (65 lots @ 58.85, opened
2026-08-11) was never closed on roll, and a second `NSE_FO|74009` leg (130 lots @ ~92.93
blended, opened 2026-08-20/21) opened under the same `overlay_pp` role. Every `overlay_pp`
snapshot since 2026-08-20 has reflected only the newer leg — the older leg's unrealized P&L,
LTP, and quantity have contributed zero to `unrealized_pnl`, `total_pnl`,
`pnl_inception_pct`, and `pnl_1d_pct` for 4+ trading days.

BUG-031 (separately tracked) explains *why* two positions were simultaneously open — the live
monitor never saw `STRATEGY_OVERLAY` positions to close the old leg on roll. This bug is the
downstream reporting-layer gap that remains latent even once BUG-031 is fixed, since any future
non-atomic roll (close-then-reopen not atomic at the snapshot-cron's granularity) can put a
role's position count above 1 again, however briefly.

## The disagreement to resolve

**Position A (aggregate):** change the three call sites to use `PaperStore.get_positions(strategy_name)`
— already grouped by `(leg_role, instrument_key)` per PG-1, already excludes flat pairs — and
sum across every open position matching a `leg_role`. `net_qty` sums cleanly across instruments.
Unrealized P&L must be computed **per-instrument against each instrument's own LTP and then
summed** — never blended into one `avg_cost`/LTP pair, since two open contracts under one role
are different strikes/expiries with independent market prices; a quantity-weighted blend of two
different cost bases produces a number with no tradeable meaning. Cost: `paper_leg_snapshots`
is currently shaped one-row-per-role; summing multiple instruments into that row loses
per-instrument visibility unless the schema also widens to key on `(leg_role, instrument_key)`,
which every downstream reader (daily digest, pct-denominators, any dashboard) would need
updating for.

**Position B (hard-fail):** at the cron level, if `get_positions()` filtered by `leg_role`
returns more than one open position, raise `GateViolation` (or equivalent) instead of computing
anything for that role — matches REVIEW.md's "don't return None to signal failure, fail loud"
convention. Forces the duplicate to be resolved (manually, or via BUG-031's fix landing) before
P&L reporting continues for that role. Cost: the daily `overlay_pp` snapshot goes missing
entirely, not just wrong, for however long the duplicate sits open — and until BUG-031 is
actually fixed, this could recur on essentially any roll, meaning the snapshot could go dark
repeatedly rather than being a one-time event.

## Questions

1. Given the operator (a single human monitoring live paper positions) needs continuous P&L
   visibility to make delta-neutral adjustment decisions, does a loudly-missing snapshot
   (Position B) actually serve that need better than a correctly-aggregated one (Position A), or
   does zero visibility during exactly the period a roll is in flight create its own operational
   risk?
2. If Position A is correct, should `paper_leg_snapshots`' schema key on `(leg_role,
   instrument_key)` going forward — exposing per-instrument granularity to every downstream
   reader — or should the aggregation happen only at read/report time, with the stored row
   staying one-per-role holding pre-summed totals?
3. Is there a hybrid — aggregate by default (Position A) but also raise a loud WARNING/alert
   whenever the ambiguous-match branch fires, so the operator gets both continuous numbers and
   an explicit signal that a role-level assumption broke — that neither A nor B as scoped fully
   captures?
4. Does BUG-031 being fixed change the answer — i.e. if genuinely-concurrent positions under one
   role become rare/transient (seconds during an atomic roll) rather than the current multi-day
   stuck state, does that shift the cost-benefit toward Position B's stricter posture, or is the
   aggregation logic in Position A needed regardless of how rare the trigger becomes?
