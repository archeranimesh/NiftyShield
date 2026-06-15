"""Encapsulates EOD auto-close and re-entry evaluation logic for overlay strategies."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import structlog

from src.backtest.ivr import compute_ivr
from src.backtest.vix_ingest import load_vix_series
from src.models.options import OptionChain
from src.paper.models import PaperPosition
from src.paper.store import PaperStore
from src.paper.tracker import get_strategy_realized_pnl
from src.strategy.executor import PaperFillSimulator
from src.strategy.overlay_closer import OverlayCloser

log = structlog.get_logger(__name__)

AUTO_CLOSE_SIGNALS: frozenset[tuple[str, str]] = frozenset(
    {
        ("overlay_cc", "PROFIT_TARGET"),
        ("overlay_cc", "TIME_STOP"),
        ("overlay_cc", "LOSS_STOP"),
        ("overlay_cc", "DELTA_STOP"),
        ("overlay_collar_call", "PROFIT_TARGET"),
        ("overlay_collar_call", "TIME_STOP"),
        ("overlay_collar_call", "LOSS_STOP"),
        ("overlay_collar_call", "DELTA_STOP"),
        ("overlay_pp", "PROFIT_TARGET"),
        ("overlay_pp", "CRASH_MONETIZE"),
        ("overlay_pp", "ROLL_ELIGIBLE"),
    }
)

OVERLAY_ROLES: frozenset[str] = frozenset(
    {
        "overlay_cc",
        "overlay_collar_call",
        "overlay_collar_put",
        "overlay_pp",
    }
)


def _is_loss_stop_signal(store: PaperStore, event_id: int) -> bool:
    """Return True when the event exit_signal is LOSS_STOP or DELTA_STOP."""
    try:
        event = store.get_exit_event(event_id)
        return event["exit_signal"] in ("LOSS_STOP", "DELTA_STOP") if event else False
    except Exception:
        return False


async def auto_close_overlay(
    store: PaperStore,
    simulator: PaperFillSimulator,
    pos: PaperPosition,
    event_id: int,
    chain: OptionChain,
    notifier: Any | None,
    lookup: Any | None,
    vix: float | None,
    exit_signal: str,
) -> bool:
    """Auto-close an overlay position after an ACTION signal.

    Resolves execution via OverlayCloser and records status as ACTED on success.
    Unified close notifications are sent via Telegram.
    """
    closer = OverlayCloser(store=store, simulator=simulator, notifier=None)
    strategy_name = pos.strategy_name
    leg_role = pos.leg_role
    is_short = pos.net_qty < 0
    entry_price = pos.avg_sell_price if is_short else pos.avg_cost

    try:
        is_loss = _is_loss_stop_signal(store, event_id)

        # Retrieve closing LTP and Delta for notification context
        opt_type = "CE" if is_short else "PE"
        # Since OverlayCloser.route or close_single_leg reads ltp from market chain:
        # We find OptionLeg for notification details
        from scripts.strategies.three_track.paper_3track_snapshot import _find_chain_leg

        opt_leg = _find_chain_leg(chain, pos.instrument_key, opt_type, lookup)
        exit_ltp = opt_leg.ltp if opt_leg is not None else Decimal("0")
        exit_delta = (
            float(opt_leg.delta) if (opt_leg is not None and opt_leg.delta is not None) else None
        )

        if leg_role == "overlay_cc":
            closer.close_single_leg(
                strategy_name=strategy_name,
                leg_role=leg_role,
                market=chain,
                event_id=event_id,
                vix=vix,
                is_loss_stop=is_loss,
            )
            leg_pnl = (entry_price - exit_ltp) * abs(pos.net_qty)
            legs_notif = [
                {
                    "role": leg_role,
                    "key": pos.instrument_key,
                    "entry": entry_price,
                    "exit": exit_ltp,
                    "delta": exit_delta,
                    "pnl": leg_pnl,
                }
            ]
            _send_close_notification(
                notifier, strategy_name, legs_notif, exit_signal, store, is_collar=False
            )

        elif leg_role == "overlay_collar_call":
            closer.close_collar_all(
                strategy_name=strategy_name,
                market=chain,
                event_id=event_id,
                vix=vix,
            )
            call_pnl = (entry_price - exit_ltp) * abs(pos.net_qty)

            # Fetch put position
            put_pos = store.get_position(strategy_name, "overlay_collar_put")
            put_entry = put_pos.avg_cost if put_pos else Decimal("0")
            put_key = put_pos.instrument_key if put_pos else "overlay_collar_put"
            put_qty = abs(put_pos.net_qty) if put_pos else 0

            put_leg = _find_chain_leg(chain, put_key, "PE", lookup) if put_pos else None
            put_exit = put_leg.ltp if put_leg is not None else Decimal("0")
            put_pnl = (put_exit - put_entry) * put_qty if put_pos else Decimal("0")

            legs_notif = [
                {
                    "role": "overlay_collar_call",
                    "key": pos.instrument_key,
                    "entry": entry_price,
                    "exit": exit_ltp,
                    "delta": exit_delta,
                    "pnl": call_pnl,
                },
                {
                    "role": "overlay_collar_put",
                    "key": put_key,
                    "entry": put_entry,
                    "exit": put_exit,
                    "delta": float(put_leg.delta)
                    if (put_leg is not None and put_leg.delta is not None)
                    else None,
                    "pnl": put_pnl,
                },
            ]
            _send_close_notification(
                notifier, strategy_name, legs_notif, exit_signal, store, is_collar=True
            )

        elif leg_role == "overlay_pp":
            closer.close_single_leg(
                strategy_name=strategy_name,
                leg_role=leg_role,
                market=chain,
                event_id=event_id,
                vix=vix,
                is_loss_stop=False,
            )
            leg_pnl = (exit_ltp - entry_price) * abs(pos.net_qty)
            legs_notif = [
                {
                    "role": leg_role,
                    "key": pos.instrument_key,
                    "entry": entry_price,
                    "exit": exit_ltp,
                    "delta": exit_delta,
                    "pnl": leg_pnl,
                }
            ]
            _send_close_notification(
                notifier, strategy_name, legs_notif, exit_signal, store, is_collar=False
            )

        else:
            log.error("auto_close.unknown_role", leg_role=leg_role)
            return False

    except Exception as exc:
        log.error(
            "auto_close.failed",
            strategy=strategy_name,
            leg=leg_role,
            event_id=event_id,
            error=str(exc),
        )
        if notifier is not None:
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(
                    notifier.send(
                        f"⚠️ AUTO-CLOSE FAILED — {strategy_name} / {leg_role}\n"
                        f"Signal: {exit_signal}  Event: {event_id}\n"
                        f"Error: {exc}\n"
                        f"Close manually via paper_cc_roll.py or record_paper_trade.py"
                    )
                )
            except Exception:
                pass
        return False

    log.info(
        "auto_close.executed",
        strategy=strategy_name,
        leg=leg_role,
        exit_signal=exit_signal,
        event_id=event_id,
    )
    return True


def _send_close_notification(
    notifier: Any | None,
    strategy_name: str,
    legs: list[dict[str, Any]],
    exit_signal: str,
    store: PaperStore,
    is_collar: bool = False,
) -> None:
    """Send unified, formatted close notifications to Telegram."""
    if notifier is None:
        return

    try:
        realized_pnl = get_strategy_realized_pnl(store, strategy_name)
        if is_collar:
            # Collar format
            call_leg = legs[0]
            put_leg = legs[1]
            net_pnl = call_leg["pnl"] + put_leg["pnl"]
            msg = (
                f"✅ COLLAR CLOSED — {strategy_name}\n"
                f"Short Call: {call_leg['key']} @ ₹{call_leg['exit']:.2f}  (entry ₹{call_leg['entry']:.2f})  → ₹{call_leg['pnl']:+,.0f}\n"
                f"Long Put:   {put_leg['key']} @ ₹{put_leg['exit']:.2f}  (entry ₹{put_leg['entry']:.2f})  → ₹{put_leg['pnl']:+,.0f}\n"
                f"Signal    : {exit_signal}\n"
                f"Net P&L   : ₹{net_pnl:+,.0f}  (call + put combined)\n"
                f"Overlay P&L (total realized): ₹{realized_pnl:+,.0f}"
            )
        else:
            leg = legs[0]
            if leg["role"] == "overlay_cc":
                msg = (
                    f"✅ CC CLOSED — {strategy_name}\n"
                    f"📤 {leg['key']} @ ₹{leg['exit']:.2f}  (entry ₹{leg['entry']:.2f})\n"
                    f"Signal : {exit_signal}\n"
                    f"Leg P&L: ₹{leg['pnl']:+,.0f}\n"
                    f"Overlay P&L (total realized): ₹{realized_pnl:+,.0f}"
                )
            else:  # overlay_pp
                if exit_signal == "CRASH_MONETIZE":
                    msg = (
                        f"💰 PP CRASH MONETIZED — {strategy_name}\n"
                        f"📤 {leg['key']} @ ₹{leg['exit']:.2f}  (entry ₹{leg['entry']:.2f})\n"
                        f"Signal : CRASH_MONETIZE  (delta {leg['delta']:.3f})\n"
                        f"Leg P&L: ₹{leg['pnl']:+,.0f}\n"
                        f"State  : → RE_ENTRY_PENDING (monitoring IVR ≤ 0.60, DTE ≥ 14)\n"
                        f"Overlay P&L (total realized): ₹{realized_pnl:+,.0f}"
                    )
                else:  # PROFIT_TARGET / ROLL_ELIGIBLE
                    msg = (
                        f"✅ PP CLOSED — {strategy_name}\n"
                        f"📤 {leg['key']} @ ₹{leg['exit']:.2f}  (entry ₹{leg['entry']:.2f})\n"
                        f"Signal : {exit_signal}\n"
                        f"Leg P&L: ₹{leg['pnl']:+,.0f}\n"
                        f"Overlay P&L (total realized): ₹{realized_pnl:+,.0f}"
                    )

        loop = asyncio.get_event_loop()
        loop.create_task(notifier.send(msg))
    except Exception as exc:
        log.warning("auto_close.notification_failed", error=str(exc))


async def evaluate_pp_reentry_eod(
    store: PaperStore,
    simulator: PaperFillSimulator,
    chain: OptionChain,
    lookup: Any | None,
    notifier: Any | None,
    vix_data_dir: Path | None,
    today: date,
) -> None:
    """Evaluate PP re-entry eligibility and notify if eligible (no auto-opening)."""
    # Import PPOverlayV1 dynamically to avoid structural coupling / circular imports
    # Retrieve all PP strategies from constants if possible, or filter
    from src.paper.constants import STRATEGY_PP_OVERLAY
    from src.strategy.pp_overlay_v1 import PPOverlayV1

    strategies = [STRATEGY_PP_OVERLAY]  # Standard PP Strategy

    for strat_name in strategies:
        try:
            # Check if active PP position exists
            existing_pos = store.get_positions(strat_name)
            active_pp = [p for p in existing_pos if p.leg_role == "overlay_pp" and p.net_qty > 0]
            if active_pp:
                continue  # already has active position

            # PP strategy expects reentry_leg_role = 'protective_put' but we check overlay_pp in track comparison context.
            # To be absolutely sure, check if there's any open position at all
            if any(p.net_qty != 0 for p in existing_pos):
                # Wait, CC/Collar tracks are separate strategies. A PP strategy track has its own strat_name.
                pass

            # Calculate IVR
            vix_series = await asyncio.to_thread(load_vix_series, vix_data_dir)
            if vix_series.empty or len(vix_series) < 252:
                continue

            vix_today = float(vix_series.iloc[-1])
            ivr = compute_ivr(vix_today, vix_series)
            if ivr is None:
                continue

            # Check if IVR passes using PPOverlayV1's method
            pp_strategy = PPOverlayV1(store=store, notifier=notifier, vix_data_dir=vix_data_dir)
            passed, reason = pp_strategy._ivr_passes(ivr)

            if passed:
                # Target next weekly expiry DTE >= 14
                if notifier is not None:
                    realized_pnl = get_strategy_realized_pnl(store, strat_name)
                    msg = (
                        f"🟢 PP RE-ENTRY ELIGIBLE — {strat_name}\n"
                        f"IVR    : {ivr:.2f} (passes reentry threshold)\n"
                        f"Status : RE_ENTRY_PENDING → ELIGIBLE\n"
                        f"Action : Run find_overlay_strikes.py --overlay-type pp to initiate manually\n"
                        f"Overlay P&L (total realized): ₹{realized_pnl:+,.0f}"
                    )
                    await notifier.send(msg)
        except Exception as exc:
            log.warning("evaluate_pp_reentry_eod.failed", strategy=strat_name, error=str(exc))
