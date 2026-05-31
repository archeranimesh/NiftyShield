# CH-9a — Hypothesis Test Design

> Spec for Antigravity (CH-9b). Implement exactly these strategies and assertions.
> No additions, no departures. Read the source signatures with `get_code_snippet` before writing.

---

## Target 1 — `compute_ivr` (`src/backtest/ivr.py`)

**Signature:** `compute_ivr(vix_today: float, vix_series: pd.Series) -> float | None`

**Observed behaviour (from source):**
- Returns `None` when `len(vix_series) < 252`
- Returns `0.5` when the 252-bar window is flat (`vix_high == vix_low`)
- Returns `float(max(0.0, min(1.0, raw)))` otherwise — always clamped to `[0.0, 1.0]`

**File:** `tests/unit/backtest/test_ivr_hypothesis.py`

---

### H-IVR-1 Short series → always None

```python
@given(
    vix_today=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    series=st.lists(
        st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=251,
    ),
)
def test_ivr_short_series_returns_none(vix_today, series):
    result = compute_ivr(vix_today, pd.Series(series))
    assert result is None
```

---

### H-IVR-2 Sufficient series → result in [0.0, 1.0], not None

```python
@given(
    vix_today=st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    series=st.lists(
        st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=252,
        max_size=400,
    ).filter(lambda s: max(s[-252:]) > min(s[-252:])),  # non-flat window
)
def test_ivr_sufficient_series_bounded(vix_today, series):
    result = compute_ivr(vix_today, pd.Series(series))
    assert result is not None
    assert 0.0 <= result <= 1.0
```

---

### H-IVR-3 Flat window → always 0.5

```python
@given(
    vix_value=st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False),
    vix_today=st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    extra=st.lists(
        st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=100,
    ),
)
def test_ivr_flat_window_returns_half(vix_value, vix_today, extra):
    # Build a series where the last 252 bars are all identical
    flat_window = [vix_value] * 252
    series = pd.Series(extra + flat_window)
    result = compute_ivr(vix_today, series)
    assert result == 0.5
```

---

### H-IVR-4 vix_today at or below window min → result == 0.0

```python
@given(
    series=st.lists(
        st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=252,
        max_size=300,
    ).filter(lambda s: max(s[-252:]) > min(s[-252:])),
)
def test_ivr_below_min_clamps_to_zero(series):
    window_min = min(series[-252:])
    vix_today = window_min - 1.0  # strictly below min
    result = compute_ivr(vix_today, pd.Series(series))
    assert result == 0.0
```

---

### H-IVR-5 vix_today at or above window max → result == 1.0

```python
@given(
    series=st.lists(
        st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=252,
        max_size=300,
    ).filter(lambda s: max(s[-252:]) > min(s[-252:])),
)
def test_ivr_above_max_clamps_to_one(series):
    window_max = max(series[-252:])
    vix_today = window_max + 1.0  # strictly above max
    result = compute_ivr(vix_today, pd.Series(series))
    assert result == 1.0
```

---

### H-IVR-6 Result is always float or None — never int, never NaN

```python
@given(
    vix_today=st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    series=st.lists(
        st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=400,
    ),
)
def test_ivr_return_type(vix_today, series):
    result = compute_ivr(vix_today, pd.Series(series))
    assert result is None or (isinstance(result, float) and not math.isnan(result))
```

---

## Target 2 — `aggregate_delta` (`src/risk/delta_tracker.py`)

**Signature:** `PortfolioDeltaTracker.aggregate_delta(paper_positions, nifty_spot, lot_size) -> PortfolioDelta`

**Observed behaviour (from source + `_position_delta` helper):**
- Raises `ValueError` if `nifty_spot <= 0` or `lot_size <= 0`
- CE in key → delta = `net_qty / lot_size` (sign of delta = sign of net_qty)
- PE in key → delta = `-net_qty / lot_size` (sign flipped)
- NiftyBees → delta = `net_qty * avg_cost / (nifty_spot * lot_size)`
- Invariant: `total_delta_lots == options_delta_lots + niftybees_delta_lots` — always

**Constructing `PaperPosition`:** use `get_code_snippet("PaperPosition")` before writing helpers.
Do not write from memory.

**File:** `tests/unit/risk/test_delta_hypothesis.py`

**Setup:** build a default `PortfolioDeltaTracker` with default thresholds for all tests.

---

### H-DELTA-1 Empty positions → all deltas are zero

```python
@given(
    nifty_spot=st.decimals(min_value=Decimal("1"), max_value=Decimal("30000"), allow_nan=False, allow_infinity=False),
    lot_size=st.integers(min_value=1, max_value=200),
)
def test_aggregate_delta_empty_positions(nifty_spot, lot_size):
    tracker = PortfolioDeltaTracker()
    result = tracker.aggregate_delta([], nifty_spot, lot_size)
    assert result.options_delta_lots == Decimal(0)
    assert result.niftybees_delta_lots == Decimal(0)
    assert result.total_delta_lots == Decimal(0)
```

---

### H-DELTA-2 Total delta always equals options + niftybees (additive invariant)

```python
@given(positions=st.lists(ce_position_strategy() | pe_position_strategy(), min_size=0, max_size=10))
def test_aggregate_delta_additive_invariant(positions):
    tracker = PortfolioDeltaTracker()
    result = tracker.aggregate_delta(positions, Decimal("22000"), 65)
    assert result.total_delta_lots == result.options_delta_lots + result.niftybees_delta_lots
```

*Note: `ce_position_strategy()` and `pe_position_strategy()` are `@composite` strategies
that build `PaperPosition` objects with `"NSE_FO|...|CE"` and `"NSE_FO|...|PE"` instrument
keys respectively. Read `PaperPosition` fields from the graph before implementing.*

---

### H-DELTA-3 CE sign: delta sign == net_qty sign

```python
@given(
    net_qty=st.integers(min_value=-10, max_value=10).filter(lambda x: x != 0),
    nifty_spot=st.decimals(min_value=Decimal("1000"), max_value=Decimal("30000"), allow_nan=False),
    lot_size=st.integers(min_value=1, max_value=200),
)
def test_ce_delta_sign_matches_net_qty(net_qty, nifty_spot, lot_size):
    pos = build_ce_position(net_qty=net_qty)
    tracker = PortfolioDeltaTracker()
    result = tracker.aggregate_delta([pos], nifty_spot, lot_size)
    expected_sign = 1 if net_qty > 0 else -1
    assert (result.options_delta_lots > 0) == (expected_sign > 0)
```

---

### H-DELTA-4 PE sign: delta sign == opposite of net_qty sign

```python
@given(
    net_qty=st.integers(min_value=-10, max_value=10).filter(lambda x: x != 0),
    nifty_spot=st.decimals(min_value=Decimal("1000"), max_value=Decimal("30000"), allow_nan=False),
    lot_size=st.integers(min_value=1, max_value=200),
)
def test_pe_delta_sign_opposite_net_qty(net_qty, nifty_spot, lot_size):
    pos = build_pe_position(net_qty=net_qty)
    tracker = PortfolioDeltaTracker()
    result = tracker.aggregate_delta([pos], nifty_spot, lot_size)
    expected_sign = -1 if net_qty > 0 else 1
    assert (result.options_delta_lots > 0) == (expected_sign > 0)
```

---

### H-DELTA-5 nifty_spot <= 0 → ValueError

```python
@given(
    nifty_spot=st.decimals(max_value=Decimal("0"), allow_nan=False, allow_infinity=False),
    lot_size=st.integers(min_value=1, max_value=200),
)
def test_aggregate_delta_nonpositive_spot_raises(nifty_spot, lot_size):
    tracker = PortfolioDeltaTracker()
    with pytest.raises(ValueError):
        tracker.aggregate_delta([], nifty_spot, lot_size)
```

---

### H-DELTA-6 lot_size <= 0 → ValueError

```python
@given(
    lot_size=st.integers(max_value=0),
)
def test_aggregate_delta_nonpositive_lot_raises(lot_size):
    tracker = PortfolioDeltaTracker()
    with pytest.raises(ValueError):
        tracker.aggregate_delta([], Decimal("22000"), lot_size)
```

---

## Target 3 — P&L arithmetic (`src/paper/tracker.py`)

**Primary test targets are the pure helpers** `_compute_leg_unrealized_pnl` and
`_compute_realized_pnl`. `PaperTracker.compute_pnl` is async and requires a live market
client — do not try to call it directly in property tests.

**Import these as module-level names** (they are not exported via `__init__.py` — import
directly from `src.paper.tracker`).

**Key invariants:**
- Both helpers always return `Decimal` — never `float`
- `_compute_leg_unrealized_pnl` with `net_qty == 0` → always `Decimal("0")`
- Long (net_qty > 0), ltp == avg_cost → unrealized == 0
- Short (net_qty < 0), ltp == avg_sell_price → unrealized == 0
- Long, ltp > avg_cost → unrealized > 0; ltp < avg_cost → unrealized < 0
- Short, ltp < avg_sell_price → unrealized > 0; ltp > avg_sell_price → unrealized < 0
- `_compute_realized_pnl` with zero trades → `Decimal("0")`
- `total = unrealized + realized` — this is the invariant asserted at the `compute_pnl` level;
  property tests verify the components, not the async orchestrator

**Constructing `PaperPosition`:** use `get_code_snippet("PaperPosition")` before writing helpers.
Do not write from memory.

**File:** `tests/unit/paper/test_pnl_hypothesis.py`

---

### H-PNL-1 net_qty == 0 → unrealized always zero

```python
@given(
    avg_cost=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("10000"), allow_nan=False),
    avg_sell_price=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("10000"), allow_nan=False),
    ltp=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("10000"), allow_nan=False),
)
def test_unrealized_zero_qty_is_zero(avg_cost, avg_sell_price, ltp):
    pos = build_paper_position(net_qty=0, avg_cost=avg_cost, avg_sell_price=avg_sell_price)
    result = _compute_leg_unrealized_pnl(pos, ltp)
    assert result == Decimal("0")
```

---

### H-PNL-2 Long position at cost → unrealized == 0

```python
@given(
    avg_cost=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("10000"), allow_nan=False),
    net_qty=st.integers(min_value=1, max_value=1000),
)
def test_long_at_cost_is_flat(avg_cost, net_qty):
    pos = build_paper_position(net_qty=net_qty, avg_cost=avg_cost)
    result = _compute_leg_unrealized_pnl(pos, ltp=avg_cost)
    assert result == Decimal("0")
```

---

### H-PNL-3 Short position at sell price → unrealized == 0

```python
@given(
    avg_sell_price=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("10000"), allow_nan=False),
    net_qty=st.integers(min_value=1, max_value=1000),
)
def test_short_at_sell_price_is_flat(avg_sell_price, net_qty):
    pos = build_paper_position(net_qty=-net_qty, avg_sell_price=avg_sell_price)
    result = _compute_leg_unrealized_pnl(pos, ltp=avg_sell_price)
    assert result == Decimal("0")
```

---

### H-PNL-4 Long position: profit when ltp > avg_cost, loss when ltp < avg_cost

```python
@given(
    avg_cost=st.decimals(min_value=Decimal("1"), max_value=Decimal("5000"), allow_nan=False),
    premium=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("5000"), allow_nan=False),
    net_qty=st.integers(min_value=1, max_value=1000),
)
def test_long_profit_loss_direction(avg_cost, premium, net_qty):
    pos = build_paper_position(net_qty=net_qty, avg_cost=avg_cost)
    ltp_up = avg_cost + premium
    ltp_down = max(Decimal("0.01"), avg_cost - premium)
    assert _compute_leg_unrealized_pnl(pos, ltp_up) >= Decimal("0")
    if ltp_down < avg_cost:
        assert _compute_leg_unrealized_pnl(pos, ltp_down) <= Decimal("0")
```

---

### H-PNL-5 Short position: profit when ltp < avg_sell_price, loss when ltp > avg_sell_price

```python
@given(
    avg_sell_price=st.decimals(min_value=Decimal("1"), max_value=Decimal("5000"), allow_nan=False),
    premium=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("5000"), allow_nan=False),
    net_qty=st.integers(min_value=1, max_value=1000),
)
def test_short_profit_loss_direction(avg_sell_price, premium, net_qty):
    pos = build_paper_position(net_qty=-net_qty, avg_sell_price=avg_sell_price)
    ltp_down = max(Decimal("0.01"), avg_sell_price - premium)
    ltp_up = avg_sell_price + premium
    if ltp_down < avg_sell_price:
        assert _compute_leg_unrealized_pnl(pos, ltp_down) >= Decimal("0")
    assert _compute_leg_unrealized_pnl(pos, ltp_up) <= Decimal("0")
```

---

### H-PNL-6 Return type is always Decimal — never float

```python
@given(
    net_qty=st.integers(min_value=-100, max_value=100),
    avg_cost=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("10000"), allow_nan=False),
    avg_sell_price=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("10000"), allow_nan=False),
    ltp=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("10000"), allow_nan=False),
)
def test_unrealized_return_type_is_decimal(net_qty, avg_cost, avg_sell_price, ltp):
    pos = build_paper_position(net_qty=net_qty, avg_cost=avg_cost, avg_sell_price=avg_sell_price)
    result = _compute_leg_unrealized_pnl(pos, ltp)
    assert isinstance(result, Decimal)
```

---

### H-PNL-7 Realized P&L: no trades → Decimal("0")

```python
def test_realized_pnl_no_trades():
    # Not a @given test — just verifies the zero-trade contract
    # Include here so Antigravity co-locates it with the hypothesis tests
    store = PaperStore(":memory:")
    result = _compute_realized_pnl(store, "paper_test")
    assert result == Decimal("0")
    assert isinstance(result, Decimal)
```

---

## Implementation notes for Antigravity (CH-9b)

1. **Composite strategies.** Implement `ce_position_strategy()`, `pe_position_strategy()`,
   `build_ce_position()`, `build_pe_position()`, and `build_paper_position()` as module-level
   helpers in each test file. Run `get_code_snippet("PaperPosition")` to get current fields
   before writing any helper — do not infer fields from memory.

2. **`hypothesis` settings.** Use `@settings(max_examples=200)` for all tests in this suite.
   Financial property tests benefit from larger example counts.

3. **`st.decimals()` note.** `hypothesis.strategies.decimals()` can produce special values
   (`Inf`, `NaN`, `sNaN`). Always pass `allow_nan=False, allow_infinity=False` unless a test
   specifically targets those inputs.

4. **No mocking of market data.** `_compute_leg_unrealized_pnl` and `_compute_realized_pnl`
   are pure — call them directly. Do not instantiate `PaperTracker` in these tests.

5. **Imports.** Import `_compute_leg_unrealized_pnl` and `_compute_realized_pnl` directly:
   `from src.paper.tracker import _compute_leg_unrealized_pnl, _compute_realized_pnl`

6. **PaperStore in-memory.** Use `PaperStore(":memory:")` for any test that needs a store
   instance (H-PNL-7). Run `get_code_snippet("PaperStore.__init__")` to confirm the
   constructor signature before use.

7. **Test count target.** 6 IVR tests + 6 Delta tests + 7 PnL tests = 19 tests total across
   3 files. All 19 must pass before CH-9b is closed.
