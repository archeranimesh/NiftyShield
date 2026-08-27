"""Nuvama options portfolio reader.

Pure functions for parsing NetPosition() API responses and building portfolio
summaries for F&O Options.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation

import structlog

from src.nuvama.models import NuvamaOptionPosition, NuvamaOptionsSummary

logger = structlog.get_logger(__name__)


def parse_options_positions(raw_response: str) -> list[NuvamaOptionPosition]:
    """Parse NetPosition() JSON and return a list of NuvamaOptionPosition objects."""
    data = json.loads(raw_response)

    resp = data.get("resp")
    if not isinstance(resp, dict):
        # Nuvama returns {"resp": ""} when the F&O position book is empty
        # (no open or same-day-closed options positions). This is a normal
        # flat-book state, not an error — Holdings() still works on the same session.
        logger.info("NetPosition() returned non-dict resp=%r. No options positions.", resp)
        return []

    try:
        raw_records = resp["data"]["pos"]
    except KeyError:
        logger.warning("NetPosition() response missing 'resp.data.pos'. Returning empty list.")
        return []

    positions: list[NuvamaOptionPosition] = []

    for rec in raw_records:
        if rec.get("asTyp") != "OPTIDX" and rec.get("asTyp") != "OPTSTK":
            continue

        try:
            nt_qty = int(rec.get("ntQty", "0"))

            # If quantity is 0, the position is fully squared off. We STILL want to capture it
            # because its rlzPL is important to add to our daily realized amount.

            # Determine average price
            if nt_qty < 0:
                avg_price = Decimal(str(rec.get("cfAvgSlPrc", "0")))
                if avg_price == 0:
                    avg_price = Decimal(str(rec.get("avgSlPrc", "0")))
            elif nt_qty > 0:
                avg_price = Decimal(str(rec.get("cfAvgByPrc", "0")))
                if avg_price == 0:
                    avg_price = Decimal(str(rec.get("avgByPrc", "0")))
            else:
                # Flat position, doesn't matter, just take any
                avg_price = Decimal("0")

            dp_name = rec.get("dpName", "")
            exp_dt = rec.get("dpExpDt", "")
            op_typ = rec.get("opTyp", "")
            stk_prc = rec.get("stkPrc", "")
            instrument_name = f"{dp_name} {exp_dt} {op_typ} {stk_prc}".strip().replace("'", "")

            pos = NuvamaOptionPosition(
                trade_symbol=rec["trdSym"],
                instrument_name=instrument_name,
                net_qty=nt_qty,
                avg_price=avg_price,
                ltp=Decimal(str(rec.get("ltp", "0"))),
                unrealized_pnl=Decimal(str(rec.get("urlzPL", "0"))),
                realized_pnl_today=Decimal(str(rec.get("rlzPL", "0"))),
            )
            positions.append(pos)
        except (KeyError, ValueError, InvalidOperation) as exc:
            logger.warning("Skipping malformed options record %r: %s", rec.get("trdSym"), exc)

    return positions


def build_options_summary(
    positions: list[NuvamaOptionPosition],
    snapshot_date: date,
    cumulative_realized_pnl_map: dict[str, Decimal],
    monthly_historical_pnl: Decimal = Decimal("0"),
    intraday_high: Decimal | None = None,
    intraday_low: Decimal | None = None,
    nifty_high: float | None = None,
    nifty_low: float | None = None,
) -> NuvamaOptionsSummary:
    """Aggregate a list of options positions into a NuvamaOptionsSummary.

    Args:
        positions: Live option positions from the API.
        snapshot_date: Date of the snapshot.
        cumulative_realized_pnl_map: All-time realized P&L per symbol from the store.
        monthly_historical_pnl: Stored EOD realized P&L for calendar month rows
            *before* today (from NuvamaStore.get_monthly_realized_pnl). Today's
            realized (from live API) is added here to produce the monthly total.
        intraday_high: Session unrealized P&L high-water mark.
        intraday_low: Session unrealized P&L low-water mark.
        nifty_high: Nifty index session high.
        nifty_low: Nifty index session low.
    """
    total_unrealized = sum((p.unrealized_pnl for p in positions), Decimal("0"))
    total_realized_today = sum((p.realized_pnl_today for p in positions), Decimal("0"))

    total_cumulative_realized = sum(cumulative_realized_pnl_map.values(), Decimal("0"))

    monthly_realized = monthly_historical_pnl + total_realized_today

    return NuvamaOptionsSummary(
        snapshot_date=snapshot_date,
        positions=tuple(positions),
        total_unrealized_pnl=total_unrealized,
        total_realized_pnl_today=total_realized_today,
        monthly_realized_pnl=monthly_realized,
        cumulative_realized_pnl=total_cumulative_realized,
        intraday_high=intraday_high,
        intraday_low=intraday_low,
        nifty_high=nifty_high,
        nifty_low=nifty_low,
    )
