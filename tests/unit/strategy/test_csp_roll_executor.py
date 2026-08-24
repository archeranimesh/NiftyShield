"""Unit tests for extracted csp_roll_executor logic."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.client.protocol import BrokerClient
from src.instruments.lookup import InstrumentLookup
from src.paper.models import PaperTrade, TradeAction
from src.paper.store import PaperStore
from src.strategy.csp_roll_executor import (
    close_csp_leg,
    open_new_csp_leg,
    roll_csp,
    roll_down_and_out,
)


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


@pytest.fixture()
def mock_broker() -> MagicMock:
    broker = MagicMock(spec=BrokerClient)
    broker.get_ltp = AsyncMock(return_value={"NSE_FO|NIFTY23000PE": Decimal("10.50")})
    return broker


@pytest.fixture()
def mock_store() -> MagicMock:
    store = MagicMock(spec=PaperStore)
    return store


@pytest.fixture()
def mock_lookup() -> MagicMock:
    lookup = MagicMock(spec=InstrumentLookup)
    lookup.get_expiry_candidates = MagicMock(return_value=[("monthly", "2026-06-26")])
    return lookup


def test_close_csp_leg_dry_run(mock_broker: MagicMock, mock_store: MagicMock) -> None:
    existing = PaperTrade(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        instrument_key="NSE_FO|NIFTY23000PE",
        trade_date=date(2026, 6, 1),
        action=TradeAction.SELL,
        quantity=50,
        price=Decimal("80.00"),
    )

    close_trade = _run(
        close_csp_leg(mock_broker, mock_store, existing, date(2026, 6, 5), dry_run=True)
    )

    assert close_trade.price == Decimal("10.50")
    assert close_trade.action == TradeAction.BUY
    assert close_trade.quantity == 50
    mock_store.record_trade.assert_not_called()


def test_close_csp_leg_live(mock_broker: MagicMock, mock_store: MagicMock) -> None:
    existing = PaperTrade(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        instrument_key="NSE_FO|NIFTY23000PE",
        trade_date=date(2026, 6, 1),
        action=TradeAction.SELL,
        quantity=50,
        price=Decimal("80.00"),
    )

    close_trade = _run(
        close_csp_leg(mock_broker, mock_store, existing, date(2026, 6, 5), dry_run=False)
    )

    assert close_trade.price == Decimal("10.50")
    mock_store.record_trade.assert_called_once_with(close_trade)
    # BUG-037: closing a CSP leg must transition the opening row to CLOSED,
    # not just insert the closing trade (mirrors BUG-035's overlay fix).
    mock_store.mark_trade_closed.assert_called_once_with(
        "paper_csp_nifty_v1", "short_put", "NSE_FO|NIFTY23000PE"
    )


def test_close_csp_leg_skips_mark_closed_when_duplicate_insert(
    mock_broker: MagicMock, mock_store: MagicMock
) -> None:
    """BUG-037: if record_trade reports a duplicate (already recorded), the
    close must not also call mark_trade_closed — the earlier successful
    close already did."""
    mock_store.record_trade.return_value = False
    existing = PaperTrade(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        instrument_key="NSE_FO|NIFTY23000PE",
        trade_date=date(2026, 6, 1),
        action=TradeAction.SELL,
        quantity=50,
        price=Decimal("80.00"),
    )

    _run(close_csp_leg(mock_broker, mock_store, existing, date(2026, 6, 5), dry_run=False))

    mock_store.mark_trade_closed.assert_not_called()


def test_open_new_csp_leg_dry_run(
    mock_broker: MagicMock, mock_store: MagicMock, mock_lookup: MagicMock
) -> None:
    # Set up option chain matching filter_strikes_by_delta expectations
    mock_broker.get_option_chain = AsyncMock(
        return_value=[
            {
                "strike_price": 22800.0,
                "put_options": {
                    "instrument_key": "NSE_FO|NIFTY22800PE",
                    "option_greeks": {
                        "delta": -0.22,
                        "iv": 15.0,
                    },
                    "market_data": {
                        "ltp": 45.50,
                        "bid_price": 45.0,
                        "ask_price": 46.0,
                        "oi": 50000.0,
                    },
                },
            }
        ]
    )

    new_trade = _run(
        open_new_csp_leg(
            mock_broker,
            mock_store,
            mock_lookup,
            strategy="paper_csp_nifty_v1",
            roll_date=date(2026, 6, 5),
            dry_run=True,
            quantity=50,
        )
    )

    assert new_trade.instrument_key == "NSE_FO|NIFTY22800PE"
    assert new_trade.price == Decimal("45.50")
    mock_store.record_trade.assert_not_called()


def test_open_new_csp_leg_live_invokes_collateral_gate(
    mock_broker: MagicMock, mock_store: MagicMock, mock_lookup: MagicMock
) -> None:
    """RH-4: a live (non-dry-run) open calls the warn-only collateral gate with
    the requested quantity, using LTPs resolved from the same broker.get_ltp
    call — never blocks even when the gate itself reports a breach."""
    mock_broker.get_option_chain = AsyncMock(
        return_value=[
            {
                "strike_price": 22800.0,
                "put_options": {
                    "instrument_key": "NSE_FO|NIFTY22800PE",
                    "option_greeks": {"delta": -0.22, "iv": 15.0},
                    "market_data": {
                        "ltp": 45.50,
                        "bid_price": 45.0,
                        "ask_price": 46.0,
                        "oi": 50000.0,
                    },
                },
            }
        ]
    )
    mock_broker.get_ltp = AsyncMock(
        return_value={
            "NSE_INDEX|Nifty 50": Decimal("24500"),
            "NSE_EQ|INF204KB14I2": Decimal("280"),
        }
    )

    with patch("src.strategy.csp_roll_executor.check_collateral_capacity") as mock_gate:
        mock_gate.return_value = None
        _run(
            open_new_csp_leg(
                mock_broker,
                mock_store,
                mock_lookup,
                strategy="paper_csp_nifty_v1",
                roll_date=date(2026, 6, 5),
                dry_run=False,
                quantity=50,
            )
        )

    mock_gate.assert_called_once()
    _, kwargs = mock_gate.call_args
    assert kwargs["strategy_name"] == "paper_csp_nifty_v1"
    assert kwargs["lots_requested"] == 50
    assert kwargs["nifty_spot"] == Decimal("24500")
    assert kwargs["niftybees_ltp"] == Decimal("280")
    mock_store.record_trade.assert_called_once()


def test_roll_csp_success(
    mock_broker: MagicMock, mock_store: MagicMock, mock_lookup: MagicMock
) -> None:
    existing = PaperTrade(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        instrument_key="NSE_FO|NIFTY23000PE",
        trade_date=date(2026, 6, 1),
        action=TradeAction.SELL,
        quantity=50,
        price=Decimal("80.00"),
    )

    mock_broker.get_option_chain = AsyncMock(
        return_value=[
            {
                "strike_price": 22800.0,
                "put_options": {
                    "instrument_key": "NSE_FO|NIFTY22800PE",
                    "option_greeks": {
                        "delta": -0.22,
                        "iv": 15.0,
                    },
                    "market_data": {
                        "ltp": 45.50,
                        "bid_price": 45.0,
                        "ask_price": 46.0,
                        "oi": 50000.0,
                    },
                },
            }
        ]
    )

    res = _run(
        roll_csp(
            mock_broker,
            mock_store,
            mock_lookup,
            existing,
            roll_date=date(2026, 6, 5),
            dry_run=False,
        )
    )

    assert res.old_instrument_key == "NSE_FO|NIFTY23000PE"
    assert res.close_price == Decimal("10.50")
    assert res.new_instrument_key == "NSE_FO|NIFTY22800PE"
    assert res.new_price == Decimal("45.50")
    assert res.cycle_pnl == (Decimal("80.00") - Decimal("10.50")) * 50
    assert mock_store.record_trade.call_count == 2


def test_roll_csp_rollback_on_failure(
    mock_broker: MagicMock, mock_store: MagicMock, mock_lookup: MagicMock
) -> None:
    existing = PaperTrade(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        instrument_key="NSE_FO|NIFTY23000PE",
        trade_date=date(2026, 6, 1),
        action=TradeAction.SELL,
        quantity=50,
        price=Decimal("80.00"),
    )

    # Make chain fetch fail to trigger error in open_new_csp_leg
    mock_broker.get_option_chain = AsyncMock(return_value=[])

    with pytest.raises(ValueError, match="No option chain data returned"):
        _run(
            roll_csp(
                mock_broker,
                mock_store,
                mock_lookup,
                existing,
                roll_date=date(2026, 6, 5),
                dry_run=False,
            )
        )

    # Check close trade was recorded and then deleted
    assert mock_store.record_trade.call_count == 1
    mock_store.delete_trade.assert_called_once()


def test_open_new_csp_leg_ivr_none_falls_to_mid_tier(
    mock_broker: MagicMock, mock_store: MagicMock, mock_lookup: MagicMock
) -> None:
    # Set up option chain. The mid-tier delta bounds are 0.20 to 0.27.
    # An entry with delta -0.22 falls in bounds; delta -0.32 is out of bounds.
    mock_broker.get_option_chain = AsyncMock(
        return_value=[
            {
                "strike_price": 22800.0,
                "put_options": {
                    "instrument_key": "NSE_FO|NIFTY22800PE",
                    "option_greeks": {"delta": -0.22, "iv": 15.0},
                    "market_data": {
                        "ltp": 45.50,
                        "bid_price": 45.0,
                        "ask_price": 46.0,
                        "oi": 50000.0,
                    },
                },
            }
        ]
    )

    trade = _run(
        open_new_csp_leg(
            mock_broker,
            mock_store,
            mock_lookup,
            strategy="paper_csp_nifty_v1",
            roll_date=date(2026, 6, 5),
            dry_run=True,
            quantity=50,
            ivr=None,
        )
    )
    assert trade.instrument_key == "NSE_FO|NIFTY22800PE"


def test_open_new_csp_leg_ivr_tiers(
    mock_broker: MagicMock, mock_store: MagicMock, mock_lookup: MagicMock
) -> None:
    # IVR < 0.25 (range 0.18-0.24)
    mock_broker.get_option_chain = AsyncMock(
        return_value=[
            {
                "strike_price": 22800.0,
                "put_options": {
                    "instrument_key": "NSE_FO|NIFTY22800PE",
                    "option_greeks": {"delta": -0.19, "iv": 15.0},
                    "market_data": {
                        "ltp": 45.50,
                        "bid_price": 45.0,
                        "ask_price": 46.0,
                        "oi": 50000.0,
                    },
                },
            }
        ]
    )
    trade_low = _run(
        open_new_csp_leg(
            mock_broker,
            mock_store,
            mock_lookup,
            strategy="paper_csp_nifty_v1",
            roll_date=date(2026, 6, 5),
            dry_run=True,
            quantity=50,
            ivr=0.10,
        )
    )
    assert trade_low.instrument_key == "NSE_FO|NIFTY22800PE"

    # IVR > 0.50 (range 0.22-0.30)
    mock_broker.get_option_chain = AsyncMock(
        return_value=[
            {
                "strike_price": 22800.0,
                "put_options": {
                    "instrument_key": "NSE_FO|NIFTY22800PE",
                    "option_greeks": {"delta": -0.28, "iv": 15.0},
                    "market_data": {
                        "ltp": 45.50,
                        "bid_price": 45.0,
                        "ask_price": 46.0,
                        "oi": 50000.0,
                    },
                },
            }
        ]
    )
    trade_high = _run(
        open_new_csp_leg(
            mock_broker,
            mock_store,
            mock_lookup,
            strategy="paper_csp_nifty_v1",
            roll_date=date(2026, 6, 5),
            dry_run=True,
            quantity=50,
            ivr=0.60,
        )
    )
    assert trade_high.instrument_key == "NSE_FO|NIFTY22800PE"


def test_open_new_csp_leg_expiry_override_bypasses_lookup(
    mock_broker: MagicMock, mock_store: MagicMock, mock_lookup: MagicMock
) -> None:
    mock_broker.get_option_chain = AsyncMock(
        return_value=[
            {
                "strike_price": 22800.0,
                "put_options": {
                    "instrument_key": "NSE_FO|NIFTY22800PE",
                    "option_greeks": {"delta": -0.22, "iv": 15.0},
                    "market_data": {
                        "ltp": 45.50,
                        "bid_price": 45.0,
                        "ask_price": 46.0,
                        "oi": 50000.0,
                    },
                },
            }
        ]
    )

    trade = _run(
        open_new_csp_leg(
            mock_broker,
            mock_store,
            mock_lookup,
            strategy="paper_csp_nifty_v1",
            roll_date=date(2026, 6, 5),
            dry_run=True,
            quantity=50,
            expiry_override="2026-06-12",
        )
    )
    assert trade.instrument_key == "NSE_FO|NIFTY22800PE"
    mock_lookup.get_expiry_candidates.assert_not_called()


def test_roll_down_and_out_happy_path(
    mock_broker: MagicMock, mock_store: MagicMock, mock_lookup: MagicMock
) -> None:
    existing = PaperTrade(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        instrument_key="NSE_FO|NIFTY23000PE",
        trade_date=date(2026, 6, 1),
        action=TradeAction.SELL,
        quantity=50,
        price=Decimal("80.00"),
    )

    mock_lookup.get_all_option_expiries = MagicMock(
        return_value=["2026-06-12", "2026-06-19", "2026-06-26"]
    )

    # Candidate 1: 2026-06-12 (7 days from 2026-06-05) -> DTE = 7
    # Use key containing "12JUN2026" so _parse_expiry_from_key succeeds
    mock_broker.get_option_chain = AsyncMock(
        return_value=[
            {
                "strike_price": 22800.0,
                "put_options": {
                    "instrument_key": "NSE_FO|NIFTY12JUN2026PE",
                    "option_greeks": {"delta": -0.22, "iv": 15.0},
                    "market_data": {
                        "ltp": 45.50,
                        "bid_price": 45.0,
                        "ask_price": 46.0,
                        "oi": 50000.0,
                    },
                },
            }
        ]
    )

    res = _run(
        roll_down_and_out(
            mock_broker,
            mock_store,
            mock_lookup,
            existing,
            roll_date=date(2026, 6, 5),
            ivr=0.30,
            dry_run=False,
        )
    )

    assert res.old_instrument_key == "NSE_FO|NIFTY23000PE"
    assert res.new_instrument_key == "NSE_FO|NIFTY12JUN2026PE"
    assert res.new_expiry == "2026-06-12"
    assert res.new_dte == 7
    assert mock_store.record_trade.call_count == 2


def test_roll_down_and_out_fallback_c2(
    mock_broker: MagicMock, mock_store: MagicMock, mock_lookup: MagicMock
) -> None:
    existing = PaperTrade(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        instrument_key="NSE_FO|NIFTY23000PE",
        trade_date=date(2026, 6, 1),
        action=TradeAction.SELL,
        quantity=50,
        price=Decimal("80.00"),
    )

    mock_lookup.get_all_option_expiries = MagicMock(
        return_value=["2026-06-12", "2026-06-19", "2026-06-26"]
    )

    # 1st call (Candidate 1: 2026-06-12) has no PE strikes in delta range
    # 2nd call (Candidate 2: 2026-06-19) returns valid strikes with parseable key
    def get_chain_side_effect(underlying, expiry):
        if expiry == "2026-06-12":
            return [
                {
                    "strike_price": 22800.0,
                    "put_options": {
                        "instrument_key": "NSE_FO|NIFTY12JUN2026PE",
                        "option_greeks": {
                            "delta": -0.05,
                            "iv": 15.0,
                        },  # out of delta range [0.20, 0.27]
                        "market_data": {
                            "ltp": 5.0,
                            "bid_price": 4.5,
                            "ask_price": 5.5,
                            "oi": 5000.0,
                        },
                    },
                }
            ]
        elif expiry == "2026-06-19":
            return [
                {
                    "strike_price": 22800.0,
                    "put_options": {
                        "instrument_key": "NSE_FO|NIFTY19JUN2026PE",
                        "option_greeks": {"delta": -0.22, "iv": 15.0},
                        "market_data": {
                            "ltp": 45.50,
                            "bid_price": 45.0,
                            "ask_price": 46.0,
                            "oi": 50000.0,
                        },
                    },
                }
            ]
        return []

    mock_broker.get_option_chain = AsyncMock(side_effect=get_chain_side_effect)

    res = _run(
        roll_down_and_out(
            mock_broker,
            mock_store,
            mock_lookup,
            existing,
            roll_date=date(2026, 6, 5),
            ivr=0.30,
            dry_run=False,
        )
    )

    assert res.new_expiry == "2026-06-19"
    assert res.new_dte == 14
    assert mock_store.record_trade.call_count == 2


def test_roll_down_and_out_c1_dte_too_large_raises_value_error(
    mock_broker: MagicMock, mock_store: MagicMock, mock_lookup: MagicMock
) -> None:
    existing = PaperTrade(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        instrument_key="NSE_FO|NIFTY23000PE",
        trade_date=date(2026, 6, 1),
        action=TradeAction.SELL,
        quantity=50,
        price=Decimal("80.00"),
    )

    # Expiring in 22 days (> 21 days)
    mock_lookup.get_all_option_expiries = MagicMock(return_value=["2026-06-27"])

    with pytest.raises(ValueError, match="Next weekly expiry exceeds 21 DTE"):
        _run(
            roll_down_and_out(
                mock_broker,
                mock_store,
                mock_lookup,
                existing,
                roll_date=date(2026, 6, 5),
                ivr=0.30,
                dry_run=False,
            )
        )


def test_roll_down_and_out_no_valid_strikes_both_candidates(
    mock_broker: MagicMock, mock_store: MagicMock, mock_lookup: MagicMock
) -> None:
    existing = PaperTrade(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        instrument_key="NSE_FO|NIFTY23000PE",
        trade_date=date(2026, 6, 1),
        action=TradeAction.SELL,
        quantity=50,
        price=Decimal("80.00"),
    )

    mock_lookup.get_all_option_expiries = MagicMock(return_value=["2026-06-12", "2026-06-19"])

    # Empty chain returns for both to trigger strike resolution failure
    mock_broker.get_option_chain = AsyncMock(
        return_value=[
            {
                "strike_price": 22800.0,
                "put_options": {
                    "instrument_key": "NSE_FO|NIFTY12JUN2026PE",
                    "option_greeks": {"delta": -0.05, "iv": 15.0},  # delta out of range
                    "market_data": {"ltp": 5.0, "bid_price": 4.5, "ask_price": 5.5, "oi": 5000.0},
                },
            }
        ]
    )

    with pytest.raises(ValueError, match="No PE strikes found in delta range"):
        _run(
            roll_down_and_out(
                mock_broker,
                mock_store,
                mock_lookup,
                existing,
                roll_date=date(2026, 6, 5),
                ivr=0.30,
                dry_run=False,
            )
        )


def test_roll_down_and_out_c2_warns_when_dte_too_large(
    mock_broker: MagicMock, mock_store: MagicMock, mock_lookup: MagicMock
) -> None:
    existing = PaperTrade(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        instrument_key="NSE_FO|NIFTY23000PE",
        trade_date=date(2026, 6, 1),
        action=TradeAction.SELL,
        quantity=50,
        price=Decimal("80.00"),
    )

    # Candidate 2 (2026-06-30) is 25 DTE (> 21 DTE) from 2026-06-05
    mock_lookup.get_all_option_expiries = MagicMock(return_value=["2026-06-12", "2026-06-30"])

    # Candidate 1 strike search fails (due to delta, not empty chain)
    def get_chain_side_effect(underlying, expiry):
        if expiry == "2026-06-12":
            return [
                {
                    "strike_price": 22800.0,
                    "put_options": {
                        "instrument_key": "NSE_FO|NIFTY12JUN2026PE",
                        "option_greeks": {"delta": -0.05, "iv": 15.0},  # fails delta range
                        "market_data": {
                            "ltp": 5.0,
                            "bid_price": 4.5,
                            "ask_price": 5.5,
                            "oi": 5000.0,
                        },
                    },
                }
            ]
        elif expiry == "2026-06-30":
            return [
                {
                    "strike_price": 22800.0,
                    "put_options": {
                        "instrument_key": "NSE_FO|NIFTY30JUN2026PE",
                        "option_greeks": {"delta": -0.22, "iv": 15.0},
                        "market_data": {
                            "ltp": 45.50,
                            "bid_price": 45.0,
                            "ask_price": 46.0,
                            "oi": 50000.0,
                        },
                    },
                }
            ]
        return []

    mock_broker.get_option_chain = AsyncMock(side_effect=get_chain_side_effect)

    with patch("src.strategy.csp_roll_executor.logger.warning") as mock_warn:
        res = _run(
            roll_down_and_out(
                mock_broker,
                mock_store,
                mock_lookup,
                existing,
                roll_date=date(2026, 6, 5),
                ivr=0.30,
                dry_run=False,
            )
        )
        assert res.new_expiry == "2026-06-30"
        mock_warn.assert_called_once_with(
            "roll_down_and_out.monthly_fallback",
            candidate_2="2026-06-30",
            dte=25,
        )
