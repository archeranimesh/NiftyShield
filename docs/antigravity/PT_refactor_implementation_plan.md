# Implementation Plan - Paper Trading Refactor (Phased)

Audit and refactor of the paper trading system (`src/paper/` and related scripts) to eliminate duplication, improve hygiene, and ensure architectural consistency.

## User Review Required

> [!IMPORTANT]
> - **Constant Consolidation**: Moving multiple repeated strings/paths to `src/paper/constants.py`.
> - **Utility Extraction**: Creating `src/paper/_utils.py` for shared arithmetic and formatting.
> - **Behavioral Change**: `scripts/paper_3track_entry.py` will be updated to use the public `InstrumentLookup` API instead of private `_instruments` access.

## Open Questions
- None at this stage. Audit findings are clear.

---

## Phase 1: Constants, Utils, and Hygiene

### [Component] Constants & Utilities

#### [MODIFY] [constants.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/constants.py)
- Add `DEFAULT_DB_PATH`, `DEFAULT_BOD_PATH`.
- Add `NIFTY_UNDERLYING`, `NIFTYBEES_KEY`.
- Add OTM thresholds and DTE roll thresholds (`PP_OTM_MIN`, `CC_TARGET_OTM`, `OVERLAY_ROLL_DTE`, etc.).
- Move `_BASE_LABELS` and `_OVERLAY_LABELS` to a central location (likely `src/paper/constants.py` or a new `_display.py`).

#### [NEW] [_utils.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/_utils.py)
- Implement `safe_float(val, default=0.0)` (deduplicated from 4 files).
- Implement `fmt_decimal(val)` (deduplicated from 2 files).

### [Component] 3-Track Scripts

#### [MODIFY] [paper_3track_entry.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_entry.py)
- **Fix G5**: Add intent comments to `except Exception` blocks (e.g., `# G5: log and continue to next leg/expiry`).
- **Fix G7**: Remove f-string from `logger.info` argument (dict comprehension).
- **Fix G8**: Group and alphabetize imports.
- **Fix Part I §5**: Replace `strike == proxy_strike` with `abs(strike - proxy_strike) < 0.01` or Decimal comparison.
- **API Fix**: Update `collect_candidate_expiries` to use `lookup.get_expiry_candidates()`.
- Use consolidated constants and `safe_float`.

#### [MODIFY] [paper_3track_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_snapshot.py)
- **Fix G5**: Add intent comments.
- **Fix G8**: Group and alphabetize imports.
- Use consolidated constants and extracted display helpers.

#### [MODIFY] [paper_3track_overlay.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_overlay.py)
- **Fix G5**: Add intent comments.
- **Fix G8**: Group and alphabetize imports.
- Use consolidated constants and `safe_float`.

#### [MODIFY] [paper_3track_overlay_roll.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_overlay_roll.py)
- **Fix G5**: Add intent comments.
- Use consolidated constants.

### [Component] CSP Scripts

#### [MODIFY] [record_paper_trade.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/record_paper_trade.py)
- **Fix G5**: Add intent comments.
- **Fix Part I §5**: Replace `underlying_spot == 0.0` with `underlying_spot < 0.001`.
- Use consolidated constants.

#### [MODIFY] [paper_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_snapshot.py)
- Use consolidated constants.

---

## Phase 2: Structural & Display Consolidation

- Extract shared display logic (`_delta_arrow`, `_hedge_verdict`, `_print_track_block`) from `paper_3track_snapshot.py` and `paper_track_snapshot.py` to a new `src/paper/_display.py`.
- Standardize logging configuration across all scripts.

---

## Verification Plan

### Automated Tests
- Run all paper trading unit tests:
  `python -m pytest tests/unit/paper/`
- Run existing instrument lookup tests:
  `python -m pytest tests/unit/instruments/`

### Manual Verification
- Dry-run each script to ensure no regressions in CLI output or logic:
  - `python scripts/paper_3track_entry.py --dry-run`
  - `python scripts/paper_3track_snapshot.py --no-save`
  - `python scripts/record_paper_trade.py --dry-run`
  - `python scripts/paper_snapshot.py --dry-run`
