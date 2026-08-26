"""Encapsulates EOD auto-close and re-entry evaluation logic for overlay strategies."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from src.backtest.ivr import compute_ivr
from src.backtest.vix_ingest import load_vix_series
from src.instruments.lookup import format_leg_label
from src.models.options import OptionChain
from src.notifications.formatting import format_greek, format_money
from src.notifications.markdown import escape_markdown, mdcode
from src.paper.models import PaperPosition

if TYPE_CHECKING:
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

        opt_type = "CE" if is_short else "PE"
        # Since OverlayCloser.route or close_single_leg reads ltp from market chain:
        # We find OptionLeg for notification details
        from src.paper.chain_utils import find_chain_leg

        opt_leg = find_chain_leg(chain, pos.instrument_key, opt_type, lookup)
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
            await _send_close_notification(
                notifier,
                strategy_name,
                legs_notif,
                exit_signal,
                store,
                is_collar=False,
                lookup=lookup,
            )

        elif leg_role == "overlay_collar_call":
            # Snapshot the put leg's position BEFORE close_collar_all() runs.
            # close_collar_all() writes the closing trade for both legs
            # atomically, so a get_position() call made *after* it returns
            # sees net_qty already flattened to 0 — computing put_pnl from
            # that would silently zero it out regardless of the real price
            # move. Capture qty/entry now, same as call_pnl already does via
            # the pre-close `pos` parameter.
            put_pos = store.get_position(strategy_name, "overlay_collar_put")
            put_entry = put_pos.avg_cost if put_pos else Decimal("0")
            put_key = put_pos.instrument_key if put_pos else "overlay_collar_put"
            put_qty = abs(put_pos.net_qty) if put_pos else 0

            closed_ok = closer.close_collar_all(
                strategy_name=strategy_name,
                market=chain,
                event_id=event_id,
                vix=vix,
            )
            if not closed_ok:
                # close_collar_all already logged + notified the write failure
                # and left both legs open. Raise so the outer except block's
                # existing AUTO-CLOSE FAILED handling fires instead of us
                # falling through to send a false "COLLAR CLOSED" report.
                raise RuntimeError("close_collar_all reported failure — position still open")
            call_pnl = (entry_price - exit_ltp) * abs(pos.net_qty)

            put_leg = find_chain_leg(chain, put_key, "PE", lookup) if put_pos else None
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
            await _send_close_notification(
                notifier,
                strategy_name,
                legs_notif,
                exit_signal,
                store,
                is_collar=True,
                lookup=lookup,
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
            await _send_close_notification(
                notifier,
                strategy_name,
                legs_notif,
                exit_signal,
                store,
                is_collar=False,
                lookup=lookup,
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
                await notifier.send(
                    f"{escape_markdown('⚠️ AUTO-CLOSE FAILED — ')}{mdcode(strategy_name)}"
                    f"{escape_markdown(' / ')}{mdcode(leg_role)}\n"
                    f"{escape_markdown('Signal: ')}{mdcode(exit_signal)}"
                    f"{escape_markdown('  Event: ')}{mdcode(str(event_id))}\n"
                    f"{escape_markdown('Error: ')}{escape_markdown(str(exc))}\n"
                    f"{escape_markdown('Close manually via paper_cc_roll.py or record_paper_trade.py')}"
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


async def _send_close_notification(
    notifier: Any | None,
    strategy_name: str,
    legs: list[dict[str, Any]],
    exit_signal: str,
    store: PaperStore,
    is_collar: bool = False,
    lookup: Any | None = None,
) -> None:
    """Send unified, formatted close notifications to Telegram."""
    if notifier is None:
        return

    def _label(key: str) -> str:
        return format_leg_label(key, lookup) if lookup is not None else key

    try:
        realized_pnl = get_strategy_realized_pnl(store, strategy_name)

        def _fmt_pnl(val: float) -> str:
            v = Decimal(str(val))
            if v > 0:
                return escape_markdown(f"+{format_money(v)}")
            return escape_markdown(format_money(v))

        realized_pnl_str = _fmt_pnl(realized_pnl)

        if is_collar:
            # Collar format
            call_leg = legs[0]
            put_leg = legs[1]
            net_pnl = call_leg["pnl"] + put_leg["pnl"]

            c_exit = escape_markdown(format_money(Decimal(str(call_leg["exit"]))))
            c_entry = escape_markdown(f"(entry {format_money(Decimal(str(call_leg['entry'])))})")
            c_pnl = _fmt_pnl(call_leg["pnl"])

            p_exit = escape_markdown(format_money(Decimal(str(put_leg["exit"]))))
            p_entry = escape_markdown(f"(entry {format_money(Decimal(str(put_leg['entry'])))})")
            p_pnl = _fmt_pnl(put_leg["pnl"])

            net_pnl_str = _fmt_pnl(net_pnl)

            msg = (
                f"✅ *Collar closed — {escape_markdown(strategy_name)}*\n"
                f"📤 Short Call: {mdcode(_label(call_leg['key']))} "
                f"@ {c_exit}  {c_entry}  → {c_pnl}\n"
                f"📤 Long Put:   {mdcode(_label(put_leg['key']))} "
                f"@ {p_exit}  {p_entry}  → {p_pnl}\n"
                f"Signal    : {escape_markdown(exit_signal)}\n"
                f"Net P&L   : {net_pnl_str}  "
                f"{escape_markdown('(call + put combined)')}\n"
                f"Overlay P&L {escape_markdown('(total realized)')}: "
                f"{realized_pnl_str}"
            )
        else:
            leg = legs[0]
            l_exit = escape_markdown(format_money(Decimal(str(leg["exit"]))))
            l_entry = escape_markdown(f"(entry {format_money(Decimal(str(leg['entry'])))})")
            l_pnl = _fmt_pnl(leg["pnl"])

            if leg["role"] == "overlay_cc":
                msg = (
                    f"✅ *CC closed — {escape_markdown(strategy_name)}*\n"
                    f"📤 {mdcode(_label(leg['key']))} @ {l_exit}  "
                    f"{l_entry}\n"
                    f"Signal : {escape_markdown(exit_signal)}\n"
                    f"Leg P&L: {l_pnl}\n"
                    f"Overlay P&L {escape_markdown('(total realized)')}: "
                    f"{realized_pnl_str}"
                )
            else:  # overlay_pp
                if exit_signal == "CRASH_MONETIZE":
                    delta_val = leg.get("delta")
                    delta = float(delta_val) if delta_val is not None else None
                    l_delta = escape_markdown(f"(delta {format_greek(delta)})")
                    msg = (
                        f"💰 *PP crash monetized — "
                        f"{escape_markdown(strategy_name)}*\n"
                        f"📤 {mdcode(_label(leg['key']))} @ {l_exit}  "
                        f"{l_entry}\n"
                        f"Signal : {escape_markdown('CRASH_MONETIZE')}  "
                        f"{l_delta}\n"
                        f"Leg P&L: {l_pnl}\n"
                        f"State  : → {escape_markdown('RE_ENTRY_PENDING')} "
                        f"{escape_markdown('(monitoring IVR ≤ 0.60, ')}"
                        f"{escape_markdown('DTE ≥ 14)')}\n"
                        f"Overlay P&L {escape_markdown('(total realized)')}: "
                        f"{realized_pnl_str}"
                    )
                else:  # PROFIT_TARGET / ROLL_ELIGIBLE
                    msg = (
                        f"✅ *PP closed — {escape_markdown(strategy_name)}*\n"
                        f"📤 {mdcode(_label(leg['key']))} @ {l_exit}  "
                        f"{l_entry}\n"
                        f"Signal : {escape_markdown(exit_signal)}\n"
                        f"Leg P&L: {l_pnl}\n"
                        f"Overlay P&L {escape_markdown('(total realized)')}: "
                        f"{realized_pnl_str}"
                    )

        await notifier.send(msg)
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
    """Evaluate PP re-entry eligibility and notify if eligible (no auto-opening).

    Since S2r (2026-07-29), PP is recorded standalone under STRATEGY_OVERLAY
    (paper_nifty_overlay) — never under a base track's strategy_name. Per
    BUG-028's resolved architecture (council 2026-08-10, decision (b) decouple
    pipeline), all overlay P&L/position reads go through STRATEGY_OVERLAY only.
    We check for an active overlay_pp leg under STRATEGY_OVERLAY and notify
    once if none is found and IVR passes the re-entry gate.
    """
    from src.paper.constants import STRATEGY_OVERLAY
    from src.strategy.pp_overlay_v1 import PPOverlayV1

    try:
        # Active if STRATEGY_OVERLAY carries a live overlay_pp position
        active_pp = [
            p
            for p in store.get_positions(STRATEGY_OVERLAY)
            if p.leg_role == "overlay_pp" and p.net_qty > 0
        ]
        if active_pp:
            return  # position already open — nothing to do

        # Calculate IVR
        vix_series = await asyncio.to_thread(load_vix_series, vix_data_dir)
        if vix_series.empty or len(vix_series) < 252:
            return

        vix_today = float(vix_series.iloc[-1])
        ivr = compute_ivr(vix_today, vix_series)
        if ivr is None:
            return

        pp_strategy = PPOverlayV1(store=store, notifier=notifier, vix_data_dir=vix_data_dir)
        passed, _ = pp_strategy._ivr_passes(ivr)

        if passed and notifier is not None:
            # Realized P&L from the standalone overlay book
            realized_pnl = get_strategy_realized_pnl(store, STRATEGY_OVERLAY)
            ivr_str = escape_markdown(f"{ivr:.2f}")

            v = Decimal(str(realized_pnl))
            if v > 0:
                realized_pnl_str = escape_markdown(f"+{format_money(v)}")
            else:
                realized_pnl_str = escape_markdown(format_money(v))

            msg = (
                f"{escape_markdown('🟢 PP RE-ENTRY ELIGIBLE — standalone overlay')}\n"
                f"{escape_markdown('IVR    : ')}{ivr_str} "
                f"{escape_markdown('(passes reentry threshold)')}\n"
                f"{escape_markdown('Status : No open PP → ELIGIBLE')}\n"
                f"{escape_markdown('Action : Run find_overlay_strikes.py --overlay-type pp to initiate manually')}\n"
                f"Overlay P&L {escape_markdown('(total realized)')}: {realized_pnl_str}"
            )
            await notifier.send(msg)
    except Exception as exc:
        log.warning("evaluate_pp_reentry_eod.failed", error=str(exc))
