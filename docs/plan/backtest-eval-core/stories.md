# backtest-eval-core — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: tick `tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md` session log.

---

## B1.1 — `src/backtest/store.py`: BacktestStore scaffold + backtest_runs + tests

**Files to change:**
- `src/backtest/store.py` — new file: `BacktestStore` class with `init_db` + `backtest_runs` CRUD
- `tests/unit/backtest/test_backtest_store.py` — new test file

**Before any code:**
- `search_graph("BacktestStore")` — confirm it does NOT yet exist (zero results expected)
- `get_code_snippet("db_connection")` — confirm shared SQLite context manager signature (`src/db.py`)
- `search_graph("MVPStore")` — reference pattern for store structure (init_db + CRUD)
- `git log --oneline -5 src/backtest/` — check recent backtest module activity

**What to implement:**

`BacktestStore.__init__(self, db_path: str)` — stores path only, no connection held open. Uses `db_connection(db_path)` from `src/db.py` for every operation.

`init_db(self) → None` — creates all four tables via the DDL in `docs/plan/backtest-eval-core/schema.md`. Safe to call repeatedly (all `CREATE TABLE IF NOT EXISTS`).

`create_run(self, run: BacktestRun) → None` — INSERT into `backtest_runs`.

`get_run(self, run_id: str) → BacktestRun | None` — by `run_id`.

`list_runs(self, strategy_name: str | None = None) → list[BacktestRun]` — all runs, optionally filtered by strategy_name, ordered by `created_at DESC`.

**`BacktestRun` dataclass** (frozen, in `src/backtest/store.py` or extract to `src/backtest/models.py` — your call, document in commit message):
```python
@dataclass(frozen=True)
class BacktestRun:
    run_id: str           # UUID
    strategy_name: str
    strategy_version: str
    variant: str | None
    start_date: str       # ISO date
    end_date: str         # ISO date
    config_json: str      # JSON string
    git_sha: str
    created_at: str       # ISO datetime UTC
```

`git_sha` capture helper: `_capture_git_sha() → str` — runs `git rev-parse HEAD` via `subprocess.run`, returns the SHA string. On failure (not a git repo, git not installed) returns `"unknown"`. This is the only place subprocess is used; it is acceptable here.

**Tests (`tests/unit/backtest/test_backtest_store.py`):**
- `init_db()` called twice → no error (idempotent).
- `create_run` → `get_run` round-trip: all fields survive serialisation.
- `get_run` on missing `run_id` → `None`.
- `list_runs()` with no filter → returns all runs.
- `list_runs(strategy_name="csp_nifty_v1")` → returns only matching runs.
- `list_runs` returns most recent first (`created_at DESC`).
- `BacktestRun` with `variant=None` → round-trips correctly (NULL in DB, None in Python).

**Commit:** `feat(backtest): add BacktestStore scaffold with backtest_runs CRUD`

---

## B1.2 — `src/backtest/store.py`: daily_pnl + trades + metrics tables + CRUD + tests

**Files to change:**
- `src/backtest/store.py` — extend with three new table groups
- `tests/unit/backtest/test_backtest_store.py` — extend with new tests

**Before any code:**
- `get_code_snippet("BacktestStore")` — get current method list (post B1.1)
- `get_code_snippet("BacktestRun")` — exact field list
- `search_graph("db_connection")` — confirm context manager usage pattern

**What to implement (add to `BacktestStore`):**

**`BacktestDailyPnl` dataclass** (frozen):
```python
@dataclass(frozen=True)
class BacktestDailyPnl:
    run_id: str
    date: str           # ISO date
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    mark_to_market: Decimal
    open_positions: int
```

**`BacktestTrade` dataclass** (frozen) — mirrors live `trades` table + backtest additions:
```python
@dataclass(frozen=True)
class BacktestTrade:
    run_id: str
    strategy_name: str
    leg_role: str
    instrument_key: str
    trade_date: str     # ISO date
    action: str         # 'BUY' | 'SELL'
    quantity: int
    price: Decimal
    notes: str = ''
    intended_risk: Decimal | None = None
    fill_model: str | None = None
```

**`BacktestMetric` dataclass** (frozen):
```python
@dataclass(frozen=True)
class BacktestMetric:
    run_id: str
    metric_name: str
    value: str          # always stored as TEXT; caller serialises Decimal/date
    computed_at: str    # ISO datetime UTC
```

**Methods to add:**

`record_daily_pnl(self, pnl: BacktestDailyPnl) → None` — INSERT OR REPLACE (idempotent on `(run_id, date)` unique constraint).

`get_daily_pnl(self, run_id: str) → list[BacktestDailyPnl]` — all rows for a run, ordered by `date ASC`.

`record_trade(self, trade: BacktestTrade) → None` — INSERT into `backtest_trades`.

`get_trades(self, run_id: str) → list[BacktestTrade]` — all trades for a run, ordered by `trade_date ASC`.

`record_metric(self, metric: BacktestMetric) → None` — INSERT OR REPLACE on `(run_id, metric_name)`.

`get_metric(self, run_id: str, metric_name: str) → BacktestMetric | None`.

`get_all_metrics(self, run_id: str) → dict[str, str]` — `{metric_name: value}` for all metrics on a run.

**Tests (add to `tests/unit/backtest/test_backtest_store.py`):**
- `record_daily_pnl` → `get_daily_pnl` round-trip: all Decimal fields survive TEXT serialisation.
- `record_daily_pnl` called twice with same `(run_id, date)` → second call replaces (no duplicate row error).
- `record_trade` → `get_trades` round-trip: `price` and `intended_risk` Decimal survive round-trip.
- `get_trades` with `intended_risk=None` → `None` in result (NULL in DB).
- `record_metric` → `get_metric` round-trip.
- `record_metric` called twice with same name → replaces (no duplicate).
- `get_all_metrics` returns dict with all recorded metric names as keys.
- `get_daily_pnl` results ordered by `date ASC`.

**Commit:** `feat(backtest): add BacktestStore daily_pnl, trades, metrics persistence`

---

## B2.1 — `src/analytics/` package setup: `__init__.py`, `CLAUDE.md`, relocate `test_analytics_apis.py`

**Files to change:**
- `src/analytics/__init__.py` — replace empty stub with proper package docstring
- `src/analytics/CLAUDE.md` — new file: module invariants
- `scripts/test_analytics_apis.py` — move from `src/analytics/test_analytics_apis.py` (git mv)

**Before any code:**
- `git log --oneline -5 src/analytics/` — understand what's currently there and why
- `search_graph("AnalyticsClient")` — confirm `test_analytics_apis.py` has no importers

**What to implement:**

`src/analytics/__init__.py`:
```python
"""Analytics module — pure-function strategy evaluation layer.

Operates identically on live trades, paper trades, and backtest trades.
Takes trade-like records as input; never touches the DB directly.
"""
```

`src/analytics/CLAUDE.md` — module invariants document:
```markdown
# src/analytics/ — Module Invariants

## What this module is
Pure-function strategy evaluation layer. Computes metrics, ratios, drawdown
statistics, position sizing recommendations, and statistical process control
signals from trade records and return series.

## Invariants (never violate)
1. **No I/O.** No DB access, no file reads, no network calls inside any public function.
   All functions take plain Python objects (lists of dataclasses/dicts, Decimal series).
2. **Decimal in, Decimal out.** All monetary inputs and outputs are `Decimal`.
   Float is only acceptable at the numpy/scipy boundary for vectorised operations —
   document every `Decimal → float → Decimal` conversion with an inline comment.
3. **Cite literature.** Every public function's docstring must cite the relevant
   `LITERATURE.md` LIT code (e.g. `LIT-04` for Sharpe). If no LIT entry exists, add one.
4. **Pinned test values.** PSR/DSR tests must replicate López de Prado's published
   numerical examples from *Advances in Financial Machine Learning* Ch. 14 to within 1e-4.
   Kelly tests must replicate Thorp's biased-coin example (60% win, even money → f*=0.20).
   Optimal f tests must replicate Vince's examples from *The Mathematics of Money Management* Ch. 1.
5. **No side effects.** Functions must be pure — same input always yields same output.
   Monte Carlo functions accept a `seed` parameter for reproducibility.

## Submodule responsibilities
- `trade_metrics.py` — per-trade and aggregate trade statistics
- `ratios.py` — risk-adjusted return ratios (Sharpe, Sortino, Calmar, Ulcer, PSR, DSR)
- `drawdown.py` — equity curve drawdown analysis
- `sizing.py` — position sizing (Kelly, Optimal f, risk-of-ruin)
- `spc.py` — statistical process control (Z-score drift, CUSUM, runs test)
- `report.py` — composes all submodules into `StrategyReport`

## Literature references
See `LITERATURE.md` for LIT-02 through LIT-09. All cited in individual function docstrings.
```

**Relocate `test_analytics_apis.py`:**
```bash
git mv src/analytics/test_analytics_apis.py scripts/test_analytics_apis.py
```
This file is an API connectivity verifier for the Upstox Analytics Token — it belongs in `scripts/`, not in the analytics domain module.

**No tests required for this task** (no logic added — package scaffold and file move only).

**Commit:** `chore(analytics): set up package scaffold, CLAUDE.md, relocate test_analytics_apis`

---

## B2.2 — `src/analytics/trade_metrics.py`: trade-level metrics + tests

**Files to change:**
- `src/analytics/trade_metrics.py` — new file
- `tests/unit/analytics/__init__.py` — new test package (single comment line)
- `tests/unit/analytics/test_trade_metrics.py` — new test file

**Before any code:**
- `search_graph("PaperTrade")` — confirm trade model shape used in this codebase (Pydantic frozen)
- `search_graph("BacktestTrade")` — get field list including `intended_risk`
- `search_graph("trade_metrics")` — confirm does NOT yet exist

**What to implement:**

All functions accept `trades: list[Any]` where each element has at minimum:
- `.price: Decimal` (entry fill price — or use `entry_price` if present)
- `.action: str` — `'BUY'` or `'SELL'`
- `.quantity: int`

For P&L computation, a "trade" in this context is a **closed round-trip** represented as a single value (Decimal). The caller is responsible for pairing entries and exits and computing the net P&L per closed trade before passing to these functions. Functions that take `trades` accept `list[Decimal]` (per-trade P&L values), not raw trade records. Document this clearly.

```python
def total_pnl(trades: list[Decimal]) -> Decimal:
    """Sum of all trade P&Ls. LIT-09."""

def win_rate(trades: list[Decimal]) -> Decimal:
    """Fraction of trades with pnl > 0. Returns Decimal in [0, 1].
    Empty list → Decimal('0'). LIT-09."""

def avg_win(trades: list[Decimal]) -> Decimal:
    """Mean P&L of winning trades (pnl > 0).
    No winners → Decimal('0'). LIT-09."""

def avg_loss(trades: list[Decimal]) -> Decimal:
    """Mean P&L of losing trades (pnl < 0), returned as a positive number.
    No losers → Decimal('0'). LIT-09."""

def max_win(trades: list[Decimal]) -> Decimal:
    """Largest winning trade. Empty or no winners → Decimal('0')."""

def max_loss(trades: list[Decimal]) -> Decimal:
    """Largest losing trade, returned as a positive number.
    Empty or no losers → Decimal('0')."""

def profit_factor(trades: list[Decimal]) -> Decimal:
    """Gross wins / gross losses.
    Zero losses → Decimal('Infinity').
    Zero wins and zero losses → Decimal('0'). LIT-09."""

def expectancy(trades: list[Decimal]) -> Decimal:
    """(win_rate * avg_win) - (loss_rate * avg_loss). Rupee value per trade.
    Empty list → Decimal('0'). LIT-09."""

def trade_duration_stats(
    trades: list[tuple[date, date, Decimal]]
) -> dict[str, dict[str, float]]:
    """Duration statistics split by outcome.

    Args:
        trades: list of (entry_date, exit_date, pnl) tuples.

    Returns:
        {"winners": {"mean": ..., "median": ..., "p25": ..., "p75": ...},
         "losers":  {"mean": ..., "median": ..., "p25": ..., "p75": ...}}

    Duration is in calendar days. Float values (days) — not Decimal.
    Empty winner or loser bucket → all values 0.0. LIT-09.
    """

def r_multiple_distribution(
    trades: list[Decimal],
    risks: list[Decimal | None],
) -> dict:
    """R-multiple distribution for trades with known risk.

    Args:
        trades: per-trade P&L (Decimal).
        risks: per-trade intended risk (positive Decimal, or None if unknown).
               Must be same length as trades.

    Returns:
        {"bin_edges": [...], "counts": [...], "mean": float, "std": float,
         "pct_above_1r": float, "pct_below_neg_1r": float,
         "n_with_risk": int}  # trades where risk was not None

    Trades with risk=None are excluded from R-multiple calculation.
    bin_edges: [-3, -2, -1, 0, 1, 2, 3, inf] (8 bins).
    Float values for all stats. LIT-09.
    """
```

**Tests (`tests/unit/analytics/test_trade_metrics.py`):**
- `profit_factor([100, 100, 100, -50, -50])` → `Decimal('3')` exactly.
- `profit_factor([])` → `Decimal('0')`.
- `profit_factor([100, 100])` → `Decimal('Infinity')` (no losses).
- `win_rate([100, -50, 100])` → `Decimal('2') / Decimal('3')`.
- `win_rate([])` → `Decimal('0')`.
- `expectancy([100, 100, -50, -50])` → `(0.5 * 100) - (0.5 * 50)` = `Decimal('25')`.
- `avg_loss` returns positive number for negative P&L trades.
- `trade_duration_stats` with two winners (3 days, 7 days) and one loser (5 days):
  winners mean = 5.0, losers mean = 5.0.
- `trade_duration_stats` with empty winner bucket → winners all 0.0.
- `r_multiple_distribution` with trades=[100, -50] and risks=[100, 100]:
  R-multiples = [1.0, -0.5]; `pct_above_1r` = 0.5, `pct_below_neg_1r` = 0.0.
- `r_multiple_distribution` with all risks=None → `n_with_risk = 0`.

**Commit:** `feat(analytics): trade-level metrics`

---

## B2.3 — `src/analytics/ratios.py`: Sharpe / Sortino / Calmar / Ulcer / PSR / DSR + tests

**Files to change:**
- `src/analytics/ratios.py` — new file
- `tests/unit/analytics/test_ratios.py` — new test file

**Before any code:**
- `search_graph("ratios")` — confirm does NOT yet exist
- Read `LITERATURE.md` entries for LIT-04, LIT-05, LIT-06, LIT-07, LIT-08 before writing any formula

**What to implement:**

```python
def sharpe_ratio(
    returns: list[Decimal],
    risk_free_rate: Decimal = Decimal('0'),
    periods_per_year: int = 252,
) -> Decimal | None:
    """Annualised Sharpe ratio. Returns None if std dev is zero (flat returns).
    Decimal → float → Decimal at numpy boundary. LIT-04."""

def sortino_ratio(
    returns: list[Decimal],
    target_return: Decimal = Decimal('0'),
    periods_per_year: int = 252,
) -> Decimal | None:
    """Annualised Sortino ratio using downside deviation.
    Returns None if downside deviation is zero. LIT-05."""

def calmar_ratio(
    returns: list[Decimal],
    periods_per_year: int = 252,
) -> Decimal | None:
    """Annualised return / max drawdown. Returns None if no drawdown observed. LIT-06."""

def ulcer_index(returns: list[Decimal]) -> Decimal:
    """Ulcer Index — RMS of percentage drawdowns from running peak.
    Zero if no drawdown. LIT-06."""

def probabilistic_sharpe_ratio(
    returns: list[Decimal],
    benchmark_sharpe: Decimal,
    periods_per_year: int = 252,
) -> Decimal:
    """Probability that observed Sharpe exceeds benchmark_sharpe.
    Returns Decimal in [0, 1]. Uses normal CDF (scipy.stats.norm.cdf).
    Decimal → float → Decimal at scipy boundary. LIT-07."""

def deflated_sharpe_ratio(
    returns: list[Decimal],
    num_trials: int,
    periods_per_year: int = 252,
) -> Decimal:
    """Multiple-testing-corrected Sharpe ratio significance.
    Returns Decimal in [0, 1] — probability the strategy has skill after
    correcting for num_trials experiments. LIT-08."""
```

**Decimal ↔ float boundary rule:** Convert `Decimal → float` only at the numpy/scipy call site, and convert back immediately after. One-line comment `# Decimal → float for numpy` at every boundary crossing.

**Tests (`tests/unit/analytics/test_ratios.py`):**
- `sharpe_ratio([Decimal('0.01')] * 252, risk_free_rate=Decimal('0'))` → positive value, not None.
- `sharpe_ratio([Decimal('0')] * 10)` → `None` (zero std dev).
- `sharpe_ratio([])` → `None`.
- `sortino_ratio` with all positive returns (no downside) → `None` (zero downside dev).
- `calmar_ratio` with flat returns (no drawdown) → `None`.
- `ulcer_index([Decimal('0')] * 10)` → `Decimal('0')`.
- **Pinned PSR:** Using López de Prado Ch. 14 example — replicate to within 1e-4. Pin the exact input series and expected output as a constant in the test. If you cannot locate the published example, use: `returns = [Decimal('0.001')] * 50 + [Decimal('-0.0005')] * 10`, `benchmark_sharpe = Decimal('1.0')`, `periods_per_year = 252` — assert result is in (0, 1) and document the computed value.
- **Pinned DSR:** Same Ch. 14 sourcing requirement. Pin exact inputs and expected value to within 1e-4.
- `probabilistic_sharpe_ratio` with very large positive returns vs low benchmark → close to 1.0.
- `deflated_sharpe_ratio` with `num_trials=1` degenerates to PSR (values should be close).

**Commit:** `feat(analytics): strategy-level ratios (Sharpe/Sortino/Calmar/Ulcer/PSR/DSR)`

---

## B2.4 — `src/analytics/drawdown.py`: drawdown analysis + tests

**Files to change:**
- `src/analytics/drawdown.py` — new file
- `tests/unit/analytics/test_drawdown.py` — new test file

**Before any code:**
- `search_graph("drawdown")` — confirm does NOT yet exist
- Read `LITERATURE.md` LIT-06 entry

**What to implement:**

```python
def equity_curve(returns: list[Decimal], initial: Decimal = Decimal('1')) -> list[Decimal]:
    """Convert a list of period returns to a cumulative equity curve.
    Each element is (1 + r_i). initial is the starting NAV."""

def drawdown_series(curve: list[Decimal]) -> list[Decimal]:
    """Running drawdown at each point: (peak - value) / peak.
    Returns list of non-negative Decimal values (0 = at peak). LIT-06."""

def max_drawdown(
    curve: list[Decimal],
) -> tuple[Decimal, int, int, int | None]:
    """Maximum drawdown analysis.

    Returns:
        (max_dd_pct, peak_idx, trough_idx, recovery_idx_or_None)
        max_dd_pct is a non-negative Decimal (0.25 = 25% drawdown).
        recovery_idx is None if curve never recovers to the peak level.
        Returns (Decimal('0'), 0, 0, None) on empty or flat curve. LIT-06.
    """

def drawdown_duration_distribution(
    curve: list[Decimal],
) -> dict[str, float]:
    """Statistics on drawdown episode durations (in periods).

    A drawdown episode starts when curve falls below the running peak
    and ends when it recovers to or above that peak (or at end of series).

    Returns:
        {"count": int, "mean": float, "median": float,
         "max": float, "p75": float, "p90": float}
    All zero / empty when no drawdown episodes exist. LIT-06.
    """

def conditional_drawdown_at_risk(
    curve: list[Decimal],
    confidence: float = 0.95,
) -> Decimal:
    """Expected drawdown in the worst (1 - confidence) fraction of periods.
    Returns Decimal. Returns Decimal('0') if curve is flat or empty. LIT-06."""
```

**Tests (`tests/unit/analytics/test_drawdown.py`):**
- `equity_curve([Decimal('0.1'), Decimal('-0.1')])` → `[Decimal('1.1'), Decimal('0.99')]`.
- `drawdown_series([Decimal('1'), Decimal('0.9'), Decimal('0.95')])` → `[0, 0.1, ~0.05]` (verify to 4 dp).
- `max_drawdown` on `[1, 1.1, 0.9, 1.05]` → max_dd_pct ≈ `Decimal('0.1818')` (100/110), peak_idx=1, trough_idx=2.
- `max_drawdown` on `[1, 1.1, 0.9, 1.1]` → recovery_idx is not None (curve recovers).
- `max_drawdown` on `[1, 1.1, 0.9]` → recovery_idx is None (never recovers to 1.1).
- `max_drawdown([])` → `(Decimal('0'), 0, 0, None)`.
- `drawdown_duration_distribution` on a curve with two distinct DD episodes → count = 2.
- `drawdown_duration_distribution` on flat curve → count = 0, all zeros.
- `conditional_drawdown_at_risk` on flat curve → `Decimal('0')`.

**Commit:** `feat(analytics): drawdown analytics`

---

## B2.5 — `src/analytics/sizing.py`: Kelly / Optimal f / risk-of-ruin / Monte Carlo + tests

**Files to change:**
- `src/analytics/sizing.py` — new file
- `tests/unit/analytics/test_sizing.py` — new test file

**Before any code:**
- `search_graph("sizing")` — confirm does NOT yet exist
- Read `LITERATURE.md` LIT-02 (Kelly) and LIT-03 (Optimal f, risk-of-ruin)

**What to implement:**

```python
def kelly_fraction(
    win_rate: Decimal,
    win_loss_ratio: Decimal,
) -> Decimal:
    """Classical Kelly criterion: f* = win_rate - (loss_rate / win_loss_ratio).
    Returns Decimal. Negative result means no edge — return Decimal('0').
    win_loss_ratio must be > 0. LIT-02."""

def fractional_kelly(
    win_rate: Decimal,
    win_loss_ratio: Decimal,
    fraction: Decimal = Decimal('0.25'),
) -> Decimal:
    """Practitioner Kelly: fraction * kelly_fraction(...).
    Default fraction is 0.25 (quarter-Kelly). LIT-02."""

def optimal_f(trades: list[Decimal]) -> Decimal:
    """Optimal f via numerical search over f ∈ [0.01, 0.99] (step 0.01).
    Maximises the Terminal Wealth Relative (TWR) on the trade sequence.
    Returns Decimal. Returns Decimal('0') if trades list is empty or all trades
    are non-negative (no losses → optimal_f is undefined, return 0). LIT-03."""

def risk_of_ruin(
    win_rate: Decimal,
    win_loss_ratio: Decimal,
    fraction_risked_per_trade: Decimal,
    ruin_threshold: Decimal = Decimal('0.3'),
) -> Decimal:
    """Analytical risk of ruin formula.
    Probability of losing ruin_threshold fraction of starting capital.
    Returns Decimal in [0, 1]. LIT-03."""

def probability_of_drawdown(
    returns: list[Decimal],
    threshold_pct: Decimal,
    num_periods: int,
    num_simulations: int = 10_000,
    seed: int = 42,
) -> Decimal:
    """Monte Carlo probability of experiencing a drawdown >= threshold_pct
    over num_periods forward periods, sampled from the empirical return
    distribution in returns.

    Args:
        returns: historical return sample to draw from (bootstrap).
        threshold_pct: drawdown threshold, e.g. Decimal('0.10') = 10%.
        num_periods: number of periods to simulate.
        num_simulations: number of Monte Carlo paths (default 10,000).
        seed: RNG seed for reproducibility (document in docstring). LIT-03.

    Returns:
        Decimal: fraction of paths that breached threshold_pct.
    """
```

**Decimal ↔ float boundary:** `optimal_f` and `probability_of_drawdown` use float internally for the numerical loop / numpy sampling. Document each boundary crossing with an inline comment.

**Tests (`tests/unit/analytics/test_sizing.py`):**
- **Pinned Kelly (Thorp):** `kelly_fraction(Decimal('0.6'), Decimal('1'))` → `Decimal('0.20')` exactly. This is the biased coin (60% win, even money payoff). Non-negotiable.
- `kelly_fraction` with no edge (win_rate=0.4, win_loss_ratio=1) → `Decimal('0')` (negative Kelly clamped to 0).
- `fractional_kelly(Decimal('0.6'), Decimal('1'), Decimal('0.25'))` → `Decimal('0.05')`.
- **Pinned Optimal f (Vince):** Use Vince's trade sequence from *The Mathematics of Money Management* Ch. 1: `[-1, 1, 1, 1, -1, 1, 1, -1, 1, 1]` (scaled to [-1, 1]). Expected optimal_f is approximately 0.25. Assert result is in [0.20, 0.30] (allow tolerance for step-search resolution).
- `optimal_f([])` → `Decimal('0')`.
- `optimal_f([100, 200, 50])` → `Decimal('0')` (no losses, undefined).
- `risk_of_ruin` with very high win_rate and low fraction → result close to 0.
- `probability_of_drawdown` with `seed=42`, flat returns → low probability; result is reproducible (call twice, same result).
- `probability_of_drawdown(returns=[Decimal('0')]*10, threshold_pct=Decimal('0.01'), num_periods=5)` → `Decimal('0')` (flat returns can't produce drawdown).

**Commit:** `feat(analytics): position sizing (Kelly/OptimalF/risk-of-ruin)`

---

## B2.6 — `src/analytics/spc.py`: rolling Z-score / CUSUM / runs test + tests

**Files to change:**
- `src/analytics/spc.py` — new file
- `tests/unit/analytics/test_spc.py` — new test file

**Before any code:**
- `search_graph("spc")` — confirm does NOT yet exist
- Read `LITERATURE.md` for any SPC-related entries

**What to implement:**

```python
def rolling_zscore(
    realized_returns: list[Decimal],
    backtest_mean: Decimal,
    backtest_std: Decimal,
    window: int = 3,
) -> list[Decimal]:
    """Z-score of a rolling window mean vs the backtest distribution.

    For each position i >= window-1, computes:
        z = (mean(realized[i-window+1:i+1]) - backtest_mean) / backtest_std

    Returns a list of len(realized_returns) with None-equivalent Decimal('0')
    for positions before the window fills.

    Args:
        backtest_mean: mean of the backtest return distribution.
        backtest_std: std of the backtest return distribution. Must be > 0.
        window: rolling window size (default 3 — minimum sample for drift signal).

    Raises:
        ValueError: if backtest_std <= 0.
    """

def cusum(
    realized_returns: list[Decimal],
    expected_mean: Decimal,
) -> list[Decimal]:
    """Cumulative sum of deviations from expected_mean.
    Returns list of same length as input.
    cusum[i] = sum(realized[0:i+1]) - (i+1) * expected_mean.
    Empty input → empty list."""

def runs_test(
    win_loss_sequence: list[bool],
) -> tuple[Decimal, Decimal]:
    """Wald-Wolfowitz runs test for randomness of win/loss sequence.

    Args:
        win_loss_sequence: list of bool (True = win, False = loss).

    Returns:
        (z_statistic, p_value) as Decimal pair.
        p_value from two-sided normal approximation.
        Returns (Decimal('0'), Decimal('1')) if sequence is too short (< 2 elements)
        or all wins or all losses (undefined test statistic).
    """
```

**Tests (`tests/unit/analytics/test_spc.py`):**
- `rolling_zscore` with window=3 on a list of 5 returns: first 2 positions are `Decimal('0')`, positions 2–4 are computed values.
- `rolling_zscore` raises `ValueError` when `backtest_std=Decimal('0')`.
- `rolling_zscore` with returns equal to `backtest_mean` → all Z-scores are `Decimal('0')`.
- `cusum([Decimal('0.01')] * 5, Decimal('0.01'))` → all zeros (no deviation from mean).
- `cusum([Decimal('0.02')] * 3, Decimal('0.01'))` → `[0.01, 0.02, 0.03]`.
- `cusum([])` → `[]`.
- `runs_test([True, False, True, False, True, False])` — perfectly alternating sequence: z_statistic is large positive (more runs than expected), p_value close to 0.
- `runs_test([True, True, True, True])` — all wins: returns `(Decimal('0'), Decimal('1'))`.
- `runs_test([True])` — too short: returns `(Decimal('0'), Decimal('1'))`.

**Commit:** `feat(analytics): statistical process control (Z-score/CUSUM/runs-test)`

---

## B2.7 — `src/analytics/report.py`: `StrategyReport` + composition + `compare_reports` + tests

**Files to change:**
- `src/analytics/report.py` — new file
- `tests/unit/analytics/test_report.py` — new test file

**Before any code:**
- `get_code_snippet("trade_metrics")` — confirm all public functions available
- `get_code_snippet("ratios")` — confirm all public functions available
- `get_code_snippet("drawdown")` — confirm all public functions available
- `get_code_snippet("sizing")` — confirm all public functions available
- `search_graph("StrategyReport")` — confirm does NOT yet exist

**What to implement:**

```python
@dataclass(frozen=True)
class StrategyReport:
    """Composed strategy evaluation result.

    All monetary fields are Decimal. Ratio fields are Decimal | None
    (None when undefined — e.g. Calmar with no drawdown).
    """
    strategy_name: str
    start_date: str           # ISO date
    end_date: str             # ISO date
    n_trades: int

    # Trade metrics
    total_pnl: Decimal
    win_rate: Decimal
    avg_win: Decimal
    avg_loss: Decimal
    max_win: Decimal
    max_loss: Decimal
    profit_factor: Decimal    # Decimal('Infinity') when no losses
    expectancy: Decimal

    # Ratios
    sharpe_ratio: Decimal | None
    sortino_ratio: Decimal | None
    calmar_ratio: Decimal | None
    ulcer_index: Decimal
    probabilistic_sharpe: Decimal | None   # None if not enough data
    deflated_sharpe: Decimal | None        # None if not enough data

    # Drawdown
    max_drawdown_pct: Decimal
    max_drawdown_peak_idx: int
    max_drawdown_trough_idx: int
    max_drawdown_recovery_idx: int | None

    # Sizing
    kelly_fraction: Decimal | None         # None if win_loss_ratio undefined
    fractional_kelly: Decimal | None

    # SPC (most recent values from the full series)
    latest_rolling_zscore: Decimal | None  # None if fewer than window returns
    cusum_final: Decimal

    # Narrative
    markdown_summary: str                  # generated by to_markdown()

    def to_markdown(self) -> str:
        """Render report as a Markdown string suitable for sharing."""
```

```python
@dataclass(frozen=True)
class MetricDiff:
    """Side-by-side comparison of one metric between two reports."""
    metric_name: str
    a_value: str    # str representation (Decimal or None)
    b_value: str
    delta: str | None       # b - a, or None if non-numeric
    delta_pct: str | None   # delta / |a|, or None if a is zero or non-numeric

@dataclass(frozen=True)
class ComparisonReport:
    """Side-by-side diff of two StrategyReports (backtest vs paper, A vs B)."""
    report_a_name: str
    report_b_name: str
    diffs: list[MetricDiff]

    def to_markdown(self) -> str:
        """Render comparison as Markdown table."""
```

```python
def generate_strategy_report(
    strategy_name: str,
    trades_pnl: list[Decimal],
    returns: list[Decimal],
    start_date: str,
    end_date: str,
    benchmark_sharpe: Decimal = Decimal('1.0'),
    num_trials: int = 1,
    spc_window: int = 3,
    backtest_mean: Decimal | None = None,
    backtest_std: Decimal | None = None,
) -> StrategyReport:
    """Compose a full StrategyReport from trade P&L and return series.

    Args:
        trades_pnl: per-trade P&L list (closed round-trips).
        returns: daily/periodic return series (for ratio computation).
        backtest_mean / backtest_std: if provided, compute rolling_zscore;
            otherwise latest_rolling_zscore is None.
    """

def compare_reports(
    report_a: StrategyReport,
    report_b: StrategyReport,
) -> ComparisonReport:
    """Generate a side-by-side MetricDiff for every field in StrategyReport.
    Used by Phase 1.11 variance check."""
```

**Tests (`tests/unit/analytics/test_report.py`):**
- `generate_strategy_report` with a minimal trade list (3 wins, 2 losses) + 10-day return series → returns a `StrategyReport` without error; all Decimal fields are Decimal, not float.
- `generate_strategy_report` with empty `trades_pnl` and empty `returns` → returns report with zeros/Nones; no exception.
- `StrategyReport.to_markdown()` → returns a non-empty string containing the strategy name.
- `compare_reports(a, b)` → returns `ComparisonReport` with `len(diffs) > 0`.
- `compare_reports(report, report)` → all `delta` values are `'0'` or `None` (self-comparison).
- `ComparisonReport.to_markdown()` → returns a string containing `report_a_name` and `report_b_name`.
- `profit_factor = Decimal('Infinity')` in a report → `to_markdown()` and `compare_reports` handle it without error.

**Commit:** `feat(analytics): strategy report composition`

---

## B2.8 — Backtest integration: `BacktestStore.record_metrics_from_report` + CLI + tests

**Files to change:**
- `src/backtest/store.py` — add `record_metrics_from_report(run_id, report)` method
- `scripts/analyze_strategy.py` — new CLI script
- `tests/unit/backtest/test_backtest_store.py` — extend with integration tests

**Before any code:**
- `get_code_snippet("BacktestStore")` — current method list (post B1.2)
- `get_code_snippet("StrategyReport")` — full field list
- `get_code_snippet("BacktestMetric")` — exact field list
- `search_code("argparse")` in `scripts/record_paper_trade.py` — existing CLI pattern

**What to implement:**

`BacktestStore.record_metrics_from_report(self, run_id: str, report: StrategyReport) → None`:
Iterates over every numeric field in `StrategyReport` and calls `record_metric` for each.
Field-to-metric name mapping: use the dataclass field name as the `metric_name` (e.g. `"sharpe_ratio"`, `"max_drawdown_pct"`). Skips `markdown_summary`, `strategy_name`, `start_date`, `end_date` (non-metric fields). None values are stored as the string `"None"`. `Decimal('Infinity')` is stored as `"Infinity"`.

`scripts/analyze_strategy.py` — CLI with three mutually exclusive modes:

```
python -m scripts.analyze_strategy --backtest-run <run_id>
python -m scripts.analyze_strategy --live --strategy <strategy_name>
python -m scripts.analyze_strategy --paper --strategy <strategy_name>
```

Each mode:
1. Fetches the relevant trade records from the appropriate DB table.
2. Computes the return series from daily P&L.
3. Calls `generate_strategy_report(...)`.
4. Prints `report.to_markdown()` to stdout.
5. For `--backtest-run`: also calls `record_metrics_from_report` to persist results.

DB path: `data/portfolio/portfolio.sqlite`.

For `--live` and `--paper`: the relevant tables are `trades` and `paper_trades` respectively. Map the trade records to `list[Decimal]` (per-trade P&L) and daily return series. For the initial version, a simple implementation is acceptable — daily P&L from the snapshot table if available, otherwise approximated from trade prices.

**Tests (add to `tests/unit/backtest/test_backtest_store.py`):**
- `record_metrics_from_report` with a `StrategyReport` → `get_all_metrics` returns dict with at least `sharpe_ratio`, `profit_factor`, `max_drawdown_pct` keys.
- `record_metrics_from_report` with `profit_factor = Decimal('Infinity')` → stored as `"Infinity"`, round-trips as string without error.
- `record_metrics_from_report` with `sharpe_ratio = None` → stored as `"None"`, round-trips without error.
- `record_metrics_from_report` called twice → second call replaces (idempotent, no duplicate row error).

**Commit:** `feat(analytics): backtest integration + analyze_strategy CLI`

---

## B2.9 — Docs close

**Files to change (targeted `Edit` calls only — never `Write` on these files):**
- `CONTEXT.md` — add `src/analytics/` module to "What Exists" tree; add `scripts/analyze_strategy.py` to scripts list
- `DECISIONS.md` — add entry: "Analytics module: pure-function evaluation layer on trade records; no DB access; Decimal-in/Decimal-out; PSR/DSR pinned to López de Prado Ch. 14 examples"
- `TODOS.md` — mark Task 5 (backtest-eval-core) complete in the queue table; add session log entry
- `BACKTEST_PLAN_PHASE1.md` — tick `[x]` on task 1.5 and 1.5b checkboxes

No code changes. No tests. Only `Edit` calls.

**Commit:** `docs(analytics): update CONTEXT.md, DECISIONS.md, TODOS.md, BACKTEST_PLAN for 1.5+1.5b`
