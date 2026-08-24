#!/usr/bin/env python3
"""BUG-031 B031.4 — manual exit-eligibility review of open CC/PP/Collar overlay legs.

Read-only. Fetches the live option chain and runs the real (now-fixed)
CCOverlayV1/PPOverlayV1/CollarOverlayV1.check_signals() against every
currently-open STRATEGY_OVERLAY position, then prints whatever signals
would fire. Does NOT execute anything, does NOT write to the DB, does NOT
call the broker's order-placement endpoints — get_option_chain is a
read-only market-data call, same one StrategyMonitor's real tick uses.

Run this from the live host (needs real Upstox creds in .env + network
egress to api.upstox.com — this sandbox has neither).

Usage:
    python scratch/2026-08-24_bug031_manual_exit_review.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.client.factory import create_client  # noqa: E402
from src.client.upstox_market import parse_upstox_option_chain  # noqa: E402
from src.config import settings  # noqa: E402
from src.instruments.lookup import InstrumentLookup  # noqa: E402
from src.market_calendar.holidays import market_today  # noqa: E402
from src.paper.constants import STRATEGY_OVERLAY  # noqa: E402
from src.paper.store import PaperStore  # noqa: E402
from src.strategy.cc_overlay_v1 import CCOverlayV1  # noqa: E402
from src.strategy.collar_overlay_v1 import CollarOverlayV1  # noqa: E402
from src.strategy.pp_overlay_v1 import PPOverlayV1  # noqa: E402


async def main() -> int:
    store = PaperStore(db_path=settings.db_path)
    lookup = InstrumentLookup.from_file(Path(settings.bod_instruments_path))
    broker = create_client(settings.upstox_env)
    today = market_today()

    positions = store.get_positions(STRATEGY_OVERLAY)
    open_positions = [p for p in positions if p.net_qty != 0]

    if not open_positions:
        print("No open STRATEGY_OVERLAY positions. Nothing to review.")
        return 0

    print(f"Found {len(open_positions)} open overlay leg(s):\n")
    expiries: set = set()
    for p in open_positions:
        rec = lookup.get_by_key(p.instrument_key)
        expiry = rec["expiry"] if rec else None
        expiry_date = None
        if expiry is not None:
            from datetime import datetime, timezone

            expiry_date = datetime.fromtimestamp(expiry / 1000, tz=timezone.utc).date()
            expiries.add(expiry_date)
        dte = (expiry_date - today).days if expiry_date else None
        symbol = rec["trading_symbol"] if rec else "?"
        print(
            f"  {p.leg_role:22s} {p.instrument_key:16s} qty={p.net_qty:>5d} "
            f"entry={p.entry_date} dte={dte} {symbol}"
        )

    print("\nFetching live option chain(s)...")
    chains = {}
    for expiry_date in expiries:
        raw = await broker.get_option_chain("NSE_INDEX|Nifty 50", expiry_date.isoformat())
        chains[expiry_date] = parse_upstox_option_chain(raw if isinstance(raw, list) else [])

    def chain_for(pos) -> object:
        rec = lookup.get_by_key(pos.instrument_key)
        if rec is None:
            return next(iter(chains.values()))
        from datetime import datetime, timezone

        expiry_date = datetime.fromtimestamp(rec["expiry"] / 1000, tz=timezone.utc).date()
        return chains.get(expiry_date, next(iter(chains.values())))

    print("\n--- Exit-signal check (read-only, nothing executed) ---\n")
    strategies = [CCOverlayV1(), PPOverlayV1(), CollarOverlayV1()]
    any_signal = False
    for strategy in strategies:
        matching = [p for p in open_positions if p.strategy_name == strategy.strategy_name]
        if not matching:
            continue
        # Positions may span >1 expiry; group like StrategyMonitor._tick does.
        by_chain: dict = {}
        for p in matching:
            by_chain.setdefault(id(chain_for(p)), (chain_for(p), []))[1].append(p)
        for chain, group_positions in by_chain.values():
            events = await strategy.check_signals(chain, group_positions)
            if not events:
                continue
            any_signal = True
            print(f"[{type(strategy).__name__}]")
            for e in events:
                print(f"  {e.severity:6s} {e.event_type:20s} {e.description}")
                if e.payload:
                    print(f"         payload={e.payload}")
            print()

    if not any_signal:
        print("No exit signals fired for any open leg at current market levels.")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
