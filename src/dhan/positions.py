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
    """Keep only NSE_FNO INTRADAY positions.

    Args:
        positions: Full list from parse_option_positions.

    Returns:
        Subset where exchangeSegment == 'NSE_FNO' and productType == 'INTRADAY'.
    """
    return [
        p
        for p in positions
        if p.exchange_segment == "NSE_FNO" and p.product_type == "INTRADAY"
    ]


def build_options_summary(
    positions: list[DhanOptionPosition],
    ts: datetime,
) -> DhanOptionsSummary:
    """Aggregate a list of filtered intraday positions into a summary.

    Args:
        positions: Already-filtered list (NSE_FNO INTRADAY only).
        ts: UTC timestamp of the snapshot.

    Returns:
        DhanOptionsSummary with summed P&L and position count.
    """
    realized = sum((p.realized_pnl for p in positions), Decimal("0"))
    unrealized = sum((p.unrealized_pnl for p in positions), Decimal("0"))
    return DhanOptionsSummary(
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        total_pnl=realized + unrealized,
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


def format_options_section(summary: DhanOptionsSummary, month_pnl: Decimal) -> str:
    """Format Dhan Options summary as an HTML Telegram message section.

    The unrealized P&L line is omitted when zero — for strictly intraday
    trading that is the expected state at 3:45 PM. A non-zero unrealized
    signals a position not squared off (auto-square-off or oversight);
    the ⚠️ prefix makes this unambiguous without requiring the reader to
    remember the convention.

    Args:
        summary: Aggregated DhanOptionsSummary for today.
        month_pnl: Calendar-month realized P&L from DhanStore.get_monthly_realized_pnl.

    Returns:
        HTML-formatted string for Telegram (parse_mode=HTML).
    """
    lines = [
        "📊 <b>Dhan Options (Intraday)</b>",
        f"Today P&amp;L:  <b>{summary.realized_pnl:+,.0f}</b>",
        f"Month P&amp;L:  <b>{month_pnl:+,.0f}</b>",
        f"Positions:  {summary.position_count:d}",
    ]
    if summary.unrealized_pnl != Decimal("0"):
        lines.append(f"⚠️ Unrealized: <b>{summary.unrealized_pnl:+,.0f}</b>")
    return "\n".join(lines)
