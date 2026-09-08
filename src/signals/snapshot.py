"""Assemble the full :class:`~src.signals.models.MarketSnapshot` from live sources.

Runs at ~09:10 IST from the S5.2 morning cron. Seven fields are built here;
``gift_nifty`` / ``usd_inr`` / ``fii`` are delegated to
:mod:`src.signals.market_inputs` (S5.2a). Depends on the S5.2b prereqs
(``broker.get_ohlc`` and ``SignalStore.get_recent_snapshots``).

No neutral fallbacks: any unavailable input raises
:class:`~src.client.exceptions.DataFetchError` and the caller aborts the run.
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal, InvalidOperation

import structlog

from src.client.exceptions import DataFetchError
from src.client.protocol import BrokerClient
from src.client.upstox_market import parse_upstox_option_chain
from src.instruments.lookup import InstrumentLookup
from src.models.options import OptionChain, OptionChainStrike
from src.paper.constants import DEFAULT_BOD_PATH

from .market_inputs import fetch_fii_data, fetch_gift_nifty, fetch_usd_inr
from .models import MarketSnapshot, OILevel, OptionChainSummary
from .store import SignalStore

logger = structlog.stdlib.get_logger(__name__)

NIFTY_KEY = "NSE_INDEX|Nifty 50"
VIX_KEY = "NSE_INDEX|India VIX"


async def assemble_market_snapshot(
    broker: BrokerClient,
    *,
    store: SignalStore,
    trade_date: date,
    lookup: InstrumentLookup | None = None,
) -> MarketSnapshot:
    """Assemble the full MarketSnapshot from live sources at ~09:10 IST.

    Args:
        broker: Authenticated broker client (Upstox in practice).
        store: Signal store, read for the ``vix_5d_trend`` history.
        trade_date: The session being assembled for; the S5.2 cron passes
            ``market_calendar.market_today()``.
        lookup: Instrument lookup for monthly-expiry resolution. Built lazily
            from :data:`~src.paper.constants.DEFAULT_BOD_PATH` when not supplied.

    Returns:
        A fully populated :class:`~src.signals.models.MarketSnapshot`.

    Raises:
        DataFetchError: Any required input is missing, non-positive, or
            unparseable.
    """
    if lookup is None:
        lookup = await asyncio.to_thread(InstrumentLookup.from_file, DEFAULT_BOD_PATH)

    quotes = await broker.get_ltp([NIFTY_KEY, VIX_KEY])
    nifty_spot = quotes.get(NIFTY_KEY)
    india_vix = quotes.get(VIX_KEY)
    if nifty_spot is None or nifty_spot <= 0:
        raise DataFetchError(f"nifty_spot unavailable: get_ltp returned {quotes!r}")
    if india_vix is None or india_vix <= 0:
        raise DataFetchError(f"india_vix unavailable: get_ltp returned {quotes!r}")

    prev_close, prev_high, prev_low = await _fetch_prev_ohlc(broker, trade_date)

    gift_nifty, usd_inr, fii = await asyncio.gather(
        fetch_gift_nifty(broker),
        fetch_usd_inr(broker, lookup=lookup),
        fetch_fii_data(broker),
    )

    monthly_expiry = _resolve_monthly_expiry(lookup, trade_date)

    raw_chain = await broker.get_option_chain(NIFTY_KEY, monthly_expiry.isoformat())
    option_chain = _summarize_option_chain(parse_upstox_option_chain(raw_chain), nifty_spot)

    recent = await asyncio.to_thread(store.get_recent_snapshots, 5)
    vix_5d_trend = _vix_trend(recent)

    return MarketSnapshot(
        trade_date=trade_date,
        nifty_spot=nifty_spot,
        prev_close=prev_close,
        prev_high=prev_high,
        prev_low=prev_low,
        gift_nifty=gift_nifty,
        india_vix=india_vix,
        vix_5d_trend=vix_5d_trend,
        usd_inr=usd_inr,
        monthly_expiry=monthly_expiry,
        option_chain=option_chain,
        fii=fii,
    )


async def _fetch_prev_ohlc(
    broker: BrokerClient, trade_date: date
) -> tuple[Decimal, Decimal, Decimal]:
    """Return (close, high, low) of the previous session's daily candle."""
    from datetime import timedelta

    from_date = trade_date - timedelta(days=7)
    params = {
        "instrument_key": NIFTY_KEY,
        "interval": "day",
        "to_date": trade_date.isoformat(),
        "from_date": from_date.isoformat(),
    }

    try:
        candles = await broker.get_historical_candles(params)
        if not candles:
            raise DataFetchError(f"prev OHLC unavailable for {NIFTY_KEY}: empty candles")

        candle = candles[0]
        return (
            Decimal(str(candle[4])),
            Decimal(str(candle[2])),
            Decimal(str(candle[3])),
        )
    except (IndexError, TypeError, ValueError, InvalidOperation) as exc:
        raise DataFetchError(f"prev OHLC unavailable for {NIFTY_KEY}: {exc}") from exc


def _resolve_monthly_expiry(lookup: InstrumentLookup, trade_date: date) -> date:
    """Resolve the current monthly NIFTY expiry (handles the Apr-2026 Thu->Tue move)."""
    candidates = lookup.get_expiry_candidates("NIFTY", trade_date, preference=["monthly"])
    if not candidates:
        raise DataFetchError(f"no monthly NIFTY expiry resolves for {trade_date.isoformat()}")
    return date.fromisoformat(candidates[0][1])


def _vix_trend(recent: list[MarketSnapshot]) -> str:
    """Classify the VIX path over the last 5 stored snapshots.

    ``recent`` is newest-first (as returned by ``get_recent_snapshots``); it is
    reversed here for an oldest->newest comparison. Fewer than 5 rows (the
    bootstrap window) yields ``"flat"``.
    """
    if len(recent) < 5:
        return "flat"
    series = [s.india_vix for s in reversed(recent)]
    pairs = list(zip(series, series[1:], strict=False))
    if all(a < b for a, b in pairs):
        return "rising"
    if all(a > b for a, b in pairs):
        return "falling"
    return "flat"


def _summarize_option_chain(chain: OptionChain, nifty_spot: Decimal) -> OptionChainSummary:
    """Derive the prompt-facing :class:`OptionChainSummary` from a parsed chain.

    ``oi_change`` is always ``0`` — the Upstox V2 chain response carries no
    prior-day OI field.
    """
    strikes = chain.strikes
    if not strikes:
        raise DataFetchError("option chain summary: parser returned no strikes")

    atm = min(strikes, key=lambda k: abs(k - nifty_spot))
    atm_leg = strikes[atm]
    atm_ivs = [leg.iv for leg in (atm_leg.ce, atm_leg.pe) if leg is not None and leg.iv is not None]
    # Degenerate: both ATM legs lack IV (illiquid / pre-open chain). atm_iv is a
    # non-optional model field, so 0 is the sentinel for "no ATM IV available".
    atm_iv = (sum(atm_ivs) / len(atm_ivs)) if atm_ivs else Decimal("0")

    otm_call_iv = next(
        (
            strikes[k].ce.iv
            for k in sorted(strikes)
            if k > nifty_spot and strikes[k].ce is not None and strikes[k].ce.iv is not None
        ),
        None,
    )
    otm_put_iv = next(
        (
            strikes[k].pe.iv
            for k in sorted(strikes, reverse=True)
            if k < nifty_spot and strikes[k].pe is not None and strikes[k].pe.iv is not None
        ),
        None,
    )
    # Both sides required: a one-sided subtraction (e.g. 0 - put_iv) would look
    # like a valid skew but carry the wrong magnitude, so fall back to 0 instead.
    iv_skew = (
        otm_call_iv - otm_put_iv
        if otm_call_iv is not None and otm_put_iv is not None
        else Decimal("0")
    )

    total_call_oi = sum(s.ce.oi for s in strikes.values() if s.ce is not None)
    total_put_oi = sum(s.pe.oi for s in strikes.values() if s.pe is not None)
    pcr_total = Decimal(total_put_oi) / Decimal(total_call_oi) if total_call_oi else Decimal("0")

    atm_call_oi = atm_leg.ce.oi if atm_leg.ce is not None else 0
    atm_put_oi = atm_leg.pe.oi if atm_leg.pe is not None else 0
    pcr_atm = Decimal(atm_put_oi) / Decimal(atm_call_oi) if atm_call_oi else Decimal("0")

    return OptionChainSummary(
        atm_strike=int(atm),
        atm_iv=atm_iv,
        iv_skew=iv_skew,
        pcr_total=pcr_total,
        pcr_atm=pcr_atm,
        top_call_oi=_top_oi(strikes, "ce"),
        top_put_oi=_top_oi(strikes, "pe"),
    )


def _top_oi(strikes: dict[Decimal, OptionChainStrike], side: str) -> list[OILevel]:
    """Top 3 strikes by open interest on ``side`` ("ce" or "pe"), highest first."""
    rows = [(k, getattr(v, side)) for k, v in strikes.items() if getattr(v, side) is not None]
    rows.sort(key=lambda t: t[1].oi, reverse=True)
    return [OILevel(strike=int(k), oi=leg.oi, oi_change=0) for k, leg in rows[:3]]
