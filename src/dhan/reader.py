"""Dhan portfolio reader — fetch holdings, LTP, classify, build summary.

Fetches live holdings from the Dhan API (GET /v2/holdings), retrieves
current prices via the Dhan market quote API (POST /v2/marketfeed/ltp),
classifies each holding as Equity or Bond, and builds a
DhanPortfolioSummary ready for the daily snapshot formatter.

All functions except the two HTTP callers are pure — no I/O, no side effects.
Tests can call them directly with fixture data.

Usage (integration):
    from src.dhan.reader import fetch_dhan_portfolio

    summary = fetch_dhan_portfolio(
        client_id=client_id,
        access_token=access_token,
        snapshot_date=date.today(),
        exclude_isins={"INF754K01LE1", "INF732E01037"},  # already tracked
    )
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import requests

from src.dhan.models import DhanHolding, DhanPortfolioSummary

logger = logging.getLogger(__name__)

DHAN_API_BASE = "https://api.dhan.co/v2"

_TWO_DP = Decimal("0.01")

# ── Classification config ────────────────────────────────────────
# Bond classification: tradingSymbol → "BOND" if listed here.
# Everything else defaults to "EQUITY".
# This is instrument *metadata* (what kind of asset), not position data.
# Update when a new bond/liquid instrument is added to the Dhan portfolio.
_BOND_SYMBOLS: frozenset[str] = frozenset({
    "LIQUIDCASE",
    "LIQUIDBEES",
    "LIQUIDIETF",
    "CASHIETF",
    "LIQUIDADD",
    "LIQUIDSHRI",
})


# ── HTTP callers (I/O) ──────────────────────────────────────────


def _build_headers(client_id: str, access_token: str) -> dict[str, str]:
    """Build HTTP headers for Dhan API calls.

    Args:
        client_id: Dhan client ID.
        access_token: JWT access token.

    Returns:
        Headers dict with access-token, client-id, and Content-Type.
    """
    return {
        "access-token": access_token,
        "client-id": client_id,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def fetch_holdings_raw(
    client_id: str, access_token: str
) -> list[dict[str, Any]]:
    """Fetch raw holdings from Dhan API.

    Args:
        client_id: Dhan client ID.
        access_token: JWT access token.

    Returns:
        List of holding dicts from the API.

    Raises:
        requests.HTTPError: On non-2xx response.
    """
    url = f"{DHAN_API_BASE}/holdings"
    headers = _build_headers(client_id, access_token)
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return data
    return data.get("data", data.get("holdings", []))


def fetch_ltp_raw(
    client_id: str,
    access_token: str,
    security_ids_by_exchange: dict[str, list[int]],
) -> dict[str, dict[str, dict[str, float]]]:
    """Fetch LTP from Dhan market quote API.

    Args:
        client_id: Dhan client ID.
        access_token: JWT access token.
        security_ids_by_exchange: e.g. {"NSE_EQ": [11536, 13611]}.

    Returns:
        Nested dict: {exchange: {security_id_str: {"last_price": float}}}.
        Empty dict on failure.

    Raises:
        requests.HTTPError: On non-2xx response.
    """
    url = f"{DHAN_API_BASE}/marketfeed/ltp"
    headers = _build_headers(client_id, access_token)
    resp = requests.post(url, headers=headers, json=security_ids_by_exchange, timeout=10)
    resp.raise_for_status()
    result = resp.json()
    return result.get("data", {})


# ── Pure functions (no I/O) ──────────────────────────────────────


def classify_holding(trading_symbol: str) -> str:
    """Classify a holding as EQUITY or BOND based on trading symbol.

    Args:
        trading_symbol: NSE trading symbol.

    Returns:
        'BOND' if the symbol is a known liquid/bond ETF, else 'EQUITY'.
    """
    return "BOND" if trading_symbol.strip().upper() in _BOND_SYMBOLS else "EQUITY"


def build_dhan_holdings(
    raw_holdings: list[dict[str, Any]],
    exclude_isins: set[str] | None = None,
) -> list[DhanHolding]:
    """Parse raw Dhan holdings into typed DhanHolding objects.

    Filters out holdings whose ISIN is in exclude_isins (already tracked
    by another system, e.g. finideas_ilts strategy).

    Args:
        raw_holdings: List of dicts from the Dhan holdings API.
        exclude_isins: ISINs to skip (prevents double-counting).

    Returns:
        List of DhanHolding objects (LTP=None — not yet enriched).
    """
    exclude = exclude_isins or set()
    result: list[DhanHolding] = []

    for h in raw_holdings:
        try:
            isin = h.get("isin", "").strip()
            if not isin:
                continue
            if isin in exclude:
                logger.debug("Skipping %s (ISIN %s) — already tracked", h.get("tradingSymbol"), isin)
                continue

            symbol = h.get("tradingSymbol", "UNKNOWN").strip()
            total_qty = int(h.get("totalQty", 0))
            if total_qty <= 0:
                continue  # zero or negative holdings — skip

            result.append(DhanHolding(
                trading_symbol=symbol,
                isin=isin,
                security_id=str(h.get("securityId", "")).strip(),
                exchange=h.get("exchange", "NSE_EQ").strip(),
                total_qty=total_qty,
                collateral_qty=int(h.get("collateralQty", 0)),
                avg_cost_price=Decimal(str(h.get("avgCostPrice", 0))),
                classification=classify_holding(symbol),
            ))
        except (AttributeError, TypeError, ValueError) as e:
            logger.warning("Skipping malformed Dhan holding: %s — %s", h, e)
            continue

    return result


def build_security_id_map(
    holdings: list[DhanHolding],
) -> dict[str, list[int]]:
    """Group security IDs by exchange for the marketfeed/ltp request.

    Args:
        holdings: List of DhanHolding objects.

    Returns:
        Dict like {"NSE_EQ": [11536, 13611]}.
    """
    exchange_map: dict[str, list[int]] = {}
    for h in holdings:
        if not h.security_id:
            continue
        try:
            sid = int(h.security_id)
        except ValueError:
            logger.warning("Non-numeric security_id for %s: %s", h.trading_symbol, h.security_id)
            continue
        exchange = h.exchange if h.exchange else "NSE_EQ"
        exchange_map.setdefault(exchange, []).append(sid)
    return exchange_map


def enrich_with_ltp(
    holdings: list[DhanHolding],
    ltp_data: dict[str, dict[str, dict[str, float]]],
) -> list[DhanHolding]:
    """Return new holdings with LTP populated from Dhan marketfeed response.

    NOTE: Dhan's marketfeed/ltp endpoint requires the paid Data API
    (₹499/month). Prefer enrich_with_upstox_prices() in production.

    Args:
        holdings: DhanHolding objects (ltp=None).
        ltp_data: Nested dict from fetch_ltp_raw:
            {exchange: {security_id_str: {"last_price": float}}}.

    Returns:
        New list of DhanHolding objects with ltp field populated.
        Holdings whose LTP is missing remain with ltp=None.
    """
    enriched: list[DhanHolding] = []
    for h in holdings:
        exchange = h.exchange if h.exchange else "NSE_EQ"
        exchange_data = ltp_data.get(exchange, {})
        price_data = exchange_data.get(str(h.security_id), {})
        last_price = price_data.get("last_price")

        if last_price is not None:
            new_h = DhanHolding(
                trading_symbol=h.trading_symbol,
                isin=h.isin,
                security_id=h.security_id,
                exchange=h.exchange,
                total_qty=h.total_qty,
                collateral_qty=h.collateral_qty,
                avg_cost_price=h.avg_cost_price,
                classification=h.classification,
                ltp=Decimal(str(last_price)),
            )
        else:
            logger.warning("No LTP for %s (security_id=%s)", h.trading_symbol, h.security_id)
            new_h = h
        enriched.append(new_h)
    return enriched


def enrich_with_upstox_prices(
    holdings: list[DhanHolding],
    prices: dict[str, float],
) -> list[DhanHolding]:
    """Return new holdings with LTP populated from an Upstox batch LTP dict.

    Derives the Upstox instrument key as NSE_EQ|{isin} for each holding —
    the same derivation used in the daily snapshot batch fetch. This avoids
    any dependency on Dhan's paid Data API (marketfeed/ltp).

    Args:
        holdings: DhanHolding objects (ltp=None).
        prices: Upstox batch LTP dict: {instrument_key: float}.

    Returns:
        New list of DhanHolding objects with ltp populated where available.
        Holdings with no matching Upstox key retain ltp=None.
    """
    enriched: list[DhanHolding] = []
    for h in holdings:
        upstox_key = f"NSE_EQ|{h.isin}"
        last_price = prices.get(upstox_key)

        if last_price is not None:
            new_h = DhanHolding(
                trading_symbol=h.trading_symbol,
                isin=h.isin,
                security_id=h.security_id,
                exchange=h.exchange,
                total_qty=h.total_qty,
                collateral_qty=h.collateral_qty,
                avg_cost_price=h.avg_cost_price,
                classification=h.classification,
                ltp=Decimal(str(last_price)),
            )
        else:
            logger.warning(
                "No Upstox LTP for %s (key=%s)", h.trading_symbol, upstox_key
            )
            new_h = h
        enriched.append(new_h)
    return enriched


def build_dhan_summary(
    holdings: list[DhanHolding],
    snapshot_date: date,
    prev_holdings: dict[str, DhanHolding] | None = None,
) -> DhanPortfolioSummary:
    """Split holdings into equity/bond, compute subtotals and day deltas.

    Pure function — no I/O.

    Args:
        holdings: Enriched DhanHolding objects (with LTP).
        snapshot_date: Date for the summary.
        prev_holdings: Previous day's holdings keyed by ISIN (for Δday).

    Returns:
        DhanPortfolioSummary with fully computed fields.
    """
    equity = [h for h in holdings if h.classification == "EQUITY"]
    bonds = [h for h in holdings if h.classification == "BOND"]

    def _subtotal(group: list[DhanHolding]) -> tuple[Decimal, Decimal, Decimal, Decimal | None]:
        value = sum((h.current_value or h.cost_basis for h in group), Decimal("0"))
        basis = sum((h.cost_basis for h in group), Decimal("0"))
        pnl = value - basis
        pnl_pct = (
            (pnl / basis * 100).quantize(_TWO_DP, ROUND_HALF_UP)
            if basis else None
        )
        return value, basis, pnl, pnl_pct

    eq_value, eq_basis, eq_pnl, eq_pnl_pct = _subtotal(equity)
    bd_value, bd_basis, bd_pnl, bd_pnl_pct = _subtotal(bonds)

    # Day-change deltas
    eq_day_delta: Decimal | None = None
    bd_day_delta: Decimal | None = None

    if prev_holdings:
        prev_eq_value = sum(
            (h.current_value or h.cost_basis for h in prev_holdings.values()
             if h.classification == "EQUITY"),
            Decimal("0"),
        )
        prev_bd_value = sum(
            (h.current_value or h.cost_basis for h in prev_holdings.values()
             if h.classification == "BOND"),
            Decimal("0"),
        )
        if prev_eq_value > 0 or eq_value > 0:
            eq_day_delta = eq_value - prev_eq_value
        if prev_bd_value > 0 or bd_value > 0:
            bd_day_delta = bd_value - prev_bd_value

    return DhanPortfolioSummary(
        snapshot_date=snapshot_date,
        equity_holdings=tuple(equity),
        equity_value=eq_value,
        equity_basis=eq_basis,
        equity_pnl=eq_pnl,
        equity_pnl_pct=eq_pnl_pct,
        bond_holdings=tuple(bonds),
        bond_value=bd_value,
        bond_basis=bd_basis,
        bond_pnl=bd_pnl,
        bond_pnl_pct=bd_pnl_pct,
        equity_day_delta=eq_day_delta,
        bond_day_delta=bd_day_delta,
    )


# ── High-level orchestrator ──────────────────────────────────────


def fetch_dhan_holdings(
    client_id: str,
    access_token: str,
    exclude_isins: set[str] | None = None,
) -> list[DhanHolding]:
    """Fetch and classify Dhan holdings (no LTP — call enrich_* after).

    Designed for use in daily_snapshot._async_main where the caller
    collects Upstox keys from these holdings and adds them to the batch
    LTP fetch, then calls enrich_with_upstox_prices().

    Args:
        client_id: Dhan client ID.
        access_token: Dhan JWT access token.
        exclude_isins: ISINs already tracked by strategy legs.

    Returns:
        List of DhanHolding objects with ltp=None.

    Raises:
        requests.HTTPError: On API failure (caller should catch).
    """
    raw = fetch_holdings_raw(client_id, access_token)
    return build_dhan_holdings(raw, exclude_isins)


def upstox_keys_for_holdings(holdings: list[DhanHolding]) -> set[str]:
    """Return the set of Upstox instrument keys needed to price these holdings.

    Args:
        holdings: DhanHolding objects (ltp=None).

    Returns:
        Set of keys in the form NSE_EQ|{isin}.
    """
    return {f"NSE_EQ|{h.isin}" for h in holdings}


def fetch_dhan_portfolio(
    client_id: str,
    access_token: str,
    snapshot_date: date,
    exclude_isins: set[str] | None = None,
    prev_holdings: dict[str, DhanHolding] | None = None,
    upstox_prices: dict[str, float] | None = None,
) -> DhanPortfolioSummary:
    """Fetch Dhan portfolio, enrich with LTP, classify, and build summary.

    Preferred usage: pass upstox_prices from the caller's existing batch
    LTP fetch (avoids Dhan's paid Data API). Falls back to Dhan's own
    marketfeed/ltp endpoint when upstox_prices is None (requires paid tier).

    Args:
        client_id: Dhan client ID.
        access_token: Dhan JWT access token.
        snapshot_date: Date for the summary.
        exclude_isins: ISINs already tracked by other systems.
        prev_holdings: Previous day's holdings for day-change deltas.
        upstox_prices: Pre-fetched Upstox batch LTP dict. When provided,
            Dhan's marketfeed/ltp is skipped entirely.

    Returns:
        Fully computed DhanPortfolioSummary.

    Raises:
        requests.HTTPError: On API failure (caller should catch).
    """
    # Step 1: Fetch holdings
    raw = fetch_holdings_raw(client_id, access_token)
    holdings = build_dhan_holdings(raw, exclude_isins)

    if not holdings:
        logger.info("No Dhan holdings to track (all filtered or empty)")
        return build_dhan_summary([], snapshot_date)

    # Step 2: Enrich with LTP — prefer Upstox prices, fall back to Dhan API
    if upstox_prices is not None:
        holdings = enrich_with_upstox_prices(holdings, upstox_prices)
    else:
        sec_id_map = build_security_id_map(holdings)
        if sec_id_map:
            ltp_data = fetch_ltp_raw(client_id, access_token, sec_id_map)
            holdings = enrich_with_ltp(holdings, ltp_data)

    # Step 3: Build summary
    return build_dhan_summary(holdings, snapshot_date, prev_holdings)
