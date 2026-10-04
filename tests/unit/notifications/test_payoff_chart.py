"""Tests for src.notifications.payoff_chart (Agg, no display)."""

import sys
from decimal import Decimal as D

import pytest

from src.notifications.payoff_chart import render_payoff_png
from src.payoff.core import PayoffLeg, compute_payoff
from src.payoff.errors import RenderError


def _ic():
    return compute_payoff(
        [
            PayoffLeg("PE", D(22000), 75, D(30), "long_put"),
            PayoffLeg("PE", D(22500), -75, D(80), "short_put"),
            PayoffLeg("CE", D(24000), -75, D(75), "short_call"),
            PayoffLeg("CE", D(24500), 75, D(25), "long_call"),
        ]
    )


def _naked_call():
    return compute_payoff([PayoffLeg("CE", D(24000), -75, D(75), "short_call")])


def _is_png(b: bytes) -> bool:
    return b.startswith(b"\x89PNG")


def test_render_returns_png_bytes():
    out = render_payoff_png(_ic())
    assert _is_png(out) and len(out) > 1024


def test_render_minimal():
    assert _is_png(render_payoff_png(_ic()))


def test_render_unbounded_structure():
    assert _naked_call().max_loss is None
    assert _is_png(render_payoff_png(_naked_call(), spot=D(23500)))


def test_render_full():
    out = render_payoff_png(
        _ic(), spot=D("23250.5"), current_pnl=D(1500), dte=12, margin=D(100000), title="IC"
    )
    assert _is_png(out)


def test_render_single_strike_pnl_without_max_profit():
    out = render_payoff_png(_naked_call(), spot=D(23500), current_pnl=D(500))
    assert _is_png(out)


def test_render_does_not_touch_pyplot():
    render_payoff_png(_ic(), spot=D(23250))
    if "matplotlib.pyplot" in sys.modules:
        assert sys.modules["matplotlib.pyplot"].get_fignums() == []


def test_render_wraps_failures(monkeypatch):
    import src.notifications.payoff_chart as pc

    monkeypatch.setattr(pc, "expiry_pnl_series", lambda *a, **k: 1 / 0)
    with pytest.raises(RenderError):
        render_payoff_png(_ic())


def _strip(payoff, **kw):
    from src.notifications.payoff_chart import build_stat_strip

    return dict(build_stat_strip(payoff, **kw))


def test_stat_strip_without_margin():
    rows = _strip(_ic(), spot=D(23250))
    assert "Est. Margin" not in rows
    assert rows["Net Credit"] == "₹7,500.00"
    assert "Breakevens" in rows and "%" in rows["Breakevens"]
    assert _is_png(render_payoff_png(_ic(), spot=D(23250), margin=None))


def test_stat_strip_with_margin():
    rows = _strip(_ic(), margin=D(100000))
    assert rows["Est. Margin"] == "₹100,000.00"
    assert "%" not in rows["Breakevens"]
    assert _is_png(render_payoff_png(_ic(), margin=D(100000)))


def test_stat_strip_unbounded_side():
    rows = _strip(_naked_call())
    assert rows["Max Loss"] == "Unlimited"
    assert "R:R" not in rows
    assert _is_png(render_payoff_png(_naked_call()))


def test_stat_strip_net_debit():
    long_call = compute_payoff([PayoffLeg("CE", D(24000), 75, D(75), "long_call")])
    rows = _strip(long_call)
    assert "Net Debit" in rows and rows["Max Profit"] == "Unlimited"
    assert rows["Max Loss"] == "₹5,625.00"
    assert _is_png(render_payoff_png(long_call))
