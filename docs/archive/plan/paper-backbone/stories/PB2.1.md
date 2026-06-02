# PB2.1 — `src/strategy/csp_nifty_v1.py`: CSPNiftyV1 + tests
> **Assigned to: Claude** — signal thresholds require reading and interpreting csp_nifty_v1.md spec.

**Files to change:**
- `src/strategy/csp_nifty_v1.py` — `CSPNiftyV1` implements `PaperStrategy`
- `tests/unit/strategy/test_csp_nifty_v1.py` — new test file

**Before implementing:** Read `docs/strategies/csp_nifty_v1.md` — authoritative strategy spec
(entry rules, exit triggers, delta thresholds). Do not implement from memory.

**Context:** CSP is already running via `record_paper_trade.py` + `paper_3track_snapshot.py`.
This phase adds the backbone-compatible class so the daemon can auto-detect exit signals.
Existing `paper_trades` rows are unaffected. Entry remains manual.

**What to implement:**

```python
class CSPNiftyV1:
    strategy_name = "paper_csp_nifty_v1"

    async def check_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """
        Filter positions to strategy_name == "paper_csp_nifty_v1".
        If no open positions: return [].
        For each open short_put leg, evaluate exit signals per spec.
        """
```

Signal table (from strategy spec):

| Event type | Severity | Trigger |
|---|---|---|
| `PROFIT_TARGET` | ACTION | mark ≤ 50% of entry credit |
| `LOSS_STOP` | ACTION | mark ≥ 2.0× entry credit |
| `DELTA_STOP` | ACTION | short put \|delta\| ≥ 0.35 |
| `TIME_STOP` | ACTION | DTE ≤ 21 |
| `ROLL_DUE_DTE` | WARN | DTE ≤ 5 |
| `ROLL_DUE_DECAY` | WARN | current premium ≤ 25% of entry premium |
| `DELTA_WARN` | WARN | short put \|delta\| ≥ 0.25 |

`apply_action()` accepts `CLOSE_FULL` only. Any other `action_type` raises `ValueError`.
Entry is manual — no `ENTER_*` action type.

`describe_context()` — returns a structured plain-text string: current delta, DTE,
mark vs entry credit, % of credit captured, IVR, Nifty spot.

**Tests (`tests/unit/strategy/test_csp_nifty_v1.py`):**

- No open positions → `check_signals` returns `[]`.
- Short put with mark = 48% of entry credit → `PROFIT_TARGET` ACTION event.
- Short put with mark = 210% of entry credit → `LOSS_STOP` ACTION event.
- Short put with `|delta| = 0.36` → `DELTA_STOP` ACTION event.
- Short put with DTE = 20 → `TIME_STOP` ACTION event.
- Short put with DTE = 4 → `ROLL_DUE_DTE` WARN event.
- Short put with mark = 24% of entry premium → `ROLL_DUE_DECAY` WARN event.
- Short put with `|delta| = 0.27` → `DELTA_WARN` WARN event.
- Short put with mark = 60%, `|delta| = 0.20`, DTE = 30 → `[]` (no events).
- `apply_action` with `CLOSE_FULL` → no error.
- `apply_action` with `ADJUST` → raises `ValueError`.

**Commit:** `feat(strategy): add CSPNiftyV1 backbone integration`

---

## Pre-baked Context

> Graph queries pre-run 2026-05-31. Skip "Before any code" graph calls — use these directly.

**`PaperStrategy`** — `src/strategy/protocol.py` (PB1.1). `@runtime_checkable` Protocol.
Methods: `async check_signals(market, positions) -> list[SignalEvent]`,
`describe_context(event, market, positions) -> str`,
`async apply_action(positions, action) -> list[PaperPosition]`.

**`PaperPosition`** — `src/paper/models.py:95`. Dataclass (NOT Pydantic).
Fields: `strategy_name: str`, `leg_role: str`, `net_qty: int`, `avg_cost: Decimal`,
`avg_sell_price: Decimal`, `instrument_key: str`.
`net_qty < 0` → short position. For a short put: `avg_sell_price` = entry credit received.

**`OptionChain`** — `src/models/options.py:69`.
Fields: `underlying_spot: Decimal`, `expiry: date`, `strikes: dict[Decimal, OptionChainStrike]`.
To find delta for a strike: `chain.strikes[strike].put_greeks.delta` (confirm field names
with `get_code_snippet("OptionChainStrike")` if needed).

**`get_expiry_candidates`** — `src/instruments/lookup.py:275` on `InstrumentLookup`.
Import: `from src.instruments.lookup import InstrumentLookup`.
For DTE calculation in `check_signals`: use `(expiry_date - date.today()).days` directly
from the `PaperPosition.instrument_key` decoded expiry — do not call `get_expiry_candidates`
at signal-check time (too slow). Derive DTE from the open leg's instrument expiry instead.
