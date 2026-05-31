# PB1.3 — `src/strategy/executor.py`: PaperExecutor + PaperFillSimulator + tests

**Files to change:**
- `src/strategy/executor.py` — `PaperFillSimulator` + `PaperExecutor`
- `tests/unit/strategy/test_executor.py` — new test file

**Before implementing `PaperFillSimulator`:** Read `DECISIONS.md` section on slippage model.
Port the model exactly as documented — do not reinvent.

**What to implement:**

**`PaperFillSimulator`** — VIX-regime slippage model from `DECISIONS.md §Slippage`.

```python
@dataclass(frozen=True)
class FillResult:
    instrument_key: str
    action: Literal["BUY", "SELL"]
    quantity: int
    fill_price: Decimal     # mid ± slippage
    slippage: Decimal       # absolute slip applied


class PaperFillSimulator:
    def simulate_fill(
        self,
        instrument_key: str,
        action: Literal["BUY", "SELL"],
        quantity: int,
        mid_price: Decimal,
        vix: float | None = None,
    ) -> FillResult:
        """
        Compute synthetic fill using VIX-regime slippage model.
        BUY fill_price = mid + slippage (paid more).
        SELL fill_price = mid - slippage (received less).
        """
```

**`PaperExecutor`** — thin layer over `PaperStore`. Given an `ApprovedAction`:

```python
class PaperExecutor:
    def __init__(
        self,
        store: PaperStore,
        simulator: PaperFillSimulator,
        db_path: str,
    ) -> None: ...

    def apply(
        self,
        strategy_name: str,
        action: ApprovedAction,
        market: OptionChain,
        approval_id: int,
        vix: float | None = None,
    ) -> list[PaperPosition]:
        """
        1. For each leg_role in action.legs_to_close: record a closing trade via
           PaperStore.record_trade (action=opposite of entry, price=simulated fill).
        2. For each LegSpec in action.legs_to_open: simulate fill, call
           PaperStore.record_trade to open the leg.
        3. Write a row to council_outputs for audit (approval_id FK).
        4. Return the updated list[PaperPosition] from PaperStore.get_open_positions().
        """
```

**Tests (`tests/unit/strategy/test_executor.py`):**

- `PaperFillSimulator.simulate_fill` with low VIX → slippage in low-vol band.
- `simulate_fill` with high VIX → slippage in high-vol band.
- `simulate_fill` with `vix=None` → uses base/default slippage, no error.
- BUY fill_price > mid; SELL fill_price < mid.
- `PaperExecutor.apply` with one leg to open → `PaperStore.record_trade` called once with
  correct `action`, `price`, `strategy_name`.
- `PaperExecutor.apply` with one leg to close → closing trade recorded with opposite action.
- `apply` with empty `legs_to_open` and empty `legs_to_close` → no store calls, returns
  current positions unchanged.

**Commit:** `feat(strategy): add PaperFillSimulator + PaperExecutor`

---

## Pre-baked Context

> Graph queries pre-run 2026-05-31. Skip "Before any code" graph calls — use these directly.

**`PaperStore.record_trade`** — `src/paper/store.py:143`. Signature: `record_trade(self, trade: PaperTrade) -> bool`.
Uniqueness constraint on `(strategy_name, leg_role, trade_date, action)`. Returns `True` if inserted.

**`PaperTrade`** — `src/paper/models.py:28`. Frozen Pydantic.
Fields: `strategy_name`, `leg_role`, `instrument_key`, `trade_date: date`, `action: TradeAction`,
`quantity: int`, `price: Decimal`, `notes: str = ""`, `ivr_at_entry: float | None`, `is_paper: Literal[True]`.
`TradeAction` enum: import from `src/portfolio/models.py` — values are `BUY` / `SELL`.
`strategy_name` must start with `"paper_"` (validator enforced).

**`ApprovedAction`** — defined in `src/strategy/protocol.py` (PB1.1).
Fields: `action_type: str`, `legs_to_close: list[str]`, `legs_to_open: list[LegSpec]`,
`rationale: str`, `council_rank: int`.

**`LegSpec`** — frozen dataclass in `src/strategy/protocol.py`.
Fields: `instrument_key: str`, `action: Literal["BUY","SELL"]`, `quantity: int`, `leg_role: str`, `notes: str = ""`.

**`compute_ivr`** — `src/backtest/ivr.py:15`. Import: `from src.backtest.ivr import compute_ivr`.
Signature: `compute_ivr(vix_today: float, vix_series: pd.Series) -> float | None`.
(Note: PaperFillSimulator receives `vix: float | None` directly — no need to call compute_ivr here.)

**DB connect** — `src/db.py`. Function name is `connect` (not `db_connection`).
Import: `from src.db import connect`. Context manager: `with connect(db_path) as conn:`.
