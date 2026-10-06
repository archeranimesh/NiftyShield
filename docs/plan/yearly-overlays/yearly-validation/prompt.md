# Yearly Validation — prompt

> The way to test the epic: independence tests, an end-to-end dry run, an opt-in live smoke, the IC coexistence check, and the paper-run runbook that gates the Dec 2026 -> Dec 2027 roll.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

Unit tests per story prove each piece; this story proves the two books cannot interfere, that the whole entrypoint runs offline end to end, and that IC `leaps` (quarterly) and `yearly` (December)
coexist with weekly and monthly. It also holds the one human gate: the roll cannot be trusted until Dec 2027 data exists.

## Scope guard

Tests and runbook only; the only production edit allowed is a bug fix a test exposes, in its own commit. Default `pytest` stays offline. Live checks are marker-gated and opt-in.

## Design review

No new module. The e2e harness uses `MockBrokerClient`, a temp SQLite and the YF-2 fixtures, injected, so no real token, network or DB is touched.

## Session-start load hints

`docs/plan/yearly-overlays/README.md`, `yearly-foundation/audit.md`, `src/strategy/ic_expiry_config.py`, `tests/` conftest for markers, `docs/plan/dhan-far-expiry-chain/README.md`.

## Task overview

YV-1 independence tests → YV-2 e2e dry run → YV-3 opt-in live smoke → YV-4 IC coexistence → YV-5 paper-run and roll runbook (Animesh).

## Definition of done

YV-1, YV-2, YV-4 green in the default offline run; YV-3 documented and passing when run with the live marker; YV-5 checklist exists and names the roll gate.

## Perspectives not covered

Order-execution realism: all validation is paper; real fills on thin far-dated strikes are not exercised until execution is unblocked.
