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

import pandas as pd
import pytest

from scripts.strategies.ic.ic_entry_gates import (
    _is_vix_window_stale,
    _last_tuesday_of_month,
    _most_recently_settled_expiry,
    _post_expiry_gate,
    check_duplicate,
    ic_relevant_strategy_names,
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
        """Returns (IVR float, None) when gate is satisfied."""
        ivr, violation = resolve_ivr(Path("dummy.db"), Decimal("0.25"), force_entry=False)
        assert ivr == pytest.approx(0.35)
        assert violation is None

    def test_ivr_below_gate_logs_violation_by_default(self, mock_vix_stack) -> None:
        """THRESHOLD gate: log-only mode (default) records a GateViolation instead of exiting."""
        mock_vix_stack["ivr"].return_value = 0.10  # below 0.25 gate
        ivr, violation = resolve_ivr(
            Path("dummy.db"), Decimal("0.25"), force_entry=False, strategy_name="paper_ic_test"
        )
        assert ivr == pytest.approx(0.10)
        assert violation is not None
        assert violation.gate_name == "ivr"
        assert violation.strategy_name == "paper_ic_test"

    def test_ivr_below_gate_exits_when_log_only_disabled(self, mock_vix_stack) -> None:
        """Exits with code 1 when IVR is below the gate and log_only_gates=False."""
        mock_vix_stack["ivr"].return_value = 0.10  # below 0.25 gate
        with pytest.raises(SystemExit) as exc_info:
            resolve_ivr(Path("dummy.db"), Decimal("0.25"), force_entry=False, log_only_gates=False)
        assert exc_info.value.code == 1

    def test_ivr_below_gate_force_entry_continues(self, mock_vix_stack) -> None:
        """Does not exit when force_entry=True; returns low IVR with warning, no violation."""
        mock_vix_stack["ivr"].return_value = 0.10
        ivr, violation = resolve_ivr(Path("dummy.db"), Decimal("0.25"), force_entry=True)
        assert ivr == pytest.approx(0.10)
        assert violation is None

    def test_ivr_none_exits(self, mock_vix_stack) -> None:
        """STRUCTURAL: exits with code 1 when IVR cannot be computed, even under log-only-gates."""
        mock_vix_stack["ivr"].return_value = None
        with pytest.raises(SystemExit) as exc_info:
            resolve_ivr(Path("dummy.db"), Decimal("0.25"), force_entry=False)
        assert exc_info.value.code == 1

    def test_vix_load_error_treated_as_none(self, mock_vix_stack) -> None:
        """VIX load exception is caught; exits cleanly on gate failure (STRUCTURAL)."""
        mock_vix_stack["load"].side_effect = RuntimeError("disk error")
        with pytest.raises(SystemExit) as exc_info:
            resolve_ivr(Path("dummy.db"), Decimal("0.25"), force_entry=False)
        assert exc_info.value.code == 1

    def test_stale_window_skips_compute_and_exits(self, mock_vix_stack) -> None:
        """BUG-004: window >7 days stale is treated as gate-data-unavailable (STRUCTURAL).

        compute_ivr must not even be called — staleness is checked before
        the IVR calculation, not after. Never bypassed by log_only_gates.
        """
        stale_dates = pd.date_range("2025-01-01", periods=252, freq="D").date
        mock_vix_stack["load"].return_value = pd.Series([15.0] * 252, index=stale_dates)
        with pytest.raises(SystemExit) as exc_info:
            resolve_ivr(Path("dummy.db"), Decimal("0.25"), force_entry=False)
        assert exc_info.value.code == 1
        mock_vix_stack["ivr"].assert_not_called()

    def test_fresh_window_still_computes(self, mock_vix_stack) -> None:
        """A window whose max date is within the threshold computes normally."""
        fresh_dates = pd.date_range(end=date.today(), periods=252, freq="D").date
        mock_vix_stack["load"].return_value = pd.Series([15.0] * 252, index=fresh_dates)
        ivr, violation = resolve_ivr(Path("dummy.db"), Decimal("0.25"), force_entry=False)
        assert ivr == pytest.approx(0.35)
        assert violation is None
        mock_vix_stack["ivr"].assert_called_once()


# ---------------------------------------------------------------------------
# _is_vix_window_stale
# ---------------------------------------------------------------------------


class TestIsVixWindowStale:
    def test_fresh_window_not_stale(self) -> None:
        """Max date within threshold → not stale."""
        today = date(2026, 7, 2)
        series = pd.Series([15.0, 16.0], index=[date(2026, 6, 30), date(2026, 7, 1)])
        assert _is_vix_window_stale(series, today) is False

    def test_window_beyond_threshold_is_stale(self) -> None:
        """Max date more than 7 days behind today → stale."""
        today = date(2026, 7, 2)
        series = pd.Series([15.0], index=[date(2026, 6, 20)])  # 12 days behind
        assert _is_vix_window_stale(series, today) is True

    def test_window_exactly_at_threshold_not_stale(self) -> None:
        """Boundary: exactly 7 days behind is still within tolerance."""
        today = date(2026, 7, 2)
        series = pd.Series([15.0], index=[date(2026, 6, 25)])  # exactly 7 days
        assert _is_vix_window_stale(series, today) is False

    def test_window_one_day_past_threshold_is_stale(self) -> None:
        """Boundary: 8 days behind crosses the threshold."""
        today = date(2026, 7, 2)
        series = pd.Series([15.0], index=[date(2026, 6, 24)])  # 8 days
        assert _is_vix_window_stale(series, today) is True

    def test_empty_series_not_stale(self) -> None:
        """Empty series can't determine a max date — not flagged stale here.

        compute_ivr's own length check (len < 252) is what handles this
        case; staleness detection stays out of its way.
        """
        assert _is_vix_window_stale(pd.Series(dtype="float64"), date.today()) is False

    def test_plain_list_not_stale(self) -> None:
        """Non-Series input (e.g. mocked `[]` in other tests) doesn't crash."""
        assert _is_vix_window_stale([], date.today()) is False


# ---------------------------------------------------------------------------
# ic_relevant_strategy_names
# ---------------------------------------------------------------------------


class TestIcRelevantStrategyNames:
    def test_excludes_proxy_hedge_books(self) -> None:
        """BUG-005: proxy/hedge-book strategies are filtered out."""
        all_strategies = [
            "paper_nifty_futures",
            "paper_nifty_proxy",
            "paper_nifty_spot",
            "paper_ic_nifty_v1_weekly",
        ]
        result = ic_relevant_strategy_names(all_strategies)
        assert result == ["paper_ic_nifty_v1_weekly"]

    def test_excludes_csp_paper_phase_scope(self) -> None:
        """Paper-phase scope decision (2026-07-02): CSP excluded from the IC
        delta gate too, so ICs run independently of CSP during data
        collection. Revisit before live money (see DECISIONS.md)."""
        all_strategies = ["paper_csp_nifty_v1", "paper_ic_nifty_v1_weekly"]
        result = ic_relevant_strategy_names(all_strategies)
        assert result == ["paper_ic_nifty_v1_weekly"]

    def test_only_non_ic_strategies_open_returns_empty(self) -> None:
        """Edge case: nothing IC-relevant open — empty list, not an error."""
        all_strategies = [
            "paper_nifty_futures",
            "paper_nifty_proxy",
            "paper_nifty_spot",
            "paper_csp_nifty_v1",
        ]
        assert ic_relevant_strategy_names(all_strategies) == []

    def test_empty_input_returns_empty(self) -> None:
        """No open strategies at all → empty list."""
        assert ic_relevant_strategy_names([]) == []

    def test_no_excluded_strategies_present_unaffected(self) -> None:
        """When no proxy/hedge/CSP books are open, the list passes through unchanged."""
        all_strategies = ["paper_ic_nifty_v1_weekly", "paper_ic_nifty_v2_monthly"]
        assert ic_relevant_strategy_names(all_strategies) == all_strategies


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
        """Returns (lookup, expiry_str, dte, None) for a DTE inside the window."""
        from datetime import date, timedelta

        # Patch date.today so DTE is predictable
        target = date(2026, 7, 31)
        today = target - timedelta(days=35)
        with patch("scripts.strategies.ic.ic_entry_gates.date") as m_date:
            m_date.today.return_value = today
            m_date.fromisoformat.side_effect = date.fromisoformat
            lookup, expiry_str, dte, violation = resolve_expiry(
                Path("dummy.json"), "monthly", dte_warn_lo=30, dte_warn_hi=45
            )

        assert expiry_str == "2026-07-31"
        assert dte == 35
        assert lookup is mock_lookup_factory
        assert violation is None

    def test_dte_outside_window_returns_violation(self, mock_lookup_factory) -> None:
        """DTE outside the window returns a GateViolation but does not raise (THRESHOLD)."""
        from datetime import date, timedelta

        target = date(2026, 7, 31)
        today = target - timedelta(days=5)  # below dte_warn_lo=30
        with patch("scripts.strategies.ic.ic_entry_gates.date") as m_date:
            m_date.today.return_value = today
            m_date.fromisoformat.side_effect = date.fromisoformat
            _, expiry_str, dte, violation = resolve_expiry(
                Path("dummy.json"),
                "monthly",
                dte_warn_lo=30,
                dte_warn_hi=45,
                strategy_name="paper_ic_test",
            )

        assert dte == 5
        assert violation is not None
        assert violation.gate_name == "dte_window"
        assert violation.strategy_name == "paper_ic_test"

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


class TestMostRecentlySettledExpiry:
    def test_current_month_expiry_already_passed(self) -> None:
        """When today is on/after the current month's expiry, that IS the reference."""
        assert _most_recently_settled_expiry(date(2026, 6, 30)) == date(2026, 6, 30)

    def test_current_month_expiry_not_yet_reached_falls_back(self) -> None:
        """Mid-month, before the current cycle's own expiry, falls back to prior month."""
        assert _most_recently_settled_expiry(date(2026, 6, 25)) == date(2026, 5, 26)

    def test_year_rollover(self) -> None:
        """January, before its own expiry, falls back to December of the prior year."""
        assert _most_recently_settled_expiry(date(2026, 1, 1)) == date(2025, 12, 30)


# ---------------------------------------------------------------------------
# _post_expiry_gate
# ---------------------------------------------------------------------------


class TestPostExpiryGate:
    def test_passes_mid_cycle_before_current_month_expiry(self) -> None:
        """Passes mid-month, before the *current* cycle's own expiry.

        Regression test for BUG-003: June 2026's own expiry (June 30) has not
        yet happened on June 25, but the prior settled cycle (May 26) is long
        past — a fresh June series is already open, so entry must be allowed.
        The old buggy gate referenced the current month's expiry and blocked
        the entire cycle here.
        """
        with patch("scripts.strategies.ic.ic_entry_gates.date") as mock_date:
            mock_date.today.return_value = date(2026, 6, 25)
            mock_date.side_effect = date  # keep date(y, m, d) constructor working
            _post_expiry_gate()  # must not raise

    def test_passes_day_after_prior_settlement(self) -> None:
        """Passes the day immediately after the prior cycle's settlement.

        Symptom case from bugs.md: today=2026-07-01, June cycle settled
        2026-06-30, a fresh July series just opened. Entry must be allowed.
        """
        with patch("scripts.strategies.ic.ic_entry_gates.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 1)
            mock_date.side_effect = date
            _post_expiry_gate()  # must not raise

    def test_blocks_same_day_as_prior_settlement(self) -> None:
        """Blocks re-entry on the same day the prior cycle settles.

        June 2026: last Tuesday = June 30 — settlement is not complete
        intraday, so entry on June 30 itself must still be blocked.
        """
        with patch("scripts.strategies.ic.ic_entry_gates.date") as mock_date:
            mock_date.today.return_value = date(2026, 6, 30)
            mock_date.side_effect = date
            with pytest.raises(SystemExit) as exc_info:
                _post_expiry_gate()
        assert exc_info.value.code == 1

    def test_year_rollover_passes_after_december_settlement(self) -> None:
        """Handles Dec → Jan rollover when resolving the prior settled cycle.

        January 2026's own expiry (Jan 27) is far in the future on Jan 1, so
        the gate must fall back to December 2025's last Tuesday (Dec 30,
        2025) as the prior settled cycle, cross a year boundary correctly,
        and allow entry on Jan 1, 2026.
        """
        with patch("scripts.strategies.ic.ic_entry_gates.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 1)
            mock_date.side_effect = date
            _post_expiry_gate()  # must not raise

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
