"""print_summary shows the strike of each leg (duck-typed stubs, no domain models)."""

from decimal import Decimal
from types import SimpleNamespace

from scripts.strategies.three_track.paper_3track_overlay_entry import print_summary


def _cfg() -> SimpleNamespace:
    return SimpleNamespace(
        entry_date="2026-11-11",
        cycle=1,
        overlay_type="collar",
        expiry="2026-12-29",
        expiry_type="yearly",
        dte_at_entry=48,
        lot_size=65,
        put_strike=23000.0,
        call_strike=26500.0,
    )


def _ot(leg_role: str, action: str, price: str) -> SimpleNamespace:
    trade = SimpleNamespace(
        strategy_name="paper_nifty_overlay_yearly_collar",
        leg_role=leg_role,
        action=SimpleNamespace(value=action),
        price=Decimal(price),
    )
    return SimpleNamespace(trade=trade)


def test_summary_shows_put_and_call_strikes(capsys) -> None:
    trades = [
        _ot("overlay_collar_put", "BUY", "129.10"),
        _ot("overlay_collar_call", "SELL", "130.90"),
    ]
    print_summary(_cfg(), trades, [], dry_run=True)
    out = capsys.readouterr().out
    assert "23000 PE" in out and "26500 CE" in out


def test_summary_unmapped_leg_role_shows_dash(capsys) -> None:
    print_summary(_cfg(), [_ot("unknown_role", "BUY", "10.00")], [], dry_run=True)
    assert " -" in capsys.readouterr().out
