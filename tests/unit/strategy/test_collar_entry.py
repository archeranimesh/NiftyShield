"""Unit tests for src/strategy/collar_entry.py (Collar3b shared reentry selection).

All tests are offline — no network calls, no real chain/BOD/VIX I/O; everything
below the public entry point is mocked.
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from src.strategy.collar_entry import (
    CollarEntrySelectionError,
    select_and_build_collar_entry,
)

_MODULE = "src.strategy.collar_entry"


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _healthy_vix_series() -> pd.Series:
    # 252+ points, flat — compute_ivr's real implementation returns 0.5 for a
    # flat window, which clears the >= 0.25 gate.
    return pd.Series([15.0] * 260)


def _candidate_row(strike: float, instrument_key: str, mid: float, oi: int = 50000) -> dict:
    return {
        "strike": strike,
        "instrument_key": instrument_key,
        "mid": mid,
        "ltp": mid,
        "oi": oi,
        "gate_spread": 1.0,
    }


def _mock_lookup(expiry_str: str = "2026-09-24") -> MagicMock:
    lookup = MagicMock()
    lookup.get_expiry_candidates.return_value = [("monthly", expiry_str)]
    return lookup


def test_happy_path_returns_put_and_call_trades() -> None:
    call_row = _candidate_row(25200, "NSE_FO|NIFTY25200CE", mid=45.0)
    put_row = _candidate_row(23900, "NSE_FO|NIFTY23900PE", mid=38.0)

    mock_broker = MagicMock()
    mock_broker.get_option_chain = AsyncMock(return_value=[{"raw": "chain"}])

    with (
        patch(f"{_MODULE}.InstrumentLookup.from_file", return_value=_mock_lookup()),
        patch(f"{_MODULE}.load_vix_series", return_value=_healthy_vix_series()),
        patch(f"{_MODULE}._find_candidates_for_ladder") as mock_find,
    ):
        # First call = CE ladder, second call = PE ladder (call order in source).
        mock_find.side_effect = [[call_row], [put_row]]

        trades = _run(
            select_and_build_collar_entry(
                mock_broker,
                MagicMock(),
                date(2026, 8, 4),
                "CRASH_MONETIZE",
            )
        )

    assert len(trades) == 2
    put_trade, call_trade = trades
    assert put_trade.leg_role == "overlay_collar_put"
    assert put_trade.instrument_key == "NSE_FO|NIFTY23900PE"
    assert put_trade.price == Decimal("38.0")
    assert call_trade.leg_role == "overlay_collar_call"
    assert call_trade.instrument_key == "NSE_FO|NIFTY25200CE"
    assert call_trade.price == Decimal("45.0")


def test_min_net_premium_tiebreak_selects_best_combo() -> None:
    """Collar2: tiebreak toward minimum |net_premium| among survivors of both bands."""
    call_candidates = [
        _candidate_row(25200, "NSE_FO|NIFTY25200CE", mid=45.0),
        _candidate_row(25400, "NSE_FO|NIFTY25400CE", mid=30.0),
    ]
    put_candidates = [
        _candidate_row(23900, "NSE_FO|NIFTY23900PE", mid=38.0),  # |45-38|=7
    ]
    # combo A: 45 - 38 = 7 (|7|); combo B: 30 - 38 = -8 (|8|) -> A wins.

    mock_broker = MagicMock()
    mock_broker.get_option_chain = AsyncMock(return_value=[{"raw": "chain"}])

    with (
        patch(f"{_MODULE}.InstrumentLookup.from_file", return_value=_mock_lookup()),
        patch(f"{_MODULE}.load_vix_series", return_value=_healthy_vix_series()),
        patch(f"{_MODULE}._find_candidates_for_ladder") as mock_find,
    ):
        mock_find.side_effect = [call_candidates, put_candidates]

        trades = _run(
            select_and_build_collar_entry(
                mock_broker, MagicMock(), date(2026, 8, 4), "DELTA_STOP"
            )
        )

    call_trade = next(t for t in trades if t.leg_role == "overlay_collar_call")
    assert call_trade.instrument_key == "NSE_FO|NIFTY25200CE"


def test_dte_le5_forces_next_month_expiry() -> None:
    """Rule #: closing_dte <= 5 -> select next month's expiry, not the current one."""
    lookup = MagicMock()
    # First call (no min_expiry): current month. Second call (with min_expiry): next month.
    lookup.get_expiry_candidates.side_effect = [
        [("monthly", "2026-08-25")],
        [("monthly", "2026-09-24")],
    ]

    mock_broker = MagicMock()
    mock_broker.get_option_chain = AsyncMock(return_value=[{"raw": "chain"}])

    with (
        patch(f"{_MODULE}.InstrumentLookup.from_file", return_value=lookup),
        patch(f"{_MODULE}.load_vix_series", return_value=_healthy_vix_series()),
        patch(f"{_MODULE}._find_candidates_for_ladder") as mock_find,
    ):
        mock_find.side_effect = [
            [_candidate_row(25200, "NSE_FO|NIFTY25200CE", mid=45.0)],
            [_candidate_row(23900, "NSE_FO|NIFTY23900PE", mid=38.0)],
        ]

        _run(
            select_and_build_collar_entry(
                mock_broker,
                MagicMock(),
                date(2026, 8, 4),
                "DTE_REVIEW",
                closing_dte=3,
            )
        )

    # get_expiry_candidates called twice: once plain, once with min_expiry set
    # to the current month's own expiry (forcing past it to next month).
    assert lookup.get_expiry_candidates.call_count == 2
    second_call_kwargs = lookup.get_expiry_candidates.call_args_list[1].kwargs
    assert second_call_kwargs.get("min_expiry") == "2026-08-25"
    # Chain was fetched for the *next* month's expiry, not the current one.
    mock_broker.get_option_chain.assert_awaited_once()
    assert mock_broker.get_option_chain.call_args[0][1] == "2026-09-24"


def test_dte_gt5_stays_current_month_expiry() -> None:
    lookup = _mock_lookup(expiry_str="2026-08-25")

    mock_broker = MagicMock()
    mock_broker.get_option_chain = AsyncMock(return_value=[{"raw": "chain"}])

    with (
        patch(f"{_MODULE}.InstrumentLookup.from_file", return_value=lookup),
        patch(f"{_MODULE}.load_vix_series", return_value=_healthy_vix_series()),
        patch(f"{_MODULE}._find_candidates_for_ladder") as mock_find,
    ):
        mock_find.side_effect = [
            [_candidate_row(25200, "NSE_FO|NIFTY25200CE", mid=45.0)],
            [_candidate_row(23900, "NSE_FO|NIFTY23900PE", mid=38.0)],
        ]

        _run(
            select_and_build_collar_entry(
                mock_broker,
                MagicMock(),
                date(2026, 8, 4),
                "DTE_REVIEW",
                closing_dte=20,
            )
        )

    # Only one get_expiry_candidates call — no min_expiry re-resolution needed.
    assert lookup.get_expiry_candidates.call_count == 1
    assert mock_broker.get_option_chain.call_args[0][1] == "2026-08-25"


def test_bootstrap_no_closing_dte_stays_current_month() -> None:
    """closing_dte=None (bootstrap, no prior position) behaves like far-from-expiry."""
    lookup = _mock_lookup(expiry_str="2026-08-25")

    mock_broker = MagicMock()
    mock_broker.get_option_chain = AsyncMock(return_value=[{"raw": "chain"}])

    with (
        patch(f"{_MODULE}.InstrumentLookup.from_file", return_value=lookup),
        patch(f"{_MODULE}.load_vix_series", return_value=_healthy_vix_series()),
        patch(f"{_MODULE}._find_candidates_for_ladder") as mock_find,
    ):
        mock_find.side_effect = [
            [_candidate_row(25200, "NSE_FO|NIFTY25200CE", mid=45.0)],
            [_candidate_row(23900, "NSE_FO|NIFTY23900PE", mid=38.0)],
        ]

        _run(
            select_and_build_collar_entry(
                mock_broker, MagicMock(), date(2026, 8, 4), "bootstrap"
            )
        )

    assert lookup.get_expiry_candidates.call_count == 1


def test_bod_load_failure_raises() -> None:
    mock_broker = MagicMock()
    with patch(f"{_MODULE}.InstrumentLookup.from_file", side_effect=OSError("boom")):
        with pytest.raises(CollarEntrySelectionError, match="BOD load failed"):
            _run(
                select_and_build_collar_entry(
                    mock_broker, MagicMock(), date(2026, 8, 4), "x"
                )
            )


def test_no_monthly_expiry_raises() -> None:
    lookup = MagicMock()
    lookup.get_expiry_candidates.return_value = []
    mock_broker = MagicMock()
    with patch(f"{_MODULE}.InstrumentLookup.from_file", return_value=lookup):
        with pytest.raises(CollarEntrySelectionError, match="No monthly expiry"):
            _run(
                select_and_build_collar_entry(
                    mock_broker, MagicMock(), date(2026, 8, 4), "x"
                )
            )


def test_dte_gate_failure_raises() -> None:
    # Expiry only 5 days out -> DTE < 14 gate fails.
    lookup = _mock_lookup(expiry_str="2026-08-09")
    mock_broker = MagicMock()
    with patch(f"{_MODULE}.InstrumentLookup.from_file", return_value=lookup):
        with pytest.raises(CollarEntrySelectionError, match="DTE gate failed"):
            _run(
                select_and_build_collar_entry(
                    mock_broker, MagicMock(), date(2026, 8, 4), "x"
                )
            )


def test_ivr_history_insufficient_raises() -> None:
    lookup = _mock_lookup()
    mock_broker = MagicMock()
    with (
        patch(f"{_MODULE}.InstrumentLookup.from_file", return_value=lookup),
        patch(f"{_MODULE}.load_vix_series", return_value=pd.Series([15.0] * 10)),
    ):
        with pytest.raises(CollarEntrySelectionError, match="IVR history insufficient"):
            _run(
                select_and_build_collar_entry(
                    mock_broker, MagicMock(), date(2026, 8, 4), "x"
                )
            )


def test_ivr_below_gate_raises() -> None:
    lookup = _mock_lookup()
    mock_broker = MagicMock()
    with (
        patch(f"{_MODULE}.InstrumentLookup.from_file", return_value=lookup),
        patch(f"{_MODULE}.load_vix_series", return_value=_healthy_vix_series()),
        patch(f"{_MODULE}.compute_ivr", return_value=0.10),
    ):
        with pytest.raises(CollarEntrySelectionError, match="IVR gate failed"):
            _run(
                select_and_build_collar_entry(
                    mock_broker, MagicMock(), date(2026, 8, 4), "x"
                )
            )


def test_chain_fetch_failure_raises() -> None:
    lookup = _mock_lookup()
    mock_broker = MagicMock()
    mock_broker.get_option_chain = AsyncMock(side_effect=RuntimeError("network down"))
    with (
        patch(f"{_MODULE}.InstrumentLookup.from_file", return_value=lookup),
        patch(f"{_MODULE}.load_vix_series", return_value=_healthy_vix_series()),
    ):
        with pytest.raises(CollarEntrySelectionError, match="Chain fetch failed"):
            _run(
                select_and_build_collar_entry(
                    mock_broker, MagicMock(), date(2026, 8, 4), "x"
                )
            )


def test_empty_chain_raises() -> None:
    lookup = _mock_lookup()
    mock_broker = MagicMock()
    mock_broker.get_option_chain = AsyncMock(return_value=[])
    with (
        patch(f"{_MODULE}.InstrumentLookup.from_file", return_value=lookup),
        patch(f"{_MODULE}.load_vix_series", return_value=_healthy_vix_series()),
    ):
        with pytest.raises(CollarEntrySelectionError, match="empty"):
            _run(
                select_and_build_collar_entry(
                    mock_broker, MagicMock(), date(2026, 8, 4), "x"
                )
            )


def test_no_viable_combo_raises() -> None:
    """Neither ladder clears the liquidity gate -> no candidate on one side."""
    lookup = _mock_lookup()
    mock_broker = MagicMock()
    mock_broker.get_option_chain = AsyncMock(return_value=[{"raw": "chain"}])
    with (
        patch(f"{_MODULE}.InstrumentLookup.from_file", return_value=lookup),
        patch(f"{_MODULE}.load_vix_series", return_value=_healthy_vix_series()),
        patch(f"{_MODULE}._find_candidates_for_ladder") as mock_find,
    ):
        mock_find.side_effect = [[], []]
        with pytest.raises(CollarEntrySelectionError, match="No viable collar combo"):
            _run(
                select_and_build_collar_entry(
                    mock_broker, MagicMock(), date(2026, 8, 4), "x"
                )
            )
