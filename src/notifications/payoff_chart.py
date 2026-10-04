"""Strategy-agnostic expiry payoff chart rendered to PNG bytes.

Uses the matplotlib object-oriented ``Figure`` API (never ``pyplot``) so the
render owns all its state and is safe to run off the event loop.
"""

import asyncio
import io
from decimal import Decimal
from typing import Protocol

import numpy as np
import structlog
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from src.notifications.formatting import format_money, format_pct, format_strike
from src.payoff.core import StrategyPayoff, compute_payoff, expiry_pnl_series
from src.payoff.errors import PayoffError, RenderError, SendError
from src.payoff.registry import DEFAULT_REGISTRY, HasTitle, PayoffContext, PayoffRegistry

logger = structlog.get_logger(__name__)

_POINTS = 200
_GREEN = "#2e8b57"
_RED = "#c0392b"
_RENDER_TIMEOUT_S = 30.0
_SEND_TIMEOUT_S = 30.0


def _x_range(payoff: StrategyPayoff, spot: Decimal | None) -> tuple[Decimal, Decimal]:
    """Chart x-range: key spots padded by 1.5x span, floored at zero."""
    pts = list(payoff.key_spots) or ([spot] if spot is not None else [])
    if not pts:
        pts = [payoff.legs[0].entry_price]
    lo, hi = min(pts), max(pts)
    span = hi - lo
    if span == 0:
        span = (spot if spot is not None else lo) * Decimal("0.1")
    lo, hi = lo - Decimal("1.5") * span, hi + Decimal("1.5") * span
    if spot is not None:
        lo, hi = min(lo, spot), max(hi, spot)
    return max(lo, Decimal("0")), hi


def _label(value: Decimal) -> str:
    """Whole-number spot / strike label via the shared formatter."""
    return format_strike(int(value.to_integral_value()))


def _draw_verticals(ax: Axes, payoff: StrategyPayoff, spot: Decimal | None) -> None:
    short = {leg.strike for leg in payoff.legs if leg.qty < 0 and leg.strike is not None}
    for k in payoff.key_spots:
        is_short = k in short
        ax.axvline(
            float(k),
            ls="--",
            lw=1.0 if is_short else 0.8,
            color="#555555" if is_short else "#bbbbbb",
        )
    for be in payoff.breakevens:
        ax.axvline(float(be), ls="--", lw=1.2, color="#1f77b4")
        ax.text(
            float(be),
            1.0,
            _label(be),
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="bottom",
            fontsize=8,
            color="#1f77b4",
        )
    if spot is not None:
        ax.axvline(float(spot), lw=1.6, color="black", label=f"Nifty Spot : {_label(spot)}")


def _pnl_dot_label(payoff: StrategyPayoff, current_pnl: Decimal, margin: Decimal | None) -> str:
    base = f"Target P&L : {format_money(current_pnl)}"
    denom = margin if margin is not None else payoff.max_profit
    if denom is None or denom == 0:
        return base
    pct = (current_pnl / denom * 100).quantize(Decimal("0.1"))
    return f"{base} ({pct}%)"


def _breakeven_text(be: Decimal, spot: Decimal | None) -> str:
    text = _label(be)
    if spot is None or spot == 0:
        return text
    pct = float((be - spot) / spot * 100)
    sign = "+" if pct >= 0 else "-"
    return f"{text} ({sign}{format_pct(abs(pct))})"


def build_stat_strip(
    payoff: StrategyPayoff, *, spot: Decimal | None = None, margin: Decimal | None = None
) -> list[tuple[str, str]]:
    """Return the ordered ``(label, value)`` pairs shown in the chart's stat strip.

    Args:
        payoff: Computed payoff.
        spot: Current underlying; enables breakeven distance percentages.
        margin: Margin used; adds an ``Est. Margin`` entry only when not None.

    Returns:
        Label/value pairs; ``None`` max profit / loss render as ``Unlimited`` and a
        ``None`` R:R is omitted. Max loss is shown as a magnitude;
        a non-negative worst case (guaranteed profit) is labelled ``Min Profit``.
    """
    unlimited = "Unlimited"
    rows = [
        ("Max Profit", unlimited if payoff.max_profit is None else format_money(payoff.max_profit)),
        _worst_case_row(payoff.max_loss, unlimited),
    ]
    if payoff.rr_ratio is not None:
        rows.append(("R:R", f"1:{payoff.rr_ratio.quantize(Decimal('0.01'))}"))
    credit = payoff.net_premium >= 0
    rows.append(("Net Credit" if credit else "Net Debit", format_money(abs(payoff.net_premium))))
    if payoff.breakevens:
        rows.append(("Breakevens", " – ".join(_breakeven_text(b, spot) for b in payoff.breakevens)))
    if margin is not None:
        rows.append(("Est. Margin", format_money(margin)))
    return rows


def _worst_case_row(max_loss: Decimal | None, unlimited: str) -> tuple[str, str]:
    """Return the worst-case row: ``Max Loss`` magnitude, or ``Min Profit`` if it cannot lose."""
    if max_loss is None:
        return ("Max Loss", unlimited)
    if max_loss < 0:
        return ("Max Loss", format_money(-max_loss))
    return ("Min Profit", format_money(max_loss))


def _draw_stat_strip(fig: Figure, rows: list[tuple[str, str]]) -> None:
    """Draw ``rows`` as a two-line text band above the axes."""
    half = (len(rows) + 1) // 2
    for i, line in enumerate((rows[:half], rows[half:])):
        fig.text(
            0.5,
            0.99 - 0.045 * i,
            "    ".join(f"{k}: {v}" for k, v in line),
            ha="center",
            va="top",
            fontsize=9,
            fontweight="bold",
        )


def render_payoff_png(
    payoff: StrategyPayoff,
    *,
    spot: Decimal | None = None,
    current_pnl: Decimal | None = None,
    dte: int | None = None,
    margin: Decimal | None = None,
    title: str = "",
) -> bytes:
    """Render the expiry payoff of ``payoff`` to PNG bytes.

    Args:
        payoff: Computed payoff (from ``compute_payoff``).
        spot: Current underlying price; draws a spot line and widens the range.
        current_pnl: Current P&L; draws a marker at ``(spot, current_pnl)``.
        dte: Days to expiry; accepted for caller symmetry, unused by the chart.
        margin: Margin used; denominator for the P&L percentage when given.
        title: Chart title, supplied by the caller.

    Returns:
        PNG image bytes.

    Raises:
        RenderError: On any rendering failure.
    """
    try:
        lo, hi = _x_range(payoff, spot)
        xs, ys = expiry_pnl_series(payoff, lo, hi, _POINTS)
        fig = Figure(figsize=(9, 5), facecolor="white")
        FigureCanvasAgg(fig)
        fig.subplots_adjust(top=0.80)
        _draw_stat_strip(fig, build_stat_strip(payoff, spot=spot, margin=margin))
        ax = fig.add_subplot(111)
        x = [float(v) for v in xs]
        y = [float(v) for v in ys]
        ax.fill_between(
            x, y, 0, where=[v > 0 for v in y], interpolate=True, color=_GREEN, alpha=0.2
        )
        ax.fill_between(x, y, 0, where=[v < 0 for v in y], interpolate=True, color=_RED, alpha=0.15)
        _plot_line(ax, x, y)
        ax.axhline(0, color="black", lw=0.8)
        _draw_verticals(ax, payoff, spot)
        if spot is not None and current_pnl is not None:
            ax.plot(
                [float(spot)],
                [float(current_pnl)],
                "o",
                color="black",
                label=_pnl_dot_label(payoff, current_pnl, margin),
            )
        if spot is not None:
            ax.legend(loc="upper right", fontsize=8)
        ax.set_title(title)
        ax.set_xlabel("Underlying at expiry")
        ax.set_ylabel("P&L (₹)")
        ax.grid(axis="y", alpha=0.3)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
        data = buf.getvalue()
    except Exception as exc:  # intentional: never leak matplotlib/numpy types
        raise RenderError(f"payoff chart render failed: {exc}") from exc
    logger.info("payoff_chart.rendered", title=title, bytes=len(data))
    return data


def _plot_line(ax: Axes, x: list[float], y: list[float]) -> None:
    """Draw the payoff line green above zero, red below (masked segments)."""
    xa, ya = np.array(x), np.array(y)
    ax.plot(xa, np.ma.masked_where(ya < 0, ya), color=_GREEN, lw=2)
    ax.plot(xa, np.ma.masked_where(ya >= 0, ya), color=_RED, lw=2)


class PhotoSender(Protocol):
    """Anything that can deliver a PNG (e.g. ``TelegramGateway``)."""

    async def send_photo(self, png: bytes, caption: str = "") -> None: ...


async def _build_and_send(
    sender: PhotoSender,
    strategy_name: str,
    ctx: PayoffContext,
    registry: PayoffRegistry,
    dte: int | None,
    current_pnl: Decimal | None,
    margin: Decimal | None,
    caption: str,
) -> None:
    adapter = registry.get(strategy_name)
    if adapter is None:
        logger.warning("payoff_chart.unregistered", strategy=strategy_name)
        return
    legs = adapter.legs(ctx)
    if not legs:
        logger.info("payoff_chart.no_legs", strategy=strategy_name)
        return
    payoff = compute_payoff(legs)
    title = adapter.title(ctx) if isinstance(adapter, HasTitle) else ""
    # CPU-bound render runs in a worker thread (Figure API is thread-safe;
    # to_thread copies contextvars). If GIL contention is ever measured to
    # matter, move to a ProcessPoolExecutor per the CLAUDE.md async rules.
    png = await asyncio.wait_for(
        asyncio.to_thread(
            render_payoff_png,
            payoff,
            spot=ctx.spot,
            current_pnl=current_pnl,
            dte=dte,
            margin=margin,
            title=title,
        ),
        timeout=_RENDER_TIMEOUT_S,
    )
    try:
        await asyncio.wait_for(sender.send_photo(png, caption=caption), timeout=_SEND_TIMEOUT_S)
    except asyncio.TimeoutError:
        raise
    except PayoffError:
        raise
    except Exception as exc:
        raise SendError(f"send_photo failed: {exc}") from exc


async def send_payoff_chart(
    sender: PhotoSender,
    strategy_name: str,
    ctx: PayoffContext,
    *,
    registry: PayoffRegistry = DEFAULT_REGISTRY,
    dte: int | None = None,
    current_pnl: Decimal | None = None,
    margin: Decimal | None = None,
    caption: str = "",
) -> None:
    """Render and send the payoff chart for a registered strategy; never raises.

    An unregistered strategy logs ``payoff_chart.unregistered`` and sends
    nothing. All failures and timeouts are logged and swallowed so call sites
    need no try/except of their own.

    Args:
        sender: Photo delivery target.
        strategy_name: Name the strategy registered its adapter under.
        ctx: Adapter input (positions, spot, lot size).
        registry: Registry to look the adapter up in.
        dte: Days to expiry, forwarded to the renderer.
        current_pnl: Current P&L for the marker dot.
        margin: Margin used, for the stat strip.
        caption: Photo caption.
    """
    try:
        await _build_and_send(
            sender, strategy_name, ctx, registry, dte, current_pnl, margin, caption
        )
    except PayoffError as exc:
        logger.warning("payoff_chart.failed", strategy=strategy_name, error=str(exc))
    except asyncio.TimeoutError:
        logger.warning("payoff_chart.timeout", strategy=strategy_name)
    except Exception:  # intentional: the single non-fatal choke point
        logger.exception("payoff_chart.unexpected_failure", strategy=strategy_name)
