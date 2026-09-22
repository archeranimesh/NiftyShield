#!/usr/bin/env python3
"""End-of-day signal pipeline: record outcome and push report.

Cron: 0 16 * * 1-5  (or run manually after market close)

Replaces the separate record_signal_outcome and signal_report scripts.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import mean

import structlog

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.config import settings
from src.market_calendar import market_today
from src.market_calendar.holidays import guard_trading_day
from src.notifications.formatting import format_money, pnl_emoji
from src.notifications.markdown import escape_markdown
from src.notifications.telegram import build_notifier
from src.paper.constants import DEFAULT_BOD_PATH, LOT_SIZE
from src.paper.store import PaperStore
from src.signals.models import (
    DailySignal,
    Direction,
    MarketSnapshot,
    SignalOutcome,
    SignalResponse,
    TradeAction,
)
from src.signals.option_resolver import resolve_monthly_option
from src.signals.store import SignalStore
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.signal_eod"
logger = structlog.get_logger(_SCRIPT_NAME)

load_dotenv()

_NIFTY_SPOT_KEY = "NSE_INDEX|Nifty 50"
_ACTION_LABEL = {TradeAction.BUY_CALL: "BUY CALL", TradeAction.BUY_PUT: "BUY PUT"}
_DIRECTION_EMOJI = {"BULLISH": "📈", "BEARISH": "📉"}
_E = escape_markdown

_SIGNIFICANCE_THRESHOLD = 50
_MOVE_THRESHOLD = Decimal("0.005")  # 0.5% — NO_TRADE "market moved" cutoff
_RULE = "─" * 49


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="End-of-day signal pipeline: record outcome and push report.",
    )
    # Record phase args
    parser.add_argument("--entry-premium", default=None, help="Entry premium per unit (Decimal).")
    parser.add_argument("--exit-premium", default=None, help="Exit premium per unit (Decimal).")
    parser.add_argument(
        "--executed",
        action="store_true",
        default=False,
        help="Set when the signal was actually paper-traded. Omit if you chose not to trade.",
    )
    parser.add_argument("--notes", default="", help="Optional annotation.")
    parser.add_argument(
        "--date",
        dest="trade_date",
        default=market_today().isoformat(),
        metavar="YYYY-MM-DD",
        help="Trading day to record. Default: today (IST).",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        default=False,
        help="Record phase only: non-interactive (auto) mode.",
    )
    parser.add_argument(
        "--nifty-close",
        default=None,
        help="Override Nifty close (Decimal). Default: live spot LTP (required back-dated).",
    )
    parser.add_argument(
        "--bod-path",
        type=Path,
        default=DEFAULT_BOD_PATH,
        help=f"Path to the Upstox BOD JSON (default: {DEFAULT_BOD_PATH}).",
    )

    # Report phase args
    parser.add_argument(
        "--report-only",
        action="store_true",
        default=False,
        help="Report phase only.",
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Inclusive lower bound on trade_date for report. Default: unbounded.",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Inclusive upper bound on trade_date for report. Default: unbounded.",
    )
    parser.add_argument(
        "--phase",
        default=None,
        choices=["openrouter_only", "search_enabled"],
        help="Restrict report to a single pipeline phase. Default: all phases.",
    )
    return parser.parse_args()


# --- Record phase helpers ---
def _resolve_phase() -> str:
    """Return the pipeline phase from ``SIGNAL_PHASE`` or the live key set."""
    env = os.getenv("SIGNAL_PHASE")
    if env:
        return env
    if os.getenv("XAI_API_KEY") or os.getenv("GOOGLE_AI_API_KEY"):
        return "search_enabled"
    return "openrouter_only"


def _to_decimal(raw: str | None, label: str) -> Decimal | None:
    """Parse an optional CLI Decimal argument, exiting 1 on a malformed value."""
    if raw is None:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        raise ValueError(f"--{label} must be a number, got: {raw!r}") from None


def _consensus_entry_premium(signal: DailySignal) -> Decimal | None:
    """Mean midpoint of the agreeing models' quoted entry-premium bands."""
    mids = [
        (r.entry_premium_low + r.entry_premium_high) / 2
        for r in signal.responses
        if r.provider in signal.agreeing_models
    ]
    if not mids:
        return None
    return Decimal(str(mean(mids))).quantize(Decimal("0.01"))


def _fetch_ltp(keys: list[str]) -> dict[str, Decimal]:
    """Fetch last-traded prices for ``keys`` via the live Upstox market client."""
    from src.client.upstox_market import UpstoxMarketClient

    return UpstoxMarketClient().get_ltp_sync(keys)


def _resolve_option_key(signal: DailySignal, bod_path: Path) -> str:
    """Resolve the recommended option's instrument key from the offline BOD."""
    key = resolve_monthly_option(signal, bod_path)
    if key is None:
        raise ValueError(
            f"could not resolve monthly option for strike "
            f"{signal.recommended_strike} — pass --exit-premium explicitly."
        )
    return key


def _pnl_per_lot(entry: Decimal | None, exit_premium: Decimal | None) -> Decimal | None:
    """Realised P&L per lot for a long option, or ``None`` if a leg is missing."""
    if entry is None or exit_premium is None:
        return None
    return (exit_premium - entry) * LOT_SIZE


def _high_low_pnl_per_lot(
    trade_id: int | None, entry_premium: Decimal | None
) -> tuple[Decimal | None, Decimal | None]:
    """Profit high/low per lot from the trade's mark history, or ``(None, None)``.

    Sourced from the last (most recent) ``paper_signal_marks`` row's
    ``mfe_pct`` / ``mae_pct`` — both are running extremes since entry.
    """
    if trade_id is None or entry_premium is None:
        return None, None
    marks = PaperStore(settings.db_path).get_marks(trade_id)
    if not marks:
        return None, None
    last = marks[-1]
    return last.mfe_pct * entry_premium * LOT_SIZE, last.mae_pct * entry_premium * LOT_SIZE


def _format_outcome_notification(outcome: SignalOutcome, signal: DailySignal) -> str:
    """Render the daily outcome as MarkdownV2-ready Telegram message text.\n\n    S5.5c vertical layout (reference renderer ``format_outcome_notification``,\n    validated on-device 2026-09-08): bold header + blank line + one\n    emoji-prefixed line per field. This formatter owns its escaping — every\n    dynamic part is escaped per value and literal ``*`` is emitted for bold — so\n    the caller sends the result WITHOUT re-wrapping it in ``escape_markdown``.\n\n    Would-be P&L for the not-taken case is derived here from\n    ``entry_premium``/``exit_premium`` (both populated by ``--auto`` even when\n    ``executed`` is False) — no ``SignalOutcome`` change.\n\n    Args:\n        outcome: The persisted ``SignalOutcome`` for the trading day.\n        signal: The aggregated ``DailySignal`` — direction of the trade call.\n\n    Returns:\n        Fully-escaped message text. One of: an executed block, a not-taken\n        (would-be P&L) block, a NO_TRADE line, or a close-only fallback when a\n        premium leg is missing.\n"""
    day = outcome.trade_date.strftime("%d %b")
    close = _E(f"🏁 Nifty close: {outcome.nifty_close:,.0f}")
    entry, exit_ = outcome.entry_premium, outcome.exit_premium

    if outcome.trade_action is TradeAction.NO_TRADE:
        header = _E(f"📊 SIGNAL OUTCOME · {day} · NO TRADE")
        return f"*{header}*\n\n{_E('➖ No signal issued today')}\n{close}"
    if entry is None or exit_ is None:
        header = _E(f"📊 SIGNAL OUTCOME · {day}")
        return f"*{header}*\n\n{_E('➖ Outcome not priced')}\n{close}"

    emoji = _DIRECTION_EMOJI.get(signal.consensus_direction.value, "📊")
    action = _ACTION_LABEL[outcome.trade_action]
    line_dir = _E(
        f"{emoji} {signal.consensus_direction.value} · {action} {outcome.recommended_strike}"
    )

    pnl_val = outcome.pnl_per_lot if outcome.pnl_per_lot is not None else (exit_ - entry) * LOT_SIZE
    label = "P&L" if outcome.executed else "Paper P&L"
    pnl_line = f"{pnl_emoji(pnl_val)} {_E(f'{label}: {format_money(pnl_val, signed=True)} / lot')}"

    range_line = ""
    if outcome.executed:
        header = _E(f"📊 SIGNAL OUTCOME · {day}")
        prem = _E(f"💰 Entry {format_money(entry)} → Exit {format_money(exit_)}")
        if outcome.high_pnl_per_lot is not None and outcome.low_pnl_per_lot is not None:
            range_line = "\n" + _E(
                f"📈 High {format_money(outcome.high_pnl_per_lot, signed=True)} / "
                f"📉 Low {format_money(outcome.low_pnl_per_lot, signed=True)} / lot"
            )
    else:
        header = _E(f"📊 SIGNAL OUTCOME · {day} · NOT TAKEN")
        prem = _E(f"💰 Entry {format_money(entry)} → Exit {format_money(exit_)} (would-be)")

    return (
        f"*{header}*\n\n{line_dir}\n{prem}\n{pnl_line}{range_line}\n\n"
        f"{close}\n{_E(f'🔧 Phase: {outcome.phase}')}"
    )


def _notify_outcome(outcome: SignalOutcome, signal: DailySignal) -> None:
    """Push the outcome to Telegram; non-fatal when no notifier is configured."""
    notifier = build_notifier()
    if notifier is None:
        return
    try:
        asyncio.run(notifier.send(_format_outcome_notification(outcome, signal)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("signal_outcome_notify_failed", error=str(exc))


# --- Report phase helpers ---
def _parse_date(raw: str | None, label: str) -> date | None:
    """Parse an optional ``YYYY-MM-DD`` CLI argument, exiting 1 on a bad value."""
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ValueError(f"--{label} must be YYYY-MM-DD, got: {raw!r}") from None


def _pct(num: int, denom: int) -> float:
    """Percentage ``num / denom``, or ``0.0`` when ``denom`` is zero."""
    return 100.0 * num / denom if denom else 0.0


def _coin_flip_matches(trade_date: date, action: TradeAction) -> bool:
    """Deterministic coin flip: True when the random pick matches the signal.\n\n    ``hash()`` is salted per process (PYTHONHASHSEED), so md5 is used instead to\n    keep the baseline reproducible across runs.\n"""
    digest = hashlib.md5(trade_date.isoformat().encode()).digest()
    random_is_call = digest[0] % 2 == 0
    signal_is_call = action is TradeAction.BUY_CALL
    return random_is_call == signal_is_call


def _direction_correct(direction: Direction, nifty_open: Decimal, nifty_close: Decimal) -> bool:
    """A provider call is correct only when a non-NEUTRAL direction matches the move."""
    if direction is Direction.BULLISH:
        return nifty_close > nifty_open
    if direction is Direction.BEARISH:
        return nifty_close < nifty_open
    return False


def _load_days(
    store: SignalStore, outcomes: list[SignalOutcome]
) -> dict[date, tuple[list[SignalResponse], MarketSnapshot | None, DailySignal | None]]:
    """Fetch the responses, snapshot and signal backing each outcome day."""
    return {
        o.trade_date: (
            store.get_responses(o.trade_date),
            store.get_snapshot(o.trade_date),
            store.get_signal(o.trade_date),
        )
        for o in outcomes
    }


def _overall_section(outcomes: list[SignalOutcome]) -> list[str]:
    """Build the OVERALL block — counts, win rate, realised EV and coin-flip EV."""
    trading_days = len(outcomes)
    signals = [o for o in outcomes if o.trade_action is not TradeAction.NO_TRADE]
    no_trade = trading_days - len(signals)
    executed = [o for o in signals if o.executed and o.pnl_per_lot is not None]
    skipped = len(signals) - len(executed)

    pnls = [o.pnl_per_lot for o in executed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    avg_pnl = mean(pnls) if pnls else Decimal(0)
    avg_win = mean(wins) if wins else Decimal(0)
    avg_loss = mean(losses) if losses else Decimal(0)
    win_rate = _pct(len(wins), len(executed))
    ev = Decimal(str(win_rate / 100)) * Decimal(str(avg_win)) + Decimal(
        str(1 - win_rate / 100)
    ) * Decimal(str(avg_loss))

    random_pnls = [
        o.pnl_per_lot
        if _coin_flip_matches(o.trade_date, o.trade_action)
        else -(o.entry_premium if o.entry_premium is not None else Decimal(0)) * LOT_SIZE
        for o in executed
    ]
    random_ev = mean(random_pnls) if random_pnls else Decimal(0)

    lines = ["OVERALL"]
    if len(executed) < _SIGNIFICANCE_THRESHOLD:
        lines.insert(
            0,
            f"⚠ Only {len(executed)} executed trades — results below statistical "
            f"significance threshold ({_SIGNIFICANCE_THRESHOLD} trades).\n",
        )
    lines += [
        f"  Trading days in period : {trading_days}",
        f"  Signals generated      : {len(signals)}   ({no_trade} NO_TRADE days)",
        f"  Executed trades        : {len(executed)}   ({skipped} skipped)",
        f"  Win rate               : {len(wins)}/{len(executed)}  =  {win_rate:.1f}%",
        f"  Avg P&L per lot        : ₹ {avg_pnl:,.0f}",
        f"  Expected value         : ₹ {ev:,.0f}   (win_rate × avg_win + loss_rate × avg_loss)",
        f"  Random baseline EV     : ₹ {random_ev:,.0f}   (coin flip, same entry/exit)",
    ]
    return lines


def _per_model_section(
    days: dict[date, tuple[list[SignalResponse], MarketSnapshot | None, DailySignal | None]],
    close_by_date: dict[date, Decimal],
) -> list[str]:
    """Direction accuracy per provider — open proxied by the 09:10 snapshot spot."""
    hit: dict[str, int] = defaultdict(int)
    total: dict[str, int] = defaultdict(int)
    missing_open = 0
    for trade_date, (responses, snapshot, _signal) in days.items():
        if snapshot is None:
            missing_open += 1
            continue
        outcome_close = close_by_date[trade_date]
        for r in responses:
            total[r.provider] += 1
            if _direction_correct(r.direction, snapshot.nifty_spot, outcome_close):
                hit[r.provider] += 1

    lines = ["PER-MODEL ACCURACY  (direction_called == nifty_close > nifty_open)"]
    for provider in sorted(total):
        n, t = hit[provider], total[provider]
        lines.append(f"  {provider:<6} : {n}/{t} = {_pct(n, t):.1f}%")
    if not total:
        lines.append("  (no provider responses in period)")
    if missing_open:
        lines.append(f"  ({missing_open} day(s) skipped — no stored snapshot for the open)")
    return lines


def _confidence_section(
    outcomes: list[SignalOutcome],
    days: dict[date, tuple[list[SignalResponse], MarketSnapshot | None, DailySignal | None]],
) -> list[str]:
    """Win rate bucketed by rounded consensus confidence, executed trades only."""
    buckets: dict[str, list[Decimal]] = {"1–2": [], "3": [], "4": [], "5": []}
    for o in outcomes:
        if not (o.executed and o.pnl_per_lot is not None):
            continue
        _responses, _snapshot, signal = days[o.trade_date]
        if signal is None:
            continue
        conf = int(signal.consensus_confidence.to_integral_value(rounding="ROUND_HALF_UP"))
        key = "1–2" if conf <= 2 else "5" if conf >= 5 else str(conf)
        buckets[key].append(o.pnl_per_lot)

    lines = ["CONFIDENCE CALIBRATION"]
    for key, label in (
        ("1–2", "confidence 1–2"),
        ("3", "confidence 3"),
        ("4", "confidence 4"),
        ("5", "confidence 5"),
    ):
        pnls = buckets[key]
        wins = sum(1 for p in pnls if p > 0)
        lines.append(f"  {label:<14}: {len(pnls)} trades   win rate {_pct(wins, len(pnls)):.1f}%")
    return lines


def _no_trade_section(
    outcomes: list[SignalOutcome],
    days: dict[date, tuple[list[SignalResponse], MarketSnapshot | None, DailySignal | None]],
) -> list[str]:
    """How often NO_TRADE days were quiet (< 0.5% move) — signal correctly flat."""
    no_trade = [o for o in outcomes if o.trade_action is TradeAction.NO_TRADE]
    scored = 0
    moved = 0
    for o in no_trade:
        _responses, snapshot, _signal = days[o.trade_date]
        if snapshot is None or snapshot.nifty_spot == 0:
            continue
        scored += 1
        move = abs(o.nifty_close - snapshot.nifty_spot) / snapshot.nifty_spot
        if move > _MOVE_THRESHOLD:
            moved += 1
    quiet = scored - moved
    return [
        "NO_TRADE ACCURACY",
        f"  NO_TRADE days          : {len(no_trade)}",
        f"  Market moved > 0.5%    : {moved}/{scored} ({_pct(moved, scored):.0f}%) — "
        "a directional move was missed",
        f"  Market stayed < 0.5%   : {quiet}/{scored} ({_pct(quiet, scored):.0f}%) — "
        "signal correctly avoided",
    ]


def _phase_section(outcomes: list[SignalOutcome]) -> list[str]:
    """Executed-trade count and mean realised P&L per pipeline phase."""
    by_phase: dict[str, list[Decimal]] = defaultdict(list)
    for o in outcomes:
        if o.executed and o.pnl_per_lot is not None:
            by_phase[o.phase].append(o.pnl_per_lot)
    lines = ["PHASE BREAKDOWN"]
    for phase in ("openrouter_only", "search_enabled"):
        pnls = by_phase.get(phase, [])
        ev = mean(pnls) if pnls else Decimal(0)
        lines.append(f"  {phase:<15} : {len(pnls)} trades  EV ₹{ev:+,.0f}")
    return lines


def _format_report_message(body: str) -> str:
    """Wrap the plain-text report in a MarkdownV2 fenced code block.\n\n    Telegram does not parse entities inside a fence, so only ``\\`` and\n    ````` need escaping (a backslash renders literally inside a fence — the\n    general ``escape_markdown`` must NOT be used on fence content).\n\n    Args:\n        body: The already-rendered ``"\\n".join(out)`` report text.\n\n    Returns:\n        The body wrapped as ```` ``` ````-fenced MarkdownV2, fence-safe.\n"""
    safe = body.replace("\\", "\\\\").replace("`", "\\`")
    return f"```\n{safe}\n```"


def _notify_report(body: str) -> None:
    """Push the report to Telegram; non-fatal when no notifier is configured."""
    notifier = build_notifier()
    if notifier is None:
        return
    try:
        asyncio.run(notifier.send(_format_report_message(body)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("signal_report_notify_failed", error=str(exc))


# --- Phase Runners ---
def run_record_phase(args: argparse.Namespace) -> None:
    try:
        trade_date = date.fromisoformat(args.trade_date)
    except ValueError:
        raise ValueError(f"--date must be YYYY-MM-DD, got: {args.trade_date}") from None

    store = SignalStore(settings.db_path)
    store.init_db()
    signal = store.get_signal(trade_date)
    if signal is None:
        raise ValueError(f"no signal recorded for {trade_date}.")

    entry_premium = _to_decimal(args.entry_premium, "entry-premium")
    exit_premium = _to_decimal(args.exit_premium, "exit-premium")
    executed = args.executed
    nifty_close = _to_decimal(args.nifty_close, "nifty-close")

    is_trade = signal.is_actionable

    trade_id = None
    if is_trade and not executed:
        live_entries = PaperStore(settings.db_path).get_entries(trade_date, trade_date)
        if live_entries:
            executed = True
            trade_id = live_entries[0].trade_id
            if entry_premium is None:
                # one open position at a time (open_signal_entry) -> earliest
                # trade_id is the entry for this signal_date
                entry_premium = live_entries[0].entry_premium

    if is_trade:
        if entry_premium is None:
            entry_premium = (
                signal.entry_premium
                if signal.entry_premium is not None
                else _consensus_entry_premium(signal)
            )
        try:
            option_key = _resolve_option_key(signal, args.bod_path)
            ltps = _fetch_ltp([option_key, _NIFTY_SPOT_KEY])
        # Intent: isolate record failure so report still runs.
        # noqa BLE001: catch-all needed to prevent cron death on formatting/network errors.
        except Exception as exc:  # noqa: BLE001  # noqa: BLE001
            raise RuntimeError(f"auto price fetch failed — {exc}") from exc

        if option_key not in ltps:
            raise RuntimeError(
                f"no LTP returned for the recommended option ({option_key}) — "
                "pass --exit-premium explicitly."
            )
        exit_premium = ltps[option_key].quantize(Decimal("0.01"))
        if nifty_close is None and _NIFTY_SPOT_KEY in ltps:
            nifty_close = ltps[_NIFTY_SPOT_KEY].quantize(Decimal("0.01"))

    if nifty_close is None:
        try:
            spot = _fetch_ltp([_NIFTY_SPOT_KEY]).get(_NIFTY_SPOT_KEY)
        # Intent: isolate record failure so report still runs.
        # noqa BLE001: catch-all needed to prevent cron death on formatting/network errors.
        except Exception as exc:  # noqa: BLE001  # noqa: BLE001
            raise RuntimeError(f"could not fetch Nifty close — {exc}") from exc
        if spot is None:
            raise RuntimeError("Nifty spot LTP unavailable — pass --nifty-close.")
        nifty_close = spot.quantize(Decimal("0.01"))

    if not is_trade:
        entry_premium = exit_premium = None
        executed = False
        trade_id = None

    high_pnl_per_lot, low_pnl_per_lot = _high_low_pnl_per_lot(trade_id, entry_premium)

    outcome = SignalOutcome(
        trade_date=trade_date,
        trade_action=signal.trade_action,
        recommended_strike=signal.recommended_strike,
        entry_premium=entry_premium,
        exit_premium=exit_premium,
        pnl_per_lot=_pnl_per_lot(entry_premium, exit_premium) if executed else None,
        high_pnl_per_lot=high_pnl_per_lot,
        low_pnl_per_lot=low_pnl_per_lot,
        nifty_close=nifty_close,
        executed=executed,
        phase=_resolve_phase(),
        notes=args.notes,
    )
    store.record_outcome(outcome)
    _notify_outcome(outcome, signal)

    logger.info(
        "signal_outcome_recorded",
        trade_date=trade_date.isoformat(),
        trade_action=outcome.trade_action.value,
        executed=outcome.executed,
        pnl_per_lot=str(outcome.pnl_per_lot),
        phase=outcome.phase,
    )

    if outcome.executed and outcome.pnl_per_lot is not None:
        print(
            f"✓ Outcome recorded for {trade_date}: {outcome.trade_action.value} "
            f"| P&L: ₹{outcome.pnl_per_lot} per lot"
        )
    else:
        print(f"✓ Outcome recorded for {trade_date}: {outcome.trade_action.value} | not executed")


def run_report_phase(args: argparse.Namespace) -> None:
    from_date = _parse_date(args.from_date, "from")
    to_date = _parse_date(args.to_date, "to")

    store = SignalStore(settings.db_path)
    store.init_db()
    outcomes = store.get_all_outcomes(from_date=from_date, to_date=to_date, phase=args.phase)
    if not outcomes:
        print("No signal outcomes recorded for the requested window.")
        return

    close_by_date = {o.trade_date: o.nifty_close for o in outcomes}
    days = _load_days(store, outcomes)

    period = f"{outcomes[0].trade_date.isoformat()} → {outcomes[-1].trade_date.isoformat()}"
    sections = [
        _overall_section(outcomes),
        _per_model_section(days, close_by_date),
        _confidence_section(outcomes, days),
        _no_trade_section(outcomes, days),
        _phase_section(outcomes),
    ]

    out = [
        "Signal Pipeline Performance Report",
        f"Period: {period}  |  Phase: {args.phase or 'all'}",
        _RULE,
    ]
    for i, section in enumerate(sections):
        out.extend(section)
        if i < len(sections) - 1:
            out.append("")
    out.append(_RULE)
    report = "\n".join(out)
    print(report)
    _notify_report(report)

    logger.info(
        "signal_report_generated",
        outcomes=len(outcomes),
        phase=args.phase or "all",
        from_date=from_date.isoformat() if from_date else None,
        to_date=to_date.isoformat() if to_date else None,
    )


def main() -> None:
    args = _parse_args()

    do_record = args.auto or not args.report_only
    do_report = args.report_only or not args.auto

    try:
        trade_date = date.fromisoformat(args.trade_date)
    except ValueError:
        print(f"ERROR: --date must be YYYY-MM-DD, got: {args.trade_date}", file=sys.stderr)
        sys.exit(1)

    if do_record:
        if guard_trading_day(logger, "signal_eod", trade_date):
            return
    else:
        if guard_trading_day(logger, "signal_eod"):
            return

    if do_record:
        try:
            run_record_phase(args)
        # Intent: isolate record failure so report still runs.
        # noqa BLE001: catch-all needed to prevent cron death on formatting/network errors.
        except Exception as exc:  # noqa: BLE001
            logger.error("signal_record_phase_failed", error=str(exc))
            print(f"ERROR (record phase): {exc}", file=sys.stderr)
            if not do_report:
                sys.exit(1)
            print("Continuing to report phase despite record failure...")

    if do_report:
        try:
            run_report_phase(args)
        # Intent: convert uncaught report failure to clean exit(1).
        # noqa BLE001: catch-all needed to log before exit.
        except Exception as exc:  # noqa: BLE001
            logger.error("signal_report_phase_failed", error=str(exc))
            print(f"ERROR (report phase): {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    setup_logging()
    main()
