"""Fetchers for the three :class:`~src.signals.models.MarketSnapshot` fields the
repo has no other source for: ``gift_nifty``, ``usd_inr``, and ``fii``.

Sources are spike-confirmed (2026-09-07) — see ``docs/plan/signals/signals_stories.md``
§S5.2a and ``scratch/2026-09-07_signal_input_sources.py``:

- ``gift_nifty`` → Upstox ``GLOBAL_INDEX|SGX NIFTY`` via ``broker.get_ltp``.
- ``usd_inr``    → Upstox nearest-monthly ``NCD_FO`` USDINR future via ``broker.get_ltp``.
- ``fii``        → NSE ``fiidiiTradeReact`` JSON (previous session, cash-market net).

Each helper returns the typed value or raises
:class:`~src.client.exceptions.DataFetchError` on total failure. There are **no
neutral fallbacks here** — the caller decides whether a missing input aborts the run.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from decimal import Decimal, InvalidOperation

import requests
import structlog

from src.client.exceptions import DataFetchError
from src.client.protocol import BrokerClient
from src.instruments.lookup import InstrumentLookup, parse_expiry
from src.paper.constants import DEFAULT_BOD_PATH

from .models import FIIData

logger = structlog.stdlib.get_logger(__name__)

GIFT_NIFTY_KEY = "GLOBAL_INDEX|SGX NIFTY"
_NSE_FII_DII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
_NSE_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


async def fetch_gift_nifty(broker: BrokerClient) -> Decimal:
    """Fetch the GIFT Nifty last-traded price.

    Args:
        broker: Authenticated broker client (Upstox in practice).

    Returns:
        GIFT Nifty LTP as a positive ``Decimal``.

    Raises:
        DataFetchError: The LTP dict is empty, the key is missing, or the value
            is not positive.
    """
    quotes = await broker.get_ltp([GIFT_NIFTY_KEY])
    ltp = quotes.get(GIFT_NIFTY_KEY)
    if ltp is None or ltp <= 0:
        raise DataFetchError(f"gift_nifty unavailable: get_ltp returned {quotes!r}")
    return ltp


async def fetch_usd_inr(broker: BrokerClient, *, lookup: InstrumentLookup | None = None) -> Decimal:
    """Fetch USD/INR from the nearest-monthly NCD_FO USDINR future.

    The monthly contract is liquid outside currency-market hours; weeklies return
    ``0.0`` and are excluded by taking the last expiry of the earliest live month.

    Args:
        broker: Authenticated broker client.
        lookup: Instrument lookup for expiry resolution. Built lazily from
            :data:`~src.paper.constants.DEFAULT_BOD_PATH` when not supplied.

    Returns:
        USD/INR future LTP as a positive ``Decimal``.

    Raises:
        DataFetchError: No live monthly contract resolves, or its LTP is missing
            or not positive.
    """
    if lookup is None:
        lookup = await asyncio.to_thread(InstrumentLookup.from_file, DEFAULT_BOD_PATH)

    key = _nearest_monthly_usdinr_key(lookup)
    if key is None:
        raise DataFetchError("usd_inr unavailable: no live monthly NCD_FO USDINR FUT")

    quotes = await broker.get_ltp([key])
    ltp = quotes.get(key)
    if ltp is None or ltp <= 0:
        raise DataFetchError(f"usd_inr unavailable: get_ltp({key}) returned {quotes!r}")
    return ltp


def _nearest_monthly_usdinr_key(lookup: InstrumentLookup) -> str | None:
    """Instrument key of the last-expiry USDINR future in the earliest live month."""
    futs = lookup.search("USDINR", segment="NCD_FO", instrument_type="FUT", max_results=50)
    today = dt.date.today()
    last_of_month: dict[tuple[int, int], tuple[dt.date, str]] = {}
    for fut in futs:
        exp_str = parse_expiry(fut.get("expiry"))
        key = fut.get("instrument_key")
        if not exp_str or not key:
            continue
        try:
            expiry = dt.date.fromisoformat(exp_str)
        except ValueError:
            continue
        if expiry < today:
            continue
        bucket = (expiry.year, expiry.month)
        if bucket not in last_of_month or expiry > last_of_month[bucket][0]:
            last_of_month[bucket] = (expiry, key)

    if not last_of_month:
        return None
    return last_of_month[min(last_of_month)][1]


async def fetch_fii_data(broker: BrokerClient) -> FIIData:
    """Fetch previous-session FII/DII cash-market net flows from NSE.

    Args:
        broker: Unused — kept for a uniform fetcher signature.

    Returns:
        :class:`~src.signals.models.FIIData` with FII and DII net values in ₹ cr.

    Raises:
        DataFetchError: The request fails, returns non-200, or the payload is
            missing a category or has an unparseable net value.
    """
    try:
        resp = await asyncio.to_thread(
            requests.get, _NSE_FII_DII_URL, headers=_NSE_HEADERS, timeout=15
        )
    except requests.RequestException as exc:
        raise DataFetchError(f"fii data fetch failed: {exc}") from exc

    if resp.status_code != 200:
        raise DataFetchError(f"fii data fetch failed: HTTP {resp.status_code}")

    try:
        rows = resp.json()
    except ValueError as exc:
        raise DataFetchError(f"fii data parse failed: {exc}") from exc

    if not isinstance(rows, list):
        raise DataFetchError(f"fii data unexpected shape: {type(rows).__name__}")

    by_category = {str(row.get("category", "")).upper(): row for row in rows}
    fii_row = by_category.get("FII/FPI")
    dii_row = by_category.get("DII")
    if fii_row is None or dii_row is None:
        raise DataFetchError(f"fii data missing a category: got {list(by_category)}")

    try:
        return FIIData(
            fii_cash_net_cr=Decimal(str(fii_row["netValue"])),
            dii_cash_net_cr=Decimal(str(dii_row["netValue"])),
        )
    except (KeyError, InvalidOperation, TypeError) as exc:
        raise DataFetchError(f"fii data net value unparseable: {exc}") from exc
