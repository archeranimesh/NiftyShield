# PB1.1 — `src/strategy/protocol.py`: PaperStrategy protocol + models + tests
> **Assigned to: Antigravity** — 4 files, fully spec'd, no inline judgment required.

**Files to change:**
- `src/strategy/__init__.py` — new package, single comment line only
- `src/strategy/protocol.py` — `PaperStrategy` protocol + `SignalEvent` + `ApprovedAction` + `LegSpec` models
- `tests/unit/strategy/__init__.py` — new test package, single comment line only
- `tests/unit/strategy/test_strategy_protocol.py` — model + protocol conformance tests

**Package structure — create all stubs now:**

```
src/strategy/
├── __init__.py           (this task)
├── protocol.py           (this task)
├── monitor.py            (PB1.2)
├── executor.py           (PB1.3)
├── csp_nifty_v1.py       (PB2.1)
├── ic_nifty_v1.py        (PB3.1)
└── nifty_track_comparison_v1.py  (PB4.1)
```

Create all `__init__.py` stubs (single comment line) in `src/strategy/` and
`tests/unit/strategy/` now to avoid missing-package failures in later tasks.

**What to implement (`src/strategy/protocol.py`):**

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

from src.models.options import OptionChain
from src.paper.models import PaperPosition


@dataclass(frozen=True)
class LegSpec:
    """Describes one leg to open as part of an ApprovedAction."""
    instrument_key: str
    action: Literal["BUY", "SELL"]
    quantity: int
    leg_role: str          # e.g. "short_put", "long_put_hedge"
    notes: str = ""


@dataclass(frozen=True)
class SignalEvent:
    """Emitted by a strategy when it detects something worth acting on."""
    event_type: str
    severity: Literal["INFO", "WARN", "ACTION"]
    description: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ApprovedAction:
    """An action approved by the council and optionally by the user via Telegram."""
    action_type: str
    legs_to_close: list[str]    # leg_role values of positions to close
    legs_to_open: list[LegSpec]
    rationale: str
    council_rank: int           # 1 = top pick


@runtime_checkable
class PaperStrategy(Protocol):
    """
    Contract every pluggable strategy must satisfy.

    The StrategyMonitor calls check_signals() on every tick for every registered strategy.
    Only ACTION severity events trigger council consultation + Telegram approval.
    WARN events send a plain Telegram message with no approval flow.
    INFO events are logged silently.
    """

    strategy_name: str   # must start with "paper_"

    async def check_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """Return [] if nothing to act on. Return events to trigger council or alerts."""
        ...

    def describe_context(
        self,
        event: SignalEvent,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> str:
        """Structured context string for the council prompt. Plain text, no HTML."""
        ...

    async def apply_action(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> list[PaperPosition]:
        """Apply an approved action. Returns updated position list."""
        ...
```

All three methods are `async` even if the concrete implementation is synchronous —
`check_signals` and `apply_action` are `async` because live implementations will call
`UpstoxLiveClient`; `describe_context` is sync (pure string building).

**Tests (`tests/unit/strategy/test_strategy_protocol.py`):**

Write a `MockStrategy` class that satisfies `PaperStrategy` with no-op implementations.

- `isinstance(MockStrategy(), PaperStrategy)` → `True` (runtime_checkable).
- `SignalEvent` with `severity="INFO"` → frozen dataclass, no error.
- `SignalEvent` with `severity="ACTION"` → `payload` accepts arbitrary dict.
- `ApprovedAction` with empty `legs_to_close` and empty `legs_to_open` → valid.
- `LegSpec` with `action="BUY"` → `quantity` and `leg_role` stored correctly.
- A class missing `check_signals` → `isinstance(..., PaperStrategy)` → `False`.

**Commit:** `feat(strategy): add PaperStrategy protocol + SignalEvent + ApprovedAction + LegSpec models`

---

## Pre-baked Context

> Graph queries pre-run 2026-05-31. Skip "Before any code" graph calls — use these directly.

**`PaperStrategy`** — does NOT yet exist (zero results from graph). ✅ Safe to create.

**`PaperTrade`** — `src/paper/models.py:28`. Frozen Pydantic (`model_config = {"frozen": True}`).
Fields: `strategy_name`, `leg_role`, `instrument_key`, `trade_date: date`, `action: TradeAction`,
`quantity: int`, `price: Decimal`, `notes: str = ""`, `ivr_at_entry: float | None`, `is_paper: Literal[True]`.
Validator: `strategy_name` must start with `"paper_"`.

**`PortfolioDeltaTracker`** — `src/risk/delta_tracker.py:58`. ✅ Committed. Prerequisite confirmed.

**`OptionChain`** — `src/models/options.py:69`. Import: `from src.models.options import OptionChain`.
Fields: `underlying_spot: Decimal`, `expiry: date`, `strikes: dict[Decimal, OptionChainStrike]`.

**`PaperPosition`** — `src/paper/models.py:95`. Dataclass (NOT Pydantic — note no `model_config`).
Fields: `strategy_name: str`, `leg_role: str`, `net_qty: int`, `avg_cost: Decimal`,
`avg_sell_price: Decimal`, `instrument_key: str`.
