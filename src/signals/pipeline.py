"""Morning signal pipeline body — extracted from ``scripts/morning_signal.py`` (SEC-4).

Everything from assembling the ``MarketSnapshot`` through persisting the
``DailySignal`` and the SPT-6 paper-entry tail-call. No Telegram, no
``setup_logging`` — those stay cron-boundary concerns in the script.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import structlog

from src.client.protocol import BrokerClient
from src.config import settings
from src.market_calendar import market_today
from src.paper.store import PaperStore
from src.signals.factory import build_aggregator, build_providers
from src.signals.models import DailySignal, MarketSnapshot
from src.signals.option_resolver import resolve_monthly_option
from src.signals.snapshot import assemble_market_snapshot
from src.signals.store import SignalStore
from src.strategy.signal_track_v1 import open_signal_paper_entry

logger = structlog.get_logger("scripts.morning_signal")


@dataclass(frozen=True)
class MorningSignalResult:
    """Everything the script needs to render its Telegram notification.

    Attributes:
        signal: The aggregated consensus ``DailySignal``.
        snapshot: The ``MarketSnapshot`` the signal was built from.
        n_providers: Providers dispatched (the ``0 / N`` count on failure).
        day_cost_usd: Summed OpenRouter USD cost of today's priced responses.
        n_priced: Count of today's responses that carried a usage/cost object.
    """

    signal: DailySignal
    snapshot: MarketSnapshot
    n_providers: int
    day_cost_usd: Decimal
    n_priced: int


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


async def run_morning_signal_pipeline(
    broker: BrokerClient,
    store: SignalStore,
    *,
    bod_path: Path,
) -> MorningSignalResult:
    """Assemble, aggregate, persist, and paper-enter one day's signal.

    Args:
        broker: Authenticated broker client (Upstox in practice).
        store: The shared ``SignalStore``, already initialized.
        bod_path: Beginning-of-day instrument file, for monthly-expiry
            resolution (``resolve_monthly_option`` and the SPT-6 tail-call).

    Returns:
        A ``MorningSignalResult`` carrying everything the caller needs to
        render its Telegram notification.
    """
    trade_date = market_today()
    providers = build_providers()

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

    day_cost = sum((r.usage.cost_usd for r in valid if r.usage is not None), Decimal("0"))
    n_priced = sum(1 for r in valid if r.usage is not None)
    logger.info(
        "morning_signal.llm_cost",
        day_cost_usd=str(day_cost),
        n_priced=n_priced,
        n_responses=len(valid),
    )

    signal = build_aggregator().aggregate(snapshot, valid)

    if signal.is_actionable:
        try:
            option_key = await asyncio.to_thread(resolve_monthly_option, signal, bod_path)
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

    try:
        paper_store = PaperStore(settings.db_path)
        await open_signal_paper_entry(signal, snapshot, broker, paper_store)
    except Exception as exc:  # noqa: BLE001 -- Intentional: isolate paper entry at cron boundary; the advisory pipeline must still complete
        logger.warning(
            "morning_signal.paper_entry_failed",
            error=str(exc),
        )

    logger.info(
        "morning_signal_complete",
        trade_date=trade_date.isoformat(),
        n_responses=len(valid),
        consensus_direction=signal.consensus_direction.value,
        trade_action=signal.trade_action.value,
        confidence=str(signal.consensus_confidence),
        agreeing_models=signal.agreeing_models,
    )

    return MorningSignalResult(
        signal=signal,
        snapshot=snapshot,
        n_providers=len(providers),
        day_cost_usd=day_cost,
        n_priced=n_priced,
    )
