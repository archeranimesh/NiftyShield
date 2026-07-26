# PaperStore Position Granularity — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/paper-store-position-granularity/stories.md`.

---

- [x] **PG-1** — Fix `PaperStore.get_positions()` to group by `(strategy_name, leg_role, instrument_key)` + update `PaperPosition` model + tests | SHA: c89b0d8
- [x] **PG-2** — Audit complete (2026-07-25). Split into independently implementable sub-tasks below — do not implement as one task.
- [x] **PG-2a** — `PaperStore.get_position()`: add `instrument_key: str | None = None` param; filter by it when given, else pick most-recent `entry_date` among leg_role matches and log a WARNING on ambiguity. Files: `src/paper/store.py`, `tests/unit/paper/test_store.py`. | SHA: a83d83e
- [x] **PG-2b** — `scripts/strategies/three_track/paper_3track_snapshot.py::_run`: replace the `[store.get_position(track_name, r) for r in leg_roles]` loop with a direct `store.get_positions(track_name)` call so LTP fetch doesn't silently drop one instrument's leg during a roll overlap. Independent of PG-2a. | SHA: PENDING
- [ ] **PG-2c** — `scripts/portfolio/paper_snapshot.py::_run`: `most_recent_trade_per_leg` dict keyed by `leg_role` only drops notes from the other instrument under the same leg role during a roll. Re-key by `(leg_role, instrument_key)`. Independent of PG-2a.
- [ ] **PG-2d** — `scripts/record/record_paper_trade.py::main`: final position-summary `get_position(strategy, leg_role)` call should pass the already-known `instrument_key` explicitly. Depends on PG-2a landing first (needs the new param).
- [ ] **PG-2e** — `scripts/strategies/ic/paper_ic_entry.py::run`: post-entry verification loop's `get_position(config.strategy_name, role)` call should pass `instrument_key=key` explicitly. Depends on PG-2a landing first.
- [ ] **PG-3** — Docs close: TODOS.md session log entry, DECISIONS.md entry, CONTEXT.md model tree update — no code
- [ ] **PG-4** — (new, deferred) Thread `instrument_key` through `ApprovedAction`/`LegSpec` so `PaperExecutor.apply()` can close the correct instrument by key instead of by `leg_role` alone during a roll overlap. Touches `src/strategy/protocol.py`, `src/strategy/executor.py`, and every caller that constructs `ApprovedAction` (all concrete strategies in `src/strategy/*_v1.py`, `ic_nifty_v1.py`, `ic_nifty_v2.py`). Larger, independent change — not part of PG-2's scope.
