"""Diagnostic repro: why hasn't PROFIT_TARGET auto-closed paper_ic_nifty_v1_monthly?

Context (2026-07-20 Cowork session): "IC EOD Audit" showed combined mark ₹9.80
vs entry credit ₹32.40 (~70% captured, well past the 50% profit_target_pct gate),
yet monitor_daemon.log has zero PROFIT_TARGET / auto_execute_dispatched /
pending_approvals rows for this strategy today. entry_credit computed by hand
from paper_trades matches the audit's ₹32.40 exactly, and every leg resolves
cleanly via BOD in the log (leg_resolved_via_bod x4 per tick) — so neither the
trade data nor BOD resolution explains the silence.

This script re-runs the EXACT same live objects the daemon uses
(real UpstoxLiveClient, real PaperStore, real StrategyMonitor helper methods,
real IronCondorV1 instance) against the CURRENT live chain, and prints every
intermediate value on the path from "positions in DB" to "SignalEvent list" —
so whichever step silently drops the signal becomes visible.

Read-only. Makes live Upstox API calls (get_ltp / get_option_chain) but does
NOT call apply_action / place any order / write to paper_trades.

Run from repo root with the project's normal venv active:
    python -m scratch.2026-07-20_ic_v1_monthly_profit_target_repro
or:
    python scratch/2026-07-20_ic_v1_monthly_profit_target_repro.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running as a plain script (python scratch/foo.py) as well as -m.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.client.factory import create_client  # noqa: E402
from src.config import settings  # noqa: E402
from src.instruments.lookup import InstrumentLookup  # noqa: E402
from src.paper.store import PaperStore  # noqa: E402
from src.strategy.ic_expiry_config import CONFIGS  # noqa: E402
from src.strategy.ic_nifty_v1 import IronCondorV1  # noqa: E402
from src.strategy.monitor import StrategyMonitor  # noqa: E402

STRATEGY_NAME = "paper_ic_nifty_v1_monthly"
DB_PATH = "data/portfolio/portfolio.sqlite"
BOD_PATH = "data/instruments/NSE.json.gz"  # matches DEFAULT_BOD_PATH convention


class _NoOpNotifier:
    """Satisfies NotifierProtocol without touching Telegram."""

    async def send_plain_message(self, text: str) -> bool:
        print(f"[notifier.send_plain_message SUPPRESSED] {text}")
        return True

    async def send_approval_request(self, event, context_str: str) -> int | None:
        print(f"[notifier.send_approval_request SUPPRESSED] {event.event_type}")
        print(context_str)
        return None


def _section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


async def main() -> None:
    _section("0. Setup")
    env = settings.upstox_env or "prod"
    print(f"UPSTOX_ENV = {env!r}")
    broker = create_client(env)
    store = PaperStore(db_path=DB_PATH)
    try:
        lookup = InstrumentLookup.from_file(BOD_PATH)
        print(f"BOD lookup loaded from {BOD_PATH}")
    except Exception as exc:  # noqa: BLE001 - diagnostic script, want to see any failure
        lookup = None
        print(
            f"BOD lookup FAILED to load ({exc!r}) — expiry resolution will fall back to regex only"
        )

    config = CONFIGS["monthly"]
    strategy = IronCondorV1(broker=broker, store=store, notifier=_NoOpNotifier(), config=config)
    assert strategy.strategy_name == STRATEGY_NAME
    print(f"strategy.strategy_name = {strategy.strategy_name}")
    print(f"strategy.auto_execute  = {strategy.auto_execute}")
    print(f"config.profit_target_pct = {config.profit_target_pct}")
    print(f"config.loss_stop_pct     = {config.loss_stop_pct}")

    # Reuse StrategyMonitor's real expiry-resolution + chain-fetch logic —
    # instantiate it exactly as monitor_daemon.py does, but never call run()/​_tick()
    # so nothing gets dispatched or persisted.
    monitor = StrategyMonitor(
        broker=broker,
        store=store,
        notifier=_NoOpNotifier(),
        strategies=[strategy],
        lookup=lookup,
    )

    _section("1. Positions from DB (PaperStore.get_positions)")
    positions = store.get_positions(STRATEGY_NAME)
    if not positions:
        print("No open positions found — position may already be closed. Stopping.")
        return
    for pos in positions:
        print(
            f"  {pos.leg_role:16s} key={pos.instrument_key:16s} net_qty={pos.net_qty:>4} "
            f"avg_cost={pos.avg_cost} avg_sell_price={pos.avg_sell_price} "
            f"entry_date={pos.entry_date} option_type={pos.option_type}"
        )

    _section("2. Expiry resolution per leg (StrategyMonitor._get_position_expiry)")
    resolved_expiries = set()
    for pos in positions:
        exp = monitor._get_position_expiry(pos)  # noqa: SLF001 - diagnostic introspection
        resolved_expiries.add(exp)
        print(f"  {pos.leg_role:16s} key={pos.instrument_key:16s} -> expiry={exp}")
    if len(resolved_expiries) > 1:
        print(f"  !! WARNING: legs resolved to DIFFERENT expiries: {resolved_expiries}")
    if None in resolved_expiries:
        print(
            "  !! WARNING: at least one leg's expiry did not resolve — "
            "this leg group would fall into the daemon's 'first available chain' "
            "fallback path (monitor.py:159-161), which can silently hand check_signals "
            "the WRONG expiry's chain."
        )

    _section("3. Chain fetch (StrategyMonitor._fetch_chains) — LIVE API CALL")
    chains = await monitor._fetch_chains(positions)  # noqa: SLF001
    print(f"  chains fetched for expiries: {sorted(chains.keys())}")
    for exp_date, chain in chains.items():
        print(
            f"  expiry={exp_date}  underlying_spot={chain.underlying_spot}  "
            f"n_strikes={len(chain.strikes) if hasattr(chain, 'strikes') else 'n/a'}"
        )

    expiry_groups = monitor._group_positions_by_expiry(positions)  # noqa: SLF001
    if not expiry_groups:
        print(
            "  !! _group_positions_by_expiry returned EMPTY — daemon would use "
            "next(iter(chains)) as a blanket fallback for ALL positions regardless "
            "of their real expiry. This is the leading hypothesis for a silent "
            "wrong-chain assignment."
        )
        expiry_groups = {next(iter(chains)): positions} if chains else {}

    _section("4. Per-leg chain lookup as used INSIDE _compute_combined_pnl (strategy._find_leg)")
    for exp_date, grp_positions in expiry_groups.items():
        chain = chains.get(exp_date)
        print(
            f"  Using chain for expiry={exp_date} (spot={chain.underlying_spot if chain else 'N/A'})"
        )
        if chain is None:
            print(
                "  !! No chain available for this expiry group — check_signals will be SKIPPED "
                "for these legs entirely (monitor.py:164-170, 'no_chain_for_expiry')."
            )
            continue
        for pos in grp_positions:
            opt_leg = strategy._find_leg(chain, pos.instrument_key)  # noqa: SLF001
            if opt_leg is None:
                print(
                    f"    {pos.leg_role:16s} key={pos.instrument_key:16s} -> _find_leg returned None "
                    "(THIS leg would flip mark_available=False and suppress PROFIT_TARGET/LOSS_STOP entirely)"
                )
            else:
                print(
                    f"    {pos.leg_role:16s} key={pos.instrument_key:16s} -> "
                    f"ltp={opt_leg.ltp} delta={opt_leg.delta} strike={opt_leg.strike}"
                )

    _section("5. _compute_combined_pnl (the actual profit-target gate)")
    for exp_date, grp_positions in expiry_groups.items():
        chain = chains.get(exp_date)
        if chain is None:
            continue
        ic_positions = [p for p in grp_positions if p.strategy_name == STRATEGY_NAME]
        if not ic_positions:
            continue
        combined_mark, entry_credit = strategy._compute_combined_pnl(chain, ic_positions)  # noqa: SLF001
        print(f"  entry_credit  = {entry_credit}")
        print(f"  combined_mark = {combined_mark!r}")
        if combined_mark is None:
            print(
                "  !! combined_mark is None -> mark_available was False for at least one leg "
                "-> PROFIT_TARGET/LOSS_STOP guard at ic_nifty_v1.py:256 short-circuits, "
                "NO event emitted, NO log line, NO exception. This is the silent-failure mode."
            )
        elif entry_credit > 0:
            pct = combined_mark / entry_credit
            print(f"  pct (mark/credit) = {pct}")
            print(
                f"  profit_target_pct = {config.profit_target_pct}  "
                f"-> {'WOULD FIRE PROFIT_TARGET' if pct <= config.profit_target_pct else 'would NOT fire yet'}"
            )
        else:
            print("  !! entry_credit <= 0 -> guard at ic_nifty_v1.py:256 blocks both signals")

    _section("6. Full check_signals() output (ground truth — what the daemon actually sees)")
    for exp_date, grp_positions in expiry_groups.items():
        chain = chains.get(exp_date)
        if chain is None:
            continue
        events = await strategy.check_signals(chain, grp_positions)
        if not events:
            print(
                f"  expiry={exp_date}: [] (no events — matches today's log, but now we know WHY from step 5)"
            )
        for event in events:
            print(
                f"  expiry={exp_date}: {event.event_type} ({event.severity}) "
                f"auto_execute_in_payload={event.payload.get('auto_execute', False)}"
            )
            print(f"    {event.description}")

    _section("Done — no orders placed, no DB writes, no Telegram messages sent")


if __name__ == "__main__":
    asyncio.run(main())
