"""Unit tests for scripts/position_health_check.py.

Coverage:
- run_position_checks: clean pass — open leg resolves and expiry is in the
  future — returns (False, []).
- run_position_checks: ROLL_OVERDUE — open leg's instrument_key resolves
  but its expiry is strictly before `today` (BUG-017 shape).
- run_position_checks: UNRESOLVED_INSTRUMENT — open leg's instrument_key
  does not resolve against the BOD file at all.
- run_position_checks: closed legs (net_qty == 0) are skipped entirely,
  even when their instrument_key would otherwise trigger a finding —
  mirrors the BUG-014 scoping in PaperStore._resolve_option_type.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.position_health_check import run_position_checks
from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade
from src.paper.store import PaperStore

_STRATEGY = "paper_csp_nifty_v1"
_LEG = "short_put"
_OPEN_KEY = "NSE_FO|11111"
_TODAY = date(2026, 7, 20)


class FakeInstrumentLookup:
    """Offline stand-in for InstrumentLookup — no BOD file I/O."""

    def __init__(self, instruments: dict[str, dict]) -> None:
        self._instruments = instruments

    def get_by_key(self, instrument_key: str) -> dict | None:
        return self._instruments.get(instrument_key)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_paper.db"


def _open_sell_trade(**overrides) -> PaperTrade:
    defaults = dict(
        strategy_name=_STRATEGY,
        leg_role=_LEG,
        instrument_key=_OPEN_KEY,
        trade_date=date(2026, 6, 1),
        action=TradeAction.SELL,
        quantity=75,
        price=Decimal("120.50"),
        notes="entry",
    )
    defaults.update(overrides)
    return PaperTrade(**defaults)


def test_run_position_checks_clean_pass(db_path: Path) -> None:
    store = PaperStore(db_path)
    store.record_trade(_open_sell_trade())
    lookup = FakeInstrumentLookup({_OPEN_KEY: {"instrument_type": "PE", "expiry": "2026-08-25"}})

    has_issue, findings = run_position_checks(store, lookup, _TODAY)

    assert has_issue is False
    assert findings == []


def test_run_position_checks_flags_roll_overdue(db_path: Path) -> None:
    store = PaperStore(db_path)
    store.record_trade(_open_sell_trade())
    # Expiry is 20 days before _TODAY — contract settled, leg never rolled.
    lookup = FakeInstrumentLookup({_OPEN_KEY: {"instrument_type": "PE", "expiry": "2026-06-30"}})

    has_issue, findings = run_position_checks(store, lookup, _TODAY)

    assert has_issue is True
    assert len(findings) == 1
    assert "ROLL_OVERDUE" in findings[0]
    assert _OPEN_KEY in findings[0]


def test_run_position_checks_flags_unresolved_instrument(db_path: Path) -> None:
    store = PaperStore(db_path)
    store.record_trade(_open_sell_trade())
    lookup = FakeInstrumentLookup({})  # instrument_key not in BOD at all

    has_issue, findings = run_position_checks(store, lookup, _TODAY)

    assert has_issue is True
    assert len(findings) == 1
    assert "UNRESOLVED_INSTRUMENT" in findings[0]


def test_run_position_checks_skips_closed_legs(db_path: Path) -> None:
    store = PaperStore(db_path)
    store.record_trade(_open_sell_trade())
    # Closing BUY brings net_qty to 0 — should be skipped even though the
    # lookup would otherwise flag it as unresolved.
    store.record_trade(
        _open_sell_trade(
            action=TradeAction.BUY,
            trade_date=date(2026, 6, 5),
            price=Decimal("10.00"),
        )
    )
    lookup = FakeInstrumentLookup({})  # would be UNRESOLVED_INSTRUMENT if checked

    has_issue, findings = run_position_checks(store, lookup, _TODAY)

    assert has_issue is False
    assert findings == []
