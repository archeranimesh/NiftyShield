# tests/unit/strategies/ic/test_paper_ic_monthly_comparison.py
import argparse
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import structlog.testing

from scripts.strategies.ic.paper_ic_monthly_comparison import (
    ICMonthlyStats,
    _get_cycle_start_date,
    build_comparison_report,
    build_stats,
)
from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade
from src.paper.store import PaperStore
from src.strategy.ic_expiry_config import CONFIGS as V1_CONFIGS
from src.strategy.ic_nifty_v1 import IronCondorV1

V1_CONFIG = V1_CONFIGS["monthly"]


@pytest.fixture
def store(tmp_path) -> PaperStore:
    db_path = tmp_path / "test.sqlite"
    return PaperStore(db_path)


def test_build_stats_no_open_position(store):
    # This is a unit test of the functions and structure
    # _get_cycle_start_date on empty returns None
    assert _get_cycle_start_date(store, "paper_ic_nifty_v1_monthly") is None


def test_captured_fraction_formula():
    # If entry=200, mark=50 -> captured=(200-50)/200 = 0.75
    entry = Decimal("200")
    mark = Decimal("50")
    captured = (entry - mark) / entry
    assert captured == Decimal("0.75")


def test_comparison_report_format():
    v1 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v1_monthly",
        entry_credit_pts=Decimal("200"),
        current_mark_pts=Decimal("50"),
        captured_fraction=Decimal("0.75"),
        dte=15,
        short_put_delta=Decimal("0.18"),
        short_call_delta=Decimal("0.12"),
        profit_lock_zone=0,
        realized_pnl_month=Decimal("1500"),
        unrealized_pnl=Decimal("7500"),
        signals_fired_today=["DELTA_WARN"],
        roll_count=1,
        lock_count=0,
        has_open_position=True,
        open_leg_count=4,
        inception_realized_pnl=Decimal("15000"),
        unrealized_pnl_month_change=Decimal("500"),
    )
    v2 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v2_monthly",
        entry_credit_pts=Decimal("200"),
        current_mark_pts=Decimal("40"),
        captured_fraction=Decimal("0.80"),
        dte=15,
        short_put_delta=Decimal("0.27"),
        short_call_delta=Decimal("0.24"),
        profit_lock_zone=2,
        realized_pnl_month=Decimal("2500"),
        unrealized_pnl=Decimal("8000"),
        signals_fired_today=[],
        roll_count=1,
        lock_count=1,
        has_open_position=True,
        open_leg_count=4,
        inception_realized_pnl=Decimal("16000"),
        unrealized_pnl_month_change=Decimal("600"),
    )

    report = build_comparison_report(v1, v2, date(2026, 6, 27))
    assert "paper_ic_nifty_v1_monthly" not in report  # It uses "V1 Monthly" and "V2 Monthly"
    assert "V1 Monthly" in report
    assert "V2 Monthly" in report
    assert "```" in report  # MarkdownV2 fence
    assert "Zone 2 ✓" in report
    assert "1 rolls + 1 locks" in report  # No backslash escape inside fence
    assert "Legs" in report
    assert "Flt P&L (M)" in report
    assert "Bkd P&L (M)" in report
    assert "Flt P&L (I)" in report
    assert "Bkd P&L (I)" in report
    assert "Edge so far:  V2 \\+₹1,500 vs V1" in report  # Escaped outside fence


def test_comparison_report_one_missing():
    v1 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v1_monthly",
        entry_credit_pts=Decimal("200"),
        current_mark_pts=Decimal("50"),
        captured_fraction=Decimal("0.75"),
        dte=15,
        short_put_delta=Decimal("0.18"),
        short_call_delta=Decimal("0.12"),
        profit_lock_zone=0,
        realized_pnl_month=Decimal("1500"),
        unrealized_pnl=Decimal("7500"),
        signals_fired_today=["DELTA_WARN"],
        roll_count=1,
        lock_count=0,
        has_open_position=True,
        open_leg_count=4,
        inception_realized_pnl=Decimal("15000"),
        unrealized_pnl_month_change=Decimal("500"),
    )
    v2 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v2_monthly",
        entry_credit_pts=None,
        current_mark_pts=None,
        captured_fraction=None,
        dte=None,
        short_put_delta=None,
        short_call_delta=None,
        profit_lock_zone=0,
        realized_pnl_month=Decimal("2500"),
        unrealized_pnl=Decimal("0"),
        signals_fired_today=[],
        roll_count=0,
        lock_count=0,
        has_open_position=False,
        open_leg_count=0,
        inception_realized_pnl=Decimal("16000"),
        unrealized_pnl_month_change=Decimal("0"),
    )

    report = build_comparison_report(v1, v2, date(2026, 6, 27))
    assert "No open position" in report
    # V1 total: 1500 + 7500 = 9000
    # V2 total: 2500 + 0 = 2500
    # V2 - V1 = -6500
    assert "Edge so far:  V1 \\+₹6,500 vs V2" in report


def test_edge_calculation():
    v1 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v1_monthly",
        entry_credit_pts=None,
        current_mark_pts=None,
        captured_fraction=None,
        dte=None,
        short_put_delta=None,
        short_call_delta=None,
        profit_lock_zone=0,
        realized_pnl_month=Decimal("100"),
        unrealized_pnl=Decimal("100"),
        signals_fired_today=[],
        roll_count=0,
        lock_count=0,
    )
    v2 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v2_monthly",
        entry_credit_pts=None,
        current_mark_pts=None,
        captured_fraction=None,
        dte=None,
        short_put_delta=None,
        short_call_delta=None,
        profit_lock_zone=0,
        realized_pnl_month=Decimal("150"),
        unrealized_pnl=Decimal("100"),
        signals_fired_today=[],
        roll_count=0,
        lock_count=0,
    )

    report = build_comparison_report(v1, v2, date(2026, 6, 27))
    assert "Edge so far:  V2 \\+₹50 vs V1" in report


@pytest.mark.asyncio
async def test_build_stats_happy_path(store):
    from scripts.strategies.ic.paper_ic_monthly_comparison import build_stats

    # We will just insert some positions and check if build_stats handles them.
    # We can mock the broker and chain logic.
    class _MockBroker:
        pass

    from datetime import date

    from src.models.portfolio import TradeAction
    from src.paper.models import PaperTrade

    store.record_trades(
        [
            PaperTrade(
                strategy_name="paper_ic_nifty_v1_monthly",
                leg_role="short_put",
                instrument_key="NSE_FO|NIFTY31JUL202624000PE",
                trade_date=date(2026, 6, 25),
                action=TradeAction.SELL,
                quantity=25,
                price=Decimal("100"),
            ),
            PaperTrade(
                strategy_name="paper_ic_nifty_v1_monthly",
                leg_role="short_call",
                instrument_key="NSE_FO|NIFTY31JUL202625000CE",
                trade_date=date(2026, 6, 25),
                action=TradeAction.SELL,
                quantity=25,
                price=Decimal("100"),
            ),
        ]
    )

    stats = await build_stats(
        strategy_name="paper_ic_nifty_v1_monthly",
        strategy_cls=IronCondorV1,
        config=V1_CONFIG,
        store=store,
        broker=_MockBroker(),
        today=date(2026, 6, 27),
    )
    assert stats.dte is not None
    assert stats.dte > 0
    assert stats.has_open_position is True


# ── BUG-012 follow-up: numeric-key expiry resolution + open/no-open distinction ──


@pytest.mark.asyncio
async def test_build_stats_no_open_position_has_open_position_false(store):
    """No positions at all -> has_open_position False (the one correct case)."""
    from scripts.strategies.ic.paper_ic_monthly_comparison import build_stats

    class _MockBroker:
        pass

    stats = await build_stats(
        strategy_name="paper_ic_nifty_v1_monthly",
        strategy_cls=IronCondorV1,
        config=V1_CONFIG,
        store=store,
        broker=_MockBroker(),
        today=date(2026, 6, 27),
    )
    assert stats.has_open_position is False
    assert stats.dte is None


@pytest.mark.asyncio
async def test_build_stats_resolves_expiry_via_bod_for_numeric_key(store):
    """Numeric instrument_key (no embedded date) still resolves DTE via BOD lookup.

    Regression for the bug where a real, open position with a numeric key
    (e.g. NSE_FO|63896) left dte=None because the regex-only expiry parse
    never matches — which then falsely printed "No open position" for a
    position that was genuinely open (has_open_position now decouples this).
    """
    from scripts.strategies.ic.paper_ic_monthly_comparison import build_stats
    from src.models.portfolio import TradeAction
    from src.paper.models import PaperTrade

    store.record_trades(
        [
            PaperTrade(
                strategy_name="paper_ic_nifty_v1_monthly",
                leg_role="short_put",
                instrument_key="NSE_FO|63896",
                trade_date=date(2026, 6, 25),
                action=TradeAction.SELL,
                quantity=25,
                price=Decimal("100"),
            ),
        ]
    )

    class _MockBroker:
        async def get_option_chain(self, underlying, expiry):
            return []

    lookup = MagicMock()
    lookup.get_by_key.return_value = {"expiry": "2026-07-31"}

    stats = await build_stats(
        strategy_name="paper_ic_nifty_v1_monthly",
        strategy_cls=IronCondorV1,
        config=V1_CONFIG,
        store=store,
        broker=_MockBroker(),
        today=date(2026, 6, 27),
        lookup=lookup,
    )

    assert stats.has_open_position is True
    assert stats.dte is not None
    assert stats.dte == (date(2026, 7, 31) - date(2026, 6, 27)).days


def test_report_distinguishes_open_position_unresolvable_dte_from_no_position():
    """A genuinely open position with unresolvable DTE shows N/A, not 'No open position'."""
    v1 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v1_monthly",
        entry_credit_pts=None,
        current_mark_pts=None,
        captured_fraction=None,
        dte=None,
        short_put_delta=None,
        short_call_delta=None,
        profit_lock_zone=0,
        realized_pnl_month=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        signals_fired_today=[],
        roll_count=0,
        lock_count=0,
        has_open_position=True,
    )
    v2 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v2_monthly",
        entry_credit_pts=None,
        current_mark_pts=None,
        captured_fraction=None,
        dte=None,
        short_put_delta=None,
        short_call_delta=None,
        profit_lock_zone=0,
        realized_pnl_month=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        signals_fired_today=[],
        roll_count=0,
        lock_count=0,
        has_open_position=False,
    )

    report = build_comparison_report(v1, v2, date(2026, 6, 27))

    v1_line = next(line for line in report.splitlines() if line.startswith("DTE"))
    assert "N/A" in v1_line
    assert "No open position" in v1_line  # V2 column, correctly blank
    # V1's own column must not say "No open position" — it has a real position,
    # DTE just couldn't be computed.
    v1_column = v1_line.split("N/A")[0]
    assert "No open position" not in v1_column


# ---------------------------------------------------------------------------
# TGFMT-1 — dynamic-width alignment (regression for hand-counted-width bug)
# ---------------------------------------------------------------------------


def test_comparison_report_long_label_no_collision():
    """A row label long enough to blow past the old hand-counted 20-char budget
    must not collide with the value column — direct regression for the bug that
    triggered TGFMT-1 (reproduced live with "Realized (inception)" /
    "Unrealized(inception)" colliding into the value column)."""
    v1 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v1_monthly",
        entry_credit_pts=Decimal("200"),
        current_mark_pts=Decimal("50"),
        captured_fraction=Decimal("0.75"),
        dte=15,
        short_put_delta=Decimal("0.18"),
        short_call_delta=Decimal("0.12"),
        profit_lock_zone=0,
        realized_pnl_month=Decimal("1500"),
        unrealized_pnl=Decimal("7500"),
        signals_fired_today=["DELTA_WARN"],
        roll_count=1,
        lock_count=0,
        has_open_position=True,
    )
    v2 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v2_monthly",
        entry_credit_pts=Decimal("200"),
        current_mark_pts=Decimal("40"),
        captured_fraction=Decimal("0.80"),
        dte=15,
        short_put_delta=Decimal("0.27"),
        short_call_delta=Decimal("0.24"),
        profit_lock_zone=2,
        realized_pnl_month=Decimal("2500"),
        unrealized_pnl=Decimal("8000"),
        signals_fired_today=[],
        roll_count=1,
        lock_count=1,
        has_open_position=True,
    )

    report = build_comparison_report(v1, v2, date(2026, 6, 27))
    lines = report.splitlines()

    # All data rows (skip title, blank, header, rule) must be exactly as wide
    # as the header row — that's the correctness invariant dynamic widths
    # guarantee: no row's value column can drift out of alignment regardless
    # of label length.
    from src.notifications.formatting import _display_width

    header_line = next(line for line in lines if "V1 Monthly" in line)
    row_labels = [
        "Entry credit",
        "Captured",
        "Short put Δ",
        "Short call Δ",
        "DTE",
        "Legs",
        "Flt P&L (M)",
        "Bkd P&L (M)",
        "Flt P&L (I)",
        "Bkd P&L (I)",
        "Lock Zone",
        "Adjustments",
        "Signals",
    ]
    data_lines = [line for line in lines if any(line.startswith(label) for label in row_labels)]
    for line in data_lines:
        assert _display_width(line.replace("\\", "")) == _display_width(
            header_line.replace("\\", "")
        ), f"misaligned row: {line!r}"

    # Values must be right-aligned under their header, not glued to the label.
    # We must measure display width to find the column start
    header_clean = header_line.replace("\\", "")
    v1_col_start_idx = header_clean.index("V1 Monthly")
    v1_col_start = _display_width(header_clean[:v1_col_start_idx])

    def char_at_visual_col(s: str, col: int) -> str:
        current_col = 0
        for char in s:
            width = _display_width(char)
            if current_col <= col < current_col + width:
                return char
            current_col += width
        return ""

    for line in data_lines:
        clean_line = line.replace("\\", "")
        # The visual column right before the V1 header's start must be part of the label's
        # trailing padding (space) or the value's leading padding, ensuring no collision.
        assert char_at_visual_col(clean_line, v1_col_start - 1) == " " or v1_col_start == 0, (
            f"possible collision in {clean_line!r}"
        )


def test_column_width_derived_not_hand_counted():
    """An artificially long label (25+ chars) still aligns correctly — this is
    what breaks under a fixed-width hand-count and is the regression this
    story exists to prevent."""
    v1 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v1_monthly",
        entry_credit_pts=None,
        current_mark_pts=None,
        captured_fraction=None,
        dte=None,
        short_put_delta=None,
        short_call_delta=None,
        profit_lock_zone=0,
        realized_pnl_month=Decimal("123456"),
        unrealized_pnl=Decimal("7500"),
        signals_fired_today=[],
        roll_count=0,
        lock_count=0,
        has_open_position=True,
    )
    v2 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v2_monthly",
        entry_credit_pts=None,
        current_mark_pts=None,
        captured_fraction=None,
        dte=None,
        short_put_delta=None,
        short_call_delta=None,
        profit_lock_zone=0,
        realized_pnl_month=Decimal("2500"),
        unrealized_pnl=Decimal("8000"),
        signals_fired_today=[],
        roll_count=0,
        lock_count=0,
        has_open_position=True,
    )

    report = build_comparison_report(v1, v2, date(2026, 6, 27))
    # A large realized-month value (₹123,456) must not push the "Bkd P&L
    # (M)" row's value column out of sync with the header/rule width.
    from src.notifications.formatting import _display_width

    lines = report.splitlines()
    header_line = next(line for line in lines if "V1 Monthly" in line)
    realized_line = next(line for line in lines if line.startswith("Bkd P&L (M)"))
    assert _display_width(realized_line.replace("\\", "")) == _display_width(
        header_line.replace("\\", "")
    )
    assert "₹123,456" in realized_line


# ---------------------------------------------------------------------------
# B010.3 — structlog migration (setup_logging() entrypoint + report_sent event)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_run_deps():
    """Mock all _run() collaborators so it can execute end-to-end offline."""
    with (
        patch("scripts.strategies.ic.paper_ic_monthly_comparison.PaperStore") as m_store_cls,
        patch("scripts.strategies.ic.paper_ic_monthly_comparison.create_client") as m_create,
        patch("scripts.strategies.ic.paper_ic_monthly_comparison.build_stats") as m_build_stats,
        patch("scripts.strategies.ic.paper_ic_monthly_comparison.TelegramGateway") as m_tg_cls,
    ):
        store_inst = MagicMock()
        m_store_cls.return_value = store_inst
        m_create.side_effect = ValueError("no live client in tests")

        async def _fake_build_stats(**kwargs):
            return ICMonthlyStats(
                strategy_name=kwargs["strategy_name"],
                entry_credit_pts=None,
                current_mark_pts=None,
                captured_fraction=None,
                dte=None,
                short_put_delta=None,
                short_call_delta=None,
                profit_lock_zone=0,
                realized_pnl_month=Decimal("0"),
                unrealized_pnl=Decimal("0"),
                signals_fired_today=[],
                roll_count=0,
                lock_count=0,
            )

        m_build_stats.side_effect = _fake_build_stats

        tg_inst = MagicMock()
        tg_inst.send_notification = AsyncMock()
        m_tg_cls.return_value = tg_inst

        yield {"store": store_inst, "telegram": tg_inst, "create_client": m_create}


@pytest.mark.asyncio
async def test_run_calls_setup_logging_first(mock_run_deps) -> None:
    """_run() must call setup_logging() as its first action (LOGGING.md standard)."""
    from scripts.strategies.ic.paper_ic_monthly_comparison import _run

    args = argparse.Namespace(
        date=date(2026, 6, 27), dry_run=True, db_path="dummy.sqlite", bod_path="dummy.json"
    )

    with patch("scripts.strategies.ic.paper_ic_monthly_comparison.setup_logging") as mock_setup:
        await _run(args)

    mock_setup.assert_called_once()


@pytest.mark.asyncio
async def test_run_dry_run_does_not_send_or_log_report(mock_run_deps) -> None:
    """--dry-run (default save=False) must not log report_sent or call Telegram."""
    from scripts.strategies.ic.paper_ic_monthly_comparison import _run

    args = argparse.Namespace(
        date=date(2026, 6, 27), dry_run=True, db_path="dummy.sqlite", bod_path="dummy.json"
    )

    with structlog.testing.capture_logs() as logs:
        await _run(args)

    events = [entry["event"] for entry in logs]
    assert "ic_monthly_comparison.report_sent" not in events
    mock_run_deps["telegram"].send_notification.assert_not_called()


@pytest.mark.asyncio
async def test_run_no_dry_run_logs_report_sent(mock_run_deps, monkeypatch) -> None:
    """--no-dry-run (save=True) with telegram creds present logs report_sent."""
    from scripts.strategies.ic.paper_ic_monthly_comparison import _run

    monkeypatch.setattr(
        "scripts.strategies.ic.paper_ic_monthly_comparison.settings.telegram_bot_token",
        "dummy-token",
    )
    monkeypatch.setattr(
        "scripts.strategies.ic.paper_ic_monthly_comparison.settings.telegram_chat_id",
        "dummy-chat",
    )
    # Under --no-dry-run, a broker init failure is fatal (sys.exit(1)) rather
    # than falling back to the mock broker — so give create_client a real
    # (mocked) success path instead of the ValueError used by other tests.
    mock_run_deps["create_client"].side_effect = None
    mock_run_deps["create_client"].return_value = MagicMock()

    args = argparse.Namespace(
        date=date(2026, 6, 27), dry_run=False, db_path="dummy.sqlite", bod_path="dummy.json"
    )

    with (
        patch("scripts.strategies.ic.paper_ic_monthly_comparison.setup_logging"),
        structlog.testing.capture_logs() as logs,
    ):
        await _run(args)

    events = [entry["event"] for entry in logs]
    assert "ic_monthly_comparison.report_sent" in events
    mock_run_deps["telegram"].send_notification.assert_called_once()


# ---------------------------------------------------------------------------
# ROLL-2b-ii — build_stats() consumes build_pnl_report() (Legs row / Bkd (I) /
# Flt (M) plumbing). See strategy-rollout/tasks.md ROLL-2b's three decisions:
# (1) consume PnLReport, don't duplicate; (2) uniform as-of row selection;
# (3) Bkd (M) cycle-reset gap knowingly left as-is.
# ---------------------------------------------------------------------------


class _NoOpBroker:
    """No option-chain calls expected in these tests (no open legs, or the
    chain fetch is irrelevant to the P&L-sourcing assertions)."""

    async def get_option_chain(self, underlying, expiry):
        return []


@pytest.mark.asyncio
async def test_legs_row_shows_open_count(store):
    """4 legs open (a full IC) -> open_leg_count == 4."""
    store.record_trades(
        [
            PaperTrade(
                strategy_name="paper_ic_nifty_v1_monthly",
                leg_role=role,
                instrument_key=key,
                trade_date=date(2026, 6, 25),
                action=TradeAction.SELL,
                quantity=25,
                price=Decimal("100"),
            )
            for role, key in [
                ("short_put", "NSE_FO|63001"),
                ("long_put", "NSE_FO|63002"),
                ("short_call", "NSE_FO|63003"),
                ("long_call", "NSE_FO|63004"),
            ]
        ]
    )

    stats = await build_stats(
        strategy_name="paper_ic_nifty_v1_monthly",
        strategy_cls=IronCondorV1,
        config=V1_CONFIG,
        store=store,
        broker=_NoOpBroker(),
        today=date(2026, 6, 27),
    )

    assert stats.open_leg_count == 4


@pytest.mark.asyncio
async def test_legs_row_shows_warning_when_incomplete(store):
    """Fewer than 4 legs open -> open_leg_count reflects the real (partial) count.

    The 🔴 suffix itself is a ROLL-2c rendering concern (build_comparison_report);
    this test only pins the count build_stats() threads through, per ROLL-2b-ii's
    scope (rendering is out of scope here).
    """
    store.record_trades(
        [
            PaperTrade(
                strategy_name="paper_ic_nifty_v1_monthly",
                leg_role="short_put",
                instrument_key="NSE_FO|63001",
                trade_date=date(2026, 6, 25),
                action=TradeAction.SELL,
                quantity=25,
                price=Decimal("100"),
            ),
        ]
    )

    stats = await build_stats(
        strategy_name="paper_ic_nifty_v1_monthly",
        strategy_cls=IronCondorV1,
        config=V1_CONFIG,
        store=store,
        broker=_NoOpBroker(),
        today=date(2026, 6, 27),
    )

    assert stats.open_leg_count == 1
    assert stats.open_leg_count < 4


@pytest.mark.asyncio
async def test_bkd_inception_uses_get_strategy_realized_pnl(store):
    """`inception_realized_pnl` must come from build_pnl_report()'s
    realized_since_inception (i.e. get_strategy_realized_pnl(), summed from
    paper_trades), never paper_nav_snapshots.realized_pnl's raw latest row --
    regression for the corrected sourcing in ROLL-2b's spec (that column
    resets on a full open->close->reopen cycle, per CONTEXT.md's SNAP-1).
    """
    # A closed round-trip so get_strategy_realized_pnl has something to sum,
    # while a stale/wrong paper_nav_snapshots.realized_pnl row is what the
    # old (incorrect) sourcing would have read instead.
    store.record_trades(
        [
            PaperTrade(
                strategy_name="paper_ic_nifty_v1_monthly",
                leg_role="short_put",
                instrument_key="NSE_FO|63001",
                trade_date=date(2026, 6, 20),
                action=TradeAction.SELL,
                quantity=25,
                price=Decimal("100.00"),
            ),
            PaperTrade(
                strategy_name="paper_ic_nifty_v1_monthly",
                leg_role="short_put",
                instrument_key="NSE_FO|63001",
                trade_date=date(2026, 6, 22),
                action=TradeAction.BUY,
                quantity=25,
                price=Decimal("60.00"),
            ),
        ]
    )

    with patch(
        "scripts.strategies.ic.paper_ic_monthly_comparison.build_pnl_report"
    ) as m_build_pnl_report:
        from scripts.reporting.paper_pnl_report import PnLReport

        m_build_pnl_report.return_value = PnLReport(
            strategy_name="paper_ic_nifty_v1_monthly",
            has_data=True,
            daily_series=[],
            realized_since_inception=Decimal("999999"),
            realized_this_month=Decimal("0"),
            unrealized_since_inception=Decimal("0"),
            unrealized_this_month=Decimal("0"),
        )

        stats = await build_stats(
            strategy_name="paper_ic_nifty_v1_monthly",
            strategy_cls=IronCondorV1,
            config=V1_CONFIG,
            store=store,
            broker=_NoOpBroker(),
            today=date(2026, 6, 27),
        )

    # build_stats must surface exactly what build_pnl_report() returned for
    # realized_since_inception -- a test that only checked "some number
    # appears" would pass even if a future edit silently reverted to reading
    # paper_nav_snapshots.realized_pnl directly.
    m_build_pnl_report.assert_called_once_with(
        store, "paper_ic_nifty_v1_monthly", as_of=date(2026, 6, 27)
    )
    assert stats.inception_realized_pnl == Decimal("999999")


@pytest.mark.asyncio
async def test_flt_month_differs_from_flt_inception(store):
    """A mid-month entry makes `Flt (M)` != `Flt (I)` -- the mandatory
    regression from the ROLL-2 spec. Implementing `Flt (M)` as a copy of
    `Flt (I)` looks correct whenever a position was open the whole month and
    only silently breaks on a mid-month entry, so this test constructs
    exactly that case via build_pnl_report()'s real snapshot-baseline logic
    rather than a mocked return value.
    """
    import sqlite3

    db_path = store.db_path
    conn = sqlite3.connect(db_path)
    try:
        for snap_date, unrealized, realized in [
            (date(2026, 5, 20), "2000.00", "0"),  # baseline, before month start
            (date(2026, 6, 5), "2600.00", "0"),  # mid-month mark
        ]:
            conn.execute(
                """INSERT INTO paper_nav_snapshots
                   (strategy_name, snapshot_date, unrealized_pnl, realized_pnl,
                    total_pnl, underlying_price)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    "paper_ic_nifty_v1_monthly",
                    snap_date.isoformat(),
                    unrealized,
                    realized,
                    str(Decimal(unrealized) + Decimal(realized)),
                    None,
                ),
            )
        conn.commit()
    finally:
        conn.close()

    stats = await build_stats(
        strategy_name="paper_ic_nifty_v1_monthly",
        strategy_cls=IronCondorV1,
        config=V1_CONFIG,
        store=store,
        broker=_NoOpBroker(),
        today=date(2026, 6, 27),
    )

    # Flt (I) = latest snapshot's unrealized_pnl = 2600.
    assert stats.unrealized_pnl == Decimal("2600.00")
    # Flt (M) = 2600 (latest) - 2000 (last row before month start) = 600.
    assert stats.unrealized_pnl_month_change == Decimal("600.00")
    assert stats.unrealized_pnl_month_change != stats.unrealized_pnl


@pytest.mark.asyncio
async def test_flt_month_change_uses_correct_snapshot_rows(store):
    """Mirrors `_get_monthly_realized_pnl`'s (pre-ROLL-2b-ii) curr/prev
    boundary convention -- decision (2) in ROLL-2b: both Bkd (M) and Flt (M)
    must read the latest row at-or-before `as_of` / strictly-before month
    start, never exact-equality-on-today, so a snapshot gap (holiday, or a
    run before the daily cron) doesn't make Flt (I)/Flt (M) diverge for a
    reason unrelated to the mid-month-entry case above.
    """
    import sqlite3

    db_path = store.db_path
    conn = sqlite3.connect(db_path)
    try:
        for snap_date, unrealized in [
            (date(2026, 5, 31), "1000.00"),  # last row before month start
            (date(2026, 6, 20), "1500.00"),  # last row at-or-before as_of (no row *on* as_of)
        ]:
            conn.execute(
                """INSERT INTO paper_nav_snapshots
                   (strategy_name, snapshot_date, unrealized_pnl, realized_pnl,
                    total_pnl, underlying_price)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    "paper_ic_nifty_v1_monthly",
                    snap_date.isoformat(),
                    unrealized,
                    "0",
                    unrealized,
                    None,
                ),
            )
        conn.commit()
    finally:
        conn.close()

    # as_of (today) is 2026-06-27, a date with no snapshot row of its own --
    # must still resolve off the last available row (06-20), not read as zero.
    stats = await build_stats(
        strategy_name="paper_ic_nifty_v1_monthly",
        strategy_cls=IronCondorV1,
        config=V1_CONFIG,
        store=store,
        broker=_NoOpBroker(),
        today=date(2026, 6, 27),
    )

    assert stats.unrealized_pnl == Decimal("1500.00")
    assert stats.unrealized_pnl_month_change == Decimal("500.00")


# ---------------------------------------------------------------------------
# ROLL-2c — rendering assertions for build_comparison_report
# ---------------------------------------------------------------------------


def test_render_legs_row_shows_open_count():
    """4/4, no 🔴 suffix when open_leg_count == 4."""
    v1 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v1_monthly",
        entry_credit_pts=Decimal("200"),
        current_mark_pts=Decimal("50"),
        captured_fraction=Decimal("0.75"),
        dte=15,
        short_put_delta=Decimal("0.18"),
        short_call_delta=Decimal("0.12"),
        profit_lock_zone=0,
        realized_pnl_month=Decimal("1500"),
        unrealized_pnl=Decimal("7500"),
        signals_fired_today=["DELTA_WARN"],
        roll_count=1,
        lock_count=0,
        has_open_position=True,
        open_leg_count=4,
        inception_realized_pnl=Decimal("15000"),
        unrealized_pnl_month_change=Decimal("500"),
    )
    v2 = v1
    report = build_comparison_report(v1, v2, date(2026, 6, 27))
    assert "4/4" in report
    assert "🔴" not in report


def test_render_legs_row_shows_warning_when_incomplete():
    """<4 legs gets a 🔴 suffix."""
    v1 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v1_monthly",
        entry_credit_pts=Decimal("200"),
        current_mark_pts=Decimal("50"),
        captured_fraction=Decimal("0.75"),
        dte=15,
        short_put_delta=Decimal("0.18"),
        short_call_delta=Decimal("0.12"),
        profit_lock_zone=0,
        realized_pnl_month=Decimal("1500"),
        unrealized_pnl=Decimal("7500"),
        signals_fired_today=["DELTA_WARN"],
        roll_count=1,
        lock_count=0,
        has_open_position=True,
        open_leg_count=3,
        inception_realized_pnl=Decimal("15000"),
        unrealized_pnl_month_change=Decimal("500"),
    )
    v2 = v1
    report = build_comparison_report(v1, v2, date(2026, 6, 27))
    assert "3/4🔴" in report


def test_bkd_inception_renders_from_stats_field():
    """Asserts inception_realized_pnl value appears, not a re-derived/raw snapshot value."""
    v1 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v1_monthly",
        entry_credit_pts=Decimal("200"),
        current_mark_pts=Decimal("50"),
        captured_fraction=Decimal("0.75"),
        dte=15,
        short_put_delta=Decimal("0.18"),
        short_call_delta=Decimal("0.12"),
        profit_lock_zone=0,
        realized_pnl_month=Decimal("1500"),
        unrealized_pnl=Decimal("7500"),
        signals_fired_today=["DELTA_WARN"],
        roll_count=1,
        lock_count=0,
        has_open_position=True,
        open_leg_count=4,
        inception_realized_pnl=Decimal("99999"),
        unrealized_pnl_month_change=Decimal("500"),
    )
    v2 = v1
    report = build_comparison_report(v1, v2, date(2026, 6, 27))
    assert "Bkd P&L (I)" in report
    assert "99,999" in report


def test_flt_month_renders_from_stats_field():
    """Asserts unrealized_pnl_month_change value appears and differs from unrealized_pnl."""
    v1 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v1_monthly",
        entry_credit_pts=Decimal("200"),
        current_mark_pts=Decimal("50"),
        captured_fraction=Decimal("0.75"),
        dte=15,
        short_put_delta=Decimal("0.18"),
        short_call_delta=Decimal("0.12"),
        profit_lock_zone=0,
        realized_pnl_month=Decimal("1500"),
        unrealized_pnl=Decimal("7500"),
        signals_fired_today=["DELTA_WARN"],
        roll_count=1,
        lock_count=0,
        has_open_position=True,
        open_leg_count=4,
        inception_realized_pnl=Decimal("15000"),
        unrealized_pnl_month_change=Decimal("1234"),
    )
    v2 = v1
    report = build_comparison_report(v1, v2, date(2026, 6, 27))
    assert "Flt P&L (M)" in report
    assert "1,234" in report
    # Make sure it differs from the Flt (I) value
    assert "7,500" in report
