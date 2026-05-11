# Implementation Plan — Paper Trading CLI & UX Refactor

This plan addresses a series of CLI consistency and UX improvements for the paper trading system, as outlined in `TODOS.md`.

## User Review Required

> [!IMPORTANT]
> This plan follows a specific execution sequence requested by the user:
> `UX-9` → (`CLI-1`, `CLI-2`, `CLI-4` in parallel) → (`UX-6`, `UX-7`, `UX-8`, `CLI-3`, `CLI-5`, `CLI-10` in parallel) → `CLI-11` → `CLI-12`.

> [!WARNING]
> Several CLI flags are being renamed or modified (e.g., `--no-save` → `--dry-run`, `--underlying-price` → `--spot`). This may break existing scripts or cron jobs if they are not updated.

## Proposed Changes

### Phase 1: Shared Infrastructure [UX-9]

#### [NEW] [formatting.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/formatting.py)
- Create `src/paper/formatting.py` with shared output helpers.
- Implement `fmt_inr(value: Decimal, sign_always: bool = False) -> str`.
- Implement `format_pnl_table(rows: list[dict], title: str = "", is_dry_run: bool = False) -> str`.
- Implement `format_track_summary(rows: list[dict], snap_date: date) -> str`.

#### [MODIFY] [__init__.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/__init__.py)
- Re-export functions from `formatting.py`.

#### [NEW] [test_formatting.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/tests/unit/paper/test_formatting.py)
- Happy-path tests for `fmt_inr` (positive, negative, zero, `sign_always=True`).
- Happy-path tests for `format_pnl_table` (non-empty rows, dry-run header).
- Happy-path tests for `format_track_summary` (multiple rows, snap date in header).
- Edge cases: empty row list, `Decimal` boundary values.

> **Post-phase step:** run `mcp__codebase-memory-mcp__index_repository` to register `src/paper/formatting.py` in the codebase graph before Phase 2 begins.

---

### Phase 2: CLI Unification [CLI-1, CLI-2, CLI-4]

> [!CAUTION]
> **`--dry-run` default flip is a cron-breaking change.**
> `--no-save` is `action="store_true"` (default `False`) — the script **saves by default** and the EOD cron (`python scripts/paper_3track_snapshot.py --date ...`) runs without any flag.
> After renaming to `--dry-run / --no-dry-run` with `default=True`, that same cron call becomes a silent no-op. **The cron entry and all doc examples must be updated in this commit** or the change should not land.

#### [MODIFY] [paper_3track_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_snapshot.py) [CLI-1, CLI-4]
- Rename `--no-save` → `--dry-run` (BooleanOptionalAction, default `True`).
- Update all internal references: `args.no_save` → `args.dry_run`, `save: bool = not args.dry_run`.
- Change `--date` to `type=date.fromisoformat`.
- Update the module docstring's cron example to include `--no-dry-run`.

#### [MODIFY] [paper_3track_overlay_roll.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_overlay_roll.py) [CLI-1]
- Add `--dry-run / --no-dry-run` (BooleanOptionalAction, default `True`).
- Maintain `--yes` but it will be refactored in a later phase.

#### [MODIFY] [paper_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_snapshot.py) [CLI-2, CLI-4]
- Rename `--underlying-price` → `--spot`.
- Change `--date` to `type=date.fromisoformat`.

#### [MODIFY] [paper_3track_overlay.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_overlay.py) [CLI-4]
- Change `--date` to `type=date.fromisoformat`.

#### [MODIFY] [find_strike_by_delta.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/find_strike_by_delta.py) [CLI-4]
- Change `--date` to `type=date.fromisoformat`.

#### Required doc updates (must land in this commit)
- `docs/instructions/3track.md` — update all `--no-save` examples to `--no-dry-run`; update cron entry to append `--no-dry-run`.
- `docs/instructions/paper_trade.md` — same `--no-save` → `--no-dry-run` sweep.
- `CONTEXT_TREE.md` — update `paper_3track_snapshot.py` description (currently references `--no-save`).

---

### Phase 3: UX & Functional Enhancements [UX-6, UX-7, UX-8, CLI-3, CLI-5, CLI-10]

#### [MODIFY] [paper_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_snapshot.py) [UX-6]
- Use `format_pnl_table()` from `src.paper.formatting` for output.

#### [MODIFY] [paper_3track_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_snapshot.py) [UX-7, UX-8]
- Print summary table before verbose blocks.
- Add `--verbose / -v` flag to gate per-track verbose output.

#### [MODIFY] [paper_3track_overlay_roll.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_overlay_roll.py) [CLI-3, CLI-10]
- Add `--index N` to select replacement candidate.
- Add `--overlay pp|cc|collar` to filter which overlay legs are rolled.
- Clarify interaction: `--index` and `--overlay` are independent filters; both may be supplied simultaneously. Neither bypasses the DTE gate unless `--force` is also passed.

#### [MODIFY] [find_strike_by_delta.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/find_strike_by_delta.py) [CLI-5]
- Add `--track spot|futures|proxy` shortcut.

#### [NEW] tests for Phase 3 changes
- `tests/unit/paper/test_paper_3track_snapshot.py` — add cases for `--verbose` gating.
- `tests/unit/paper/test_paper_3track_overlay_roll.py` — add cases for `--index` and `--overlay` filtering logic.

---

### Phase 4: Refinement [CLI-11, CLI-12]

#### [MODIFY] [paper_3track_overlay_roll.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_overlay_roll.py) [CLI-11]
- Align `--yes` to mean "skip confirmation prompt".
- Add interactive confirmation prompt when `--no-dry-run` is used without `--yes`.
- Guard: if running non-interactively and `--yes` is absent, raise a clear error rather than hanging on `input()`.

#### [MODIFY] [paper_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_snapshot.py) [CLI-12]
- Surface trade notes in the snapshot output.

#### [NEW] tests for Phase 4 changes
- `tests/unit/paper/test_paper_3track_overlay_roll.py` — confirmation prompt: invoked without `--yes`; skipped with `--yes`; non-interactive guard raises cleanly.

## Verification Plan

### Automated Tests
- Run `python -m pytest tests/unit/ --tb=no -q` after each phase before committing.
- Phase 1: `tests/unit/paper/test_formatting.py` — all three helpers, happy + edge cases.
- Phase 2: existing tests must stay green.
- Phase 3: new test cases for `--verbose` gating and `--index`/`--overlay` filter logic.
- Phase 4: new test cases for the confirmation prompt and non-interactive guard.

### Manual Verification
- Run each modified script with `--help` to verify flag changes.
- Perform dry-runs of each script to verify output formatting and logic.
- After Phase 2: confirm the cron-simulation call `python scripts/paper_3track_snapshot.py --date $(date +%Y-%m-%d) --no-dry-run` writes correctly.
- Verify `--no-dry-run` behavior where safe (using mock data or temporary DB).

