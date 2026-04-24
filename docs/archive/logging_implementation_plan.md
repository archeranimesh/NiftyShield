# Implementation Plan - Replace `print` with `logging`

This plan addresses the use of `print` statements in the NiftyShield codebase by transitioning to the standard Python `logging` library. This is a best practice for professional code, providing better control over output levels, redirection, and formatting without impacting the final user-facing output.

## User Review Required

> [!IMPORTANT]
> The current output of `daily_snapshot.py` and other scripts will be preserved exactly as it is today. To achieve this, we will use a dedicated "UI" logger with a clean formatter (no prefixes/timestamps) for reporting, while using a standard logger with levels for status and errors.

## Proposed Changes

### Core Utilities

#### [NEW] [logging_utils.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/utils/logging_utils.py)
- Create a central utility to configure and retrieve loggers.
- Provide a `setup_logging` function that:
    - Sets up a standard logger (with timestamps/levels) for general info/errors.
    - Sets up a "clean" logger (no formatting) for reports/UI output to maintain current aesthetics.
    - Handles console and potentially file logging.

---

### Source Files

#### [MODIFY] [test_analytics_apis.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/analytics/test_analytics_apis.py)
- Replace all `print` statements with `logger.info`, `logger.error`, or the "clean" logger for report sections.
- Initialize the logger at the top of the file.

---

### Scripts

#### [MODIFY] [daily_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/daily_snapshot.py)
- Call `setup_logging` in `main()`.
- Replace progress prints (e.g., `run_id=...`, `Recorded ...`) with `logger.info`.
- Replace error prints with `logger.error`.
- Replace the final report `print(_format_combined_summary(...))` with a call to the clean logger to preserve the table formatting exactly.

#### [MODIFY] [seed_trades.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/seed_trades.py)
- Call `setup_logging`.
- Replace prints with appropriate logging levels.

#### [MODIFY] [seed_portfolio.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/seed_portfolio.py)
- Call `setup_logging`.
- Replace prints with logging.

#### [MODIFY] [record_trade.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/record_trade.py)
- Call `setup_logging`.
- Replace prints and `sys.stderr` prints with loggers.

#### [MODIFY] [roll_leg.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/roll_leg.py)
- Replace all prints with loggers.

---

## Verification Plan

### Automated Tests
- Run `pytest` to ensure no regressions in logic (since we aren't changing logic, only side-effects).
- Verify that `src/analytics/test_analytics_apis.py` still runs correctly and produces the same output.

### Manual Verification
- Run `python -m scripts.daily_snapshot --date 2026-04-06` (or another recent date) and compare the output with the current version to ensure zero visual impact.
- Run `python scripts/seed_trades.py --dry-run` and verify output.
- Check `logs/snapshot.log` (if used in cron) to see if logging formatting (if enabled) is helpful.
