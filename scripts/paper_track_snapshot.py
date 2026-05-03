#!/usr/bin/env python3
"""CLI script for generating the daily snapshot report for the 3 Nifty Long tracks."""

import argparse
import asyncio
from datetime import date
from decimal import Decimal
import os
from pathlib import Path
import sys

# Ensure src/ is in PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.client.upstox_market import UpstoxMarketClient
from src.instruments.lookup import InstrumentLookup
from src.notifications.telegram import TelegramNotifier
from src.paper.store import PaperStore
from src.paper.proxy_monitor import ProxyDeltaMonitor
from src.paper.track_snapshot import TrackPnL, generate_track_snapshot
from src.paper.metrics import compute_nee


# --- Overlay display helpers -------------------------------------------------

# Collar has two leg roles that merge into one display line.
_OVERLAY_LABELS: dict[str, str] = {
    "overlay_pp": "PP",
    "overlay_cc": "CC",
    "overlay_collar_put": "Collar",
    "overlay_collar_call": "Collar",
}

_BASE_LABELS: dict[str, str] = {
    "paper_nifty_spot": "NiftyBees",
    "paper_nifty_futures": "Futures",
    "paper_nifty_proxy": "Proxy (DITM CE)",
}


def _fmt(value: Decimal) -> str:
    """Format a Decimal as a signed, comma-separated integer string."""
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:,.0f}"


def _hedge_verdict(base: Decimal, overlay_total: Decimal) -> str:
    """Return the emoji + text verdict for the hedge effectiveness line."""
    if base < 0:
        if overlay_total > 0:
            absorbed_pct = abs(overlay_total) / abs(base) * 100
            if abs(base + overlay_total) < abs(base):
                return f"✅ Protected ({absorbed_pct:.0f}% absorbed)"
            return f"⚠️ Partial ({absorbed_pct:.0f}% absorbed)"
        return "❌ No protection"
    # base >= 0
    if overlay_total < 0:
        return "⚠️ Cost (overlay drag on up-move)"
    return "✅ Protected"


def _format_pnl_block(track_name: str, pnl: TrackPnL) -> list[str]:
    """Build the 🛡 Hedge block lines for a track's PnL.

    Groups overlay_collar_put + overlay_collar_call into a single Collar line.
    Falls back to a plain base-only line when no overlays are present.
    """
    base_label = _BASE_LABELS.get(track_name, "Base")
    lines: list[str] = []

    # Merge overlay legs by display name (collar_put + collar_call → Collar).
    grouped: dict[str, Decimal] = {}
    for role, amount in pnl.overlay_pnls.items():
        label = _OVERLAY_LABELS.get(role, role)
        grouped[label] = grouped.get(label, Decimal("0")) + amount

    if not grouped:
        lines.append(f"  Base ({base_label}):  {_fmt(pnl.base_pnl)}")
        return lines

    overlay_names = " + ".join(grouped)
    overlay_total = sum(grouped.values())

    lines.append(f"  🛡 Hedge ({overlay_names})")
    lines.append(f"    {base_label:<22} {_fmt(pnl.base_pnl)}")
    for label, amount in grouped.items():
        lines.append(f"    {label:<22} {_fmt(amount)}")
    lines.append(f"    {'─' * 35}")
    verdict = _hedge_verdict(pnl.base_pnl, overlay_total)
    lines.append(f"    {'Net':<22} {_fmt(pnl.net_pnl)}  {verdict}")

    return lines


class MockBrokerClientDryRun:
    async def get_ltp(self, keys): return {k: 100.0 for k in keys}
    async def get_option_chain(self, u, e): return {"data": []}

class MockNotifier:
    async def send_message(self, text): print(f"[MOCK TELEGRAM] {text}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Daily 3-Track Comparison Snapshot")
    parser.add_argument(
        "--date", 
        type=str, 
        default=date.today().isoformat(),
        help="Date of the snapshot (YYYY-MM-DD)."
    )
    parser.add_argument(
        "--underlying-price", 
        type=float, 
        required=True,
        help="Current Nifty 50 spot price."
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true", 
        help="Generate report without saving nav snapshot to DB."
    )
    args = parser.parse_args()

    snapshot_date = date.fromisoformat(args.date)
    nifty_spot = Decimal(str(args.underlying_price))
    LOT_SIZE = 65  # Nifty 50, effective January 2026 — verify before each entry cycle.
    nee = compute_nee(nifty_spot, LOT_SIZE)

    store = PaperStore(Path("data/portfolio/portfolio.sqlite"))
    try:
        broker = UpstoxMarketClient()
    except ValueError:
        if args.dry_run:
            print("WARNING: UPSTOX_ANALYTICS_TOKEN not set. Using MockBrokerClient for dry run.")
            broker = MockBrokerClientDryRun()
        else:
            raise
    lookup = InstrumentLookup.from_file(Path("data/instruments/NSE.json.gz"))
    proxy_monitor = ProxyDeltaMonitor(store)
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if bot_token and chat_id:
        notifier = TelegramNotifier(bot_token, chat_id)
    else:
        notifier = MockNotifier()

    tracks = [
        "paper_nifty_spot",
        "paper_nifty_futures",
        "paper_nifty_proxy"
    ]

    print(f"\n--- Nifty 3-Track Snapshot for {snapshot_date} ---")
    print(f"Nifty Spot: {nifty_spot:.2f} | Notional Equivalent Exposure: ₹{nee:,.2f}")
    print("-" * 75)

    track_results = []
    
    for track_name in tracks:
        # Determine if we should pass the proxy monitor
        monitor = proxy_monitor if track_name == "paper_nifty_proxy" else None
        
        snapshot = await generate_track_snapshot(
            store=store,
            broker=broker,
            lookup=lookup,
            track_namespace=track_name,
            nifty_spot=nifty_spot,
            nee=nee,
            snapshot_date=snapshot_date,
            proxy_monitor=monitor
        )
        
        track_results.append(snapshot)
        
        # Save snapshot to DB if not dry run
        if not args.dry_run and snapshot.pnl.net_pnl != Decimal("0"):
            from src.paper.models import PaperNavSnapshot
            db_snap = PaperNavSnapshot(
                strategy_name=track_name,
                snapshot_date=snapshot_date,
                unrealized_pnl=snapshot.pnl.unrealized_pnl,
                realized_pnl=snapshot.pnl.realized_pnl,
                total_pnl=snapshot.pnl.net_pnl,
                underlying_price=nifty_spot
            )
            store.record_nav_snapshot(db_snap)

        # Print output
        print(f"\n[{track_name.upper()}]")
        for line in _format_pnl_block(track_name, snapshot.pnl):
            print(line)
        print(f"  GREEKS : Δ={snapshot.greeks.net_delta:.2f} | Θ={snapshot.greeks.net_theta:.2f} | V={snapshot.greeks.net_vega:.2f}")
        print(f"  METRICS: Max DD={snapshot.max_drawdown_pct:.2f}% (₹{snapshot.max_drawdown_abs:,.2f}) | Ret/NEE={snapshot.return_on_nee:.2f}%")
        
        if track_name == "paper_nifty_proxy" and snapshot.proxy_delta_alert:
            print(f"  ALERT  : Proxy Delta State -> {snapshot.proxy_delta_alert}")
            if "CRITICAL" in snapshot.proxy_delta_alert:
                await notifier.send_message(f"🚨 **CRITICAL**: Proxy Delta Monitor triggered: {snapshot.proxy_delta_alert}\nDelta: {snapshot.greeks.net_delta:.2f}")

    print("\n" + "-" * 75)
    print("Snapshot Generation Complete.")


if __name__ == "__main__":
    asyncio.run(main())
