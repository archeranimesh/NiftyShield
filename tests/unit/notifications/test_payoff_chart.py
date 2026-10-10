"""Tests for src.notifications.payoff_chart (Agg, no display)."""

import asyncio
import sys
from decimal import Decimal as D

import pytest
import structlog

from src.notifications import payoff_chart
from src.notifications.payoff_chart import render_payoff_png, send_payoff_chart
from src.payoff.core import PayoffLeg, compute_payoff
from src.payoff.errors import InvalidLegsError, RenderError
from src.payoff.registry import PayoffContext, PayoffRegistry


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

    monkeypatch.setattr(pc, "expiry_pnl_at", lambda *a, **k: 1 / 0)
    with pytest.raises(RenderError):
        render_payoff_png(_ic())


def test_render_full_inputs_returns_valid_png():
    out = render_payoff_png(
        _ic(),
        spot=D("23250.5"),
        current_pnl=D(1500),
        dte=12,
        margin=D(100000),
        title="IC",
        subtitle="Monthly",
    )
    assert _is_png(out)


def test_render_with_font_fallback(monkeypatch):
    import src.notifications.payoff_chart as pc

    monkeypatch.setattr(pc, "chart_font_family", lambda: "DejaVu Sans")
    out = render_payoff_png(_ic())
    assert _is_png(out)


def test_render_two_row_header_on_huge_values():
    # Provide huge values to force two rows
    out = render_payoff_png(
        _ic(), spot=D("23250.5"), current_pnl=D(9999999999), margin=D(99999999999)
    )
    assert _is_png(out)


def test_render_five_strike_structure():
    legs = [
        PayoffLeg("PE", D(21000), 75, D(10), "x"),
        PayoffLeg("PE", D(22000), -75, D(20), "x"),
        PayoffLeg("PE", D(23000), 75, D(30), "x"),
        PayoffLeg("CE", D(24000), -75, D(40), "x"),
        PayoffLeg("CE", D(25000), 75, D(50), "x"),
    ]
    payoff = compute_payoff(legs)
    out = render_payoff_png(payoff, spot=D(23000))
    assert _is_png(out)


def test_payoff_chart_modules_import_boundary():
    import ast
    from pathlib import Path

    src = Path("src") / "notifications"
    for module in ["payoff_chart_theme.py", "payoff_chart_axes.py", "payoff_chart_header.py"]:
        code = (src / module).read_text()
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "src.notifications.payoff_chart":
                    pytest.fail(
                        f"{module} imports from payoff_chart, violating pure helpers boundary"
                    )


# --- send_payoff_chart ---


class _Adapter:
    def __init__(self, legs=None, exc=None):
        self._legs, self._exc = legs, exc

    def legs(self, ctx):
        if self._exc:
            raise self._exc
        return self._legs if self._legs is not None else list(_ic().legs)

    def title(self, ctx):
        return "T"


class _Sender:
    def __init__(self, exc=None, hang=False):
        self.calls, self._exc, self._hang = [], exc, hang

    async def send_photo(self, png, caption=""):
        if self._hang:
            await asyncio.sleep(3600)
        if self._exc:
            raise self._exc
        self.calls.append((png, caption))


def _ctx():
    return PayoffContext(positions=[], spot=D(23000), lot_size=75, strategy_name="s")


async def _send(adapter, sender, name="s"):
    reg = PayoffRegistry()
    reg.register("s", adapter)
    await send_payoff_chart(sender, name, _ctx(), registry=reg, caption="cap")


async def test_send_happy_path():
    sender = _Sender()
    await _send(_Adapter(), sender)
    assert len(sender.calls) == 1 and _is_png(sender.calls[0][0])
    assert sender.calls[0][1] == "cap"


async def test_send_unregistered_warns_and_noops(monkeypatch):
    warned = []
    monkeypatch.setattr(payoff_chart.logger, "warning", lambda ev, **kw: warned.append(ev))
    sender = _Sender()
    await _send(_Adapter(), sender, name="missing")
    assert sender.calls == [] and warned == ["payoff_chart.unregistered"]


async def test_send_empty_legs_is_noop():
    sender = _Sender()
    await _send(_Adapter(legs=[]), sender)
    assert sender.calls == []


async def test_send_unresolved_legs_is_noop():
    sender = _Sender()
    await _send(_Adapter(exc=InvalidLegsError("x")), sender)
    assert sender.calls == []


async def test_send_swallows_render_error(monkeypatch):
    def boom(*a, **k):
        raise RenderError("nope")

    warned = []
    monkeypatch.setattr(payoff_chart, "render_payoff_png", boom)
    monkeypatch.setattr(payoff_chart.logger, "warning", lambda ev, **kw: warned.append(ev))
    sender = _Sender()
    await _send(_Adapter(), sender)
    assert sender.calls == [] and warned == ["payoff_chart.failed"]


async def test_send_swallows_unexpected_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("bug")

    monkeypatch.setattr(payoff_chart, "render_payoff_png", boom)
    await _send(_Adapter(), _Sender())


async def test_send_swallows_send_error():
    await _send(_Adapter(), _Sender(exc=RuntimeError("tg down")))


async def test_send_times_out_cleanly(monkeypatch):
    monkeypatch.setattr(payoff_chart, "_SEND_TIMEOUT_S", 0.05)
    await _send(_Adapter(), _Sender(hang=True))


async def test_correlation_context_reaches_render_thread(monkeypatch):
    seen = {}

    def spy(*a, **k):
        seen.update(structlog.contextvars.get_contextvars())
        return b"\x89PNG"

    monkeypatch.setattr(payoff_chart, "render_payoff_png", spy)
    structlog.contextvars.bind_contextvars(corr_id="abc")
    try:
        await _send(_Adapter(), _Sender())
    finally:
        structlog.contextvars.clear_contextvars()
    assert seen.get("corr_id") == "abc"
