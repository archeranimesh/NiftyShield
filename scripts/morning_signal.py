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
from pathlib import Path

import structlog
from dotenv import load_dotenv

# Path setup must happen before importing local src modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load environment before local imports
load_dotenv()

from src.client.factory import create_client  # noqa: E402
from src.config import settings  # noqa: E402
from src.market_calendar import market_today  # noqa: E402
from src.notifications.markdown import escape_markdown  # noqa: E402
from src.notifications.telegram import build_notifier  # noqa: E402
from src.signals.factory import build_aggregator, build_providers  # noqa: E402
from src.signals.models import (  # noqa: E402
    DailySignal,
    Direction,
    MarketSnapshot,
    TradeAction,
)
from src.signals.snapshot import assemble_market_snapshot  # noqa: E402
from src.signals.store import SignalStore  # noqa: E402
from src.utils.logging import setup_logging  # noqa: E402

logger = structlog.get_logger("scripts.morning_signal")

_DIRECTION_EMOJI = {
    Direction.BULLISH: "📈",
    Direction.BEARISH: "📉",
    Direction.NEUTRAL: "⏸",
}


def _format_signal_notification(signal: DailySignal) -> str:
    """Render the consensus signal as a MarkdownV2-safe Telegram message.

    Args:
        signal: The aggregated ``DailySignal`` for the session.

    Returns:
        Raw (un-escaped) message text — a two-line message for a directional
        trade (direction, mean confidence, strike, then agreeing/dissenting
        models), or a single-line "no trade" message listing each provider's
        vote. The caller escapes it for MarkdownV2 before sending.
    """
    if signal.trade_action is TradeAction.NO_TRADE:
        votes = ", ".join(f"{r.provider}: {r.direction.value}" for r in signal.responses)
        if votes:
            return f"⏸ NO TRADE — split signal ({votes})"
        return "⏸ NO TRADE — no responses"

    emoji = _DIRECTION_EMOJI[signal.consensus_direction]
    head = (
        f"{emoji} {signal.consensus_direction.value} — "
        f"confidence {signal.consensus_confidence:.1f} — "
        f"strike {signal.recommended_strike}"
    )
    agreed = ", ".join(signal.agreeing_models) or "—"
    dissented = ", ".join(signal.dissenting_models) or "—"
    tail = f"Agreed: {agreed}  |  Dissented: {dissented}"
    return f"{head}\n{tail}"


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
    await asyncio.to_thread(store.record_signal, signal)

    notifier = build_notifier()
    if notifier:
        msg = escape_markdown(_format_signal_notification(signal))
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
