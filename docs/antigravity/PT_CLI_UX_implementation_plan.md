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

---

### Phase 2: CLI Unification [CLI-1, CLI-2, CLI-4]

#### [MODIFY] [paper_3track_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_snapshot.py) [CLI-1, CLI-4]
- Rename `--no-save` → `--dry-run` (BooleanOptionalAction, default True).
- Change `--date` to `type=date.fromisoformat`.

#### [MODIFY] [paper_3track_overlay_roll.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_overlay_roll.py) [CLI-1]
- Add `--dry-run / --no-dry-run` (BooleanOptionalAction, default True).
- Maintain `--yes` but it will be refactored in a later phase.

#### [MODIFY] [paper_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_snapshot.py) [CLI-2, CLI-4]
- Rename `--underlying-price` → `--spot`.
- Change `--date` to `type=date.fromisoformat`.

#### [MODIFY] [paper_3track_overlay.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_overlay.py) [CLI-4]
- Change `--date` to `type=date.fromisoformat`.

#### [MODIFY] [find_strike_by_delta.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/find_strike_by_delta.py) [CLI-4]
- Change `--date` to `type=date.fromisoformat`.

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

#### [MODIFY] [find_strike_by_delta.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/find_strike_by_delta.py) [CLI-5]
- Add `--track spot|futures|proxy` shortcut.

---

### Phase 4: Refinement [CLI-11, CLI-12]

#### [MODIFY] [paper_3track_overlay_roll.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_overlay_roll.py) [CLI-11]
- Align `--yes` to mean "skip confirmation prompt".
- Add interactive confirmation prompt when `--no-dry-run` is used without `--yes`.

#### [MODIFY] [paper_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_snapshot.py) [CLI-12]
- Surface trade notes in the snapshot output (as a footer or additional column).

## Verification Plan

### Automated Tests
- Run `python -m pytest tests/unit/ --tb=no -q` to ensure all existing and new tests pass.
- New tests for `src/paper/formatting.py`.
- New tests for CLI flag changes and logic enhancements in scripts.

### Manual Verification
- Run each modified script with `--help` to verify flag changes.
- Perform dry-runs of each script to verify output formatting and logic.
- Verify `--no-dry-run` behavior where safe (using mock data or temporary DB).
