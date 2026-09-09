#!/usr/bin/env python3
"""Morning signal-pipeline cron script.

Cron: 15 9 * * 1-5

Pure orchestration: assemble the market snapshot, fan out to every configured
signal provider, aggregate their responses into one consensus DailySignal,
persist every stage, and send a one-line Telegram notification. All
data-source logic lives in ``assemble_market_snapshot`` — this script contains
none.
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
from src.market_calendar import is_trading_day, market_today  # noqa: E402
from src.notifications.formatting import format_money, format_strike  # noqa: E402
from src.notifications.markdown import escape_markdown  # noqa: E402
from src.notifications.telegram import build_notifier  # noqa: E402
from src.paper.constants import DEFAULT_BOD_PATH  # noqa: E402
from src.signals.factory import build_aggregator, build_providers  # noqa: E402
from src.signals.models import (  # noqa: E402
    DailySignal,
    Direction,
    MarketSnapshot,
    TradeAction,
)
from src.signals.option_resolver import resolve_monthly_option  # noqa: E402
from src.signals.snapshot import assemble_market_snapshot  # noqa: E402
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


def _format_signal_notification(signal: DailySignal, n_providers: int) -> str:
    """Render the consensus signal as MarkdownV2-ready Telegram message text.

    Vertical layout agreed with Animesh 2026-09-08 (reference renderer
    ``format_directional_v3``). This formatter owns its escaping — every dynamic
    part is escaped per value and literal ``*`` is emitted for bold — so the
    caller sends the result WITHOUT re-wrapping it in ``escape_markdown``.

    Args:
        signal: The aggregated ``DailySignal`` for the session.
        n_providers: Providers dispatched — the ``0 / N`` count in the
            pipeline-failure variant.

    Returns:
        Fully-escaped message text. One of three variants: a directional
        consensus block, a no-consensus block (one line per model vote), or a
        pipeline-failure alert when no provider responded.
    """
    if signal.trade_action is TradeAction.NO_TRADE:
        if not signal.responses:
            return (
                f"*{_E('🚨 SIGNAL PIPELINE FAILED')}*\n"
                f"\n"
                f"{_E(f'❌ 0 / {n_providers} models responded')}\n"
                f"{_E('⏸ No signal issued today')}\n"
                f"\n"
                f"{_E('👉 Check logs before the next run')}"
            )
        votes = "\n".join(
            _E(f"{_DIRECTION_EMOJI[r.direction]} {r.provider}: {r.direction.value}")
            for r in signal.responses
        )
        return f"*{_E('⏸ NO TRADE · NO CONSENSUS')}*\n\n{votes}"

    emoji = _DIRECTION_EMOJI[signal.consensus_direction]
    band_low, band_high = _consensus_entry_band(signal)
    agree = ", ".join(signal.agreeing_models) or "—"
    dissent = ", ".join(signal.dissenting_models) or "—"
    return (
        f"*{_E(f'{emoji} CONSENSUS: {signal.consensus_direction.value}')}*\n"
        f"\n"
        f"{_E(f'🎯 Strike: {format_strike(signal.recommended_strike)}')}\n"
        f"{_E(f'📊 Confidence: {signal.consensus_confidence:.1f} / 5.0')}\n"
        f"{_E(f'💰 Entry band: {format_money(band_low)} – {format_money(band_high)}')}\n"
        f"\n"
        f"*{_E('Model Votes:')}*\n"
        f"{_E(f'👍 Agree: {agree}')}\n"
        f"{_E(f'👎 Dissent: {dissent}')}"
    )


def _log_snapshot(snapshot: MarketSnapshot) -> None:
    """Log the scalar market context sent to every LLM.

    The strike-by-strike OI arrays are omitted — they are persisted in full to
    ``signal_inputs.snapshot_json``.
    """
    oc = snapshot.option_chain
    logger.info(
        "morning_signal.snapshot_assembled",
        nifty_spot=str(snapshot.nifty_spot),
        prev_close=str(snapshot.prev_close),
        prev_high=str(snapshot.prev_high),
        prev_low=str(snapshot.prev_low),
        gift_nifty=str(snapshot.gift_nifty),
        india_vix=str(snapshot.india_vix),
        vix_5d_trend=snapshot.vix_5d_trend,
        usd_inr=str(snapshot.usd_inr),
        monthly_expiry=snapshot.monthly_expiry.isoformat(),
        atm_strike=oc.atm_strike,
        atm_iv=str(oc.atm_iv),
        iv_skew=str(oc.iv_skew),
        pcr_total=str(oc.pcr_total),
        pcr_atm=str(oc.pcr_atm),
        fii_cash_net_cr=str(snapshot.fii.fii_cash_net_cr),
        dii_cash_net_cr=str(snapshot.fii.dii_cash_net_cr),
    )


async def run() -> None:
    """Execute the full morning signal pipeline once."""
    trade_date = market_today()
    if not is_trading_day(trade_date):
        logger.info("morning_signal.skip_non_trading_day", date=trade_date.isoformat())
        return

    providers = build_providers()
    broker = create_client(settings.upstox_env)
    store = SignalStore(settings.db_path)
    await asyncio.to_thread(store.init_db)

    snapshot = await assemble_market_snapshot(broker, store=store, trade_date=trade_date)
    await asyncio.to_thread(store.record_snapshot, snapshot)
    _log_snapshot(snapshot)

    logger.info(
        "morning_signal.providers_dispatched",
        providers=[p.__class__.__name__ for p in providers],
        count=len(providers),
    )
    responses = await asyncio.gather(
        *[p.get_signal(snapshot) for p in providers],
        return_exceptions=True,
    )

    valid = []
    for r in responses:
        if isinstance(r, Exception):
            logger.warning("morning_signal.provider_error", exc=str(r))
        else:
            await asyncio.to_thread(store.record_response, r)
            logger.info(
                "morning_signal.provider_response",
                provider=r.provider,
                direction=r.direction.value,
                confidence=r.confidence,
                recommended_strike=r.recommended_strike,
                premium_low=str(r.entry_premium_low),
                premium_high=str(r.entry_premium_high),
                key_reason=r.key_reason,
                key_risk=r.key_risk,
            )
            valid.append(r)

    if not valid:
        logger.warning(
            "morning_signal.no_valid_responses",
            dispatched=len(providers),
            errors=len(responses),
        )

    signal = build_aggregator().aggregate(snapshot, valid)

    if signal.trade_action is not TradeAction.NO_TRADE:
        try:
            option_key = await asyncio.to_thread(resolve_monthly_option, signal, DEFAULT_BOD_PATH)
            if option_key:
                ltps = await broker.get_ltp([option_key])
                if option_key in ltps:
                    entry_premium = ltps[option_key].quantize(Decimal("0.01"))
                    signal = signal.model_copy(update={"entry_premium": entry_premium})
                else:
                    logger.warning(
                        "morning_signal.ltp_missing_for_key",
                        option_key=option_key,
                    )
        except Exception as exc:  # noqa: BLE001 -- Intentional: isolate premium capture at cron boundary; pipeline must still record the signal
            logger.warning(
                "morning_signal.entry_premium_capture_failed",
                error=str(exc),
            )

    await asyncio.to_thread(store.record_signal, signal)

    notifier = build_notifier()
    if notifier:
        msg = _format_signal_notification(signal, len(providers))
        await notifier.send(msg)

    logger.info(
        "morning_signal_complete",
        trade_date=trade_date.isoformat(),
        n_responses=len(valid),
        consensus_direction=signal.consensus_direction.value,
        trade_action=signal.trade_action.value,
        confidence=str(signal.consensus_confidence),
        agreeing_models=signal.agreeing_models,
    )


if __name__ == "__main__":
    setup_logging()
    asyncio.run(run())
