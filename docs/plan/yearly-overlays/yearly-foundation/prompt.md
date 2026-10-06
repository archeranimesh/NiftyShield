# Yearly Foundation — prompt

> Everything the three yearly overlays share: an exhaustive audit, test fixtures, a tenor-policy registry, a clock-injectable expiry resolver, and the ledger namespace read-paths.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

CC, PP and Collar share one `STRATEGY_OVERLAY` namespace and hardcode monthly tenor and `date.today()`. A yearly variant cannot be added safely until tenor, clock and namespace are parameters, and
until monthly behaviour is pinned by tests. Doing this once here keeps the three variant stories small.

## Scope guard

No new strategy classes. No change to monthly behaviour or to the default `--expiry-type`. No entrypoint flag changes (those belong to `yearly-cc/`, `yearly-pp/`, `yearly-collar/`). No DB schema
change unless YF-1 proves one is needed — if it does, stop and add a `schema.md` before continuing.

## Design review

OCP: tenor differences live in a frozen `OverlayTenorPolicy` registry `dict`, never an `elif` in a bootstrap. DIP: `today` and the policy are parameters. SRP: one pure `resolve_overlay_expiry`
replaces three copies. Prior-art: YF-1 runs the `code-deduplication-and-taxonomy.md` check before any new helper is written.

## Session-start load hints

`docs/plan/yearly-overlays/README.md` (scope, verified facts). `src/strategy/CLAUDE.md`. `DB_REGISTRY.md` only if a table question arises. Graph project id and param rules: `CLAUDE.md` Rule 0.

## Task overview

YF-1 audit (docs only) → YF-2 fixtures + frozen clock → YF-3 `OverlayTenorPolicy` registry + monthly regression pin → YF-4 `resolve_overlay_expiry` + bootstrap clock injection → YF-5 namespace
read-paths.

## Definition of done

Monthly policy values pinned by a test; yearly resolves 2026-12-29 on 2026-10-06 and 2027-12-28 on 2026-12-30 from fixtures; every namespace consumer from the YF-1 audit handles the yearly namespace;
default `pytest tests/unit/ --tb=no -q` green.

## Perspectives not covered

Margin: a short far-dated call needs different SPAN/exposure margin than a monthly one. Nothing here models it; `collateral_gate` pooling (README open decision 2) is the only margin touchpoint.
