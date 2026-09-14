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
from src.market_calendar.holidays import market_today
from src.models.options import OptionChain
from src.notifications.exit_message import ExitKind, ExitMessage, format_exit_message
from src.notifications.formatting import CloseLegRow, format_money
from src.notifications.markdown import escape_markdown, mdcode
from src.paper.cycle_pnl import cycle_stats, reconstruct_cycles
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
    dte = (chain.expiry - market_today()).days
    held_days = (market_today() - (pos.entry_date or market_today())).days

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
                dte=dte,
                held_days=held_days,
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
            entry_dates = [p.entry_date for p in (pos, put_pos) if p and p.entry_date]
            collar_held_days = (market_today() - min(entry_dates)).days if entry_dates else 0

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
                dte=dte,
                held_days=collar_held_days,
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
                dte=dte,
                held_days=held_days,
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


_ROLE_LABEL = {
    "overlay_cc": ("CC", "Short Call"),
    "overlay_pp": ("PP", "Long Put"),
}

_COLLAR_ROLES = ("overlay_collar_call", "overlay_collar_put")


async def _send_close_notification(
    notifier: Any | None,
    strategy_name: str,
    legs: list[dict[str, Any]],
    exit_signal: str,
    store: PaperStore,
    is_collar: bool = False,
    lookup: Any | None = None,
    dte: int = 0,
    held_days: int = 0,
) -> None:
    """Send the shared exit-confirmation card for a daemon overlay close. Non-fatal."""
    if notifier is None:
        return

    def _label(key: str) -> str:
        return format_leg_label(key, lookup) if lookup is not None else key

    try:
        realized_pnl = get_strategy_realized_pnl(store, strategy_name)

        if is_collar:
            call_leg, put_leg = legs[0], legs[1]
            close_legs = [
                CloseLegRow(
                    role="Short Call",
                    instrument=_label(call_leg["key"]),
                    entry=float(call_leg["entry"]),
                    exit=float(call_leg["exit"]),
                    pnl=Decimal(str(call_leg["pnl"])),
                ),
                CloseLegRow(
                    role="Long Put",
                    instrument=_label(put_leg["key"]),
                    entry=float(put_leg["entry"]),
                    exit=float(put_leg["exit"]),
                    pnl=Decimal(str(put_leg["pnl"])),
                ),
            ]
            this_exit_pnl = Decimal(str(call_leg["pnl"])) + Decimal(str(put_leg["pnl"]))
            headline_label = "Collar"
            kind = ExitKind.CLOSE
            state_line = None
            leg_roles = _COLLAR_ROLES
        else:
            leg = legs[0]
            headline_label, role = _ROLE_LABEL[leg["role"]]
            close_legs = [
                CloseLegRow(
                    role=role,
                    instrument=_label(leg["key"]),
                    entry=float(leg["entry"]),
                    exit=float(leg["exit"]),
                    pnl=Decimal(str(leg["pnl"])),
                )
            ]
            this_exit_pnl = Decimal(str(leg["pnl"]))
            leg_roles = (leg["role"],)
            if leg["role"] == "overlay_pp" and exit_signal == "CRASH_MONETIZE":
                kind = ExitKind.CRASH_MONETIZE
                state_line = "RE_ENTRY_PENDING (monitoring IVR ≤ 0.60, DTE ≥ 14)"
            else:
                kind = ExitKind.CLOSE
                state_line = None

        cycle_pnl = None
        cycle_index = None
        cycle_decay_pct = None
        cycle_short_credit = None
        cycle_short_buyback = None
        cycle_held_days = None
        stats = None
        try:
            trades = [t for t in store.get_trades(strategy_name) if t.leg_role in leg_roles]
            cycles_all = reconstruct_cycles(trades)
            if cycles_all and not cycles_all[-1].is_open:
                last = cycles_all[-1]
                cycle_pnl = last.realized_pnl
                cycle_index = last.index
                cycle_decay_pct = last.short_decay_pct
                cycle_short_credit = last.short_credit_per_unit
                cycle_short_buyback = last.short_buyback_per_unit
                cycle_held_days = last.days_in_trade
            stats = cycle_stats(trades)
        except Exception as exc:  # Intentional: footer stats are optional, card still sends
            log.warning("auto_close.footer_calc_failed", error=str(exc))

        text = format_exit_message(
            ExitMessage(
                headline_label=headline_label,
                kind=kind,
                signal=exit_signal,
                dte=dte,
                held_days=held_days,
                legs=close_legs,
                this_exit_pnl=this_exit_pnl,
                cycle_pnl=cycle_pnl,
                cycle_index=cycle_index,
                cycle_decay_pct=cycle_decay_pct,
                cycle_short_credit=cycle_short_credit,
                cycle_short_buyback=cycle_short_buyback,
                cycle_held_days=cycle_held_days,
                inception_pnl=realized_pnl,
                stats=stats,
                overlay_total_pnl=realized_pnl,
                state_line=state_line,
            )
        )
        await notifier.send(text)
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
        passed, _, _ = pp_strategy._ivr_passes(ivr)

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
