from __future__ import annotations

from pathlib import Path

from src.instruments.lookup import InstrumentLookup
from src.signals.models import DailySignal, TradeAction

OPTION_TYPE = {TradeAction.BUY_CALL: "CE", TradeAction.BUY_PUT: "PE"}


def resolve_monthly_option(signal: DailySignal, bod_path: Path) -> str | None:
    """Resolve the recommended monthly option's instrument key from offline BOD.

    Returns ``None`` if the BOD is missing, the signal has no recommended strike,
    no monthly expiry candidate is found, or no exact option matches.
    """
    if not bod_path.exists() or signal.recommended_strike is None:
        return None

    opt_type = OPTION_TYPE.get(signal.trade_action)
    if opt_type is None:
        return None

    lookup = InstrumentLookup.from_file(bod_path)
    candidates = lookup.get_expiry_candidates(
        underlying="NIFTY", today=signal.trade_date, preference=["monthly"]
    )
    if not candidates:
        return None

    _, expiry = candidates[0]
    matches = lookup.search_options(
        underlying="NIFTY",
        strike=float(signal.recommended_strike),
        option_type=opt_type,
        expiry=expiry,
    )
    if not matches:
        return None

    return matches[0]["instrument_key"]
