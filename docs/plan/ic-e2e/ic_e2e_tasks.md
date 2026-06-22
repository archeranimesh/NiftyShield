# ic-e2e — Task Checklist

> Find the first unchecked `- [ ]` line **assigned to you**. That is your only task for this session.
> Each task is tagged `[Claude]` or `[Antigravity]` — **only pick up tasks tagged for you**.
> If the next unchecked task is tagged for the other agent, stop and hand off.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md` session log.
> Full story spec for each task: `docs/plan/ic-e2e/stories/<TASK_ID>.md`
>
> **Goal:** Complete IronCondorV1 end-to-end for paper trading.
> Four gaps identified after paper-backbone-adj was shipped:
> (1) missing `auto_execute` attribute — monitor falls back to False but it should be explicit;
> (2) no entry script — currently requires manual `record_paper_trade.py` invocations;
> (3) IVR hardcoded as "N/A" in `describe_context` — Telegram context block is incomplete;
> (4) no EOD snapshot script — IC positions get no daily exit-signal report.

---

## Phase IC-F1 — Protocol Compliance

- [ ] **IC-E1** `[Claude]` — `src/strategy/ic_nifty_v1.py`: add `auto_execute: bool = False` class attribute + `STRATEGY_IC` constant to `src/paper/constants.py` + tests

## Phase IC-F2 — Entry Script

- [ ] **IC-E2** `[Antigravity]` — `scripts/strategies/ic/paper_ic_entry.py`: 4-leg entry helper with asymmetric delta targets, IVR gate, portfolio interaction check, duplicate guard, dry-run mode + tests

## Phase IC-F3 — Context Wiring

- [ ] **IC-E3** `[Claude]` — `src/strategy/ic_nifty_v1.py`: wire IVR into `describe_context` from VIX Parquet (same pattern as `paper_cc_entry.py`) + tests

## Phase IC-F4 — EOD Snapshot

- [ ] **IC-E4** `[Antigravity]` — `scripts/strategies/ic/paper_ic_snapshot.py`: EOD cron — exit signal detection for open IC positions, Telegram report, DTE alert + tests
