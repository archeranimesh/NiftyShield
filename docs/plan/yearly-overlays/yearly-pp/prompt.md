# Yearly PP — prompt

> `--auto-pp --expiry-type yearly` buys one December protective put under the yearly namespace; `PPOverlayV1` rolls and re-enters at yearly tenor.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

The monthly PP routine-rolls at DTE <= 5 (`_PP_ROLL_DTE_THRESHOLD`) and crash-monetize re-entry gates on DTE >= 14. For a December put the roll is the point of the whole book (Dec 2026 -> Dec 2027),
so roll timing must come from the policy and be validated.

## Scope guard

Only PP. The roll window default is policy `roll_dte`; its final value is set by `dhan-far-expiry-chain/` FG-3, not here. No change to monthly PP.

## Design review

OCP/DIP as in `yearly-cc/`. The roll trigger is a policy field, not a branch.

## Session-start load hints

`docs/plan/yearly-overlays/README.md`, `yearly-foundation/audit.md`, `src/strategy/CLAUDE.md`, `src/paper/CLAUDE.md`, `roll_utils.py`.

## Task overview

YP-1 flag + bootstrap → YP-2 yearly roll and crash-monetize re-entry.

## Definition of done

Dry run opens a December put; a leg inside the policy roll window triggers the gap-fill roll to the next yearly expiry on fixtures; `roll-validator` clean; tests green.

## Perspectives not covered

Put-protection sizing versus the NiftyBees holding is unchanged from monthly and not re-examined for a 12-month hedge.
