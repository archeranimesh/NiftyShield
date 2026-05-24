"""Dhan intraday options position fetching, parsing, and formatting.

All parsers are pure functions — no I/O except the two HTTP callers
(fetch_positions_raw, fetch_fund_limit_raw). Callers decide whether to
filter and what to persist.

Decimal conversion rule: always Decimal(str(v)) — never Decimal(v) directly
from a Dhan float, which introduces binary floating-point error.

API note: Dhan's /v2/fundlimit response uses 'availabelBalance' (missing an 'l')
— a known Dhan API bug. The parser maps it explicitly; tests confirm the spelling.
"""

from __future__ import annotations

import re

from datetime import datetime
from decimal import Decimal
from typing import Any

import requests

from src.dhan.models import DhanFundLimit, DhanOptionPosition, DhanOptionsSummary
from src.dhan.reader import DHAN_API_BASE, _build_headers


# ── HTTP callers ──────────────────────────────────────────────────────────────


def fetch_positions_raw(client_id: str, access_token: str) -> list[dict[str, Any]]:
    """Fetch raw position data from Dhan GET /v2/positions.

    Args:
        client_id: Dhan client ID.
        access_token: JWT access token (24h expiry).

    Returns:
        List of raw position dicts from the API.

    Raises:
        requests.HTTPError: On non-2xx response.
    """
    url = f"{DHAN_API_BASE}/positions"
    headers = _build_headers(client_id, access_token)
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return data
    return data.get("data", data.get("positions", []))


def fetch_fund_limit_raw(client_id: str, access_token: str) -> dict[str, Any]:
    """Fetch raw fund/margin data from Dhan GET /v2/fundlimit.

    Args:
        client_id: Dhan client ID.
        access_token: JWT access token (24h expiry).

    Returns:
        Raw fund limit dict from the API.

    Raises:
        requests.HTTPError: On non-2xx response.
    """
    url = f"{DHAN_API_BASE}/fundlimit"
    headers = _build_headers(client_id, access_token)
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()


# ── Parsers ───────────────────────────────────────────────────────────────────


def parse_option_positions(raw: list[dict[str, Any]]) -> list[DhanOptionPosition]:
    """Map raw Dhan position dicts to DhanOptionPosition objects.

    Does NOT filter by segment or product type — caller decides what to keep.
    Decimal(str(v)) is used for all float fields to avoid binary FP error.

    Args:
        raw: List of raw position dicts from fetch_positions_raw.

    Returns:
        List of DhanOptionPosition (same length as raw).
    """
    return [
        DhanOptionPosition(
            security_id=str(r["securityId"]),
            trading_symbol=str(r["tradingSymbol"]),
            exchange_segment=str(r["exchangeSegment"]),
            product_type=str(r["productType"]),
            position_type=str(r["positionType"]),
            buy_qty=int(r["buyQty"]),
            sell_qty=int(r["sellQty"]),
            net_qty=int(r["netQty"]),
            buy_avg=Decimal(str(r["buyAvg"])),
            sell_avg=Decimal(str(r["sellAvg"])),
            realized_pnl=Decimal(str(r["realizedProfit"])),
            unrealized_pnl=Decimal(str(r["unrealizedProfit"])),
        )
        for r in raw
    ]


def filter_intraday_options(
    positions: list[DhanOptionPosition],
) -> list[DhanOptionPosition]:
    """Keep only NSE_FNO option positions (INTRADAY or NORMAL product type).

    Both INTRADAY (MIS) and MARGIN (NRML) product types are included because
    MARGIN orders on NSE_FNO are used for same-day intraday trades — the user
    squares off manually before close rather than relying on Dhan auto-square-off.
    Dhan's UI labels these "Normal" but the API returns productType="MARGIN".
    NSE_EQ and other segments are always excluded.

    Args:
        positions: Full list from parse_option_positions.

    Returns:
        Subset where exchangeSegment == 'NSE_FNO' and productType in
        ('INTRADAY', 'MARGIN').
    """
    return [
        p
        for p in positions
        if p.exchange_segment == "NSE_FNO"
        and p.product_type in ("INTRADAY", "MARGIN")
    ]


def _parse_strike_from_symbol(symbol: str) -> Decimal:
    """Parse the strike price from a trading symbol.

    Examples:
        'NIFTY-May2026-23750-PE' -> Decimal('23750')
        'NIFTY2550523500CE' -> Decimal('23500')
    """
    # Try hyphenated format first (e.g. NIFTY-May2026-23750-PE)
    match = re.search(r"-(\d+(?:\.\d+)?)-(?:CE|PE)", symbol, re.IGNORECASE)
    if match:
        return Decimal(match.group(1))

    # Try NSE standard format (e.g. NIFTY2550523500CE)
    match = re.search(r"(\d+(?:\.\d+)?)(?:CE|PE)", symbol, re.IGNORECASE)
    if match:
        digits = match.group(1)
        if len(digits) >= 8:
            digits = digits[5:]
        return Decimal(digits)

    return Decimal("0")


def compute_charges(
    positions: list[DhanOptionPosition],
    trade_count: int,
    is_itm_expiry: bool = False,
) -> tuple[Decimal, Decimal]:
    """Compute statutory charges and brokerage for a list of positions.

    Inputs are list[DhanOptionPosition] — turnover is derived from buy/sell
    quantities and average prices.

    Rates (NSE F&O):
        exchange_charges = 0.000530 × total_turnover
        sebi_charges     = 0.000010 × total_turnover
        stamp_duty       = 0.000030 × buy_turnover (buy side only)
        stt              = 0.001000 × sell_turnover (Budget 2024 rate, sell side only)
                           If is_itm_expiry is True and option is ITM (held to expiry, net_qty > 0),
                           STT is 0.001250 × strike × net_qty (exercised value).
        gst              = 0.18 × (brokerage + exchange_charges + sebi_charges)

    Rounding: all intermediate values Decimal, final results rounded to 2dp
    with ROUND_HALF_UP.

    Args:
        positions: List of intraday option positions.
        trade_count: Number of executed orders (used for ₹20/order brokerage).
        is_itm_expiry: Whether the positions are expired in-the-money.

    Returns:
        (total_charges, brokerage) as Decimals.
    """
    from src.dhan.models import _TWO_DP

    buy_turnover = sum((p.buy_qty * p.buy_avg for p in positions), Decimal("0"))
    sell_turnover = sum((p.sell_qty * p.sell_avg for p in positions), Decimal("0"))
    total_turnover = buy_turnover + sell_turnover

    brokerage = Decimal("20") * trade_count
    exchange_charges = Decimal("0.000530") * total_turnover
    sebi_charges = Decimal("0.000010") * total_turnover
    stamp_duty = Decimal("0.000030") * buy_turnover
    
    # 1. Standard STT on premium for sell trades
    stt = Decimal("0.001000") * sell_turnover
    
    # 2. Additional STT for ITM expiry: if option is exercised (net_qty > 0)
    if is_itm_expiry:
        for p in positions:
            if p.net_qty > 0:
                strike = _parse_strike_from_symbol(p.trading_symbol)
                stt += Decimal("0.001250") * strike * p.net_qty

    gst = Decimal("0.18") * (brokerage + exchange_charges + sebi_charges)

    total_charges = exchange_charges + sebi_charges + stamp_duty + stt + gst

    return (
        total_charges.quantize(_TWO_DP, rounding="ROUND_HALF_UP"),
        brokerage.quantize(_TWO_DP, rounding="ROUND_HALF_UP"),
    )


def build_options_summary(
    positions: list[DhanOptionPosition],
    ts: datetime,
    trade_count: int = 0,
    is_itm_expiry: bool = False,
) -> DhanOptionsSummary:
    """Aggregate a list of filtered intraday positions into a summary.

    Args:
        positions: Already-filtered list (NSE_FNO INTRADAY only).
        ts: UTC timestamp of the snapshot.
        trade_count: Number of executed orders for brokerage calculation.
        is_itm_expiry: Whether the positions are expired in-the-money.

    Returns:
        DhanOptionsSummary with summed P&L, charges, and position count.
    """
    realized = sum((p.realized_pnl for p in positions), Decimal("0"))
    unrealized = sum((p.unrealized_pnl for p in positions), Decimal("0"))
    charges, brokerage = compute_charges(positions, trade_count, is_itm_expiry=is_itm_expiry)

    return DhanOptionsSummary(
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        total_pnl=realized + unrealized,
        charges=charges,
        brokerage=brokerage,
        position_count=len(positions),
        snapshot_ts=ts,
    )


def parse_fund_limit(raw: dict[str, Any], ts: datetime) -> DhanFundLimit:
    """Map raw Dhan fund limit dict to DhanFundLimit.

    Note: Dhan's API uses 'availabelBalance' (sic — missing an 'l'). This is
    a known Dhan API bug; the mapping here is intentional and tested.

    Args:
        raw: Raw dict from fetch_fund_limit_raw.
        ts: UTC timestamp of the fetch.

    Returns:
        DhanFundLimit with all monetary fields as Decimal.
    """
    return DhanFundLimit(
        available_balance=Decimal(str(raw["availabelBalance"])),  # sic: Dhan typo
        utilized_amount=Decimal(str(raw["utilizedAmount"])),
        collateral_amount=Decimal(str(raw["collateralAmount"])),
        withdrawable_balance=Decimal(str(raw["withdrawableBalance"])),
        snapshot_ts=ts,
    )


# ── Telegram formatter ────────────────────────────────────────────────────────


def format_options_section(
    summary: DhanOptionsSummary,
    month_pnl: Decimal,
    month_charges: Decimal,
    month_brokerage: Decimal,
) -> str:
    """Format Dhan Options summary as a plain-text Telegram message section.

    The output is plain text — no HTML markup — because send() in
    TelegramNotifier wraps the entire message in a <pre> block and
    HTML-escapes the content before sending. Inline HTML tags inside
    <pre> are not rendered by Telegram clients anyway.

    The unrealized P&L line is omitted when zero — for strictly intraday
    trading that is the expected state at 3:45 PM. A non-zero unrealized
    signals a position not squared off (auto-square-off or oversight);
    the ⚠️ prefix makes this unambiguous without requiring the reader to
    remember the convention.

    Args:
        summary: Aggregated DhanOptionsSummary for today.
        month_pnl: Calendar-month realized P&L.
        month_charges: Calendar-month total statutory charges.
        month_brokerage: Calendar-month total brokerage.

    Returns:
        Plain-text string ready for embedding in the combined Telegram message.
    """
    today_cost = summary.charges + summary.brokerage
    month_cost = month_charges + month_brokerage

    lines = [
        "📊 Dhan Options (Intraday)",
        f"Today P&L:    {summary.realized_pnl:+,.0f}  gross",
        f"Today Cost:   {-today_cost:,.0f}  (chg: {-summary.charges:,.0f}  brk: {-summary.brokerage:,.0f})",
        f"Today Net:    {summary.net_pnl:+,.0f}",
        f"Month P&L:    {month_pnl:+,.0f}  gross",
        f"Month Cost:   {-month_cost:,.0f}  (chg: {-month_charges:,.0f}  brk: {-month_brokerage:,.0f})",
        f"Month Net:    {month_pnl - month_cost:+,.0f}",
        f"Positions:   {summary.position_count:d}",
    ]
    if summary.unrealized_pnl != Decimal("0"):
        lines.append(f"⚠️ Unrealized: {summary.unrealized_pnl:+,.0f}")
    return "\n".join(lines)
