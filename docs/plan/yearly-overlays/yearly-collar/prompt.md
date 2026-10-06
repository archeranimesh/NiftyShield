# Yearly Collar — prompt

> `--auto-collar --expiry-type yearly` opens a December call + put pair under the yearly namespace; `CollarOverlayV1` manages both legs at yearly tenor.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

The collar is the CC and PP together; both legs must sit on the same December expiry and be managed as one unit. It depends on the two single-leg stories so their policy plumbing is reused, not
copied.

## Scope guard

Only the collar. Reuse the CC and PP policy fields; add none. Monthly collar unchanged.

## Design review

SRP: pair validation stays in `_validate_collar_pairs`; it gains an expected-expiry argument instead of a yearly branch. DIP: policy and namespace injected.

## Session-start load hints

`docs/plan/yearly-overlays/README.md`, `yearly-cc/` and `yearly-pp/` closing notes, `src/strategy/collar_entry.py`, `src/strategy/CLAUDE.md`.

## Task overview

YL-1 flag + bootstrap + same-expiry pair validation → YL-2 yearly collar exits and re-entry.

## Definition of done

Dry run opens a December call and put on the same expiry under the yearly namespace; a mismatched-expiry pair is rejected; collar tests green for both tenors.

## Perspectives not covered

Tax and margin-offset treatment of a 12-month collar versus a monthly one is not modelled.
