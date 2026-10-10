from dataclasses import dataclass
from decimal import Decimal

import numpy as np
from matplotlib.axes import Axes
from matplotlib.ticker import FuncFormatter

from src.notifications.formatting import format_money_k, format_strike
from src.notifications.payoff_chart_theme import ChartTheme
from src.payoff.core import StrategyPayoff


def x_range(payoff: StrategyPayoff, spot: Decimal | None) -> tuple[float, float]:
    """Chart x-range: key spots padded by 0.4x span, widened to include spot, floored at 0."""
    pts = list(payoff.key_spots) or ([spot] if spot is not None else [])
    if not pts:
        pts = [payoff.legs[0].entry_price]

    lo, hi = min(pts), max(pts)
    span = float(hi - lo)

    if span == 0:
        span = float(spot if spot is not None else lo) * 0.1

    lo_f, hi_f = float(lo) - 0.4 * span, float(hi) + 0.4 * span

    if spot is not None:
        lo_f, hi_f = min(lo_f, float(spot)), max(hi_f, float(spot))

    return max(0.0, lo_f), hi_f


def sample_xs(payoff: StrategyPayoff, lo: float, hi: float, n: int = 240) -> np.ndarray:
    """linspace unioned with every strike and breakeven, sorted, unique."""
    xs = np.linspace(lo, hi, n)
    extra = []
    for leg in payoff.legs:
        if leg.strike is not None:
            extra.append(float(leg.strike))
    for be in payoff.breakevens:
        extra.append(float(be))

    return np.unique(np.concatenate([xs, np.array(extra)]))


@dataclass(frozen=True)
class StrikeTick:
    x: float
    text: str
    short: bool


def strike_ticks(payoff: StrategyPayoff, span: float) -> list[StrikeTick]:
    """One per option strike, ascending. Staggers close neighbours."""
    legs = [leg for leg in payoff.legs if leg.strike is not None]
    legs.sort(key=lambda leg: leg.strike)

    ticks = []
    last_x = None
    last_lowered = False

    for leg in legs:
        x_val = float(leg.strike)
        strike_str = format_strike(leg.strike)
        side = "SELL" if leg.qty < 0 else "BUY"
        base_text = f"{strike_str} {leg.kind}\n{side}"

        lowered = False
        if last_x is not None and (x_val - last_x) < 0.14 * span:
            if not last_lowered:
                lowered = True

        text = "\n" + base_text if lowered else base_text
        ticks.append(StrikeTick(x=x_val, text=text, short=leg.qty < 0))

        last_x = x_val
        last_lowered = lowered

    return ticks


def style_axes(ax: Axes, theme: ChartTheme, family: str) -> None:
    """Quiet chrome: no top/right spines, muted axes, light horizontal grid, ₹k ticks."""
    ax.set_facecolor(theme.bg)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(theme.faint)

    ax.tick_params(colors=theme.muted, labelsize=9.5, length=0)
    ax.grid(axis="y", color=theme.faint, lw=0.6)
    ax.set_axisbelow(True)

    # Display-only float to Decimal conversion for y-ticks
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: format_money_k(Decimal(str(round(v))))))
    for lab in ax.get_yticklabels():
        lab.set_family(family)


def draw_strike_ticks(ax: Axes, ticks: list[StrikeTick], theme: ChartTheme, family: str) -> None:
    """x ticks at the strikes ("21900 PE / SELL"); a tick too near its neighbour drops a row."""
    if not ticks:
        return

    ax.set_xticks([t.x for t in ticks])
    ax.set_xticklabels([t.text for t in ticks], family=family)

    for ax_tick, t in zip(ax.get_xticklabels(), ticks, strict=True):
        color = theme.ink if t.short else theme.muted
        weight = "bold" if t.short else "normal"
        ax_tick.set_color(color)
        ax_tick.set_fontweight(weight)

        ax.axvline(t.x, ls=":", lw=0.8, color=theme.ink if t.short else theme.faint, zorder=1)


def draw_breakevens(
    ax: Axes, breakevens: tuple[Decimal, ...], spot: Decimal | None, theme: ChartTheme, family: str
) -> None:
    """Open dot on the zero line, value + % distance beside it, outside the profit tent."""
    # Sort breakevens for consistent left/right assignment if spot is None
    sorted_bes = sorted(float(be) for be in breakevens)

    for i, be in enumerate(sorted_bes):
        if spot is not None:
            left = be < float(spot)
        else:
            left = i < len(sorted_bes) / 2

        text = f"BE {int(be)}"
        ax.annotate(
            text,
            (be, 0),
            xytext=(-7 if left else 7, 5),
            textcoords="offset points",
            ha="right" if left else "left",
            va="bottom",
            fontsize=9,
            color=theme.ink,
            family=family,
        )
        ax.plot([be], [0], "o", ms=5, color=theme.bg, mec=theme.ink, mew=1.1, zorder=5)


def draw_spot(ax: Axes, spot: Decimal, theme: ChartTheme, family: str) -> None:
    """Solid vertical spot line and SPOT label."""
    spot_f = float(spot)
    ax.axvline(spot_f, lw=0.9, color=theme.ink, zorder=4)
    ax.annotate(
        f"SPOT {int(spot_f)}",
        (spot_f, 1.0),
        xycoords=("data", "axes fraction"),
        xytext=(0, 4),
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=10,
        weight="bold",
        color=theme.ink,
        family=family,
    )


def draw_now_marker(ax: Axes, spot: Decimal, pnl: Decimal, theme: ChartTheme, family: str) -> None:
    """Filled dot at (spot, pnl) and a "Now" label."""
    spot_f, pnl_f = float(spot), float(pnl)
    ax.plot([spot_f], [pnl_f], "o", ms=8, color=theme.ink, zorder=6)
    ax.annotate(
        "Now",
        (spot_f, pnl_f),
        xytext=(0, -24),
        textcoords="offset points",
        ha="center",
        fontsize=9.5,
        color=theme.ink,
        family=family,
        bbox={"fc": theme.bg, "ec": "none", "pad": 1.5},
    )
