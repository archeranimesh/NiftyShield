# Yearly CC — prompt

> `--auto-cc --expiry-type yearly` opens one December covered call under the yearly namespace, and `CCOverlayV1` manages it at yearly tenor.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

The monthly CC rolls every cycle. The yearly CC holds one December short call, so entry resolution, exit thresholds and re-entry must use the yearly policy and namespace from `yearly-foundation/`.

## Scope guard

Only CC. No PP or Collar code. No change to monthly CC behaviour; `--expiry-type` defaults to `monthly`. No new strategy class — a second `CCOverlayV1` instance with the yearly policy.

## Design review

OCP: the policy object carries every tenor difference; no `if expiry_type == "yearly"` in `CCOverlayV1` or the bootstrap. DIP: policy and namespace come from the registry.

## Session-start load hints

`docs/plan/yearly-overlays/README.md`, `yearly-foundation/audit.md`, `src/strategy/CLAUDE.md`, `src/paper/CLAUDE.md`.

## Task overview

YC-1 flag + bootstrap yearly entry → YC-2 yearly CC exit and re-entry behaviour.

## Definition of done

`--auto-cc --expiry-type yearly --dry-run` selects a December call under `paper_nifty_overlay_yearly` and writes nothing under the monthly namespace; yearly exits use policy values; tests green.

## Perspectives not covered

Strike choice on thin far-dated calls: until the liquidity gate (`dhan-far-expiry-chain/`) lands, the yearly CC uses the existing selector and its spread gate only.
