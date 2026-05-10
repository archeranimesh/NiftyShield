# Walkthrough - Paper Trading Refactor (Phase 1 & 2)

Refactored the paper trading system to eliminate duplication, improve robustness against dirty market data, and ensure architectural consistency.

## Key Changes

### 1. Centralized Domain Knowledge
- **Constants**: All paths, thresholds, and instrument keys are now in [constants.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/constants.py). This eliminated magic numbers and scattered definitions across 9 scripts.
- **Display**: Labels and formatting helpers moved to [display.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/_display.py). Reports now use a standardized nomenclature.

### 2. Robustness & Hygiene
- **Safe Math**: Integrated [safe_float](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/_utils.py) everywhere. The system now gracefully handles `None` or non-numeric values from Upstox API without crashing.
- **Tiebreaker Logic**: Fixed a bug where proxy candidates with identical delta proximity would tie-break inconsistently. The new logic prefers deeper ITM (higher delta) candidates.
- **Epsilon Comparisons**: Replaced `==` with `< 0.01` for floating-point strike comparisons to prevent precision errors.
- **Exception Intent**: Added G5-compliant comments to `except Exception` blocks to clarify why broad catching is necessary (mostly for API isolation).

### 3. API Hygiene
- Migrated `paper_3track_entry.py` from accessing `InstrumentLookup._instruments` directly to using the public `get_expiry_candidates` API.

## Verification Results

### Automated Tests
- **All 216 tests passed**.
- Fixed `test_tie_takes_higher_delta` which was failing due to missing tiebreaker logic.
- Added new tests for `safe_float` and display helpers.

```bash
python -m pytest tests/unit/paper/
# Output: 216 passed, 15 skipped, 31 warnings in 1.60s
```

### Manual Verification
- Verified `record_paper_trade.py` auto-expiry lookup still functions correctly after internal refactor.
- Verified `paper_3track_snapshot.py` output format remains consistent with standardized labels.
