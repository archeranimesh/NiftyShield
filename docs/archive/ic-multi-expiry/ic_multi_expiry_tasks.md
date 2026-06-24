# ic-multi-expiry — Task Checklist

> Find the first unchecked `- [ ]` line **assigned to you**. That is your only task for this session.
> Each task is tagged `[Claude]` or `[Antigravity]` — **only pick up tasks tagged for you**.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md` session log.
> Full story spec: `docs/plan/ic-multi-expiry/stories/<TASK_ID>.md`
>
> **Goal:** Single parameterised `IronCondorV1` class that supports weekly / monthly / leaps /
> yearly expiry ICs — tracked independently in the DB, monitored independently by the daemon,
> entered via one entry script with `--expiry-type`, snapshotted via one EOD script.
>
> **Prerequisite:** ic-e2e IC-E3 must be committed before IC-M2 starts (both touch ic_nifty_v1.py).
> IC-E2 and IC-E4 from ic-e2e are **superseded** by IC-M5 and IC-M6 in this plan — do not
> implement them from ic-e2e.

---

## Phase IC-M1 — Expiry Config Model

- [ ] **IC-M1** `[Claude]` — `src/strategy/ic_expiry_config.py`: `ICExpiryConfig` frozen dataclass + `CONFIGS` presets for all four expiry types + four new strategy name constants in `src/paper/constants.py` + tests

## Phase IC-M2 — Parameterise IronCondorV1

- [ ] **IC-M2** `[Antigravity]` — `src/strategy/ic_nifty_v1.py`: replace all hardcoded threshold constants with values from injected `ICExpiryConfig`; `strategy_name` derived from config; constructor updated; all existing tests updated + new per-expiry signal tests

## Phase IC-M3 — Weekly Expiry Bucket

- [ ] **IC-M3** `[Claude]` — `src/instruments/lookup.py`: add `"weekly"` DTE bucket (nearest Tuesday, DTE ≤ 14) to `get_expiry_candidates()`; update docstring; add tests for weekly bucket selection

## Phase IC-M4 — Daemon Registration

- [ ] **IC-M4** `[Antigravity]` — `scripts/monitor_daemon.py`: replace single `IronCondorV1` registration with four instances (one per expiry type), each using its `ICExpiryConfig` preset; guard pattern preserved; tests updated

## Phase IC-M5 — Entry Script (supersedes ic-e2e IC-E2)

- [ ] **IC-M5** `[Antigravity]` — `scripts/strategies/ic/paper_ic_entry.py`: rebuild entry script with `--expiry-type [weekly|monthly|leaps|yearly]` flag; resolves correct expiry bucket; uses per-type delta targets; carries all existing gates (IVR, duplicate, portfolio-delta, liquidity); tests

## Phase IC-M6 — EOD Snapshot Script (supersedes ic-e2e IC-E4)

- [ ] **IC-M6** `[Antigravity]` — `scripts/strategies/ic/paper_ic_snapshot.py`: EOD cron iterates all four IC strategy names; emits per-type exit signal report via Telegram; DTE alert per expiry; offline tests
