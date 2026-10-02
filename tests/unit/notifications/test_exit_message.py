"""Tests for the unified exit confirmation renderer (UXM-2)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from src.notifications.exit_message import ExitKind, ExitMessage, format_exit_message
from src.notifications.formatting import CloseLegRow, build_close_leg_table
from src.paper.cycle_pnl import CycleStats

_LEGS = [
    CloseLegRow(
        role="Short",
        instrument="23500 PE",
        entry=Decimal("103.4"),
        exit=Decimal("42.0"),
        pnl=Decimal("61.40"),
    ),
]

_STATS_5 = CycleStats(
    closed_count=5,
    wins=3,
    losses=2,
    win_rate=0.6,
    avg_win=Decimal("120.00"),
    avg_loss=Decimal("-45.00"),
    best=Decimal("200.00"),
    worst=Decimal("-80.00"),
    avg_hold_days=6.4,
    avg_decay_pct=Decimal("68.5"),
)


def _msg(**overrides: Any) -> ExitMessage:
    base = dict(
        headline_label="CSP",
        kind=ExitKind.CLOSE,
        signal="target hit",
        dte=3,
        held_days=6,
        legs=_LEGS,
        this_exit_pnl=Decimal("61.40"),
        cycle_pnl=Decimal("61.40"),
        cycle_index=1,
        cycle_decay_pct=Decimal("59"),
        cycle_short_credit=Decimal("103.40"),
        cycle_short_buyback=Decimal("42.00"),
        cycle_held_days=6,
        inception_pnl=Decimal("340.10"),
        stats=None,
    )
    base.update(overrides)
    return ExitMessage(**base)


def test_full_close_collapses_this_exit_and_cycle() -> None:
    out = format_exit_message(_msg()).splitlines()
    joined = "\n".join(out)
    assert "💰 *This exit:*" not in joined
    assert any(line.startswith("🔁 *Cycle") for line in out)


def test_partial_close_omits_cycle_row() -> None:
    out = format_exit_message(
        _msg(
            this_exit_pnl=Decimal("20.00"),
            cycle_pnl=None,
            cycle_index=None,
            cycle_decay_pct=None,
            cycle_short_credit=None,
            cycle_short_buyback=None,
            cycle_held_days=None,
        )
    ).splitlines()
    joined = "\n".join(out)
    assert "🔁" not in joined
    assert any(line.startswith("💰 *This exit:*") for line in out)


def test_cycle_line_shows_short_credit_cost_decay() -> None:
    out = format_exit_message(
        _msg(this_exit_pnl=Decimal("999.00"))  # force no collapse
    )
    line = next(line for line in out.splitlines() if line.startswith("🔁"))
    assert "103\\.40" in line
    assert "42\\.00" in line
    assert "59% decay" in line


def test_cycle_line_drops_decay_segment_for_pure_long() -> None:
    out = format_exit_message(
        _msg(
            this_exit_pnl=Decimal("999.00"),
            cycle_decay_pct=None,
            cycle_short_credit=None,
            cycle_short_buyback=None,
        )
    )
    line = next(line for line in out.splitlines() if line.startswith("🔁"))
    assert "→" not in line
    assert "decay" not in line
    assert "6d" in line


def test_win_rate_hidden_below_five_cycles() -> None:
    stats = CycleStats(
        closed_count=4,
        wins=2,
        losses=2,
        win_rate=0.5,
        avg_win=Decimal("100"),
        avg_loss=Decimal("-50"),
        best=Decimal("150"),
        worst=Decimal("-70"),
        avg_hold_days=5.0,
        avg_decay_pct=Decimal("50"),
    )
    out = format_exit_message(_msg(stats=stats))
    assert "🎯" not in out


def test_win_rate_shown_at_five() -> None:
    out = format_exit_message(_msg(stats=_STATS_5))
    assert "🎯 *Win rate:* 60%" in out


def test_win_rate_line_omits_avg_decay_when_none() -> None:
    stats = CycleStats(
        closed_count=5,
        wins=3,
        losses=2,
        win_rate=0.6,
        avg_win=Decimal("120.00"),
        avg_loss=Decimal("-45.00"),
        best=Decimal("200.00"),
        worst=Decimal("-80.00"),
        avg_hold_days=6.4,
        avg_decay_pct=None,
    )
    out = format_exit_message(_msg(stats=stats))
    line = next(line for line in out.splitlines() if line.startswith("🎯"))
    assert "avg decay" not in line
    assert "avg" in line


def test_net_loss_renders_minus_sign() -> None:
    out = format_exit_message(_msg(inception_pnl=Decimal("-500.00")))
    line = next(line for line in out.splitlines() if line.startswith("📈"))
    assert "-₹500" in line
    assert "₹\\-500" not in line


def test_footer_uses_bug043_cycle_and_since_inception_labels() -> None:
    """BUG-043 (operator decision 2026-10-02): fixed `Cycle P&L` / `Since inception` labels."""
    out = format_exit_message(_msg()).splitlines()
    assert (
        "🔁 *Cycle P&L \\(\\#1\\):* \\+₹61\\.40  ·  ₹103\\.40 → ₹42\\.00  ·  59% decay  ·  6d"
        in out
    )
    assert "📈 *Since inception:* \\+₹340\\.10" in out
    assert not any("Inception:" in line for line in out)


def test_footer_never_renders_overlay_total_line() -> None:
    """BUG-043: the overlay-only total line duplicated inception and is gone."""
    out = format_exit_message(_msg())
    assert "📊" not in out
    assert "Overlay P&L" not in out


def test_close_leg_table_badges() -> None:
    rows = [
        CloseLegRow(
            role="Short Put",
            instrument="23500 PE",
            entry=Decimal("103.4"),
            exit=Decimal("42.0"),
            pnl=Decimal("61.40"),
        ),
        CloseLegRow(
            role="Long Put",
            instrument="23000 PE",
            entry=Decimal("21.2"),
            exit=Decimal("23.8"),
            pnl=Decimal("-2.60"),
        ),
    ]
    table = build_close_leg_table(rows)
    lines = table.splitlines()
    assert lines[2].startswith("[S]")
    assert lines[3].startswith("[B]")
    assert "+₹61.40" in lines[2]
    assert "-₹2.60" in lines[3]


def test_close_leg_table_rounds_half_up() -> None:
    """B043.6: Decimal 72.55 quantizes ROUND_HALF_UP to 72.6 (float :.1f gave 72.5)."""
    rows = [
        CloseLegRow(
            role="Short Put",
            instrument="23500 PE",
            entry=Decimal("72.55"),
            exit=Decimal("10.25"),
            pnl=Decimal("62.30"),
        )
    ]
    row_line = build_close_leg_table(rows).splitlines()[2]
    assert " 72.6 " in row_line
    assert " 10.3 " in row_line
    assert "72.5 " not in row_line


def test_close_leg_table_rejects_float_prices() -> None:
    """A float price raises TypeError (as format_money does), never float-formatted."""
    rows = [
        CloseLegRow(
            role="Short Put",
            instrument="23500 PE",
            entry=72.55,  # type: ignore[arg-type]
            exit=Decimal("10"),
            pnl=Decimal("0"),
        )
    ]
    with pytest.raises(TypeError, match="Decimal"):
        build_close_leg_table(rows)


def test_close_leg_table_raises_on_empty() -> None:
    with pytest.raises(ValueError):
        build_close_leg_table([])


def test_roll_kind_headline() -> None:
    out = format_exit_message(_msg(kind=ExitKind.ROLL, headline_label="CSP", signal="delta breach"))
    assert out.splitlines()[0] == "🔄 *CSP Rolled* — delta breach"


def test_waiting_kind_headline() -> None:
    out = format_exit_message(
        _msg(kind=ExitKind.WAITING, headline_label="CSP", signal="re-entry gated")
    )
    assert out.splitlines()[0].startswith("⛔ *CSP Closed — waiting* — ")
