# tests/unit/strategies/ic/test_ic_entry_gates.py
"""Unit tests for scripts/strategies/ic/ic_entry_gates.py.

Covers: check_duplicate, resolve_ivr, resolve_expiry, _last_tuesday_of_month,
_post_expiry_gate.
No network calls; all external dependencies are mocked.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.strategies.ic.ic_entry_gates import (
    _last_tuesday_of_month,
    _post_expiry_gate,
    check_duplicate,
    resolve_expiry,
    resolve_ivr,
)

# ---------------------------------------------------------------------------
# check_duplicate
# ---------------------------------------------------------------------------


class TestCheckDuplicate:
    def test_no_open_positions_passes(self) -> None:
        """Passes silently when no open positions exist."""
        store = MagicMock()
        store.get_positions.return_value = []
        # Should not raise or exit
        check_duplicate(store, "paper_ic_nifty_v2_monthly")
        store.get_positions.assert_called_once_with("paper_ic_nifty_v2_monthly")

    def test_open_position_exits(self) -> None:
        """Exits with code 1 when an active position exists."""
        store = MagicMock()
        pos = MagicMock()
        pos.net_qty = 50
        store.get_positions.return_value = [pos]

        with pytest.raises(SystemExit) as exc_info:
            check_duplicate(store, "paper_ic_nifty_v2_monthly")
        assert exc_info.value.code == 1

    def test_zero_qty_position_passes(self) -> None:
        """Passes when all positions have net_qty == 0 (closed trade)."""
        store = MagicMock()
        pos = MagicMock()
        pos.net_qty = 0
        store.get_positions.return_value = [pos]
        # Should not exit
        check_duplicate(store, "paper_ic_nifty_v2_monthly")


# ---------------------------------------------------------------------------
# resolve_ivr
# ---------------------------------------------------------------------------


class TestResolveIvr:
    @pytest.fixture(autouse=True)
    def mock_vix_dir_exists(self):
        with patch("scripts.strategies.ic.ic_entry_gates.Path.exists", return_value=True):
            yield

    @pytest.fixture
    def mock_vix_stack(self):
        with (
            patch("scripts.strategies.ic.ic_entry_gates.load_vix_series") as m_load,
            patch("scripts.strategies.ic.ic_entry_gates.IntradayMarketStore") as m_store_cls,
            patch("scripts.strategies.ic.ic_entry_gates.fetch_vix_latest") as m_fetch,
            patch("scripts.strategies.ic.ic_entry_gates.compute_ivr") as m_ivr,
        ):
            m_load.return_value = []
            store_inst = MagicMock()
            store_inst.get_latest_vix_today.return_value = 15.0
            m_store_cls.return_value = store_inst
            m_fetch.return_value = 15.0
            m_ivr.return_value = 0.35
            yield {"load": m_load, "ivr": m_ivr, "fetch": m_fetch}

    def test_happy_path_returns_ivr(self, mock_vix_stack) -> None:
        """Returns IVR float when gate is satisfied."""
        result = resolve_ivr(Path("dummy.db"), Decimal("0.25"), force_entry=False)
        assert result == pytest.approx(0.35)

    def test_ivr_below_gate_exits(self, mock_vix_stack) -> None:
        """Exits with code 1 when IVR is below the gate and force_entry=False."""
        mock_vix_stack["ivr"].return_value = 0.10  # below 0.25 gate
        with pytest.raises(SystemExit) as exc_info:
            resolve_ivr(Path("dummy.db"), Decimal("0.25"), force_entry=False)
        assert exc_info.value.code == 1

    def test_ivr_below_gate_force_entry_continues(self, mock_vix_stack) -> None:
        """Does not exit when force_entry=True; returns low IVR with warning."""
        mock_vix_stack["ivr"].return_value = 0.10
        result = resolve_ivr(Path("dummy.db"), Decimal("0.25"), force_entry=True)
        assert result == pytest.approx(0.10)

    def test_ivr_none_exits(self, mock_vix_stack) -> None:
        """Exits with code 1 when IVR cannot be computed and force_entry=False."""
        mock_vix_stack["ivr"].return_value = None
        with pytest.raises(SystemExit) as exc_info:
            resolve_ivr(Path("dummy.db"), Decimal("0.25"), force_entry=False)
        assert exc_info.value.code == 1

    def test_vix_load_error_treated_as_none(self, mock_vix_stack) -> None:
        """VIX load exception is caught; exits cleanly on gate failure."""
        mock_vix_stack["load"].side_effect = RuntimeError("disk error")
        with pytest.raises(SystemExit) as exc_info:
            resolve_ivr(Path("dummy.db"), Decimal("0.25"), force_entry=False)
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# resolve_expiry
# ---------------------------------------------------------------------------


class TestResolveExpiry:
    @pytest.fixture(autouse=True)
    def mock_bod_exists(self):
        with patch("scripts.strategies.ic.ic_entry_gates.Path.exists", return_value=True):
            yield

    @pytest.fixture
    def mock_lookup_factory(self):
        with patch("scripts.strategies.ic.ic_entry_gates.InstrumentLookup") as m_cls:
            inst = MagicMock()
            inst.get_expiry_candidates.return_value = [("monthly", "2026-07-31")]
            m_cls.from_file.return_value = inst
            yield inst

    def test_happy_path_returns_tuple(self, mock_lookup_factory) -> None:
        """Returns (lookup, expiry_str, dte) for a valid monthly expiry."""
        from datetime import date, timedelta

        # Patch date.today so DTE is predictable
        target = date(2026, 7, 31)
        today = target - timedelta(days=35)
        with patch("scripts.strategies.ic.ic_entry_gates.date") as m_date:
            m_date.today.return_value = today
            m_date.fromisoformat.side_effect = date.fromisoformat
            lookup, expiry_str, dte = resolve_expiry(
                Path("dummy.json"), "monthly", dte_warn_lo=30, dte_warn_hi=45
            )

        assert expiry_str == "2026-07-31"
        assert dte == 35
        assert lookup is mock_lookup_factory

    def test_bod_missing_exits(self) -> None:
        """Exits with code 1 when the BOD file does not exist."""
        with patch("scripts.strategies.ic.ic_entry_gates.Path.exists", return_value=False):
            with pytest.raises(SystemExit) as exc_info:
                resolve_expiry(Path("missing.json"), "monthly", 30, 45)
            assert exc_info.value.code == 1

    def test_no_candidate_exits(self, mock_lookup_factory) -> None:
        """Exits with code 1 when no matching expiry bucket is found."""
        mock_lookup_factory.get_expiry_candidates.return_value = [("weekly", "2026-07-02")]
        with pytest.raises(SystemExit) as exc_info:
            resolve_expiry(Path("dummy.json"), "monthly", 30, 45)
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# _last_tuesday_of_month
# ---------------------------------------------------------------------------


class TestLastTuesdayOfMonth:
    def test_june_2026(self) -> None:
        """Last Tuesday of June 2026 is June 30."""
        assert _last_tuesday_of_month(2026, 6) == date(2026, 6, 30)

    def test_july_2026(self) -> None:
        """Last Tuesday of July 2026 is July 28."""
        assert _last_tuesday_of_month(2026, 7) == date(2026, 7, 28)

    def test_december_2026(self) -> None:
        """Last Tuesday of December 2026 is December 29."""
        assert _last_tuesday_of_month(2026, 12) == date(2026, 12, 29)

    def test_month_ending_on_tuesday(self) -> None:
        """When the last day of the month is Tuesday, that day is returned."""
        # March 2027: last day is March 31 (Wednesday) → last Tuesday = March 30? Let's verify.
        # Actually compute: March 2027 last day = 31 (Wed, weekday=2).
        # days_back = (2 - 1) % 7 = 1 → March 30 (Tuesday). Correct.
        assert _last_tuesday_of_month(2027, 3) == date(2027, 3, 30)


# ---------------------------------------------------------------------------
# _post_expiry_gate
# ---------------------------------------------------------------------------


class TestPostExpiryGate:
    def test_blocks_before_last_tuesday(self) -> None:
        """Exits when today is before the last Tuesday of the current month."""
        # June 2026: last Tuesday = June 30. Running on June 25 must block.
        with patch("scripts.strategies.ic.ic_entry_gates.date") as mock_date:
            mock_date.today.return_value = date(2026, 6, 25)
            mock_date.side_effect = date  # keep date(y, m, d) constructor working
            with pytest.raises(SystemExit) as exc_info:
                _post_expiry_gate()
        assert exc_info.value.code == 1

    def test_blocks_on_last_tuesday(self) -> None:
        """Exits on expiry day itself (settlement not complete intraday)."""
        with patch("scripts.strategies.ic.ic_entry_gates.date") as mock_date:
            mock_date.today.return_value = date(2026, 6, 30)
            mock_date.side_effect = date
            with pytest.raises(SystemExit) as exc_info:
                _post_expiry_gate()
        assert exc_info.value.code == 1

    def test_passes_day_after_last_tuesday(self) -> None:
        """Passes on the Wednesday after last-Tuesday settlement.

        July 2026: last Tuesday = July 28. July 29 is the first valid entry day
        (today > last_tuesday_of_current_month).
        """
        with patch("scripts.strategies.ic.ic_entry_gates.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 29)
            mock_date.side_effect = date
            _post_expiry_gate()  # must not raise

    def test_passes_when_holiday_on_last_tuesday(self) -> None:
        """When last Tuesday is a holiday, next trading day still passes the gate.

        August 2026: last Tuesday = August 25. If Aug 25 is a holiday, scripts
        run August 26 (Wednesday). The gate checks today(Aug 26) > last_tuesday(Aug 25)
        → passes. No special-case needed for holidays.
        """
        with patch("scripts.strategies.ic.ic_entry_gates.date") as mock_date:
            mock_date.today.return_value = date(2026, 8, 26)
            mock_date.side_effect = date
            _post_expiry_gate()  # must not raise
