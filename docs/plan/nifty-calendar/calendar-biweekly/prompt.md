
# Calendar Bi-weekly variant — prompt

> Add the bi-weekly variant on the shared core built by `calendar-monthly/`: its config, cycle policy and exit rules, its own wiring, and a full-month integration test of the handoff.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

The epic `README.md` carries the motivation. The bi-weekly is the second leg of the presenter's cycle: after the monthly exits (day 7 to 10), he deploys back-to-back bi-weeklies until the next monthly
expiry, then restarts the monthly. Entry is at about 14 DTE by skipping the current weekly: sell the expiry after next, buy wings one week beyond. Target ₹1,600/lot, max hold 7 days, exit before the
short leg is a weekly (DTE 7 or less), wings 400 put / 400 call, net vega at most about 5. Bi-weekly-only rules: a breach is acted on only by about day 3-4; on day 4-5 with no target and no breach,
spot 200 points or more from the entry short strike means close and redeploy at spot; an early target hit redeploys the same expiry pair at shorter DTE with the same max-hold date.

## Scope guard

**In bounds:**
- `BIWEEKLY` config, `BiweeklyCyclePolicy`, `BiweeklyExitRule` and a registry entry, in `src/nifty_calendar/`; tests.
- Registration of `paper_nifty_calendar_biweekly` in the daemon, entry and snapshot scripts parameterised by variant (extend the CM-7 scripts; do not fork them), payoff registration.
- A full-month offline integration test across both variants.

**Out of bounds:**
- Any change to the shell's logic for the monthly variant, to `StructureSelector` internals, or to shared message renderers beyond adding a label. If the shell needs a change to host bi-weekly, that
  is a finding: stop and amend `calendar-monthly/` first.
- Order placement, live capital, sizing, backtest.

## Design review

OCP is the test of this story: it must be possible with additive changes only (new config instance, new policy and rule classes, new registry entries, a new label). Any edit that adds an `if` / `elif`
on the variant to existing code means the monthly design is wrong; stop and report. Dependency direction and the prior-art audit are the epic `README.md`'s.

## Session-start load hints

- Epic `README.md`; `calendar-monthly/` task results (its `stories.md` CM-0 findings in particular); the combined findings file.
- `src/nifty_calendar/CLAUDE.md` (written in CM-8) and `src/strategy/CLAUDE.md`.
- `LOGGING.md` for any script change; `FORMATTING.md` for any message label.

## Task overview

CB-1 config and cycle policy (including the monthly/bi-weekly handoff) · CB-2 exit rule · CB-3 strategy registration, scripts and messages for the second variant · CB-4 full-cycle integration test and
close-out. CB-1 and CB-2 are pure and Antigravity's; CB-3 and CB-4 are Claude's.

## Definition of done

All tasks ticked with SHAs; unit suite green; on fixture dates a month runs monthly, back-to-back bi-weeklies, then monthly again with exactly one variant active per date; docs closed.

## Perspectives not covered

The two strategies run as independent ledgers, so the combined cycle P&L the presenter tracks per month is a sum across two `strategy_name`s that no existing report produces; whether that report is
wanted is Animesh's call and is not built here. The 200-point threshold is the video's single number and is not scaled with IV or spot level.
