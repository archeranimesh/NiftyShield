# Implementation Plan - Paper Trading Refactor (Refined v4)

Audit and refactor of the paper trading system (`src/paper/` and related scripts) to eliminate duplication, improve hygiene, and ensure architectural consistency.

## User Review Required

> [!IMPORTANT]
> - **Commit Granularity**: Phase 1 and Phase 2 will be delivered in distinct commits.
> - **Expiry Adapter**: `InstrumentLookup.get_expiry_candidates` returns `list[tuple[str, str]]`. In `paper_3track_entry.py`, an adapter `dict(...)` will be used to maintain compatibility with the expected `dict[str, str]` (band -> expiry) mapping.
> - **Logging**: `configure_logging()` has been removed from the refactor scope to avoid architectural over-engineering; logging setup will remain inline in each script (cosmetic inconsistency accepted).
> - **Constant Extraction**: All constants added to `constants.py` are extracted from existing script definitions (no new behavioral constants introduced).

## Open Questions
- None.

---

## Phase 1: Constants, Utils, and Hygiene

### [Component] Constants & Utilities

#### [MODIFY] [constants.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/constants.py)
- **Extracted core domain constants**:
    - `DEFAULT_DB_PATH = Path("data/portfolio/portfolio.sqlite")` (from `paper_3track_entry.py` L69)
    - `DEFAULT_BOD_PATH = Path("data/instruments/NSE.json.gz")` (from `paper_3track_entry.py` L68)
    - `NIFTY_UNDERLYING = "NSE_INDEX|Nifty 50"` (from `paper_3track_entry.py` L56)
    - `NIFTYBEES_KEY = "NSE_EQ|INF204KB14I2"` (from `paper_3track_entry.py` L55)
- **Extracted 3-Track targeting thresholds** (all from `paper_3track_overlay.py` L63-76):
    - `PP_OTM_MIN = 0.08`, `PP_OTM_MAX = 0.10`, `PP_TARGET_OTM = 0.09`
    - `CC_OTM_MIN = 0.03`, `CC_OTM_MAX = 0.05`, `CC_TARGET_OTM = 0.04`
    - `OVERLAY_ROLL_DTE = 5`
    - `SPREAD_PCT_MAX = 3.0`
- **NOTE**: `_BASE_LABELS` and `_OVERLAY_LABELS` are deferred to Phase 2 (Display).

#### [NEW] [_utils.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/_utils.py)
- Implement `safe_float(val: Any, default: float = 0.0) -> float`:
    - Numeric string returns float.
    - `None` returns `default`.
    - Non-numeric string returns `default`.

### [Component] Script Refactoring (Scope: 8 scripts)

Files: `paper_3track_entry.py`, `paper_3track_snapshot.py`, `paper_3track_overlay.py`, `paper_3track_overlay_roll.py`, `paper_track_snapshot.py`, `paper_3track_overlay_entry.py`, `record_paper_trade.py`, `paper_snapshot.py`.

#### [MODIFY] [paper_3track_entry.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_entry.py)
- **Fix G5**: Add intent comments explaining *why* the broad catch is correct at that boundary — not a tag. Required format per REVIEW.md G5:
    ```python
    # Intentional: isolate all per-expiry chain-fetch failures so a single
    # bad expiry does not abort the full multi-expiry entry sweep.
    ```
    Do NOT use `# G5: ...` as a label — that describes what happens, not why the catch is justified.
- **Fix G7**: Remove f-string from `logger.info` argument (dict comprehension at L297).
- **Fix G8**: Group and alphabetize imports.
- **Fix Part I §5**: Replace `c["strike"] == p.proxy_strike` with `abs(c["strike"] - p.proxy_strike) < 0.01` (# epsilon < 50/100 NSE strike increments).
- **API Fix**: Replace `lookup._instruments` loop with `dict(lookup.get_expiry_candidates(underlying="NIFTY", today=today))`.
    - *Verification*: `lookup.get_expiry_candidates` returns `list[tuple[str, str]]`, so `dict()` is required for the subsequent `.items()` call.
    - *Preference order*: Use the default `["monthly", "quarterly", "yearly"]` — do NOT pass `["quarterly", "yearly", "monthly"]`. The original code fetches monthly first (smallest DTE, first in sorted calendar order); preserving that order ensures the Nifty spot price is sourced from the monthly chain, which is the most liquid. Changing preference order is a silent behavioural change and must not be introduced in a refactor commit.
- Use consolidated constants and `safe_float`.

#### [MODIFY] [record_paper_trade.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/record_paper_trade.py)
- **Fix G5**: Add intent comments.
- **Fix Part I §5**: Replace `underlying_spot == 0.0` with `underlying_spot <= 0.0` (on the float before Decimal conversion).
- Use consolidated constants.

---

## Phase 2: Display Logic Consolidation

### [NEW] [_display.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/_display.py)
- Extract shared display logic from `paper_3track_snapshot.py` and `paper_track_snapshot.py`:
    - `_BASE_LABELS`, `_OVERLAY_LABELS` (as constants in this module).
    - `fmt_decimal(val: Decimal) -> str`.
    - `get_delta_arrow(delta: Decimal | None) -> str`.
    - `get_hedge_verdict(base: Decimal, overlay_total: Decimal) -> str`.
- Update both snapshot scripts to use these centralized helpers.

### Phase 2 Commit Plan
- **Commit**: `refactor(paper): extract display helpers to _display module`
- **Verification**: Run the full paper regression suite before committing — not just `test_display.py`:
    ```
    python -m pytest tests/unit/paper/ --tb=no -q
    ```
    A display extraction that silently breaks `test_track_snapshot.py` or `test_paper_store.py` must be caught before the commit, not after.

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
    - *Scope for G5/G8*: Touched files include `paper_3track_entry.py`, `paper_3track_snapshot.py`, `paper_3track_overlay.py`, `paper_3track_overlay_roll.py`, `record_paper_trade.py`, `overlay_selector.py`, and `track_snapshot.py`.

---

## Out of Scope — Design Gaps Surfaced by This Refactor

### CSP has no roll script (`paper_csp_roll.py`)

The 3-track system has `paper_3track_overlay_roll.py` to roll expiring overlay
legs atomically when DTE ≤ 5. CSP has no equivalent. Rolling the CSP short put
at expiry — buy back the expiring strike, sell the next monthly at 22-delta —
is the same operational concept: DTE gate, strike re-selection, atomic close+open
with rollback on failure. Currently the operator must manually chain
`record_paper_trade.py --close` followed by a new entry, with no guard against
partial execution.

**This is new functionality and must NOT be implemented in this refactor.**
Add the following task to `TODOS.md` before closing this plan:

> **New task**: Implement `scripts/paper_csp_roll.py` — atomic DTE-gated roll
> of the CSP short put leg. Reuse the atomic close+open pattern from
> `paper_3track_overlay_roll.py`. Inputs: DTE gate (default `OVERLAY_ROLL_DTE`),
> target delta (default 22, parameterised), `--dry-run` flag. Log India VIX
> level at roll time for future R3 calibration. IVR enforcement deferred until
> VIX ingestion lands (Task 1).

**Forward-looking note for this refactor:** The atomic close+open logic inside
`paper_3track_overlay_roll.py` will eventually need to be extracted into
`src/paper/` (e.g. `src/paper/roll.py`) so both roll scripts share it without
duplication. Do not bake this logic deeper into overlay-specific code during
Phase 1 or Phase 2 — keep it separable. When `paper_csp_roll.py` is
implemented, extracting into `src/paper/roll.py` becomes Phase 3 of this
refactor series.

---

## Verification Plan

### Automated Tests
- **Unit Tests for _utils**: `tests/unit/paper/test_utils.py` (New).
- **Unit Tests for _display**: `tests/unit/paper/test_display.py` (New - Phase 2).
- **Regression Suite**: `python -m pytest tests/unit/paper/`

### Manual Verification
- `python scripts/paper_3track_entry.py` (Dry-run is default).
- `python scripts/paper_3track_snapshot.py --no-save`
- `python scripts/record_paper_trade.py --dry-run` (Note: flag exists via `BooleanOptionalAction`).
- `python scripts/paper_snapshot.py --dry-run`

### Phase 1 Definition of Done (DoD)
- [ ] All Phase 1 unit tests pass.
- [ ] `safe_float` handles `None`, non-numeric, and numeric strings correctly.
- [ ] Codebase graph is re-indexed using `mcp__codebase-memory-mcp__index_repository` after `_utils.py` creation.

### Phase 2 Definition of Done (DoD)
- [ ] `paper_3track_snapshot.py` and `paper_track_snapshot.py` both import from `_display.py`.
- [ ] Labels and helpers are no longer defined inline in snapshot scripts.
- [ ] All Phase 2 unit tests pass (including smoke tests for arrows and verdicts).
- [ ] Codebase graph is re-indexed after `_display.py` creation.
