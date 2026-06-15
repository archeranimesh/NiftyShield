#!/usr/bin/env python3
"""Persistent daemon process for NiftyShield paper trading.

Runs StrategyMonitor and TelegramGateway concurrently.
Handles SIGTERM signals to shut down cleanly by cancelling tasks,
expiring pending approvals in the DB, and writing a final heartbeat.

Cron requirements:
00 09 * * 1-5  python -m scripts.pre_market_brief
15 09 * * 1-5  python -m scripts.start_monitor
30 15 * * 1-5  python -m scripts.stop_monitor
35 15 * * 1-5  python -m scripts.eod_summary
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
from datetime import date
from pathlib import Path

import structlog
from dotenv import load_dotenv

# Path setup must happen before importing local src modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load environment before local imports
load_dotenv()

from src.client.factory import create_client  # noqa: E402
from src.client.upstox_market import parse_upstox_option_chain  # noqa: E402
from src.config import settings  # noqa: E402
from src.db import connect as _connect  # noqa: E402
from src.instruments.lookup import InstrumentLookup  # noqa: E402
from src.notifications.telegram_gateway import TelegramGateway  # noqa: E402
from src.paper.store import PaperStore  # noqa: E402
from src.strategy.executor import (  # noqa: E402
    PaperExecutor,
    PaperFillSimulator,
)
from src.strategy.monitor import StrategyMonitor  # noqa: E402
from src.strategy.protocol import ApprovedAction, LegSpec  # noqa: E402
from src.utils.logging import setup_logging  # noqa: E402

# Strategies (dynamic import to avoid failing if not yet implemented)
try:
    from src.strategy.csp_nifty_v1 import CSPNiftyV1  # noqa: E402
except ImportError:
    # Intentional: Ignore import errors for unimplemented strategies
    CSPNiftyV1 = None

try:
    from src.strategy.ic_nifty_v1 import IronCondorV1  # noqa: E402
except ImportError:
    # Intentional: Ignore import errors for unimplemented strategies
    IronCondorV1 = None

try:
    from src.strategy.nifty_track_comparison_v1 import (
        NiftyTrackComparisonV1,
    )  # noqa: E402
except ImportError:
    # Intentional: Ignore import errors for unimplemented strategies
    NiftyTrackComparisonV1 = None

try:
    from src.strategy.cc_overlay_v1 import CCOverlayV1  # noqa: E402
except ImportError:
    # Intentional: Ignore import errors for unimplemented strategies
    CCOverlayV1 = None

try:
    from src.strategy.pp_overlay_v1 import PPOverlayV1  # noqa: E402
except ImportError:
    # Intentional: Ignore import errors for unimplemented strategies
    PPOverlayV1 = None

try:
    from src.strategy.collar_overlay_v1 import CollarOverlayV1  # noqa: E402
except ImportError:
    # Intentional: Ignore import errors for unimplemented strategies
    CollarOverlayV1 = None

try:
    from src.strategy.overlay_closer import OverlayCloser  # noqa: E402
except ImportError:
    # Intentional: Ignore import errors for unimplemented strategies
    OverlayCloser = None

logger = structlog.get_logger("scripts.monitor_daemon")

# Intraday overlay monitoring gate — disabled by default in Phase 0
MONITOR_OVERLAYS: bool = os.getenv("MONITOR_OVERLAYS", "0") == "1"

# Overlay action types routed to OverlayCloser (not PaperExecutor)
_OVERLAY_ACTION_TYPES: frozenset[str] = frozenset(
    {"CLOSE_CC", "MONETIZE_PP", "CLOSE_CALL_ONLY", "MONETIZE_PUT", "CLOSE_ALL_OVERLAY"}
)

# Global task references for signal handling
monitor_task: asyncio.Task | None = None
gateway_task: asyncio.Task | None = None
store_ref: PaperStore | None = None
strategies_ref: list[str] = []
_shutdown_started: bool = False


async def shutdown():
    """Cancel background tasks, clean up DB, write heartbeat, and exit."""
    global _shutdown_started
    if _shutdown_started:
        logger.info("Shutdown already in progress, ignoring duplicate signal.")
        return
    _shutdown_started = True

    logger.info("Cancelling running tasks...")

    # 1. Cancel concurrent tasks
    if monitor_task and not monitor_task.done():
        monitor_task.cancel()
    if gateway_task and not gateway_task.done():
        gateway_task.cancel()

    # Wait for cancellation to propagate
    if monitor_task or gateway_task:
        try:
            await asyncio.gather(
                *(t for t in [monitor_task, gateway_task] if t is not None),
                return_exceptions=True,
            )
        except Exception:
            # Intentional: Ignore errors during task cancellation on shutdown
            pass

    # 2. Set all PENDING approvals to EXPIRED
    if store_ref:
        try:
            logger.info("Expiring all pending approvals...")
            await asyncio.to_thread(store_ref.expire_all_pending_approvals)
        except Exception as e:
            # Intentional: Isolate errors on shutdown database operations
            logger.warning(
                "Failed to expire pending approvals on shutdown",
                error=str(e),
            )

        # 3. Write final heartbeat with last_event="SHUTDOWN"
        try:
            logger.info("Writing final shutdown heartbeat...")
            await asyncio.to_thread(
                store_ref.write_heartbeat,
                os.getpid(),
                strategies_ref,
                "SHUTDOWN",
            )
        except Exception as e:
            # Intentional: Isolate errors on heartbeat writes during shutdown
            logger.warning(
                "Failed to write final heartbeat on shutdown",
                error=str(e),
            )

    logger.info("Shutdown complete. Exiting.")
    sys.exit(0)


async def main() -> int:
    global monitor_task, gateway_task, store_ref, strategies_ref

    desc = "Paper Trading Monitor Daemon"
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--db-path",
        default=settings.db_path,
        help="Path to the SQLite database file",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=90,
        help="Poll interval for strategy monitor in seconds",
    )
    args = parser.parse_args()

    logger.info("Starting Paper Trading Monitor Daemon", pid=os.getpid())

    # Build DB store
    store = PaperStore(args.db_path)
    store_ref = store

    # Build Telegram gateway
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing. " + "Exiting.")
        return 1

    gateway = TelegramGateway(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        db_path=str(store.db_path),
    )

    # Initialize broker client
    broker = create_client(settings.upstox_env)

    # Initialize InstrumentLookup for expiry date computation
    lookup = None
    try:
        bod_path = Path(settings.bod_instruments_path)
        if bod_path.exists():
            lookup = InstrumentLookup.from_file(bod_path)
    except Exception as e:
        # Intentional: Non-fatal initialization error fallback
        logger.warning(
            "Failed to load BOD instruments for expiry resolver",
            error=str(e),
        )

    def get_expiry() -> str:
        if lookup is not None:
            try:
                expiries = lookup.get_expiry_candidates(
                    "NIFTY",
                    date.today(),
                    ["monthly", "quarterly", "yearly"],
                )
                if expiries:
                    return expiries[0][1]
            except Exception:
                # Intentional: Safe fallback if candidate lookup fails
                pass
        return ""

    # Instantiate strategies (non-crashing)
    strategies = []

    if CSPNiftyV1 is not None:
        try:
            strategies.append(
                CSPNiftyV1(
                    broker=broker,
                    store=store,
                    notifier=gateway,
                )
            )
            logger.info("Registered CSPNiftyV1 strategy")
        except Exception as e:
            # Intentional: Safe strategy init guard
            logger.error("Failed to initialize CSPNiftyV1", error=str(e))
    else:
        logger.warning("CSPNiftyV1 module not found; skipping registration")

    if IronCondorV1 is not None:
        try:
            strategies.append(
                IronCondorV1(
                    broker=broker,
                    store=store,
                    notifier=gateway,
                )
            )
            logger.info("Registered IronCondorV1 strategy")
        except Exception as e:
            # Intentional: Safe strategy init guard
            logger.error("Failed to initialize IronCondorV1", error=str(e))
    else:
        logger.warning("IronCondorV1 module not found; skipping registration")

    if NiftyTrackComparisonV1 is not None:
        try:
            strategies.append(
                NiftyTrackComparisonV1(
                    broker=broker,
                    store=store,
                    notifier=gateway,
                )
            )
            logger.info("Registered NiftyTrackComparisonV1 strategy")
        except Exception as e:
            # Intentional: Safe strategy init guard
            logger.error(
                "Failed to initialize NiftyTrackComparisonV1",
                error=str(e),
            )
    else:
        logger.warning("NiftyTrackComparisonV1 module not found; " + "skipping registration")

    if MONITOR_OVERLAYS:
        logger.info("MONITOR_OVERLAYS=1 — registering overlay strategies")
        vix_data_dir = Path(settings.vix_data_dir) if settings.vix_data_dir else None
        overlay_kwargs = {"store": store, "notifier": gateway, "vix_data_dir": vix_data_dir}
        for overlay_cls, overlay_name in [
            (CCOverlayV1, "CCOverlayV1"),
            (PPOverlayV1, "PPOverlayV1"),
            (CollarOverlayV1, "CollarOverlayV1"),
        ]:
            if overlay_cls is not None:
                try:
                    strategies.append(overlay_cls(**overlay_kwargs))
                    logger.info("Registered overlay strategy", name=overlay_name)
                except Exception as e:
                    # Intentional: Safe overlay init guard
                    logger.error(
                        "Failed to initialize overlay strategy",
                        name=overlay_name,
                        error=str(e),
                    )
            else:
                logger.warning(
                    "Overlay module not found; skipping registration",
                    name=overlay_name,
                )
    else:
        logger.info("MONITOR_OVERLAYS=0 — overlay strategies disabled (Phase 0)")

    strategies_ref = [s.strategy_name for s in strategies]

    # Initialize StrategyMonitor
    monitor = StrategyMonitor(
        broker=broker,
        store=store,
        notifier=gateway,
        strategies=strategies,
        poll_interval_s=args.poll_interval,
        expiry_fn=get_expiry,
    )

    # Initialize PaperExecutor for resolving callbacks
    simulator = PaperFillSimulator()
    executor = PaperExecutor(
        store=store,
        simulator=simulator,
        db_path=str(store.db_path),
    )

    # Initialize OverlayCloser for overlay action routing
    overlay_closer = (
        OverlayCloser(store=store, simulator=simulator, notifier=gateway)
        if OverlayCloser is not None
        else None
    )

    # Define callbacks for Telegram long polling
    async def on_approved(telegram_msg_id: int, rank: int) -> None:
        logger.info(
            "Approval callback received",
            telegram_msg_id=telegram_msg_id,
            rank=rank,
        )

        row = await asyncio.to_thread(
            store.get_pending_approval_by_msg_id,
            telegram_msg_id,
        )
        if not row:
            logger.warning(
                "No pending approval found for Telegram message ID",
                telegram_msg_id=telegram_msg_id,
            )
            return

        approval_id = row["id"]
        strategy_name = row["strategy_name"]
        council_output = row["council_output"]

        try:
            await asyncio.to_thread(
                store.resolve_approval,
                approval_id,
                "APPROVED",
                rank,
            )
            logger.info(
                "Marked pending approval as APPROVED in DB",
                approval_id=approval_id,
                rank=rank,
            )
        except Exception as e:
            # Intentional: Isolate DB updates from Telegram event loop
            logger.error(
                "Failed to resolve approval in DB",
                approval_id=approval_id,
                error=str(e),
            )
            return

        # Reconstruct ApprovedAction
        try:
            data = council_output
            actions_list = data.get("actions", [])
            action_dict = next(
                (a for a in actions_list if a.get("council_rank") == rank),
                None,
            )
            if not action_dict:
                logger.error(
                    "Approved action rank not found in council output",
                    rank=rank,
                )
                return

            legs_to_open = [
                LegSpec(
                    instrument_key=leg.get("instrument_key", ""),
                    action=leg.get("action", "BUY"),
                    quantity=int(leg.get("quantity", 0)),
                    leg_role=leg.get("leg_role", ""),
                    notes=leg.get("notes", ""),
                )
                for leg in action_dict.get("legs_to_open", [])
            ]
            approved_action = ApprovedAction(
                action_type=action_dict.get("action_type", ""),
                legs_to_close=action_dict.get("legs_to_close", []),
                legs_to_open=legs_to_open,
                rationale=action_dict.get("rationale", ""),
                council_rank=rank,
            )
        except Exception as e:
            # Intentional: Isolate payload reconstruction errors
            logger.exception(
                "Failed to reconstruct approved action payload",
                error=str(e),
            )
            return

        # Fetch live option chain at execution time
        market = parse_upstox_option_chain([])
        try:
            expiry_str = get_expiry()
            if expiry_str:
                raw = await broker.get_option_chain(
                    "NSE_INDEX|Nifty 50",
                    expiry_str,
                )
                market = parse_upstox_option_chain(
                    raw if isinstance(raw, list) else [],
                )
        except Exception as e:
            # Intentional: Option chain fetching is non-fatal for fallback
            logger.warning(
                "Failed to fetch market chain; using empty chain fallback",
                error=str(e),
            )

        # Apply action — overlay types routed to OverlayCloser
        try:
            if approved_action.action_type in _OVERLAY_ACTION_TYPES and overlay_closer is not None:
                await asyncio.to_thread(
                    overlay_closer.route,
                    strategy_name=strategy_name,
                    action=approved_action,
                    market=market,
                    event_id=None,
                )
                logger.info(
                    "Successfully executed overlay action via OverlayCloser",
                    strategy_name=strategy_name,
                    action_type=approved_action.action_type,
                    approval_id=approval_id,
                )
            else:
                await asyncio.to_thread(
                    executor.apply,
                    strategy_name=strategy_name,
                    action=approved_action,
                    market=market,
                    approval_id=approval_id,
                )
                logger.info(
                    "Successfully executed approved action",
                    strategy_name=strategy_name,
                    approval_id=approval_id,
                )
        except Exception as e:
            # Intentional: Isolate execution errors from crashing the daemon
            logger.exception(
                "Failed to apply approved action",
                strategy_name=strategy_name,
                approval_id=approval_id,
                error=str(e),
            )

    async def on_rejected(telegram_msg_id: int) -> None:
        logger.info(
            "Rejection callback received",
            telegram_msg_id=telegram_msg_id,
        )

        def _get_pending_approval():
            with _connect(store.db_path) as conn:
                return conn.execute(
                    "SELECT id FROM pending_approvals "
                    "WHERE telegram_msg_id = ? AND status = 'PENDING'",
                    (telegram_msg_id,),
                ).fetchone()

        row = await asyncio.to_thread(_get_pending_approval)
        if not row:
            logger.warning(
                "No pending approval found for Telegram message ID",
                telegram_msg_id=telegram_msg_id,
            )
            return

        approval_id = row["id"]
        try:
            await asyncio.to_thread(
                store.resolve_approval,
                approval_id,
                "REJECTED",
            )
            logger.info(
                "Marked pending approval as REJECTED in DB",
                approval_id=approval_id,
            )
        except Exception as e:
            # Intentional: Isolate rejection database updates from polling
            logger.error(
                "Failed to resolve rejection in DB",
                approval_id=approval_id,
                error=str(e),
            )

    # Register signal handlers for SIGTERM and SIGINT
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: loop.create_task(shutdown()))

    # Start tasks
    monitor_task = asyncio.create_task(monitor.run())
    gateway_task = asyncio.create_task(
        gateway.start_polling(
            on_approved,
            on_rejected,
        )
    )

    logger.info("Tasks started. Running daemon...")
    try:
        await asyncio.gather(monitor_task, gateway_task)
    except asyncio.CancelledError:
        logger.info("Daemon execution cancelled.")
    except Exception as e:
        # Intentional: Capture and log top-level daemon exceptions
        logger.exception(
            "Unexpected error in daemon task execution",
            error=str(e),
        )
        return 1

    return 0


if __name__ == "__main__":
    setup_logging()
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
