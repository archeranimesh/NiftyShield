# Options Income Strategy — Story Specs

> One task per session. Find the first unchecked item in `options_income_tasks.md`. That is your only task.
> Full spec for each task is in this file. After each task: tick `options_income_tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md`.

---

## S0 — Data Audit

**Goal:** Confirm historical Nifty options EOD data is sufficient to backtest. Output a data audit report.
**Files to change:**
- `scripts/audit/__init__.py` — new package, single comment line
- `scripts/audit/options_data_audit.py` — audit script
- `docs/plan/options_income/DATA_AUDIT.md` — output report (written by the script)

**Before any code:**
`search_graph("options_data_audit")` — confirm does NOT yet exist;
`bash find /sessions/bold-hopeful-hypatia/mnt/NiftyShield/data -name "*.parquet" | head -20` — inventory existing data files;
`bash ls /sessions/bold-hopeful-hypatia/mnt/NiftyShield/data/` — top-level data dirs.

**What to implement:**

Script reads all Nifty options Parquet files from `data/historical/` (or wherever they reside — use audit to discover path). For each calendar year 2018–present, compute:
- Total expected monthly expiry dates (last Thursday of each month)
- Count of expiry dates with data present
- Completeness % = present / expected
- Count of distinct strikes per expiry (min, max, avg)
- Whether 5-delta and 2-delta strikes are identifiable (proxy: check if `delta` column exists, else note absent)

Output: `docs/plan/options_income/DATA_AUDIT.md` with a markdown table per year + summary recommendation (PROCEED / GAPS — describe gap-fill strategy).

No unit tests required. Script is a one-shot audit tool.

**Commit:** `chore(audit): options data audit script + DATA_AUDIT.md report`

---

## S1 — Signal Engine

**Goal:** Module returning `SignalResult` (ENTER / WAIT / BLOCKED + reason) for any given date.
**Files to change:**
- `src/options_income/__init__.py` — new package, single comment line
- `src/options_income/signal.py`
- `tests/unit/options_income/__init__.py` — new test package
- `tests/unit/options_income/test_signal.py`

**Before any code:**
`search_graph("SignalResult")` — confirm does NOT yet exist;
`search_graph("PortfolioDelta")` — see frozen Pydantic pattern used in this codebase;
`bash cat /sessions/bold-hopeful-hypatia/mnt/NiftyShield/docs/plan/options_income/options_income_strategy.md | grep -A 30 "Entry Conditions"` — get exact filter rules.

**What to implement:**

```python
class SignalStatus(str, Enum):
    ENTER = "ENTER"
    WAIT = "WAIT"       # trend not confirmed or neutral zone
    BLOCKED = "BLOCKED" # event calendar or VIX floor

class BlockReason(str, Enum):
    BELOW_SMA = "BELOW_SMA"
    NEUTRAL_ZONE = "NEUTRAL_ZONE"        # within 2% of SMA
    VIX_FLOOR = "VIX_FLOOR"             # India VIX < 12.0
    EVENT_CALENDAR = "EVENT_CALENDAR"

@dataclass(frozen=True)
class SignalResult:
    date: date
    status: SignalStatus
    reason: BlockReason | None          # None when status=ENTER
    nifty_spot: Decimal
    sma_100: Decimal
    india_vix: Decimal | None

def compute_sma(spot_series: pd.Series, period: int = 100) -> pd.Series:
    """Vectorised 100-period SMA on Nifty spot close prices."""

def get_signal(
    signal_date: date,
    spot_df: pd.DataFrame,       # columns: date, close — Nifty spot EOD
    vix_df: pd.DataFrame,        # columns: date, close — India VIX EOD
    event_dates: set[date],      # blocked dates loaded from calendar CSV
) -> SignalResult:
    """Return SignalResult for signal_date. Entry executes next session open."""

def load_event_calendar(csv_path: str) -> set[date]:
    """Load blocked dates from CSV. Columns: date (YYYY-MM-DD), reason."""
```

Filter evaluation order (stop at first block):
1. Insufficient history (< 100 rows) → WAIT / BELOW_SMA
2. spot close < sma_100 → WAIT / BELOW_SMA
3. `|spot - sma| / sma < 0.02` → WAIT / NEUTRAL_ZONE
4. `signal_date` in `event_dates` → BLOCKED / EVENT_CALENDAR
5. India VIX close < 12.0 → BLOCKED / VIX_FLOOR
6. All pass → ENTER

**Tests (`tests/unit/options_income/test_signal.py`):**
- Spot well above SMA, VIX=14, no events → `ENTER`
- Spot below SMA → `WAIT / BELOW_SMA`
- Spot 1.5% above SMA (within neutral zone) → `WAIT / NEUTRAL_ZONE`
- Spot 2.5% above SMA (outside neutral zone) → `ENTER`
- Date in event calendar → `BLOCKED / EVENT_CALENDAR`
- India VIX = 11.5 → `BLOCKED / VIX_FLOOR`
- India VIX = 12.0 → `ENTER` (boundary: 12.0 is allowed)
- Fewer than 100 rows of spot data → `WAIT / BELOW_SMA`

**Commit:** `feat(options_income): signal engine — SMA, neutral zone, VIX floor, event calendar`

---

## S2 — Strike Selector

**Goal:** Given option chain data for a date+expiry, return the correct strike at target delta.
**Files to change:**
- `src/options_income/strike_selector.py`
- `tests/unit/options_income/test_strike_selector.py`

**Before any code:**
`search_graph("StrikeSelection")` — confirm does NOT yet exist;
`search_graph("SignalResult")` — confirm S1 complete;
`bash head -3 <options-parquet-path>` (from DATA_AUDIT.md) — confirm column names (delta, strike, close/ltp, option_type).

**What to implement:**

```python
@dataclass(frozen=True)
class StrikeSelection:
    strike: int
    delta: Decimal
    premium: Decimal            # LTP or EOD close at selection date
    expiry: date
    instrument_key: str | None  # None if absent from data

@dataclass(frozen=True)
class SpreadSelection:
    short_leg: StrikeSelection  # 5-delta put (sold)
    long_leg: StrikeSelection   # 2-delta put (bought)

def find_put_strike(
    chain_df: pd.DataFrame,     # pre-filtered: date=entry_date, expiry=target_expiry, option_type='PE'
    target_delta: Decimal,      # Decimal("0.05") for 5-delta
) -> StrikeSelection | None:
    """Nearest OTM put with delta <= target_delta. Never ITM. None if not found."""

def find_spread(
    chain_df: pd.DataFrame,
    short_delta: Decimal = Decimal("0.05"),
    long_delta: Decimal = Decimal("0.02"),
) -> SpreadSelection | None:
    """Both legs for a put spread. None if either leg unavailable."""
```

If delta column absent in chain_df: log warning, return None.

**Tests (`tests/unit/options_income/test_strike_selector.py`):**
- Chain with deltas [0.08, 0.05, 0.03, 0.01] → target 0.05 returns the 0.05 row
- No row with delta ≤ 0.05 → returns None
- Chain missing delta column → returns None (no exception)
- `find_spread`: both legs found → `short_leg.delta >= long_leg.delta`
- `find_spread`: long leg unavailable → returns None

**Commit:** `feat(options_income): strike selector — delta-based put and spread selection`

---

## S3 — Position Manager

**Goal:** Position model, exit-check pure function, P&L computation.
**Files to change:**
- `src/options_income/position.py`
- `tests/unit/options_income/test_position.py`

**Before any code:**
`get_code_snippet("StrikeSelection")` — exact fields from S2;
`search_graph("OptionPosition")` — confirm does NOT yet exist;
`get_code_snippet("PickStatus")` — see terminal-status pattern in mvp models.

**What to implement:**

```python
class Variant(str, Enum):
    V1_MONTHLY_NAKED = "V1_MONTHLY_NAKED"
    V2_QUARTERLY_SPREAD = "V2_QUARTERLY_SPREAD"

class ExitReason(str, Enum):
    TAKE_PROFIT = "TAKE_PROFIT"
    DELTA_STOP = "DELTA_STOP"
    EXPIRY_EXIT = "EXPIRY_EXIT"

class OptionPosition(BaseModel, frozen=True):
    position_id: str            # UUID
    variant: Variant
    entry_date: date
    expiry: date
    short_strike: int
    long_strike: int | None     # None for V1 naked
    premium_collected: Decimal  # net (short − long for spread)
    entry_short_delta: Decimal

@dataclass(frozen=True)
class ExitSignal:
    reason: ExitReason
    current_short_delta: Decimal
    current_premium: Decimal

@dataclass(frozen=True)
class ClosedPosition:
    position: OptionPosition
    exit_date: date
    exit_reason: ExitReason
    exit_premium: Decimal
    pnl: Decimal                # premium_collected − exit_premium (positive = profit)
    hold_days: int

def check_exit(
    position: OptionPosition,
    current_date: date,
    current_short_delta: Decimal,
    current_short_premium: Decimal,
    trading_days_to_expiry: int,
) -> ExitSignal | None:
    """Priority order: DELTA_STOP > EXPIRY_EXIT > TAKE_PROFIT."""

def close_position(
    position: OptionPosition,
    exit_date: date,
    exit_signal: ExitSignal,
    current_long_premium: Decimal = Decimal("0"),
) -> ClosedPosition:
```

Take-profit: `current_short_premium <= premium_collected * Decimal("0.75")`.
Delta stop: `current_short_delta >= Decimal("0.25")`.
Expiry exit: `trading_days_to_expiry <= 5`.

**Tests (`tests/unit/options_income/test_position.py`):**
- Delta=0.20, premium at 80%, 10 days to expiry → no exit
- Delta=0.25 → `DELTA_STOP`
- Premium ≤ 75% of collected → `TAKE_PROFIT`
- 5 days to expiry, delta=0.10, premium=90% → `EXPIRY_EXIT`
- Delta stop takes priority when both stop and TP triggered simultaneously
- `close_position` with TAKE_PROFIT → `pnl > 0`
- `close_position` with DELTA_STOP where exit > entry → `pnl < 0`
- V1 naked: `long_strike=None`, `current_long_premium=0` → P&L from short leg only

**Commit:** `feat(options_income): position model, exit logic, P&L computation`

---

## S4 — Backtest Engine V1 (Monthly Naked Put)

**Goal:** Simulate V1 on full historical data. Output trade log + metrics.
**Files to change:**
- `src/options_income/backtest_v1.py`
- `scripts/backtest/__init__.py` — new package if absent, single comment line
- `scripts/backtest/run_v1.py`
- `tests/unit/options_income/test_backtest_v1.py`

**Before any code:**
`search_graph("BacktestV1")` — confirm does NOT yet exist;
`get_code_snippet("get_signal")` — exact signature from S1;
`get_code_snippet("find_put_strike")` — exact signature from S2;
`get_code_snippet("check_exit")` — exact signature from S3;
`get_code_snippet("OptionPosition")` — exact fields;
`bash ls /sessions/bold-hopeful-hypatia/mnt/NiftyShield/data/backtest/` — create dir if absent.

**What to implement:**

```python
@dataclass
class BacktestConfig:
    variant: Variant = Variant.V1_MONTHLY_NAKED
    target_delta: Decimal = Decimal("0.05")
    sma_period: int = 100
    neutral_zone_pct: Decimal = Decimal("0.02")
    vix_floor: Decimal = Decimal("12.0")
    slippage_pct: Decimal = Decimal("0.005")
    brokerage_per_order: Decimal = Decimal("20")

class BacktestV1:
    def run(
        self,
        spot_df: pd.DataFrame,
        vix_df: pd.DataFrame,
        chain_df: pd.DataFrame,
        event_dates: set[date],
        config: BacktestConfig,
    ) -> list[ClosedPosition]: ...

def compute_metrics(trades: list[ClosedPosition]) -> dict:
    """Keys: win_rate, avg_hold_days, avg_pnl, total_pnl, max_drawdown, sharpe_annualised, trade_count."""
```

Engine loop per trading day:
1. No open position + signal = ENTER → `find_put_strike` on nearest monthly expiry 30–45 DTE → open position.
2. Open position → `check_exit` → if signal → `close_position` + apply slippage + brokerage.
3. One position at a time for V1.

Slippage: `premium_collected * slippage_pct` deducted at entry; `exit_premium * slippage_pct` deducted at exit.
Brokerage: `brokerage_per_order * 2` per trade (entry order + exit order).

`run_v1.py` — CLI: loads parquet data, runs BacktestV1, writes `data/backtest/v1_results.parquet`, prints metrics table.

**Tests (`tests/unit/options_income/test_backtest_v1.py`):**
- 3-month fixture, ENTER on day 1, TP hit day 8 → 1 trade in output, `pnl > 0`
- Signal BLOCKED (VIX < 12) → no trade opened
- DELTA_STOP triggered → closed trade with `exit_reason=DELTA_STOP`
- Second ENTER signal while position open → ignored (no second position)
- `compute_metrics` on 5-trade list → dict has all 7 expected keys

**Commit:** `feat(options_income): backtest engine V1 — monthly naked put simulation`

---

## S5 — Backtest Engine V2 (Quarterly Put Spread)

**Goal:** V2 simulation on quarterly expiry put spread.
**Files to change:**
- `src/options_income/backtest_v2.py`
- `scripts/backtest/run_v2.py`
- `tests/unit/options_income/test_backtest_v2.py`

**Before any code:**
`get_code_snippet("BacktestV1")` — mirror this pattern;
`get_code_snippet("find_spread")` — exact signature from S2;
`get_code_snippet("BacktestConfig")` — reuse same dataclass;
`get_code_snippet("close_position")` — confirm two-leg P&L path.

**What to implement:**

`BacktestV2` mirrors `BacktestV1` with differences:
- Target expiry: 60–90 DTE (quarterly — last Thursday ~3 months out)
- Uses `find_spread` not `find_put_strike`
- Slippage: 4 events per round trip (entry short, entry long, exit short, exit long)
- Brokerage: `brokerage_per_order * 4` per trade
- `OptionPosition.long_strike` is populated
- `compute_metrics` adds key: `spread_efficiency` = `avg(premium_collected / spread_width)`

`run_v2.py` writes to `data/backtest/v2_results.parquet`.

**Tests (`tests/unit/options_income/test_backtest_v2.py`):**
- Spread entry, TP hit → net P&L = short collected − long paid − 4× slippage − brokerage
- `spread_efficiency` key present in metrics dict
- DELTA_STOP → both legs closed simultaneously
- Signal BLOCKED → no position opened

**Commit:** `feat(options_income): backtest engine V2 — quarterly put spread simulation`

---

## S6 — Paper Trading Integration

**Goal:** Daily runner wired to live Upstox option chain.
**Files to change:**
- `src/paper/options_income_runner.py`
- `tests/unit/paper/test_options_income_runner.py`

**Before any code:**
`search_graph("PaperTradeRunner")` — find existing runner pattern in `src/paper/`;
`search_graph("BrokerClient")` — confirm protocol interface;
`get_code_snippet("get_option_chain")` — Upstox option chain method on BrokerClient;
`get_code_snippet("build_notifier")` — notifier factory signature;
`get_code_snippet("get_signal")` — signal engine signature;
`search_code("MockBrokerClient")` — confirm available for tests.

**What to implement:**

```python
class OptionsIncomeRunner:
    def __init__(
        self,
        client: BrokerClient,
        notifier: TelegramNotifier | None,
        config: BacktestConfig,
        event_calendar_path: str,
        spot_parquet_path: str,    # local cache for SMA computation
        vix_parquet_path: str,
    ) -> None: ...

    async def run_daily(self, run_date: date) -> None:
        """Check exits first, then new entries."""
```

Telegram on entry:
```
📥 OPTIONS INCOME — ENTRY
V1 Monthly | Strike: 23000 PE | Expiry: 2026-06-26
Premium: ₹45.50 | Delta: 0.049
```
On exit:
```
📤 OPTIONS INCOME — EXIT (TAKE_PROFIT)
Strike: 23000 PE | Hold: 7 days
P&L: +₹1,706 | Decay: 25.3%
```

Non-fatal contract: if `notifier` is None, skip silently. Never raise on Telegram failure.

**Tests (`tests/unit/paper/test_options_income_runner.py`):**
- ENTER signal + valid strike → position opened, notifier called once
- BLOCKED signal → no position, notifier not called
- Open position + TP triggered → position closed, notifier called with EXIT message
- `notifier=None` → no exception raised
- All via `MockBrokerClient` — no network

**Commit:** `feat(paper): OptionsIncomeRunner — live Upstox chain + Telegram alerts`

---

## S7 — Reporting

**Goal:** Script printing backtest summary + V1 vs V2 comparison + active paper positions.
**Files to change:**
- `scripts/reports/options_income_report.py`

**Before any code:**
`get_code_snippet("compute_metrics")` — confirm metric dict keys from S4;
`bash ls /sessions/bold-hopeful-hypatia/mnt/NiftyShield/data/backtest/` — confirm parquet files exist.

**What to implement:**

```
python -m scripts.reports.options_income_report [--telegram]
```

Output sections:
1. V1 Backtest Summary — metrics from `v1_results.parquet`
2. V2 Backtest Summary — metrics from `v2_results.parquet`
3. V1 vs V2 Comparison — side-by-side: win rate, avg hold, avg P&L, Sharpe, spread efficiency
4. Active Paper Positions — open positions from runner state file (if any)

`--telegram`: send report via `build_notifier()`.

No unit tests required.

**Commit:** `feat(scripts): options income backtest + paper position report`

---

## S8 — Docs Close

**Files to change:**
- `CONTEXT.md` — add `src/options_income/` to module tree; add new scripts
- `DECISIONS.md` — entries: V1/V2 structure, hard stop no rolling, delta-25 stop
- `TODOS.md` — session log entry

Targeted `Edit` calls only — never `Write` on these files.

**Commit:** `docs(options_income): update CONTEXT.md, DECISIONS.md, TODOS.md`
