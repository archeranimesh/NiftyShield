"""Nuvama bond portfolio reader.

Pure functions for parsing Holdings() API responses and building portfolio
summaries. All I/O-bound operations are isolated to fetch_nuvama_portfolio().

Key design decisions (see DECISIONS.md — Nuvama Integration):
- Cost basis comes from the seeded nuvama_positions table, not the API.
- Day-change delta is derived from chgP field (no prior snapshot needed).
- All holdings classified as BOND; excluded ISINs skipped silently.
- LTP sourced inline from Holdings() — no Upstox enrichment required.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from src.nuvama.models import NuvamaBondHolding, NuvamaBondSummary

logger = logging.getLogger(__name__)

# ISINs already tracked by other systems (e.g. strategy legs, Dhan reader).
# Holdings with these ISINs are silently skipped to prevent double-counting.
_EXCLUDE_ISINS: frozenset[str] = frozenset(
    [
        "INF732E01037",  # LIQUIDBEES — tracked in finideas_ilts strategy
    ]
)

_TWO_DP = Decimal("0.01")


def parse_bond_holdings(
    raw_response: str,
    positions: dict[str, Decimal],
    exclude_isins: frozenset[str] | None = None,
) -> list[NuvamaBondHolding]:
    """Parse Holdings() JSON and return a list of NuvamaBondHolding objects.

    Pure function — no I/O. Joins each record with the positions dict to
    attach avg_price. Records missing from positions are skipped with a
    WARNING so the snapshot is not silently wrong.

    Args:
        raw_response: JSON string returned by api.Holdings().
        positions: ISIN → avg_price mapping loaded from nuvama_positions table.
        exclude_isins: ISINs to skip (merged with module-level _EXCLUDE_ISINS).

    Returns:
        List of NuvamaBondHolding instances, one per accepted rmsHdg record.

    Raises:
        json.JSONDecodeError: If raw_response is not valid JSON.
        KeyError: If expected response structure is entirely absent.
    """
    data = json.loads(raw_response)
    raw_records = _extract_rms_hdg(data)

    skip = _EXCLUDE_ISINS | (exclude_isins or frozenset())
    holdings: list[NuvamaBondHolding] = []

    for rec in raw_records:
        isin = rec.get("isin", "").strip()
        if not isin:
            logger.warning("Skipping rmsHdg record with missing isin: %r", rec)
            continue
        if isin in skip:
            logger.debug("Skipping excluded ISIN %s", isin)
            continue

        avg_price = positions.get(isin)
        if avg_price is None:
            logger.warning(
                "No cost basis found for ISIN %s (%s) — skipping. "
                "Run seed_nuvama_positions.py to add it.",
                isin,
                rec.get("cpName", "?").strip(),
            )
            continue

        try:
            holding = NuvamaBondHolding(
                isin=isin,
                company_name=rec["cpName"].strip(),
                trading_symbol=rec.get("dpName", "").strip(),
                exchange=rec.get("exc", "").strip(),
                qty=int(rec["totalQty"]),
                avg_price=Decimal(str(avg_price)),
                ltp=Decimal(str(rec["ltp"])),
                chg_pct=Decimal(str(rec["chgP"])),
                hair_cut=Decimal(str(rec.get("hairCut", "0"))),
            )
        except (KeyError, ValueError, InvalidOperation) as exc:
            logger.warning("Skipping malformed rmsHdg record %r: %s", isin, exc)
            continue

        holdings.append(holding)

    return holdings


def build_nuvama_summary(
    holdings: list[NuvamaBondHolding],
    snapshot_date: date,
) -> NuvamaBondSummary:
    """Aggregate a list of holdings into a NuvamaBondSummary.

    Pure function — no I/O.

    Args:
        holdings: Parsed NuvamaBondHolding list (may be empty).
        snapshot_date: The date this summary represents.

    Returns:
        NuvamaBondSummary with totals computed from holdings.
    """
    total_value = sum((h.current_value for h in holdings), Decimal("0"))
    total_basis = sum((h.cost_basis for h in holdings), Decimal("0"))
    total_pnl = total_value - total_basis
    total_day_delta = sum((h.day_delta for h in holdings), Decimal("0"))

    total_pnl_pct: Decimal | None = None
    if total_basis > 0:
        total_pnl_pct = (total_pnl / total_basis * 100).quantize(
            _TWO_DP, rounding="ROUND_HALF_UP"
        )

    return NuvamaBondSummary(
        snapshot_date=snapshot_date,
        holdings=tuple(holdings),
        total_value=total_value,
        total_basis=total_basis,
        total_pnl=total_pnl,
        total_pnl_pct=total_pnl_pct,
        total_day_delta=total_day_delta,
    )


def fetch_nuvama_portfolio(
    api: Any,
    positions: dict[str, Decimal],
    snapshot_date: date,
    exclude_isins: frozenset[str] | None = None,
) -> NuvamaBondSummary:
    """Fetch Nuvama holdings, parse, and build portfolio summary.

    This is the only I/O-bound function in this module. Caller is responsible
    for wrapping in try/except (see daily_snapshot.py non-fatal pattern).

    Args:
        api: Initialized APIConnect instance (from load_api_connect()).
        positions: ISIN → avg_price mapping (from NuvamaStore.get_positions()).
        snapshot_date: Date for the summary.
        exclude_isins: Additional ISINs to skip beyond the module default.

    Returns:
        NuvamaBondSummary (may have empty holdings if none pass filters).

    Raises:
        json.JSONDecodeError: On malformed API response.
        Exception: Propagates any APIConnect errors to caller.
    """
    raw = api.Holdings()
    holdings = parse_bond_holdings(raw, positions, exclude_isins)

    if not holdings:
        logger.info("No Nuvama bond holdings after filtering — returning empty summary.")

    return build_nuvama_summary(holdings, snapshot_date)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_rms_hdg(data: dict) -> list[dict]:
    """Extract the rmsHdg list from a Holdings() response dict.

    Tries the primary path first (resp.data.rmsHdg), falls back to the
    legacy eq.data.rmsHdg path used in earlier API versions.

    Args:
        data: Parsed JSON dict from Holdings() response.

    Returns:
        List of raw holding record dicts (may be empty).

    Raises:
        KeyError: If neither response path yields a valid rmsHdg list.
    """
    try:
        return data["resp"]["data"]["rmsHdg"]
    except KeyError:
        pass

    fallback = data.get("eq", {}).get("data", {}).get("rmsHdg")
    if fallback is not None:
        return fallback

    raise KeyError(
        "Holdings() response has neither 'resp.data.rmsHdg' nor 'eq.data.rmsHdg'. "
        f"Top-level keys: {list(data.keys())}"
    )
