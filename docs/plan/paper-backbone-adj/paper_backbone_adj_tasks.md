# paper-backbone-adj — Task Checklist

> Find the first unchecked `- [ ]` line **assigned to you**. That is your only task for this session.
> Each task is tagged `[Claude]` or `[Antigravity]` — **only pick up tasks tagged for you**.
> If the next unchecked task is tagged for the other agent, stop and hand off.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md` session log.
> Full story spec for each task: `docs/plan/paper-backbone-adj/stories/<TASK_ID>.md`
>
> **Context:** The executor already handles `legs_to_open` (PB1.3 — `src/strategy/executor.py`).
> The gap is in the strategy layer only — signals and apply_action. No executor work needed.
>
> **Council gate (2026-06-02):** Full chain fetch kept as-is. Roll target selection uses Option Y
> (immediate, inside `check_signals`). Shared utility `src/strategy/roll_utils.py` must be
> built first (PA0) — all strategy `_select_*_roll_target()` helpers depend on it.

---

## Phase PA-0 — Shared Roll Utility

- [x] **PA0** `[Claude]` — `src/strategy/roll_utils.py`: `find_strike_by_delta(chain, option_type, delta_range, target_delta)` shared helper + tests | SHA: eef6cca

## Phase PA-S0 — CSP Full Adjustment

- [ ] **PA1.1** `[Claude]` — `src/strategy/csp_nifty_v1.py`: add `ROLL` signal emission with strike selection + `apply_action` ROLL branch + tests

## Phase PA-S1 — Iron Condor Adjustment

- [ ] **PA1.2** `[Claude]` — `src/strategy/ic_nifty_v1.py`: add wing-roll adjustment signals + `apply_action` ROLL branch + tests

## Phase PA-S3 — 3-Track Overlay Adjustment

- [ ] **PA1.3** `[Claude]` — `src/strategy/nifty_track_comparison_v1.py`: upgrade WARN→ACTION for roll signals, add `_select_overlay_roll_target()`, implement `apply_action` (ROLL_OVERLAY, ROLL_COLLAR) + tests

## Phase PA-X — Cleanup

- [ ] **PA2** `[Claude]` — Retire `scripts/strategies/csp/paper_csp_roll.py` + `scripts/strategies/three_track/paper_3track_overlay_roll.py`; update `CONTEXT.md`, `DECISIONS.md`, `TODOS.md`
