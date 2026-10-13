"""Tests for the calendar payoff adapter, curve summary and chart wiring (CM-6)."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import structlog

from src.nifty_calendar.payoff import compute_metrics, payoff_at
from src.notifications.payoff_chart import render_payoff_png, send_payoff_chart
from src.payoff.core import PayoffLeg, compute_payoff, summarise_curve
from src.payoff.registry import PayoffContext, PayoffRegistry
from src.strategy.nifty_calendar_payoff import CalendarPayoffAdapter
from src.strategy.payoff_registrations import ensure_registered
from tests.unit.nifty_calendar.test_payoff import _make_video_fixture

NAME = "paper_nifty_calendar_monthly"


def _ctx(**extras):
    structure, spot, carry, lot = _make_video_fixture()
    ex = {"structure": structure, "far_carry": carry} if extras.pop("full", True) else {}
    return PayoffContext(
        positions=[], spot=spot, lot_size=lot, strategy_name=NAME, extras={**ex, **extras}
    )


def test_calendar_adapter_values_far_legs() -> None:
    ctx = _ctx()
    structure, spot, carry, lot = _make_video_fixture()
    adapter = CalendarPayoffAdapter()
    legs = adapter.legs(ctx)
    assert sorted(leg.qty for leg in legs) == [-65, -65, 65, 65]
    curve = adapter.curve(ctx)
    assert curve is not None
    # Far wings keep time value at the near expiry: curve differs from the intrinsic payoff.
    far_out = Decimal("24500")
    intrinsic = compute_payoff(legs)
    assert curve(far_out) == payoff_at(structure, far_out, far_carry=carry, lot_size=lot)
    from src.payoff.core import expiry_pnl_at

    assert curve(far_out) != expiry_pnl_at(intrinsic, far_out)
    assert adapter.subtitle(ctx) == "SHORT 27 OCT · LONG 24 NOV"


def test_calendar_adapter_fails_closed_on_missing_iv() -> None:
    """No structure (e.g. build failed on a missing IV) -> no legs, no curve, one warning."""
    ctx = _ctx(full=False)
    adapter = CalendarPayoffAdapter()
    with structlog.testing.capture_logs() as logs:
        assert adapter.legs(ctx) == []
        assert adapter.curve(ctx) is None
    assert [e["event"] for e in logs] == ["calendar_payoff.inputs_missing"] * 2


def test_breakevens_match_poc_within_tolerance() -> None:
    structure, spot, carry, lot = _make_video_fixture()
    metrics = compute_metrics(structure, spot, far_carry=carry, lot_size=lot)
    ctx = _ctx()
    adapter = CalendarPayoffAdapter()
    base = compute_payoff(adapter.legs(ctx))
    out = summarise_curve(
        base, adapter.curve(ctx), spot * Decimal("0.85"), spot * Decimal("1.15"), Decimal("5")
    )
    low, high = out.breakevens
    assert abs(low - metrics.breakeven_low) < Decimal("5")
    assert abs(high - metrics.breakeven_high) < Decimal("5")
    assert out.max_loss < 0 < out.max_profit and out.rr_ratio is not None


def test_summarise_curve_rejects_bad_window() -> None:
    base = compute_payoff([PayoffLeg("CE", Decimal(100), -1, Decimal(5))])
    for lo, hi, step in ((10, 5, 1), (1, 5, 0)):
        try:
            summarise_curve(base, lambda x: x, Decimal(lo), Decimal(hi), Decimal(step))
        except ValueError:
            continue
        raise AssertionError("expected ValueError")


def test_registered_under_monthly_name_and_renders_through_ic_renderer() -> None:
    registry = PayoffRegistry()
    ensure_registered(registry)
    assert isinstance(registry.get(NAME), CalendarPayoffAdapter)
    sent: list[bytes] = []

    class Sender:
        async def send_photo(self, png: bytes, caption: str = "") -> None:
            sent.append(png)

    asyncio.run(send_payoff_chart(Sender(), NAME, _ctx(), registry=registry, dte=20))
    assert len(sent) == 1 and sent[0].startswith(b"\x89PNG")


def test_chart_skipped_with_warning_when_inputs_missing() -> None:
    registry = PayoffRegistry()
    registry.register(NAME, CalendarPayoffAdapter())
    sent: list[bytes] = []

    class Sender:
        async def send_photo(self, png: bytes, caption: str = "") -> None:
            sent.append(png)

    asyncio.run(send_payoff_chart(Sender(), NAME, _ctx(full=False), registry=registry))
    assert sent == []


def test_calendar_strike_ticks_merge_ce_and_pe_at_one_strike() -> None:
    from src.notifications.payoff_chart_axes import strike_ticks

    legs = CalendarPayoffAdapter().legs(_ctx())
    ticks = strike_ticks(compute_payoff(legs), 3000.0)
    assert [t.text.strip() for t in ticks if "22700" in t.text] == ["22700 CE/PE\nSELL"]
    assert len(ticks) == 3


def test_render_accepts_curve_argument() -> None:
    ctx = _ctx()
    adapter = CalendarPayoffAdapter()
    png = render_payoff_png(
        compute_payoff(adapter.legs(ctx)), spot=ctx.spot, curve=adapter.curve(ctx)
    )
    assert png.startswith(b"\x89PNG")
