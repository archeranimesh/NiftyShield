#!/usr/bin/env python3
"""BUG-031/B031.4 follow-up — close every open overlay_pp (Protective Put) leg.

Animesh's call (2026-08-24): close all open PP legs unconditionally, re-enter
fresh manually afterward. This does NOT go through StrategyMonitor's approval
flow (MONETIZE_PP) — it's a direct, one-off close, mirroring exactly what
PPOverlayV1._record_close_trade() writes (same TradeAction.SELL shape, same
notes convention), so the ledger stays consistent with how the system closes
PP legs everywhere else.

Safety:
  - DRY RUN by default — prints what it would close and at what price, writes
    nothing.
  - Pass --execute to actually write the closing SELL trades.
  - Uses the live LTP from the real option chain as the close price (falls
    back to avg_cost with a loud warning if a leg's LTP can't be found in the
    chain — never silently closes at 0).
  - Does not touch overlay_cc / overlay_collar_* legs — PP only, per the ask.
  - Does not call ReEntryMixin._check_reentry (no paper_exit_events row) —
    Animesh is re-entering by hand, not through auto-bootstrap, so that gate
    doesn't apply here.

Run this from the live host (needs real Upstox creds in .env + network
egress — this sandbox has neither).

Usage:
    python scratch/2026-08-24_close_all_pp_legs.py            # dry run
    python scratch/2026-08-24_close_all_pp_legs.py --execute  # actually closes
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.client.factory import create_client  # noqa: E402
from src.client.upstox_market import parse_upstox_option_chain  # noqa: E402
from src.config import settings  # noqa: E402
from src.instruments.lookup import InstrumentLookup  # noqa: E402
from src.market_calendar.holidays import market_today  # noqa: E402
from src.models.portfolio import TradeAction  # noqa: E402
from src.paper.constants import STRATEGY_OVERLAY  # noqa: E402
from src.paper.models import PaperTrade  # noqa: E402
from src.paper.store import PaperStore  # noqa: E402

# NOT importing PPOverlayV1.LONG_PUT_ROLES here deliberately — it's
# {"long_put", "protective_put", "pp_long_put"}, a stale pre-S2r constant
# that never matches the real production leg_role ("overlay_pp") written by
# paper_3track_overlay_entry.py's auto_pp_bootstrap(). Confirmed live
# 2026-08-24: PPOverlayV1.check_signals() silently evaluates ZERO real
# positions because of this filter, independent of and upstream of BUG-033's
# DTE-parsing bug. Filed as BUG-034. Using the real leg_role literal here so
# this script actually finds and closes the legs regardless of that bug.
_REAL_PP_LEG_ROLE = "overlay_pp"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually write the closing trades. Without this flag: dry run only.",
    )
    args = parser.parse_args()

    store = PaperStore(db_path=settings.db_path)
    lookup = InstrumentLookup.from_file(Path(settings.bod_instruments_path))
    broker = create_client(settings.upstox_env)
    today = market_today()

    positions = store.get_positions(STRATEGY_OVERLAY)
    pp_legs = [p for p in positions if p.leg_role == _REAL_PP_LEG_ROLE and p.net_qty > 0]

    if not pp_legs:
        print("No open overlay_pp legs. Nothing to close.")
        return 0

    print(f"Found {len(pp_legs)} open overlay_pp leg(s) to close:\n")

    # Resolve each leg's expiry via BOD so we can fetch the right chain(s).
    leg_info = []
    expiries: dict = {}  # date -> expiry_str for get_option_chain
    for pos in pp_legs:
        rec = lookup.get_by_key(pos.instrument_key)
        if rec is None:
            print(f"  WARNING: {pos.instrument_key} not found in BOD instruments — skipping.")
            continue
        expiry_date = datetime.fromtimestamp(rec["expiry"] / 1000, tz=timezone.utc).date()
        expiries[expiry_date] = expiry_date.isoformat()
        leg_info.append((pos, rec, expiry_date))

    print("Fetching live option chain(s)...")
    chains = {}
    for expiry_date, expiry_str in expiries.items():
        raw = await broker.get_option_chain("NSE_INDEX|Nifty 50", expiry_str)
        chains[expiry_date] = parse_upstox_option_chain(raw if isinstance(raw, list) else [])

    print("\n--- Close plan ---\n")
    to_close = []
    for pos, rec, expiry_date in leg_info:
        chain = chains.get(expiry_date)
        strike_key = Decimal(str(rec["strike_price"]))
        strike = chain.strikes.get(strike_key) if chain else None
        put_leg = strike.pe if strike is not None else None

        if put_leg is not None and put_leg.ltp is not None:
            close_price = put_leg.ltp
            price_source = "live LTP"
        else:
            close_price = pos.avg_cost
            price_source = "FALLBACK: avg_cost (live LTP unavailable)"

        pnl = (close_price - pos.avg_cost) * pos.net_qty
        to_close.append((pos, close_price))
        print(
            f"  {pos.instrument_key:14s} qty={pos.net_qty:>4d} entry_debit={pos.avg_cost} "
            f"close_price={close_price} ({price_source}) est_pnl={pnl}"
        )

    if not args.execute:
        print("\nDRY RUN — no trades written. Re-run with --execute to close these legs.")
        return 0

    print("\n--- Executing closes ---\n")
    for pos, close_price in to_close:
        trade = PaperTrade(
            strategy_name=pos.strategy_name,
            leg_role=pos.leg_role,
            instrument_key=pos.instrument_key,
            trade_date=today,
            action=TradeAction.SELL,
            quantity=abs(pos.net_qty),
            price=close_price,
            notes="manual close — BUG-031 B031.4, re-entering manually",
        )
        inserted = store.record_trade(trade)
        print(f"  {pos.instrument_key}: inserted={inserted}, closed at {close_price}")

    print("\nDone. Verify with the B031.4 review script or a direct get_positions() check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
