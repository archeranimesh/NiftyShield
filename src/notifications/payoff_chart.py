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
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from src.notifications.payoff_chart_axes import (
    draw_breakevens,
    draw_now_marker,
    draw_spot,
    draw_strike_ticks,
    sample_xs,
    strike_ticks,
    style_axes,
    x_range,
)
from src.notifications.payoff_chart_header import build_header_cells, draw_header
from src.notifications.payoff_chart_theme import DARK, chart_font_family
from src.payoff.core import StrategyPayoff, compute_payoff, expiry_pnl_at
from src.payoff.errors import PayoffError, RenderError, SendError
from src.payoff.registry import (
    DEFAULT_REGISTRY,
    HasSubtitle,
    HasTitle,
    PayoffContext,
    PayoffRegistry,
)

logger = structlog.get_logger(__name__)

_RENDER_TIMEOUT_S = 30.0
_SEND_TIMEOUT_S = 30.0


def render_payoff_png(
    payoff: StrategyPayoff,
    *,
    spot: Decimal | None = None,
    current_pnl: Decimal | None = None,
    dte: int | None = None,
    margin: Decimal | None = None,
    title: str = "",
    subtitle: str = "",
) -> bytes:
    """Render the expiry payoff of ``payoff`` to PNG bytes.

    Args:
        payoff: Computed payoff (from ``compute_payoff``).
        spot: Current underlying price; draws a spot line and widens the range.
        current_pnl: Current P&L; draws a marker at ``(spot, current_pnl)``.
        dte: Days to expiry; accepted for caller symmetry.
        margin: Margin used; denominator for the P&L percentage when given.
        title: Chart title, supplied by the caller.
        subtitle: Chart subtitle, supplied by the caller.

    Returns:
        PNG image bytes.

    Raises:
        RenderError: On any rendering failure.
    """
    try:
        family = chart_font_family()

        # Subtitle composition
        parts = []
        if subtitle:
            parts.append(subtitle)
        if dte is not None:
            parts.append(f"{dte} DTE")
        display_subtitle = " · ".join(parts)

        cells = build_header_cells(payoff, spot=spot, margin=margin, current_pnl=current_pnl)

        # We start with height 4.9, layout will adjust if draw_header returns 2
        fig = Figure(figsize=(7, 4.9), facecolor=DARK.bg)
        FigureCanvasAgg(fig)

        rows = draw_header(fig, title, display_subtitle, cells, DARK, family)

        if rows > 1:
            fig.set_size_inches(7, 5.7)
            fig.subplots_adjust(left=0.13, right=0.97, top=0.585, bottom=0.12)
        else:
            fig.subplots_adjust(left=0.13, right=0.97, top=0.70, bottom=0.14)

        ax = fig.add_subplot(111)

        lo, hi = x_range(payoff, spot)
        xs = sample_xs(payoff, lo, hi)
        ys = np.array([float(expiry_pnl_at(payoff, Decimal(str(x)))) for x in xs])

        ax.fill_between(
            xs,
            ys,
            0,
            where=ys >= 0,
            interpolate=True,
            color=DARK.green,
            alpha=DARK.fill_alpha_green,
            lw=0,
        )
        ax.fill_between(
            xs,
            ys,
            0,
            where=ys <= 0,
            interpolate=True,
            color=DARK.red,
            alpha=DARK.fill_alpha_red,
            lw=0,
        )
        ax.plot(
            xs, np.ma.masked_where(ys < 0, ys), color=DARK.green, lw=1.8, solid_capstyle="round"
        )
        ax.plot(xs, np.ma.masked_where(ys > 0, ys), color=DARK.red, lw=1.8, solid_capstyle="round")
        ax.axhline(0, color=DARK.muted, lw=0.7)

        style_axes(ax, DARK, family)
        ax.set_xlim(lo, hi)

        s_ticks = strike_ticks(payoff, hi - lo)
        draw_strike_ticks(ax, s_ticks, DARK, family)

        draw_breakevens(ax, payoff.breakevens, spot, DARK, family)

        if spot is not None:
            draw_spot(ax, spot, DARK, family)
            if current_pnl is not None:
                draw_now_marker(ax, spot, current_pnl, DARK, family)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=170, facecolor=DARK.bg)
        data = buf.getvalue()
    except Exception as exc:  # intentional: never leak matplotlib/numpy types
        raise RenderError(f"payoff chart render failed: {exc}") from exc
    logger.info("payoff_chart.rendered", title=title, bytes=len(data))
    return data


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
    subtitle = adapter.subtitle(ctx) if isinstance(adapter, HasSubtitle) else ""
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
            subtitle=subtitle,
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
