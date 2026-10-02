"""BUG-067 (B067.5): NiftyTrackComparisonV1._persist_roll must flip rolled-out legs to CLOSED.

Uses a real temp-file PaperStore so the state transition is asserted on the
actual paper_trades rows, not on mock call recordings.
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade
from src.paper.store import PaperStore
from src.strategy.nifty_track_comparison_v1 import NiftyTrackComparisonV1
from src.strategy.protocol import ApprovedAction, LegClose, LegSpec

_STRATEGY = "paper_nifty_spot"
_ROLE = "overlay_pp"
_OLD_KEY = "NSE_FO|NIFTY_OLD_PE"
_NEW_KEY = "NSE_FO|NIFTY_NEW_PE"
_TODAY = date(2026, 10, 2)


def _seed(store: PaperStore, key: str, action: TradeAction, day: date) -> None:
    """Insert one 65-unit overlay_pp row."""
    store.record_trade(
        PaperTrade(
            strategy_name=_STRATEGY,
            leg_role=_ROLE,
            instrument_key=key,
            trade_date=day,
            action=action,
            quantity=65,
            price=Decimal("80"),
        )
    )


def _states(store: PaperStore, key: str) -> list[str]:
    """Return the state of every overlay_pp row for ``key``."""
    return [t.state.value for t in store.get_trades(_STRATEGY, _ROLE) if t.instrument_key == key]


def _roll(store: PaperStore) -> None:
    """Roll the open overlay_pp leg from _OLD_KEY into _NEW_KEY via apply_action."""
    strategy = NiftyTrackComparisonV1(store=store)
    action = ApprovedAction(
        action_type="ROLL_OVERLAY",
        legs_to_close=[LegClose(leg_role=_ROLE, instrument_key=_OLD_KEY)],
        legs_to_open=[
            LegSpec(
                instrument_key=_NEW_KEY,
                action="BUY",
                quantity=65,
                leg_role=_ROLE,
                price=Decimal("60"),
            )
        ],
        rationale="test",
        council_rank=1,
        metadata={"strategy_name": _STRATEGY, "mark": "55"},
    )
    with patch("src.strategy.nifty_track_comparison_v1.market_today", return_value=_TODAY):
        asyncio.run(strategy.apply_action(store.get_positions(_STRATEGY), action))


def test_roll_flips_closed_leg_and_keeps_new_leg_open(tmp_path: Path) -> None:
    """Close row inserts → old leg flat → its rows CLOSED; replacement leg stays OPEN."""
    store = PaperStore(tmp_path / "paper.sqlite")
    _seed(store, _OLD_KEY, TradeAction.BUY, date(2026, 9, 20))

    _roll(store)

    assert _states(store, _OLD_KEY) == ["CLOSED", "CLOSED"]
    assert _states(store, _NEW_KEY) == ["OPEN"]
    positions = store.get_positions(_STRATEGY)
    assert [(p.instrument_key, p.net_qty) for p in positions] == [(_NEW_KEY, 65)]


def test_roll_duplicate_close_insert_does_not_flip(tmp_path: Path) -> None:
    """A close skipped as a duplicate (same key/date/SELL already present) leaves
    the old leg's rows OPEN — the store is not flat on that insert's account."""
    store = PaperStore(tmp_path / "paper.sqlite")
    _seed(store, _OLD_KEY, TradeAction.BUY, date(2026, 9, 20))
    _seed(store, _OLD_KEY, TradeAction.BUY, date(2026, 9, 21))
    _seed(store, _OLD_KEY, TradeAction.SELL, _TODAY)  # partial exit already booked today

    _roll(store)  # close: SELL 65 today → conflict on (key, date, SELL)

    assert _states(store, _OLD_KEY) == ["OPEN", "OPEN", "OPEN"]
    assert _states(store, _NEW_KEY) == ["OPEN"]
