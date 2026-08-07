# tests/unit/paper/test_formatting.py
from decimal import Decimal

from src.paper.formatting import fmt_inr, format_pnl_table, format_track_summary


def test_fmt_inr():
    # Basic cases
    assert fmt_inr(Decimal("1234.56")) == "₹1,235"
    assert fmt_inr(Decimal("-1234.56")) == "₹-1,235"
    assert fmt_inr(Decimal("0")) == "₹0"

    # sign_always=True
    assert fmt_inr(Decimal("1234.56"), sign_always=True) == "₹+1,235"
    assert fmt_inr(Decimal("-1234.56"), sign_always=True) == "₹-1,235"
    assert fmt_inr(Decimal("0"), sign_always=True) == "₹+0"

    # None case
    assert fmt_inr(None) == "₹-"


def test_format_pnl_table():
    rows = [
        {
            "strategy": "paper_csp_nifty_v1",
            "unrealized": Decimal("5000"),
            "realized": Decimal("2000"),
            "total": Decimal("7000"),
        },
        {
            "strategy": "paper_ic_nifty_v1",
            "unrealized": Decimal("-1000"),
            "realized": Decimal("3000"),
            "total": Decimal("2000"),
        },
    ]

    # Dry run
    output = format_pnl_table(rows, title="My Snapshot", is_dry_run=True)
    assert "[DRY RUN] My Snapshot" in output
    assert "Strategy" in output
    assert "paper_csp_nifty_v1" in output
    assert "₹+5,000" in output
    assert "₹-1,000" in output

    # No dry run
    output = format_pnl_table(rows, title="Live Snapshot", is_dry_run=False)
    assert "Live Snapshot" in output
    assert "[DRY RUN]" not in output


def test_format_pnl_table_empty():
    output = format_pnl_table([], title="Empty Table")
    assert "Empty Table" in output
    assert "No active strategies found." in output


def test_format_track_summary():
    rows = [
        {
            "track": "NiftyBees (Spot)",
            "base_pnl": Decimal("10000"),
            "overlay_pnl": Decimal("-2000"),
            "net_pnl": Decimal("8000"),
            "return_on_nee": 1.23,
        },
        {
            "track": "Nifty Futures",
            "base_pnl": Decimal("15000"),
            "overlay_pnl": Decimal("-3000"),
            "net_pnl": Decimal("12000"),
            "return_on_nee": 1.85,
        },
    ]
    output = format_track_summary(rows, title="Summary — 2026-05-11")

    assert "Summary — 2026-05-11" in output
    assert "Track" in output
    assert "Base P&L" in output
    assert "NiftyBees (Spot)" in output
    assert "₹10,000" in output
    assert "₹-2,000" in output
    assert "1.23%" in output
    assert "1.85%" in output
    assert "═" * 88 in output


def test_format_track_summary_dry_run_prefix():
    rows = [
        {
            "track": "Spot",
            "base_pnl": Decimal("0"),
            "overlay_pnl": Decimal("0"),
            "net_pnl": Decimal("0"),
            "return_on_nee": 0.0,
        }
    ]
    output = format_track_summary(rows, title="Test", is_dry_run=True)
    assert "[DRY RUN] Test" in output


def test_format_track_summary_empty():
    output = format_track_summary([], title="No data")
    assert "No data" in output
    assert "═" * 88 in output


def test_format_track_summary_inception_headers():
    """Default period='inception' uses cumulative P&L column headers."""
    rows = [
        {
            "track": "Spot",
            "base_pnl": Decimal("1000"),
            "overlay_pnl": Decimal("0"),
            "net_pnl": Decimal("1000"),
            "return_on_nee": 0.5,
        }
    ]
    output = format_track_summary(rows, period="inception")
    assert "Base P&L" in output
    assert "Overlay" in output
    assert "Net P&L" in output
    assert "Day Base" not in output


def test_format_track_summary_daily_headers():
    """period='daily' uses plain 1-day delta column headers (no 'Day' prefix —
    the period is already implied by the daily table itself)."""
    rows = [
        {
            "track": "Spot",
            "base_pnl": Decimal("500"),
            "overlay_pnl": Decimal("-100"),
            "net_pnl": Decimal("400"),
            "return_on_nee": 0.2,
        }
    ]
    output = format_track_summary(rows, period="daily")
    assert "Day Base" not in output
    assert "Day Overlay" not in output
    assert "Day Net" not in output
    assert "Base P&L" not in output
    header_line = output.splitlines()[1]
    assert "Base" in header_line
    assert "Overlay" in header_line
    assert "Net" in header_line


def test_format_track_summary_daily_breakdown_headers():
    """period='daily' breakdown view (rows carry cc_pnl/collar_pnl/pp_pnl)
    also drops the redundant 'Day' prefix from all five columns."""
    rows = [
        {
            "track": "Spot",
            "base_pnl": Decimal("500"),
            "cc_pnl": Decimal("10"),
            "collar_pnl": Decimal("0"),
            "pp_pnl": Decimal("-5"),
            "net_pnl": Decimal("505"),
            "return_on_nee": 0.2,
        }
    ]
    output = format_track_summary(rows, period="daily")
    assert "Day" not in output
    header_line = output.splitlines()[1]
    assert "Base" in header_line
    assert "CC" in header_line
    assert "Collar" in header_line
    assert "PP" in header_line
    assert "Net" in header_line


def test_format_track_summary_default_period_is_inception():
    """Omitting period= defaults to inception headers."""
    rows = [
        {
            "track": "Spot",
            "base_pnl": Decimal("0"),
            "overlay_pnl": Decimal("0"),
            "net_pnl": Decimal("0"),
            "return_on_nee": 0.0,
        }
    ]
    output = format_track_summary(rows)
    assert "Base P&L" in output
