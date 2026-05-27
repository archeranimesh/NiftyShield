# signals-eval-core — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: tick `tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md`.
>
> **Source of truth for strategy parameters and validation thresholds:**
> - Swing strategies (Donchian, ORB, Gap Fade): `docs/plan/signals-eval-core/` (this file)
> - Investment strategies (SMA, Dual Momentum, PE Band): `docs/plan/signals-eval-core/` (this file)
> - Council decisions: `docs/archive/council/strategy/` (binding, read before implementing any strategy)
> - Phase 2 task checklist: `BACKTEST_PLAN_PHASE1.md §Phase 2`

---

## SE1.1 — Data infrastructure verification

**Files to change:**
- `scripts/verify_data_coverage.py` — new script (no unit tests)

**Before any code:**
`search_code("bhavcopy_ingest")` — confirm bhavcopy Parquet path and partition convention;
`search_graph("vix_ingest")` — confirm VIX Parquet location;
`bash ls data/historical/ohlc/` — see what exists.

**What to implement:**
Script that checks five things and prints PASS / FAIL per item:
1. Nifty 50 Index daily OHLC Parquet exists; row count and date range printed; latest date verified.
2. Nifty 50 Index 15-min OHLC Parquet exists; same checks.
3. India VIX daily close Parquet exists; <1% missing trading days (fill holidays with prev close; flag gaps >1 day).
4. Derived field check: load daily Parquet for the last 300 rows; confirm ATR-14, ATR-40, ATR-20 and 50D slope columns are present or compute them inline and print sample values for visual spot-check.
5. Nifty 50 close ±0.05% match vs NSE published values for 5 random dates in the last 12 months (hard-code NSE spot values pulled manually; this is a one-time sanity check, not a live assertion).

If any item fails, print the specific gap and stop — do not proceed to SE1.2 until this passes.

**No unit tests.** This is a one-time verification script.
**Commit:** `chore(signals-eval-core): add verify_data_coverage.py — SE1.1 data infrastructure gate`

---

## SE1.2 — `src/instruments/pe_loader.py`: NSE PE data pipeline

**Files to change:**
- `src/instruments/pe_loader.py` — new module
- `tests/unit/instruments/test_pe_loader.py` — new test file

**Before any code:**
`search_graph("vix_ingest")` — reuse Parquet write pattern;
`get_code_snippet("get_expiry_candidates")` — existing instruments module pattern;
`bash ls data/historical/` — confirm storage root.

**NSE PE CSV format:** NSE publishes `ind_close_all_20XXXXXX.csv` with columns:
`Index Name`, `Index Date` (DD-MM-YYYY), `Open Index Value`, `High Index Value`,
`Low Index Value`, `Closing Index Value`, `Points Change`, `Change(%)`, `Volume`, `Turnover (Rs. Cr.)`,
`P/E`, `P/B`, `Div Yield`. Filter rows where `Index Name == "Nifty 50"`. The `P/E` column is the trailing PE.

**What to implement:**

```python
NIFTY_PE_PARQUET = Path("data/historical/pe/nifty50_pe.parquet")

def load_pe_csv(csv_path: Path) -> pd.DataFrame:
    """
    Parse one NSE PE CSV file into a clean DataFrame.

    Returns columns: date (datetime64), pe (float64).
    Drops rows where P/E is "-" or 0. Converts Index Date from DD-MM-YYYY.
    Raises ValueError if no "Nifty 50" rows found in the file.
    """

def ingest_pe_csvs(csv_dir: Path, output_path: Path = NIFTY_PE_PARQUET) -> int:
    """
    Load all NSE PE CSV files from csv_dir, merge, deduplicate, sort by date,
    and write to Parquet. Returns row count written.

    Resumable: if output_path already exists, loads it and merges — new rows appended,
    existing rows not overwritten (deduplicate on date).
    Gaps ≤1 month filled with the previous valid PE value (forward fill).
    Gaps >1 month left as NaN and logged as WARNING.
    """

def get_pe_series(
    from_date: date,
    to_date: date,
    parquet_path: Path = NIFTY_PE_PARQUET,
) -> pd.Series:
    """
    Load PE series for [from_date, to_date] from Parquet. Index is pd.DatetimeIndex.
    Raises FileNotFoundError if Parquet does not exist.
    """
```

**Tests (`tests/unit/instruments/test_pe_loader.py`):**
- `load_pe_csv` with a fixture CSV (2 rows with P/E values) → DataFrame with correct `date` and `pe` columns.
- `load_pe_csv` with P/E as "-" (missing) → those rows dropped; no error.
- `load_pe_csv` with no "Nifty 50" rows → `ValueError` raised.
- `ingest_pe_csvs` called twice with same file → row count stays 1 (deduplication).
- `get_pe_series` on date range with 5 rows in fixture Parquet → returns Series of length 5.
- `get_pe_series` when Parquet missing → `FileNotFoundError`.

**Commit:** `feat(instruments): add pe_loader — NSE PE CSV ingest + Parquet storage (SE1.2)`

---

## SE1.3 — Risk-free rate series

**Files to change:**
- `src/instruments/rf_rate.py` — new module
- `tests/unit/instruments/test_rf_rate.py` — new test file

**Before any code:**
`search_graph("MFHolding")` — confirm AMFI/MF infrastructure in `src/mf/`;
`get_code_snippet("get_nav_series")` or `search_code("nav_snapshots")` — confirm MF NAV table.

**What to implement:**

```python
DEFAULT_RF_RATE = Decimal("0.07")   # 7% annual fallback

def get_monthly_rf_rate(
    check_date: date,
    db_path: str | None = None,
) -> Decimal:
    """
    Return the annualised risk-free rate as a Decimal for the given month.

    Lookup order:
    1. Query mf_nav_snapshots for a liquid fund scheme (AMFI code: configurable,
       default 102885 = SBI Liquid Fund — Direct) for the 12-month window ending
       check_date. Compute annualised return = (end_nav / start_nav) ** (12/months) - 1.
       Return as Decimal if at least 11 months of data available.
    2. Fallback: return DEFAULT_RF_RATE (7%).

    Never raises — falls back to DEFAULT_RF_RATE on any error and logs WARNING.
    """

def annualised_to_period(annual_rate: Decimal, months: int) -> Decimal:
    """
    Convert annualised rate to equivalent N-month return.
    Formula: (1 + annual_rate) ** (months / 12) - 1
    """
```

**Tests (`tests/unit/instruments/test_rf_rate.py`):**
- `get_monthly_rf_rate` with mocked DB returning 12 months of NAV → returns computed rate (not fallback).
- `get_monthly_rf_rate` with empty DB (no NAV rows) → returns `DEFAULT_RF_RATE`.
- `get_monthly_rf_rate` with <11 months of data → returns `DEFAULT_RF_RATE`.
- `annualised_to_period(Decimal("0.07"), 12)` ≈ `Decimal("0.07")` (within 0.001).
- `annualised_to_period(Decimal("0.07"), 6)` < `Decimal("0.07")` (shorter period → smaller return).

**Commit:** `feat(instruments): add rf_rate — monthly risk-free rate from AMFI NAV with fallback (SE1.3)`

---

## SE2.1 — `src/strategy/` package setup

**Files to change:**
- `src/strategy/__init__.py` — package stub (comment line only)
- `src/strategy/CLAUDE.md` — module invariants and conventions
- `src/strategy/signals/__init__.py` — sub-package stub

**Before any code:**
`bash ls src/strategy/` — confirm does NOT exist (expected: no such directory).

**`src/strategy/CLAUDE.md` content:**

```markdown
# src/strategy/ — Module Context

## Invariants

1. **Signal generators are pure functions over DataFrames.** No I/O in signal generators.
   All data (OHLC, VIX, regime tags) is loaded before calling `generate()`. Network calls
   belong in scripts, not in this module.

2. **No BrokerClient dependency in signal generators.** Signal generators consume Parquet
   DataFrames only. The `SpreadSelector` in `execution.py` consumes a live `OptionChain`
   model (from `src/models/options.py`) — this is the only place `BrokerClient` data enters.

3. **Config dataclasses are frozen.** Every strategy has a `*Config` frozen dataclass with
   explicit parameter fields. Default values match the research document initial parameters.
   Sweep ranges are in comments.

4. **`RegimeTag` is the authority on regime classification.** Do not re-derive trend or vol
   labels from raw data in signal generators — call `RegimeTagger.tag_history(df)` once and
   attach the tags to the DataFrame before running any signal generator.

5. **VIX-IVP filters use 63-day trailing percentile rank.** Never use raw VIX level as a
   filter threshold. Use `percentile_rank(vix_series[-63:], current_vix)`.

6. **Calendar exclusions are in `src/market_calendar/`.** Do not hard-code dates in signal
   generators — call `is_event_exclusion_date(date) -> tuple[bool, str | None]`.
```

**No tests required.** Package init files and CLAUDE.md are not unit-tested.
**Commit:** `chore(strategy): add src/strategy/ package setup + CLAUDE.md invariants (SE2.1)`

---

## SE2.2 — `src/strategy/regime.py`: regime classifier

**Files to change:**
- `src/strategy/regime.py` — `RegimeTag` frozen dataclass + `RegimeTagger` class
- `src/backtest/signal_eval_store.py` — new store (init_db + regime_tags CRUD); this store will be extended by SE3.1 and SE4.1
- `tests/unit/strategy/test_regime.py` — new test file
- `tests/unit/strategy/__init__.py` — new test package stub
- `tests/unit/backtest/test_signal_eval_store.py` — new test file (regime-related methods only)

**Before any code:**
`search_graph("BacktestStore")` — confirm existing store pattern for init_db/CRUD;
`get_code_snippet("OptionChainStrike")` — confirm Decimal/float conventions in models;
`search_code("percentile_rank")` or `search_code("percentileofscore")` in `src/` — existing usage.

**What to implement (`src/strategy/regime.py`):**

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import numpy as np
import pandas as pd

TREND_SLOPE_WINDOW  = 50   # days
TREND_ATR_WINDOW    = 50   # days (normalisation)
VIX_PERCENTILE_WINDOW = 252  # days

TREND_UP_THRESHOLD   = 1.0
TREND_DOWN_THRESHOLD = -1.0
VIX_HIGH_THRESHOLD   = 0.75
VIX_LOW_THRESHOLD    = 0.25


@dataclass(frozen=True)
class RegimeTag:
    tag_date:         date
    trend_score:      float      # slope / ATR, dimensionless
    trend_label:      str        # "trending_up" | "range_bound" | "trending_down"
    vix_percentile:   float      # 0.0–1.0
    vol_label:        str        # "high_vol" | "normal_vol" | "low_vol"
    regime_cell:      str        # "{trend_label}|{vol_label}"
    atr_14:           float      # 14D ATR in Nifty points
    atr_40:           float      # 40D ATR in Nifty points
    atr_pct_rank_252: float | None  # None if < 252 bars available


class RegimeTagger:
    """
    Tags every trading day with its 3×3 regime cell.

    Dimension 1 (trend): 50D linear regression slope of daily close,
      normalised by 50D ATR. Dimensionless trend score.
    Dimension 2 (vol): trailing 252D VIX percentile rank.

    See BACKTEST_PLAN_PHASE1.md §2.S1 for full gate criteria.
    Multi-timeframe note from DECISIONS.md: tag both daily and weekly bars
    when called from paper trading scripts; the weekly regime vetoes
    daily for strangle entry decisions.
    """

    def tag_history(
        self,
        nifty_df: pd.DataFrame,
        vix_df: pd.DataFrame,
    ) -> list[RegimeTag]:
        """
        Tag all rows in nifty_df with regime.

        nifty_df must have: date (index or column), close, high, low.
        vix_df must have: date (index or column), close (India VIX daily close).
        Both DataFrames must be sorted ascending by date.
        Rows with insufficient lookback history return NaN trend_score and
        are tagged "range_bound|normal_vol" (conservative default).
        """

    def tag_date(
        self,
        nifty_df: pd.DataFrame,
        vix_df: pd.DataFrame,
        target_date: date,
    ) -> RegimeTag:
        """
        Tag a single date. nifty_df and vix_df must include sufficient
        history before target_date (≥252 rows for full accuracy).
        Raises ValueError if target_date not found in nifty_df.
        """
```

ATR formula: `pd.DataFrame.rolling(n).apply(lambda w: true_range_mean(w))` using Wilder's
smoothing or simple rolling mean — document choice in docstring. Use simple rolling mean for
consistency with the research doc.

Slope formula: `numpy.polyfit(range(n), close_window, 1)[0]` — slope of degree-1 polynomial.
Trend score = `slope / ATR_50`.

VIX percentile: `scipy.stats.percentileofscore(vix_series[-252:], current_vix) / 100`.
If fewer than 252 VIX rows, use all available rows and log DEBUG.

**`src/backtest/signal_eval_store.py`** — new store class (extended in SE3.1 and SE4.1):

```python
class SignalEvalStore:
    """Persistence layer for regime_tags, swing_signals, allocation_decisions."""
    def __init__(self, db_path: str): ...
    def init_db(self) -> None: ...              # creates all 3 tables + indexes (idempotent)
    def record_regime_tag(self, tag: RegimeTag) -> None: ...   # INSERT OR REPLACE
    def get_regime_tag(self, tag_date: date) -> RegimeTag | None: ...
    def get_regime_tags(self, from_date: date, to_date: date) -> list[RegimeTag]: ...
```

DDL: use exact schema from `docs/plan/signals-eval-core/schema.md`.

**Tests (`tests/unit/strategy/test_regime.py`):**
- `tag_history` on 300-day synthetic DataFrame with monotone increasing close and flat VIX (15th pctile) → all post-warm-up rows labelled "trending_up|low_vol".
- Monotone decreasing close + VIX at 80th pctile → "trending_down|high_vol".
- Flat close + VIX at 50th pctile → "range_bound|normal_vol".
- Fewer than 50 rows of history → row tagged "range_bound|normal_vol" (insufficient history default).
- `tag_date` with valid target_date → returns single `RegimeTag`; `regime_cell` is pipe-delimited string.
- `tag_date` with target_date not in DataFrame → `ValueError`.

**Tests (`tests/unit/backtest/test_signal_eval_store.py`):**
- `init_db` called twice → no error (idempotent).
- `record_regime_tag` → `get_regime_tag` round-trip: all float fields survive.
- `record_regime_tag` twice for same date → OR REPLACE, row count stays 1.
- `get_regime_tag` on missing date → `None`.
- `get_regime_tags` date range → only rows within range returned.

**Commit:** `feat(strategy): add RegimeTagger + SignalEvalStore regime CRUD (SE2.2)`

---

## SE2.3 — `scripts/regime_distribution_report.py`

**Files to change:**
- `scripts/regime_distribution_report.py` — new script (no unit tests)

**Before any code:**
`get_code_snippet("RegimeTagger")` — constructor and `tag_history` signature;
`search_code("NIFTY_OHLC_PARQUET")` or similar — confirm Parquet path for Nifty daily data.

**What to implement:**
Script that loads full Nifty daily OHLC and VIX Parquet, calls `RegimeTagger().tag_history()`,
then prints a distribution table:

```
Regime Distribution Report
Training period: 2019-01-01 → 2023-12-31 (pre-Jan 2024 train set)
Total trading days: 1234

Regime Cell                  | Days  | % Days | % Nifty Return
-----------------------------|-------|--------|---------------
trending_up   | normal_vol  |  412  |  33.4% |   +62.1%
trending_up   | low_vol     |  189  |  15.3% |   +28.4%
trending_up   | high_vol    |   78  |   6.3% |   +11.2%
range_bound   | normal_vol  |  ...
...
```

Also prints: "Gate check: no single cell >40% of trading days — PASS / FAIL".
Saves the tagged DataFrame to `data/historical/regime/regime_tags_YYYYMMDD.parquet`.

**No unit tests.** Visual inspection script.
**Commit:** `feat(scripts): regime_distribution_report.py — SE2.3 regime distribution gate`

---

## SE3.1 — `src/strategy/signals/donchian.py` + SwingSignal model + store extension

**Files to change:**
- `src/strategy/signals/donchian.py` — `DonchianConfig` + `DonchianSignalGenerator`
- `src/strategy/signals/models.py` — `SwingSignal` frozen dataclass (shared across SE3.x)
- `src/strategy/signals/__init__.py` — update stub to export `SwingSignal`
- `src/backtest/signal_eval_store.py` — extend with `record_swing_signal` + `get_swing_signals`
- `tests/unit/strategy/signals/__init__.py` — new test package stub
- `tests/unit/strategy/signals/test_donchian.py` — new test file
- `tests/unit/backtest/test_signal_eval_store.py` — extend with swing signal CRUD tests

**Before any code:**
`get_code_snippet("RegimeTag")` — frozen dataclass fields;
`get_code_snippet("SignalEvalStore")` — current public API (post SE2.2);
`search_graph("SwingSignal")` — confirm does NOT yet exist.

**Council constraints (from `docs/archive/council/strategy/2026-04-30_donchian-roll-mechanics.md`):**
- Signal-in-only architecture (NOT always-in). Flat between signals — no position during consolidation.
- ATR-proportional spread width: `min(round_to_50(0.8 × ATR_40d), 500)`, floor 150 points.
- 21-DTE management rule: if trade reaches 21 DTE with ≥50% profit captured, close.

**`SwingSignal` frozen dataclass:**
```python
@dataclass(frozen=True)
class SwingSignal:
    signal_date:    date
    strategy:       str        # "donchian" | "orb" | "gap_fade"
    direction:      str        # "LONG" | "SHORT" | "FLAT" | "NO_TRADE"
    trigger_price:  Decimal | None
    stop_level:     Decimal | None
    target_level:   Decimal | None  # None for Donchian (trailing stop, not fixed target)
    atr_value:      Decimal | None
    or_high:        Decimal | None  # ORB only
    or_low:         Decimal | None  # ORB only
    gap_size_pct:   Decimal | None  # Gap Fade only
    expiry_date:    date | None     # ORB + Gap Fade only
    regime_cell:    str
    excluded_reason: str | None
```

**`DonchianConfig` frozen dataclass:**
```python
@dataclass(frozen=True)
class DonchianConfig:
    channel_lookback: int = 40    # sweep 20–60 step 5
    atr_stop_mult:    float = 3.0  # sweep 2.0–4.5 step 0.5
    atr_lookback:     int = 20     # sweep 14, 20
    width_mult_k:     float = 0.8  # spread width factor; sweep 0.6–1.0 step 0.1
```

**`DonchianSignalGenerator.generate(df, regime_tags) → list[SwingSignal]`:**
- Input: daily OHLC DataFrame + pre-computed `list[RegimeTag]` (keyed by date).
- Signal logic: close > N-day channel high → LONG; close < N-day channel low → SHORT.
- A new breakout in the opposite direction while holding → exits current signal, emits reverse signal.
- No signal for the first `channel_lookback` days (warm-up).
- Trailing stop: `stop_level = entry_price ± (atr_stop_mult × atr_value)`, recalculated daily.
  When stop triggers, emit FLAT signal. Next signal only on next fresh channel breakout.
- `spread_width` is NOT stored on `SwingSignal` (it's computed at execution time in SE5.3).

**Tests (`tests/unit/strategy/signals/test_donchian.py`):**
- 100-bar synthetic DataFrame with sustained uptrend after bar 50 → at least one LONG signal after warm-up.
- Downtrend after LONG signal → SHORT signal emitted; prior LONG position implicitly closed.
- Stop trigger: price reverses 3× ATR from entry → FLAT signal emitted; no new signal until next breakout.
- Flat period (price oscillates within channel) → no signal (only FLAT).
- First `channel_lookback` bars → no signals.
- All signals have non-null `regime_cell`.

**Commit:** `feat(strategy): add DonchianSignalGenerator + SwingSignal model + store CRUD (SE3.1)`

---

## SE3.2 — `src/strategy/signals/orb.py`: ORB signal generator

**Files to change:**
- `src/strategy/signals/orb.py` — `ORBConfig` + `ORBSignalGenerator`
- `src/market_calendar/exclusions.py` — `is_event_exclusion_date(date) → tuple[bool, str | None]`
  (if not already implemented; check `search_graph("is_event_exclusion_date")` first)
- `tests/unit/strategy/signals/test_orb.py` — new test file

**Before any code:**
`get_code_snippet("SwingSignal")` — frozen dataclass fields;
`get_code_snippet("RegimeTag")` — for regime_cell;
`search_graph("is_event_exclusion_date")` — confirm if already exists in `src/market_calendar/`;
`search_graph("select_expiry")` or `get_code_snippet("get_expiry_candidates")` — expiry selection logic;
`search_code("vix_ivp")` in `src/` — any existing VIX percentile rank utility.

**Council constraints (from `docs/archive/council/strategy/2026-05-01_orb-volatility-filter-design.md`):**
- Primary ATR filter: OR width < (fraction × 14D ATR).
- VIX-IVP structural exclusion: skip when 63D IVP ≥ 90th percentile. Binary flag `vix_exclusion_enabled = True`. NOT a swept parameter.
- Structural calendar exclusions: weekly expiry Thursdays, RBI MPC days, Budget day, FOMC+1 IST days.
- DTE floor: minimum 3 DTE for any spread entry. ≤2 DTE → skip to next weekly (+7 calendar days).
- Expiry on close of breakout candle (not intraday).

**`ORBConfig` frozen dataclass:**
```python
@dataclass(frozen=True)
class ORBConfig:
    opening_candles:         int   = 2      # sweep 1–3 step 1 (15-min bars)
    or_width_fraction:       float = 0.6   # sweep 0.3–0.8 step 0.1
    rr_multiple:             float = 1.5   # sweep 1.0–2.5 step 0.5
    vix_exclusion_enabled:   bool  = True  # NOT swept — ablation flag only
    vix_ivp_threshold:       float = 0.90  # 63D IVP threshold (fixed; not swept)
    vix_lookback_days:       int   = 63
```

**`ORBSignalGenerator.generate(daily_df, intraday_df, vix_df, regime_tags) → list[SwingSignal]`:**
- One entry per qualifying day per direction (max 2 signals per day — long OR short break).
- Entry price = close of breakout 15-min candle.
- Target = entry ± (rr_multiple × OR width). Stop = session high/low of first N candles.
- `expiry_date` set by DTE rule: find next Thursday ≥3 DTE from signal_date.

**`is_event_exclusion_date(d: date) → tuple[bool, str | None]`:**
Returns `(True, "reason_string")` for excluded dates, `(False, None)` otherwise.
Reason strings: `"thursday_expiry"`, `"rbi_mpc_day"`, `"budget_day"`, `"fomc_plus1"`.
Hard-code known 2019–2026 RBI MPC and Budget dates. FOMC+1 is the next NSE session after
each FOMC meeting date (hard-coded list for 2019–2026). Log a WARNING if the requested date
is beyond the hard-coded calendar range.

**Tests (`tests/unit/strategy/signals/test_orb.py`):**
- Day with OR width < 0.6× ATR → LONG signal when close breaks above OR high.
- Day with OR width > 0.6× ATR → NO_TRADE (width filter fires).
- Day with VIX-IVP ≥ 90th pctile AND `vix_exclusion_enabled=True` → NO_TRADE; `excluded_reason="vix_ivp_above_90th"`.
- `vix_exclusion_enabled=False` → same day → signal NOT excluded (ablation path).
- Thursday expiry day → NO_TRADE; `excluded_reason="thursday_expiry"`.
- RBI MPC day (one of the hard-coded dates) → NO_TRADE; `excluded_reason="rbi_mpc_day"`.
- DTE ≤2 on nearest Thursday → `expiry_date` jumps to next Thursday (+7 days).
- DTE ≥3 on nearest Thursday → `expiry_date` is that Thursday.

**Commit:** `feat(strategy): add ORBSignalGenerator + calendar exclusions + DTE selection (SE3.2)`

---

## SE3.3 — `src/strategy/signals/gap_fade.py`: gap fade signal generator

**Files to change:**
- `src/strategy/signals/gap_fade.py` — `GapFadeConfig` + `GapFadeSignalGenerator`
- `tests/unit/strategy/signals/test_gap_fade.py` — new test file

**Before any code:**
`get_code_snippet("SwingSignal")` — frozen dataclass fields;
`get_code_snippet("ORBConfig")` — reuse VIX-IVP pattern;
`get_code_snippet("is_event_exclusion_date")` — for consistency (gap fade does NOT exclude
RBI/Budget days, but does exclude Thursday expiry; document this asymmetry).

**Council constraints (from `docs/archive/council/strategy/2026-05-02_gap-fade-vix-filter-threshold.md`):**
- VIX-IVP threshold: 75th percentile (63D lookback). `vix_ivp_threshold = 0.75`.
- Asymmetric with ORB (90th) — this is MANDATORY, not an error. Different failure modes.
- Mandatory ablation: report Sharpe at [0.70, 0.75, 0.80, 0.85] in Phase SE6 walk-forward.
- DTE floor: same as ORB — minimum 3 DTE, ≤2 → skip to next weekly.
- Entry at close of 2nd 15-min candle (9:45 IST), NOT on the breakout candle.
- Hard exit at 12:30 IST (gap fills that haven't happened by lunch rarely complete).

**`GapFadeConfig` frozen dataclass:**
```python
@dataclass(frozen=True)
class GapFadeConfig:
    min_gap_pct:         float = 0.003   # 0.3%; sweep 0.002–0.005 step 0.001
    max_gap_pct:         float = 0.010   # 1.0%; sweep 0.007–0.015 step 0.001
    fill_fraction:       float = 0.5    # sweep 0.3–0.7 step 0.1
    vix_ivp_threshold:   float = 0.75   # 63D IVP; NOT swept (ablation only)
    vix_lookback_days:   int   = 63
```

**`GapFadeSignalGenerator.generate(daily_df, intraday_df, vix_df, regime_tags) → list[SwingSignal]`:**
- Gap up (open > prev_close by min–max range) → short signal (price fades back toward prev_close).
- Gap down → long signal.
- Entry at close of 2nd 15-min candle. Stop at session high/low established in first 2 candles.
- Target = open ± (fill_fraction × gap_size_points). Hard exit at 12:30.
- `expiry_date` by same DTE rule as ORB.

**Tests (`tests/unit/strategy/signals/test_gap_fade.py`):**
- Gap-up 0.5% (within 0.3–1.0%) + VIX IVP at 60th pctile → SHORT signal.
- Gap-up 0.5% + VIX IVP at 80th pctile (≥0.75) → NO_TRADE; `excluded_reason="vix_ivp_above_75th"`.
- Gap-up 1.5% (>max_gap_pct) → NO_TRADE (gap too large, not a correlation-driven gap).
- Gap-up 0.1% (<min_gap_pct) → NO_TRADE (gap too small).
- Thursday expiry day → NO_TRADE; `excluded_reason="thursday_expiry"`.
- VIX exclusion: `vix_ivp_threshold=0.70` → same day at 72nd pctile → now excluded.
- `gap_size_pct` field on returned signal ≈ (open - prev_close) / prev_close.

**Commit:** `feat(strategy): add GapFadeSignalGenerator with VIX-IVP 75th pctile filter (SE3.3)`

---

## SE4.1 — `src/strategy/signals/sma_filter.py` + AllocationDecision model + store extension

**Files to change:**
- `src/strategy/signals/sma_filter.py` — `SMAFilterConfig` + `SMASignalGenerator`
- `src/strategy/signals/models.py` — add `AllocationDecision` frozen dataclass
- `src/backtest/signal_eval_store.py` — extend with `record_allocation_decision` + `get_allocation_decisions`
- `tests/unit/strategy/signals/test_sma_filter.py` — new test file
- `tests/unit/backtest/test_signal_eval_store.py` — extend with allocation CRUD tests

**Before any code:**
`get_code_snippet("SwingSignal")` — existing `models.py` for co-location of AllocationDecision;
`get_code_snippet("SignalEvalStore")` — current API;
`search_graph("AllocationDecision")` — confirm does NOT yet exist.

**`AllocationDecision` frozen dataclass:**
```python
@dataclass(frozen=True)
class AllocationDecision:
    decision_date:    date
    strategy:         str      # "sma_v1" | "dual_mom_v1" | "pe_band_v1"
    signal_value:     Decimal  # current indicator value (monthly close, return, or PE)
    signal_reference: Decimal  # threshold being compared (SMA value, RF rate, PE threshold)
    allocation_pct:   Decimal  # 0.0, 0.30, 0.70, or 1.0
    allocation_reason: str     # one-line
    regime_cell:      str | None
```

**`SMAFilterConfig` frozen dataclass:**
```python
@dataclass(frozen=True)
class SMAFilterConfig:
    sma_lookback_months:  int = 10   # sweep 8–14 step 1
    reentry_delay_months: int = 0    # sweep 0–2 step 1
```

**`SMASignalGenerator.generate(monthly_df, regime_tags=None) → list[AllocationDecision]`:**
- Input: monthly OHLC DataFrame (last trading day of each month = monthly close).
- Signal: close > N-month SMA → 100% allocation. Close < SMA → 0% allocation.
- `reentry_delay_months`: require N consecutive months above SMA before re-entry.
- Decision emitted on the last trading day of each month.
- `signal_value` = current monthly close; `signal_reference` = current SMA value.

**Tests (`tests/unit/strategy/signals/test_sma_filter.py`):**
- 24-month synthetic series with close persistently above 10-month SMA → all decisions are 100%.
- 24-month series with close dropping below SMA at month 12 → allocation drops to 0% from that month.
- `reentry_delay_months=1`: one month of close > SMA alone is insufficient; needs 2 consecutive months → allocation stays 0% after one month recovery.
- Fewer than `sma_lookback_months` bars → no decisions (insufficient warm-up).
- Decision `allocation_reason` contains "SMA" keyword.

**Store extension tests:**
- `record_allocation_decision` + `get_allocation_decisions` round-trip: Decimal fields survive.
- `get_allocation_decisions` with strategy filter → only matching rows returned.
- `record_allocation_decision` twice same date+strategy → OR REPLACE, count stays 1.

**Commit:** `feat(strategy): add SMASignalGenerator + AllocationDecision model + store CRUD (SE4.1)`

---

## SE4.2 — `src/strategy/signals/dual_mom.py`: dual momentum signal generator

**Files to change:**
- `src/strategy/signals/dual_mom.py` — `DualMomConfig` + `DualMomSignalGenerator`
- `tests/unit/strategy/signals/test_dual_mom.py` — new test file

**Before any code:**
`get_code_snippet("AllocationDecision")` — frozen dataclass fields;
`get_code_snippet("get_monthly_rf_rate")` — RF rate helper signature;
`get_code_snippet("annualised_to_period")` — helper.

**`DualMomConfig` frozen dataclass:**
```python
@dataclass(frozen=True)
class DualMomConfig:
    abs_lookback_months: int     = 12    # sweep 6–15 step 3
    rel_lookback_months: int     = 12    # sweep 6–15 step 3
    rf_rate_annual:      Decimal = Decimal("0.07")  # sweep 0.05–0.08 step 0.01
```

**`DualMomSignalGenerator.generate(monthly_df, rf_series=None) → list[AllocationDecision]`:**
- Both conditions required for 100% allocation:
  1. Absolute: Nifty trailing N-month return > 0%.
  2. Relative: Nifty trailing N-month return > `annualised_to_period(rf_rate, N)`.
- Either fails → 0% allocation (exit to cash).
- `signal_value` = trailing N-month return as Decimal.
- `signal_reference` = N-month equivalent of RF rate.
- `allocation_reason` must state which condition failed (e.g. "absolute_momentum_negative").

**Tests (`tests/unit/strategy/signals/test_dual_mom.py`):**
- Both conditions pass → 100% allocation.
- Trailing return = −5% (absolute fails) → 0%; reason contains "absolute_momentum".
- Trailing return = +4%, RF equivalent = +5.8% (relative fails) → 0%; reason contains "relative_momentum".
- Both fail → 0% (only one reason needed, log the first failure).
- `rf_series=None` → uses `DualMomConfig.rf_rate_annual` as fallback (not `get_monthly_rf_rate`).
- Fewer than `rel_lookback_months` bars → no decisions.

**Commit:** `feat(strategy): add DualMomSignalGenerator — absolute + relative momentum filter (SE4.2)`

---

## SE4.3 — `src/strategy/signals/pe_band.py`: PE band rebalancing signal generator

**Files to change:**
- `src/strategy/signals/pe_band.py` — `PEBandConfig` + `PEBandSignalGenerator`
- `tests/unit/strategy/signals/test_pe_band.py` — new test file

**Before any code:**
`get_code_snippet("AllocationDecision")` — frozen dataclass fields;
`get_code_snippet("get_pe_series")` — PE data loader signature;
`get_code_snippet("SMASignalGenerator")` — reuse monthly decision pattern.

**`PEBandConfig` frozen dataclass:**
```python
@dataclass(frozen=True)
class PEBandConfig:
    low_pe_threshold:       Decimal = Decimal("18")   # sweep 15–20 step 1
    high_pe_threshold:      Decimal = Decimal("25")   # sweep 23–28 step 1
    intermediate_alloc_pct: Decimal = Decimal("0.70") # sweep 0.50–0.80 step 0.10
    floor_alloc_pct:        Decimal = Decimal("0.30") # fixed — NiftyBees collateral floor
```

**`PEBandSignalGenerator.generate(pe_df, quarterly_dates) → list[AllocationDecision]`:**
- Allocation rules:
  - PE < low_threshold → 100%
  - low_threshold ≤ PE ≤ high_threshold → intermediate_alloc_pct (default 70%)
  - PE > high_threshold → floor_alloc_pct (default 30%)
- Decision emitted only on `quarterly_dates` (quarterly rebalancing cadence), not on every PE change.
- `quarterly_dates`: list of dates (last trading day of Jan, Apr, Jul, Oct each year).
- `signal_value` = PE at decision_date; `signal_reference` = whichever threshold governs the allocation.

**Tests (`tests/unit/strategy/signals/test_pe_band.py`):**
- PE = 15 (< 18) → 100% allocation.
- PE = 22 (between 18–25) → 70% allocation.
- PE = 27 (> 25) → 30% allocation (floor, not 0%, because of collateral constraint).
- Allocation only changes on quarterly dates — mid-quarter PE change is ignored.
- `signal_reference` = `low_pe_threshold` when PE is below it; `high_pe_threshold` when above.
- `allocation_reason` contains PE value and which band it falls in.

**Commit:** `feat(strategy): add PEBandSignalGenerator with quarterly rebalancing cadence (SE4.3)`

---

## SE4.4 — Covered Call Overlay: strategy doc + paper-trading setup

> **Type:** Yield enhancement overlay — not a signal generator. No backtest engine required.
> Validation is a 6-month paper overlay period, not a walk-forward pipeline.
> Full spec lives at `docs/strategies/covered_call_overlay_v1.md`.
> The task for this story is to create that doc, confirm broker mechanics, and begin paper trading.

**Files to change:**
- `docs/strategies/covered_call_overlay_v1.md` — new strategy doc (primary deliverable)
- Paper trades recorded via `record_paper_trade.py` (no code changes to the tool itself)
- After task completion: note broker compatibility status in `DECISIONS.md`

**Before any code:**
`get_code_snippet("record_paper_trade")` — confirm CLI interface and `leg_role` values;
`search_code("paper_csp_nifty_v1")` — confirm naming convention for paper strategy prefixes.

**Prerequisite (HARD BLOCK — do not paper-trade until confirmed):**
Contact Upstox support to verify: NiftyBees ETF units pledged as Finideas margin collateral
can simultaneously serve as the covered leg for a short Nifty 50 call position. These are
two margin obligations on the same asset. If Upstox treats them as separate margin blocks,
the short call must be cash-margined independently — the capital efficiency argument changes
and the position size may need revision.

Record the broker's response in `docs/strategies/covered_call_overlay_v1.md` under a
"Broker Mechanics" section. Status must be either ✅ Confirmed or ⛔ Blocked before
paper trading can start.

**What `docs/strategies/covered_call_overlay_v1.md` must contain:**

**Header table:**
```
Name:          Covered Call Overlay on NiftyBees / Nifty 50 v1
Version:       v1
Underlying:    Nifty 50 index options (NSE_INDEX|Nifty 50) for the short call leg
Collateral:    NiftyBees ETF units already pledged (NSE_EQ|INF204KB14I2)
Instrument:    Nifty 50 monthly call options — same expiry cycle as CSP
Strategy type: Yield enhancement overlay (always-on, not an allocation strategy)
Status:        Pending broker confirmation
```

**Core parameters:**
- Call delta target: 15 (sweep 10–20 in future paper calibration, step 5)
- Exit profit target: 50% of credit collected
- IVR filter: skip cycle if IVR < 25 (trailing 252D VIX percentile) — same R3 discipline as CSP
- Entry window: Wednesday after most recent monthly expiry (same as CSP); coordinate with CSP so both legs enter the same cycle
- Time stop: 21 calendar days from entry
- Delta stop: close immediately if call delta crosses +0.40
- Quantity: maximum 1 lot (65 units) per ~5,700 NiftyBees units pledged; recompute at each annual NiftyBees leg reset

**Entry logic:**
Sell 1 Nifty 50 monthly call at the 15-delta strike, same expiry as the CSP short put.
Use live Upstox option chain for delta. Limit order at mid of bid/ask; same ₹0.25 improvement
discipline as CSP if unfilled after 5 minutes. Log India VIX + IVR at every entry decision,
including cycles where entry is skipped due to IVR filter.

**Exit rules (first to fire wins):**
1. Profit target: close when mark-to-market value decays to ≤50% of entry credit.
2. Time stop: 21 calendar days from entry.
3. Delta stop: close when call delta > +0.40.

**Expected yield (indicative):**
15-delta OTM Nifty monthly call at IVR ~35 collects ₹55–85/unit × 65 units = ₹3,575–5,525
gross credit. Net of ₹80–100 round-trip costs per lot: **₹3,475–5,425 per cycle**.
On ₹15.5L NiftyBees notional ≈ **0.22–0.35% per cycle; 2.7–4.2% annualised**.

**Portfolio context:**
Running CSP (short put) + Covered Call (short call) in the same monthly cycle creates a
synthetic short strangle at the portfolio level. When Iron Condor is eventually deployed,
evaluate retiring the standalone Covered Call leg to avoid position overlap and double margin.

**Paper trading:**
- Prefix: `paper_covered_call_v1`
- Duration: minimum 6 months (2 rebalance events minimum per strategy; 6 gives 5–6 cycles)
- Retrospective Bhavcopy cross-check: once SE7.1 Bhavcopy data is available, cross-check
  paper entry/exit prices against Bhavcopy settle_price for validation
- Report: paper trading report after 6 months; comparison to indicative yield range above

**No unit tests.** This task produces a strategy doc and paper trades, not library code.

**Commit:** `docs(strategies): add covered_call_overlay_v1.md — yield overlay on pledged NiftyBees (SE4.4)`

---

## SE5.1 — `src/backtest/points_bt.py`: Tier 1 points-based backtester

**Files to change:**
- `src/backtest/points_bt.py` — `PointsBacktesterConfig` + `PointsBacktester`
- `tests/unit/backtest/test_points_bt.py` — new test file

**Before any code:**
`get_code_snippet("BacktestStore")` — `record_trade`, `record_daily_pnl` API from backtest-eval-core;
`get_code_snippet("SwingSignal")` — frozen dataclass fields;
`get_code_snippet("DonchianConfig")` — for expected signal format.

**What to implement:**

```python
@dataclass(frozen=True)
class PointsBacktesterConfig:
    brokerage_per_roundtrip: Decimal = Decimal("40")   # ₹
    slippage_points_per_side: Decimal = Decimal("0.5") # Nifty points
    lot_size: int = 75                                  # Nifty lot size (Nov 2024+)
```

`PointsBacktester.run(signals, nifty_df, config, run_id, store) → BacktestResult`:
- `signals`: `list[SwingSignal]` from any swing generator.
- `nifty_df`: daily OHLC DataFrame.
- `run_id`: written to `BacktestStore`.
- Each trade: entry on signal trigger date close; exit on stop or target or next opposite signal.
- P&L in Nifty points. Mark-to-market daily (unrealised equity curve via `record_daily_pnl`).
- Trade P&L: `(exit_price − entry_price) × direction_sign − 2 × slippage_points`.
- `BacktestResult` frozen dataclass: `run_id, total_trades, win_rate, avg_pnl_points, max_dd_points, calmar_ratio`.

**Donchian pass criteria (must document in test):** trade count 15–25/year, win rate 35–50%, profit factor >1.3. Tests do not validate these thresholds (too few synthetic bars for reliable stats), but the test docstring notes them as the Phase 2.S3a gate.

**Tests (`tests/unit/backtest/test_points_bt.py`):**
- Empty signals list → `BacktestResult` with zero trades, no error.
- Single LONG signal followed by stop trigger → one trade in `BacktestStore`; P&L negative (stop loss).
- Single LONG signal followed by higher close → one trade; P&L positive.
- Slippage applied: gross P&L reduced by `2 × slippage_points_per_side`.
- Mark-to-market: daily equity curve rows written for all days a position is open.
- FLAT signal (no active position) → no daily MTM row written.

**Commit:** `feat(backtest): add PointsBacktester — Tier 1 points-based swing backtester (SE5.1)`

---

## SE5.2 — `src/backtest/allocation_bt.py`: investment strategy backtester

**Files to change:**
- `src/backtest/allocation_bt.py` — `AllocationBacktesterConfig` + `AllocationBacktester`
- `tests/unit/backtest/test_allocation_bt.py` — new test file

**Before any code:**
`get_code_snippet("AllocationDecision")` — frozen dataclass fields;
`get_code_snippet("BacktestStore")` — API;
`get_code_snippet("get_monthly_rf_rate")` — for cash return computation.

**What to implement:**

```python
@dataclass(frozen=True)
class AllocationBacktesterConfig:
    roundtrip_cost:     Decimal = Decimal("100")  # ₹ per round-trip (conservative for large ETF orders)
    cash_rf_annual:     Decimal = Decimal("0.07") # annual return on cash during out-of-market periods
```

`AllocationBacktester.run(decisions, niftybees_df, config, run_id, store) → BacktestResult`:
- `decisions`: `list[AllocationDecision]`.
- `niftybees_df`: daily NiftyBees close prices.
- Between allocation changes, track daily equity value = allocated_pct × units × NAV + cash × (1 + daily_cash_rate).
- Cash return computed from `cash_rf_annual` (convert to daily: `(1 + annual) ** (1/252) - 1`).
- Transaction cost deducted at each allocation change (buy or sell).
- Buy-and-hold baseline equity curve computed in parallel (100% allocation always).
- `BacktestResult` extended: add `buyhold_calmar`, `buyhold_max_dd` fields.

**Tests (`tests/unit/backtest/test_allocation_bt.py`):**
- 100% allocation throughout → performance matches buy-and-hold (minus initial cost of entry).
- 0% allocation throughout → equity curve grows at cash rate.
- Allocation change from 100% to 0% → transaction cost deducted once; equity drops by cost amount.
- Cash return applied correctly: 30-day flat period with 0% allocation → equity grows by ~0.57% (7%/12).
- Buy-and-hold Calmar field populated.

**Commit:** `feat(backtest): add AllocationBacktester — NiftyBees allocation backtester with cash return (SE5.2)`

---

## SE5.3 — `src/strategy/execution.py`: spread selector

**Files to change:**
- `src/strategy/execution.py` — `SpreadSpec` frozen dataclass + `SpreadSelector`
- `tests/unit/strategy/test_execution.py` — new test file

**Before any code:**
`get_code_snippet("OptionChain")` and `get_code_snippet("OptionLeg")` — existing models;
`get_code_snippet("SwingSignal")` — fields consumed by SpreadSelector;
`search_graph("parse_upstox_option_chain")` — confirm OptionChain source.

**`SpreadSpec` frozen dataclass:**
```python
@dataclass(frozen=True)
class SpreadSpec:
    signal_date:    date
    direction:      str        # "LONG_PUT_SPREAD" | "SHORT_CALL_SPREAD"
    short_strike:   int
    long_strike:    int
    spread_width:   int        # points
    short_delta:    Decimal    # at entry; ~0.15 target
    expiry_date:    date
    net_credit:     Decimal | None  # None in backtest (not a live OptionChain)
    atr_40d:        Decimal    # ATR used for width calculation
    k_multiplier:   Decimal    # width_mult_k used (from DonchianConfig or default)
```

**`SpreadSelector.select(signal, option_chain, k=0.8) → SpreadSpec`:**
- `spread_width = min(round_to_50(int(k × atr_40d)), 500)`, floor 150 points.
- Short strike: find the option leg in `option_chain` with |delta| closest to 0.15.
- Long strike: `short_strike ± spread_width` (direction-dependent).
- LONG signal → bull put spread (short put + long put further OTM).
- SHORT signal → bear call spread (short call + long call further OTM).
- Raises `ValueError` if no option leg with |delta| in [0.10, 0.25] found.

`round_to_50(n: int) → int`: round n to nearest 50 (utility function, also exported).

**Tests (`tests/unit/strategy/test_execution.py`):**
- `round_to_50(375)` → 400; `round_to_50(225)` → 200; `round_to_50(150)` → 150.
- `spread_width` with ATR_40d=400, k=0.8 → `round_to_50(320)` = 300 (>150 floor; <500 cap).
- ATR_40d=700, k=0.8 → `560` → capped at 500.
- ATR_40d=100, k=0.8 → `80` → floored at 150.
- LONG signal → `direction == "LONG_PUT_SPREAD"`; `short_strike < long_strike` (put spread: short above long).
- `ValueError` when no 0.10–0.25 delta option found in chain (mock OptionChain with only ATM options).

**Commit:** `feat(strategy): add SpreadSelector + SpreadSpec + round_to_50 utility (SE5.3)`

---

## SE6.1 — `src/backtest/walkforward.py`: rolling walk-forward engine

**Files to change:**
- `src/backtest/walkforward.py` — `WalkForwardConfig` + `WalkForwardEngine` + `WFWindow` + `WFResult`
- `tests/unit/backtest/test_walkforward.py` — new test file

**Before any code:**
`get_code_snippet("PointsBacktester")` — runner protocol it must accept;
`get_code_snippet("AllocationBacktester")` — same;
`get_code_snippet("BacktestStore")` — how to write per-window results.

**`WalkForwardConfig` frozen dataclass:**
```python
@dataclass(frozen=True)
class WalkForwardConfig:
    training_days:   int = 252   # investment strategies use 36 months — caller converts
    step_days:       int = 63
    min_trades:      int = 10    # per window; 2 for investment strategies
    max_insufficient_pct: float = 0.25  # abandon if >25% windows are insufficient
```

**`WalkForwardEngine.run(runner, df, param_grid, config) → WFResult`:**
- `runner`: callable — `(signals_or_decisions, df, config, run_id, store) → BacktestResult`.
- `param_grid`: dict of `{param_name: [values]}` — full grid is swept each window.
- Per window: find best param set (max OOS Calmar on that window's test segment), record it.
- `WFResult`: list of `WFWindow` (train dates, test dates, best params, OOS Calmar, trade count).
- `median_calmar`: median OOS Calmar across all windows (the ranking metric).
- Insufficient window (trade count < min_trades): skip window; if >25% skipped → log WARNING.

**Tests (`tests/unit/backtest/test_walkforward.py`):**
- 500-row synthetic DataFrame + MockRunner (returns fixed `BacktestResult`) → `WFResult` has correct number of windows (≈ (500 - 252) // 63).
- Each window OOS period does not overlap with the next.
- `max_insufficient_pct` exceeded → WARNING logged; `WFResult.insufficient_window_count` populated.
- Single parameter sweep: 3 values tested per window → per-window best param recorded.
- `median_calmar` is the median of all per-window OOS Calmars.

**Commit:** `feat(backtest): add WalkForwardEngine — rolling window + param sweep + OOS Calmar (SE6.1)`

---

## SE6.2 — `src/backtest/montecarlo.py`: trade-sequence Monte Carlo

**Files to change:**
- `src/backtest/montecarlo.py` — `MCConfig` + `MonteCarloSimulator` + `MCResult`
- `tests/unit/backtest/test_montecarlo.py` — new test file

**Before any code:**
`search_code("numpy")` in `src/backtest/` — confirm numpy import pattern;
`get_code_snippet("BacktestResult")` — trade return field format.

**`MCResult` frozen dataclass:**
```python
@dataclass(frozen=True)
class MCResult:
    iterations:    int
    p50_max_dd:    float   # 50th percentile max drawdown
    p95_max_dd:    float   # 95th percentile — position sizing anchor
    p99_max_dd:    float   # 99th percentile — sanity check
    observed_max_dd: float
    p95_exceeds_1_5x: bool  # kill condition: p95 > 1.5× observed
    p99_exceeds_50pct: bool # kill condition: p99 > 50% of allocated capital
```

**`MonteCarloSimulator.run(trade_returns, iterations=10_000, seed=42) → MCResult`:**
- `trade_returns`: list of per-trade P&L floats (from OOS walk-forward segments).
- Shuffle trade sequence 10,000 times (numpy vectorised — no Python loop).
- Per shuffled sequence: compute max drawdown on the running cumulative sum.
- Returns MCResult with p50/p95/p99 from the distribution of max drawdowns.
- `seed` for reproducibility.

**Tests (`tests/unit/backtest/test_montecarlo.py`):**
- All-positive trade returns → p99 drawdown ≈ 0 (no losing runs).
- Alternating +1/−1 returns (many small draw-recover cycles) → p95 > 0.
- `iterations=100` with `seed=42` → same result on repeated calls (reproducibility).
- `trade_returns` with single element → `MCResult` returned without error.
- `p95_exceeds_1_5x`: if `p95_max_dd > 1.5 × observed_max_dd` → flag set `True`.

**Commit:** `feat(backtest): add MonteCarloSimulator — 10k-iteration trade-sequence bootstrap (SE6.2)`

---

## SE6.3 — `src/backtest/sensitivity.py`: parameter sensitivity analyser

**Files to change:**
- `src/backtest/sensitivity.py` — `SensitivityConfig` + `SensitivityAnalyser` + `SensitivityResult`
- `tests/unit/backtest/test_sensitivity.py` — new test file

**Before any code:**
`get_code_snippet("WalkForwardEngine")` — how to get optimal params and metric;
`get_code_snippet("WFResult")` — structure.

**`SensitivityResult` frozen dataclass:**
```python
@dataclass(frozen=True)
class SensitivityResult:
    optimal_params:     dict
    optimal_metric:     float
    neighbour_results:  dict   # {param_tuple: metric_value} for ±2-step neighbourhood
    plateau_pct:        float  # fraction of neighbours ≥80% of optimal
    plateau_width:      dict   # {param_name: int} — number of consecutive steps ≥80%
    spike_detected:     bool   # True if plateau_pct < 0.40
```

**`SensitivityAnalyser.analyse(optimal_params, param_grid, runner, df, wf_config) → SensitivityResult`:**
- Constructs full local ±2-step grid around each optimal parameter.
- Runs `WalkForwardEngine` (with terminal window only — not full walk-forward) for each neighbour.
- Plateau: ≥60% of neighbours produce metric ≥80% of optimal.
- Spike: <40% of neighbours reach 80% of optimal.
- `plateau_width[param]`: starting from optimal, count consecutive steps in each direction that remain ≥80% of optimal.

**Tests (`tests/unit/backtest/test_sensitivity.py`):**
- Flat metric across all neighbours (MockRunner always returns same Calmar) → `plateau_pct = 1.0`, `spike_detected = False`.
- One neighbour is optimal, all others are 50% of optimal → `spike_detected = True`.
- `plateau_width` for a parameter with 3 good neighbours on one side → width ≥ 3 on that axis.
- Optimal at parameter boundary (only 1-step neighbourhood on one side) → handled without IndexError.

**Commit:** `feat(backtest): add SensitivityAnalyser — plateau/spike detection for parameter robustness (SE6.3)`

---

## SE6.4 — `src/backtest/reports.py`: validation report generators

**Files to change:**
- `src/backtest/reports.py` — `SwingValidationReport` + `InvestmentValidationReport` + generator functions
- `tests/unit/backtest/test_reports.py` — new test file

**Before any code:**
`get_code_snippet("WFResult")` — fields needed;
`get_code_snippet("MCResult")` — fields;
`get_code_snippet("SensitivityResult")` — fields;
`get_code_snippet("SignalEvalStore")` — `get_regime_tags`, `get_swing_signals`;
`get_code_snippet("BacktestStore")` — `get_metrics`.

**`SwingValidationReport` frozen dataclass:**
All fields from: `WFResult`, `MCResult`, `SensitivityResult`, regime decomposition table,
6 failure condition checks. Plus:
- `strategy`: str
- `train_period`, `test_period`: tuple[date, date]
- `regime_decomposition`: dict — `{regime_cell: {"days_pct": float, "profit_pct": float}}`
- `failure_conditions`: dict — `{condition_name: {"passed": bool, "value": float, "threshold": float}}`
- `summary`: str — one-line human-readable result ("PASS" or "KILL: <reason>")

**`InvestmentValidationReport`** — same structure but with `buyhold_comparison` field
(required per `docs/plan/signals-eval-core/stories.md §SE4.x` design: must demonstrate
either higher Calmar OR >30% drawdown reduction).

**`generate_swing_report(run_id, store, signal_store) → SwingValidationReport`:**
- Loads WFResult, MCResult, SensitivityResult from BacktestStore.
- Computes regime decomposition from swing_signals + backtest_trades joined by date.
- Evaluates all 6 failure conditions; sets `summary` to "PASS" or "KILL: <condition>".

**`generate_investment_report(run_id, store, signal_store) → InvestmentValidationReport`:**
- Same but uses investment-specific thresholds (OOS Calmar ≥0.3 vs swing's ≥0.5).
- Adds buy-and-hold comparison.

**Tests (`tests/unit/backtest/test_reports.py`):**
- `generate_swing_report` with all 6 conditions passing → `summary = "PASS"`.
- OOS Calmar = 0.4 (below Donchian threshold 0.8) → `summary` contains "KILL" and "calmar".
- `regime_decomposition` sums to 100% across all cells.
- MC kill condition: `p95_exceeds_1_5x = True` → failure condition for MC fires.
- `generate_investment_report`: OOS Calmar = 0.25 (below 0.3) → KILL.
- Buy-and-hold comparison: if strategy Calmar < buyhold Calmar AND max DD reduction < 30% → KILL.

**Commit:** `feat(backtest): add SwingValidationReport + InvestmentValidationReport generators (SE6.4)`

---

## SE6.5 — Portfolio construction analysis script (swing strategies, conditional)

> **Conditional:** Run only if ≥2 of SE3.1–SE3.3 swing strategies pass all 6 failure
> conditions in SE6.1–SE6.4. If only 1 strategy survives, skip this task — combining one
> validated strategy with a failed one adds no diversification and dilutes the edge.
> If all 3 fail, the swing research track ends here.

**Files to change:**
- `scripts/portfolio_construction_report.py` — new research script (no unit tests)

**Before any code:**
`get_code_snippet("PointsBacktester")` — trade record structure (daily equity curve format);
`get_code_snippet("MonteCarloSimulator")` — how to pass trade returns;
`search_code("BacktestStore")` — how to load per-strategy OOS trade sequences.

**What to implement:**
Script that takes N surviving strategy run_ids from the walk-forward OOS phase (SE6.1) and
combines them into a portfolio equity curve. Prints PASS / FAIL and key metrics.

```python
def equal_risk_allocate(
    strategy_results: dict[str, list[Trade]],  # strategy_name → OOS trade list
    atr_values: dict[str, float],              # strategy_name → ATR at trade entry
) -> dict[str, float]:
    """
    Normalise position size so each strategy contributes equal ATR-based risk.
    Returns a weight per strategy that sums to 1.0.

    Mechanism: weight_i ∝ 1 / ATR_i. Strategy with smaller ATR gets higher weight
    (smaller moves, need more units to match risk contribution).
    """
```

**Portfolio metrics to compute and print:**

1. **Combined walk-forward median Calmar** — using the combined daily equity curve from
   the OOS windows. Gate: combined Calmar ≥ 1.0. If below this, the combination adds
   complexity without meaningful improvement — trade the single best strategy.

2. **Pairwise daily return correlation** — compute for every pair of surviving strategies.
   Gate: all pairwise correlations < 0.3. If any pair > 0.3, note which pair and explain
   why: correlated strategies share a regime dependency and combining them does not reduce
   tail risk.

3. **Combined Monte Carlo (95th pctile drawdown)** — bootstrap the combined trade sequence
   (10,000 iterations). Gate: combined MC p95 drawdown < individual strategy worst-case
   drawdown. If the combination does not reduce tail risk vs. the single-strategy Monte Carlo,
   diversification is not working — report this explicitly.

4. **Individual vs. combined equity curve comparison** — print side-by-side:
   - Individual OOS Calmar for each surviving strategy
   - Combined portfolio OOS Calmar
   - Individual MC p95 drawdown
   - Combined MC p95 drawdown
   The combination must be Pareto-superior (higher Calmar AND lower p95 DD) to justify
   the operational overhead of running multiple strategies simultaneously.

**If only 1 strategy survived (skip path):**
Script prints: "Only 1 strategy validated — portfolio construction skipped. Deploy as
single strategy." and exits. This is a valid outcome.

**Output format (print to stdout):**
```
=== Portfolio Construction Report ===
Surviving strategies: Donchian (Calmar 1.2), ORB (Calmar 0.8)
Equal-risk weights:   Donchian 52%, ORB 48%

Correlation matrix:
  Donchian × ORB: 0.21 ✅ (< 0.3)

Combined metrics:
  Walk-forward median Calmar: 1.35 ✅ (≥ 1.0)
  MC p95 drawdown:   12.4%  ✅ (< Donchian 16.1%, ORB 18.3%)

RESULT: PASS — proceed with combined portfolio
Allocation weights: docs/plan/signals-eval-core/portfolio_allocation.md [auto-generated]
```

Auto-generates `docs/plan/signals-eval-core/portfolio_allocation.md` with the final weights
and a brief rationale (which strategies, why weights were chosen, gate metrics).

**No unit tests.** This is a research script that requires live BacktestStore data.
Run manually after SE6.4 completes for each surviving strategy.

**Commit:** `feat(scripts): add portfolio_construction_report.py — swing strategy combination analysis (SE6.5)`

---

## SE7.1 — `src/backtest/spread_bt.py`: Tier 2 option spread backtester

*(Start only after SE5.1 Donchian Tier 1 passes and Bhavcopy exclusion rate is measured.)*

**Files to change:**
- `src/backtest/spread_bt.py` — `SpreadBacktesterConfig` + `SpreadBacktester`
- `tests/unit/backtest/test_spread_bt.py` — new test file

**Before any code:**
`get_code_snippet("BhavcopyLoader")` — Bhavcopy data access;
`get_code_snippet("SpreadSpec")` — execution input;
`get_code_snippet("PointsBacktester")` — reuse trade record structure;
`search_code("brentq")` or `search_code("bs_iv")` — any existing IV reconstruction.

**What to implement:**
`SpreadBacktester.run(signals, spread_specs, bhavcopy_df, config, run_id, store) → BacktestResult`:
- For each signal with a `SpreadSpec`, look up Bhavcopy settle_price for both legs.
- If either leg missing (settle_price = 0 or NaN) → mark trade "excluded"; increment exclusion counter.
- Net credit = short leg settle_price − long leg settle_price.
- Mark-to-market daily using Bhavcopy close for each active leg.
- Cost model: ₹20/order brokerage + STT + exchange charges + 2pt slippage per leg.
- Slippage sensitivity: config param `slippage_pts_per_leg` (test at 0, 2, 4).
- Exclusion rate report: if >20% excluded → log CRITICAL with count; `BacktestResult.exclusion_rate` field.

IV reconstruction (for delta verification only, not P&L):
`compute_bs_iv(settle_price, spot, strike, tte_years, rate, is_call) → float | None`
using `scipy.optimize.brentq`. Returns `None` if solution not found.

**Tests (`tests/unit/backtest/test_spread_bt.py`):**
- Both legs have valid Bhavcopy data → trade recorded; P&L = credit minus costs.
- Short leg settle_price = 0 → trade excluded; `exclusion_rate` incremented.
- Slippage at 4pts/leg → P&L lower than at 0pts (by exactly 4 × 2 legs).
- Exclusion rate >20% → CRITICAL logged; `result.exclusion_rate > 0.20`.
- `compute_bs_iv` with valid ATM option inputs → returns float in [0.05, 2.0] range.
- `compute_bs_iv` with deeply ITM price (no BS solution) → returns `None`.

**Commit:** `feat(backtest): add SpreadBacktester — Tier 2 Bhavcopy + BS IV option spread backtester (SE7.1)`

---

## SE8 — Docs close

**Files to change:**
- `CONTEXT.md` — targeted `Edit` only: add `src/strategy/`, `src/strategy/signals/` to module tree; add new `src/backtest/` files
- `DECISIONS.md` — targeted `Edit`: new entries for regime classifier (multi-TF constraint, ATR% percentile rank), ATR-proportional spread width, signal-in-only architecture
- `TODOS.md` — targeted `Edit`: session log entry
- `BACKTEST_PLAN_PHASE1.md` — tick completed Phase 2 checkboxes (2.S0–2.S3b, 2.I0–2.I2 as applicable)

No code changes. No tests. **Never use `Write` on these files — `Edit` only.**
**Commit:** `docs(signals-eval-core): update CONTEXT.md, DECISIONS.md, TODOS.md, BACKTEST_PLAN_PHASE1.md (SE8)`
