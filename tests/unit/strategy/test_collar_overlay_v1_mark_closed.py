"""BUG-067: CollarOverlayV1._close_both_legs must flip closed legs to CLOSED.

Uses a real temp-file PaperStore so the state transition is asserted on the
actual paper_trades rows, not on mock call recordings.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from src.models.portfolio import TradeAction
from src.paper.constants import STRATEGY_OVERLAY
from src.paper.models import PaperTrade
from src.paper.store import PaperStore
from src.strategy.collar_overlay_v1 import LONG_PUT_ROLE, SHORT_CALL_ROLE, CollarOverlayV1
from src.strategy.protocol import ApprovedAction, LegClose

_TODAY = date(2026, 10, 2)
_CALL_KEY = "NSE_FO|CALL"
_PUT_KEY = "NSE_FO|PUT"


def _seed(store: PaperStore, role: str, key: str, action: TradeAction, day: date) -> None:
    """Insert one 75-unit collar leg row."""
    store.record_trade(
        PaperTrade(
            strategy_name=STRATEGY_OVERLAY,
            leg_role=role,
            instrument_key=key,
            trade_date=day,
            action=action,
            quantity=75,
            price=Decimal("40"),
        )
    )


def _seed_collar(store: PaperStore) -> None:
    """Open a short call + long put collar on a prior day."""
    _seed(store, SHORT_CALL_ROLE, _CALL_KEY, TradeAction.SELL, date(2026, 9, 20))
    _seed(store, LONG_PUT_ROLE, _PUT_KEY, TradeAction.BUY, date(2026, 9, 20))


def _states(store: PaperStore, role: str) -> list[str]:
    """Return the state of every collar row for ``role``."""
    return [t.state.value for t in store.get_trades(STRATEGY_OVERLAY, role)]


def _close(store: PaperStore) -> None:
    """Run _close_both_legs against the store's live positions."""
    strategy = CollarOverlayV1(store=store)
    action = ApprovedAction(
        action_type="CLOSE_COLLAR",
        legs_to_close=[LegClose(leg_role=SHORT_CALL_ROLE), LegClose(leg_role=LONG_PUT_ROLE)],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
        metadata={"mark": "30.0"},
    )
    with patch("src.strategy.collar_overlay_v1.market_today", return_value=_TODAY):
        strategy._close_both_legs(store.get_positions(STRATEGY_OVERLAY), action)


def test_close_both_legs_flips_both_legs_to_closed(tmp_path: Path) -> None:
    """Both close rows insert → both legs flat → every row CLOSED."""
    store = PaperStore(tmp_path / "paper.sqlite")
    _seed_collar(store)

    _close(store)

    assert store.get_positions(STRATEGY_OVERLAY) == []
    assert _states(store, SHORT_CALL_ROLE) == ["CLOSED", "CLOSED"]
    assert _states(store, LONG_PUT_ROLE) == ["CLOSED", "CLOSED"]


def test_close_both_legs_duplicate_insert_does_not_flip(tmp_path: Path) -> None:
    """A call close skipped as a duplicate leaves the call OPEN; the put close
    that did insert still flips the put."""
    store = PaperStore(tmp_path / "paper.sqlite")
    _seed(store, SHORT_CALL_ROLE, _CALL_KEY, TradeAction.SELL, date(2026, 9, 20))
    _seed(store, SHORT_CALL_ROLE, _CALL_KEY, TradeAction.SELL, date(2026, 9, 21))
    _seed(store, SHORT_CALL_ROLE, _CALL_KEY, TradeAction.BUY, _TODAY)  # partial buyback
    _seed(store, LONG_PUT_ROLE, _PUT_KEY, TradeAction.BUY, date(2026, 9, 20))

    _close(store)  # call: BUY 75 today → conflict on (key, date, BUY)

    assert _states(store, SHORT_CALL_ROLE) == ["OPEN", "OPEN", "OPEN"]
    assert _states(store, LONG_PUT_ROLE) == ["CLOSED", "CLOSED"]
