from datetime import date
from decimal import Decimal

from src.models.portfolio import PortfolioSummary, AssetType
from src.dhan.models import DhanPortfolioSummary
from src.nuvama.models import NuvamaBondSummary, NuvamaOptionsSummary
from src.mf.tracker import PortfolioPnL
from src.portfolio.formatting import _format_combined_summary


def test_telegram_fully_populated_summary():
    mf = PortfolioPnL(
        snapshot_date=date(2026, 4, 15),
        schemes=(),
        total_current_value=Decimal("500000.00"),
        total_invested=Decimal("450000.00"),
        total_pnl=Decimal("50000.00"),
        total_pnl_pct=Decimal("11.11")
    )
    dhan = DhanPortfolioSummary(
        snapshot_date=date(2026, 4, 15),
        equity_holdings=(),
        equity_value=Decimal("137700.00"),
        equity_basis=Decimal("134250.00"),
        equity_pnl=Decimal("3450.00"),
        equity_pnl_pct=Decimal("2.57"),
        bond_holdings=(),
        bond_value=Decimal("201100.00"),
        bond_basis=Decimal("200650.00"),
        bond_pnl=Decimal("450.00"),
        bond_pnl_pct=Decimal("0.22"),
        equity_day_delta=Decimal("500.00"),
        bond_day_delta=Decimal("100.00")
    )
    nuvama = NuvamaBondSummary(
        snapshot_date=date(2026, 4, 15),
        holdings=(),
        total_value=Decimal("3158740.00"),
        total_basis=Decimal("3629222.00"),
        total_pnl=Decimal("529518.00"),
        total_pnl_pct=Decimal("14.59"),
        total_day_delta=Decimal("-12345.00")
    )
    nuvama_options = NuvamaOptionsSummary(
        snapshot_date=date(2026, 4, 15),
        positions=(),
        total_unrealized_pnl=Decimal("800.00"),
        total_realized_pnl_today=Decimal("200.00"),
        cumulative_realized_pnl=Decimal("0.00"),
        intraday_high=Decimal("1500.00"),
        intraday_low=Decimal("-500.00"),
        nifty_high=24000.0,
        nifty_low=23900.0
    )

    out = _format_combined_summary(
        strategies=[],
        prices={},
        strategy_pnls={},
        mf_pnl=mf,
        snap_date=date(2026, 4, 15),
        dhan_summary=dhan,
        nuvama_summary=nuvama,
        nuvama_options_summary=nuvama_options
    )
    
    assert "Dhan Equity" in out
    assert "+500" in out # Dhan Equity Day Delta
    assert "Nuvama Bonds" in out
    assert "-12,345" in out # Nuvama Bonds Day Delta
    assert "Dhan Bonds" in out
    assert "+100" in out # Dhan Bonds Day Delta
    assert "Nuvama P&L" in out
    assert "+1,000" in out # Nuvama options net pnl
    assert "MF" in out
    assert "39,97,540" in out # Total Portfolio Value
