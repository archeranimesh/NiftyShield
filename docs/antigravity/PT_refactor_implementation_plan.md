# Implementation Plan - Paper Trading Refactor (Refined)

Audit and refactor of the paper trading system (`src/paper/` and related scripts) to eliminate duplication, improve hygiene, and ensure architectural consistency.

## User Review Required

> [!IMPORTANT]
> - **Commit Granularity**: Phase 1 will be delivered in three distinct commits (Constants, Utils, Hygiene).
> - **DTE Verification**: `InstrumentLookup.get_expiry_candidates` has been verified to match script-level DTE bands exactly (Monthly: 15-45, Quarterly: 46-200, Yearly: 201-420).
> - **Logging Standardization**: A new `configure_logging()` helper will be added to `src/paper/_utils.py` to unify script logging setup.

## Open Questions
- None. All audit findings and correction requirements are incorporated.

---

## Phase 1: Constants, Utils, and Hygiene

### [Component] Constants & Utilities

#### [MODIFY] [constants.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/constants.py)
- Add core domain constants:
    - `DEFAULT_DB_PATH = Path("data/portfolio/portfolio.sqlite")`
    - `DEFAULT_BOD_PATH = Path("data/instruments/NSE.json.gz")`
    - `NIFTY_UNDERLYING = "NSE_INDEX|Nifty 50"`
    - `NIFTYBEES_KEY = "NSE_EQ|INF204KB14I2"`
- Add 3-Track targeting thresholds:
    - `PP_OTM_MIN`, `PP_OTM_MAX`, `PP_TARGET_OTM`
    - `CC_OTM_MIN`, `CC_OTM_MAX`, `CC_TARGET_OTM`
    - `OVERLAY_ROLL_DTE = 5`
    - `SPREAD_PCT_MAX = 3.0`
- **NOTE**: `_BASE_LABELS` and `_OVERLAY_LABELS` are deferred to Phase 2 (Display).

#### [NEW] [_utils.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/_utils.py)
- Implement `safe_float(val: Any, default: float = 0.0) -> float`:
    - Numeric string returns float.
    - `None` returns `default`.
    - Non-numeric string returns `default`.
- Implement `configure_logging(level: str | None = None)`:
    - Standardizes `logging.basicConfig` with format `%(asctime)s %(levelname)-8s %(name)s — %(message)s`.
    - Defaults to `LOG_LEVEL` environment variable or `INFO`.

### [Component] Script Refactoring (Scope: 8 scripts)

Files: `paper_3track_entry.py`, `paper_3track_snapshot.py`, `paper_3track_overlay.py`, `paper_3track_overlay_roll.py`, `paper_track_snapshot.py`, `paper_3track_overlay_entry.py`, `record_paper_trade.py`, `paper_snapshot.py`.

#### [MODIFY] [paper_3track_entry.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_entry.py)
- **Fix G5**: Add intent comments (e.g., `# G5: Log failure and continue to next candidate`).
- **Fix G7**: Remove f-string from `logger.info` argument (dict comprehension at L297).
- **Fix G8**: Group and alphabetize imports.
- **Fix Part I §5**: Replace `c["strike"] == p.proxy_strike` with `abs(c["strike"] - p.proxy_strike) < 0.01` (epsilon < 50/100 NSE strike increments).
- **API Fix**: Replace `lookup._instruments` loop with `lookup.get_expiry_candidates(underlying="NIFTY", today=today, preference=["quarterly", "yearly", "monthly"])`.
- Use consolidated constants and `safe_float`.

#### [MODIFY] [record_paper_trade.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/record_paper_trade.py)
- **Fix G5**: Add intent comments.
- **Fix Part I §5**: Replace `underlying_spot == 0.0` with `underlying_spot <= 0.0` (on the float before Decimal conversion).
- Use consolidated constants.

#### [MODIFY] [All other scripts](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/)
- Replace local `DEFAULT_DB`, `DEFAULT_BOD`, `LOT_SIZE`, `_safe_float` with imports from `src.paper.constants` and `src.paper._utils`.
- Apply G5/G8 fixes where identified in audit.
- Update `paper_3track_overlay_entry.py` and `paper_track_snapshot.py` (missing in previous draft).

---

## Phase 2: Display Logic Consolidation

### [NEW] [_display.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/_display.py)
- Extract shared display logic from `paper_3track_snapshot.py` and `paper_track_snapshot.py`:
    - `_BASE_LABELS`, `_OVERLAY_LABELS` (as constants in this module).
    - `fmt_decimal(val: Decimal) -> str`.
    - `get_delta_arrow(delta: Decimal | None) -> str`.
    - `get_hedge_verdict(base: Decimal, overlay_total: Decimal) -> str`.
- Update both snapshot scripts to use these centralized helpers.

---

## Commit Plan (Phase 1)

1.  **Commit A**: `refactor(paper): consolidate domain constants and update imports`
    - Update `src/paper/constants.py`.
    - Update all scripts to import from `src.paper.constants`.
2.  **Commit B**: `refactor(paper): extract safe_float to _utils and migrate scripts`
    - Create `src/paper/_utils.py`.
    - Update all scripts to use `src.paper._utils.safe_float`.
    - Add unit tests for `safe_float`.
3.  **Commit C**: `refactor(paper): fix hygiene (G5/G7/G8) and floating-point bugs`
    - Fix Part I §5 in `paper_3track_entry.py` and `record_paper_trade.py`.
    - Fix logger f-string in `paper_3track_entry.py`.
    - Add intent comments to `except Exception` blocks.
    - Standardize logging via `configure_logging()`.

---

## Verification Plan

### Automated Tests
- **Unit Tests for _utils**: `tests/unit/paper/test_utils.py` (New).
- **Unit Tests for _display**: `tests/unit/paper/test_display.py` (New - Phase 2).
- **Regression Suite**: `python -m pytest tests/unit/paper/`

### Manual Verification
- `python scripts/paper_3track_entry.py` (Dry-run is default).
- `python scripts/paper_3track_snapshot.py --no-save`
- `python scripts/record_paper_trade.py --dry-run`
- `python scripts/paper_snapshot.py --dry-run`

### Definition of Done (DoD)
- [ ] All unit tests pass.
- [ ] `safe_float` handles `None`, non-numeric, and numeric strings correctly.
- [ ] `_display.py` helpers have smoke tests for arrows and verdicts.
- [ ] Codebase graph is re-indexed using `mcp__codebase-memory-mcp__index_repository` after `_utils.py` and `_display.py` creation.
