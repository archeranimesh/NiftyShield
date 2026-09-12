#!/usr/bin/env python3
"""Morning signal-pipeline cron script.

Cron: 15 9 * * 1-5  (also opens the paper_signal_track_v1 entry — no separate cron)

Pure orchestration: assemble the market snapshot, fan out to every configured
signal provider, aggregate their responses into one consensus DailySignal,
persist every stage, and send a one-line Telegram notification. All
data-source logic lives in ``assemble_market_snapshot`` — this script contains
none. After the DailySignal is persisted, a guarded tail-call opens the
signals-paper-track entry (SPT-6) — a failure there is logged and isolated,
never crashing the advisory pipeline.
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from statistics import mean

import structlog
from dotenv import load_dotenv

# Path setup must happen before importing local src modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load environment before local imports
load_dotenv()

from src.client.factory import create_client  # noqa: E402
from src.config import settings  # noqa: E402
from src.market_calendar.holidays import guard_trading_day  # noqa: E402
from src.notifications.formatting import format_money, format_strike  # noqa: E402
from src.notifications.markdown import escape_markdown  # noqa: E402
from src.notifications.telegram import build_notifier  # noqa: E402
from src.paper.constants import DEFAULT_BOD_PATH  # noqa: E402
from src.signals.models import (  # noqa: E402
    DailySignal,
    Direction,
)
from src.signals.pipeline import run_morning_signal_pipeline  # noqa: E402
from src.signals.store import SignalStore  # noqa: E402
from src.utils.logging import setup_logging  # noqa: E402

logger = structlog.get_logger("scripts.morning_signal")

_DIRECTION_EMOJI = {
    Direction.BULLISH: "📈",
    Direction.BEARISH: "📉",
    Direction.NEUTRAL: "➖",
}

_E = escape_markdown


def _consensus_entry_band(signal: DailySignal) -> tuple[Decimal, Decimal]:
    """Mean of the agreeing models' quoted entry-premium bands.

    Mirrors ``record_signal_outcome._consensus_entry_premium`` — the band shown
    to the operator is the average of every agreeing model's low / high, not a
    single model's quote.

    Args:
        signal: A directional (non-``NO_TRADE``) ``DailySignal``.

    Returns:
        ``(low, high)`` — both ``Decimal``, quantized to 2dp.
    """
    lows = [r.entry_premium_low for r in signal.responses if r.provider in signal.agreeing_models]
    highs = [r.entry_premium_high for r in signal.responses if r.provider in signal.agreeing_models]
    if not lows:  # a directional signal always has agreeing models — defensive only
        return (Decimal("0"), Decimal("0"))
    return (
        mean(lows).quantize(Decimal("0.01")),
        mean(highs).quantize(Decimal("0.01")),
    )


def _format_usd(value: Decimal) -> str:
    """Render a small USD amount as ``$X.XXXX`` (4dp, ``$`` prefix).

    ``format_money`` is INR-only (``₹`` prefix, 2dp) and unfit for the sub-cent
    LLM-call costs (~1e-3 USD) shown here, so this local helper is used instead.

    Args:
        value: USD amount. Quantized to 4dp for display.

    Returns:
        e.g. ``"$0.0042"``.
    """
    return f"${value.quantize(Decimal('0.0001')):.4f}"


def _format_signal_notification(
    signal: DailySignal,
    n_providers: int,
    day_cost: Decimal = Decimal("0"),
    n_priced: int = 0,
) -> str:
    """Render the consensus signal as MarkdownV2-ready Telegram message text.

    Vertical layout agreed with Animesh 2026-09-08 (reference renderer
    ``format_directional_v3``). This formatter owns its escaping — every dynamic
    part is escaped per value and literal ``*`` is emitted for bold — so the
    caller sends the result WITHOUT re-wrapping it in ``escape_markdown``.

    Args:
        signal: The aggregated ``DailySignal`` for the session.
        n_providers: Providers dispatched — the ``0 / N`` count in the
            pipeline-failure variant.
        day_cost: Summed OpenRouter USD cost of today's priced responses.
        n_priced: Count of today's responses that carried a usage/cost object.

    Returns:
        Fully-escaped message text. One of three variants: a directional
        consensus block, a no-consensus block (one line per model vote), or a
        pipeline-failure alert when no provider responded. Every variant ends
        with a ``💵 LLM cost`` line.
    """
    plural = "" if n_priced == 1 else "s"
    cost_line = _E(f"💵 LLM cost: {_format_usd(day_cost)} ({n_priced} call{plural})")

    if not signal.is_actionable:
        if not signal.responses:
            return (
                f"*{_E('🚨 SIGNAL PIPELINE FAILED')}*\n"
                f"\n"
                f"{_E(f'❌ 0 / {n_providers} models responded')}\n"
                f"{_E('⏸ No signal issued today')}\n"
                f"\n"
                f"{_E('👉 Check logs before the next run')}\n"
                f"{cost_line}"
            )
        votes = "\n".join(
            _E(f"{_DIRECTION_EMOJI[r.direction]} {r.provider}: {r.direction.value}")
            for r in signal.responses
        )
        return f"*{_E('⏸ NO TRADE · NO CONSENSUS')}*\n\n{votes}\n{cost_line}"

    emoji = _DIRECTION_EMOJI[signal.consensus_direction]
    if signal.entry_premium is not None:
        entry_line = f"💰 Entry: {format_money(signal.entry_premium)}"
    else:
        band_low, band_high = _consensus_entry_band(signal)
        entry_line = f"💰 Entry band: {format_money(band_low)} – {format_money(band_high)}"

    agree = ", ".join(signal.agreeing_models) or "—"
    dissent = ", ".join(signal.dissenting_models) or "—"
    return (
        f"*{_E(f'{emoji} CONSENSUS: {signal.consensus_direction.value}')}*\n"
        f"\n"
        f"{_E(f'🎯 Strike: {format_strike(signal.recommended_strike)}')}\n"
        f"{_E(f'📊 Confidence: {signal.consensus_confidence:.1f} / 5.0')}\n"
        f"{_E(entry_line)}\n"
        f"\n"
        f"*{_E('Model Votes:')}*\n"
        f"{_E(f'👍 Agree: {agree}')}\n"
        f"{_E(f'👎 Dissent: {dissent}')}\n"
        f"{cost_line}"
    )


async def run() -> None:
    """Execute the full morning signal pipeline once."""
    if guard_trading_day(logger, "morning_signal"):
        return

    broker = create_client(settings.upstox_env)
    store = SignalStore(settings.db_path)
    await asyncio.to_thread(store.init_db)

    result = await run_morning_signal_pipeline(broker, store, bod_path=DEFAULT_BOD_PATH)

    notifier = build_notifier()
    if notifier:
        msg = _format_signal_notification(
            result.signal, result.n_providers, result.day_cost_usd, result.n_priced
        )
        await notifier.send(msg)


if __name__ == "__main__":
    setup_logging()
    asyncio.run(run())
