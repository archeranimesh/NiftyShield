#!/usr/bin/env python3
"""On-demand performance report for the multi-LLM directional signal pipeline.

Run manually — no cron. Aggregates every ``SignalOutcome`` in the window against
its ``DailySignal`` / ``SignalResponse`` rows and the 09:10 ``MarketSnapshot``,
then prints OVERALL, per-model direction accuracy, confidence calibration,
NO_TRADE accuracy and a phase breakdown, plus a deterministic coin-flip baseline.

Usage:
    python -m scripts.signal_report
    python -m scripts.signal_report --from 2026-08-01 --to 2026-10-31
    python -m scripts.signal_report --phase openrouter_only
    python -m scripts.signal_report --phase search_enabled

Judgment calls (spec gaps in docs/plan/signals/signals_stories.md §S5.4):
- No ``nifty_open`` is stored anywhere; the 09:10 ``MarketSnapshot.nifty_spot``
  is used as the open proxy for direction accuracy and the NO_TRADE move check.
  Days with no stored snapshot are excluded from those two sections.
- Confidence calibration buckets on ``round(DailySignal.consensus_confidence)``.
- The random baseline uses ``hashlib.md5`` (not ``hash()``, which is salted per
  process) so the report is reproducible: coin flip matches the signal direction
  -> actual P&L, else a full long-premium loss.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from statistics import mean

import structlog

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.config import settings
from src.market_calendar import is_trading_day, market_today
from src.notifications.telegram import build_notifier
from src.paper.constants import LOT_SIZE
from src.signals.models import (
    DailySignal,
    Direction,
    MarketSnapshot,
    SignalOutcome,
    SignalResponse,
    TradeAction,
)
from src.signals.store import SignalStore
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.signal_report"
logger = structlog.get_logger(_SCRIPT_NAME)

load_dotenv()

_SIGNIFICANCE_THRESHOLD = 50
_MOVE_THRESHOLD = Decimal("0.005")  # 0.5% — NO_TRADE "market moved" cutoff
_RULE = "─" * 49


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="On-demand performance report for the directional signal pipeline.",
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Inclusive lower bound on trade_date. Default: unbounded.",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Inclusive upper bound on trade_date. Default: unbounded.",
    )
    parser.add_argument(
        "--phase",
        default=None,
        choices=["openrouter_only", "search_enabled"],
        help="Restrict to a single pipeline phase. Default: all phases.",
    )
    return parser.parse_args()


def _parse_date(raw: str | None, label: str) -> date | None:
    """Parse an optional ``YYYY-MM-DD`` CLI argument, exiting 1 on a bad value."""
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        print(f"ERROR: --{label} must be YYYY-MM-DD, got: {raw!r}", file=sys.stderr)
        sys.exit(1)


def _pct(num: int, denom: int) -> float:
    """Percentage ``num / denom``, or ``0.0`` when ``denom`` is zero."""
    return 100.0 * num / denom if denom else 0.0


def _coin_flip_matches(trade_date: date, action: TradeAction) -> bool:
    """Deterministic coin flip: True when the random pick matches the signal.

    ``hash()`` is salted per process (PYTHONHASHSEED), so md5 is used instead to
    keep the baseline reproducible across runs.
    """
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
    return False  # NEUTRAL is always counted incorrect


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
    """Wrap the plain-text report in a MarkdownV2 fenced code block.

    Telegram does not parse entities inside a fence, so only ``\\`` and
    ````` need escaping (a backslash renders literally inside a fence — the
    general ``escape_markdown`` must NOT be used on fence content).

    Args:
        body: The already-rendered ``"\\n".join(out)`` report text.

    Returns:
        The body wrapped as ```` ``` ````-fenced MarkdownV2, fence-safe.
    """
    safe = body.replace("\\", "\\\\").replace("`", "\\`")
    return f"```\n{safe}\n```"


def _notify(body: str) -> None:
    """Push the report to Telegram; non-fatal when no notifier is configured."""
    notifier = build_notifier()
    if notifier is None:
        return
    try:
        asyncio.run(notifier.send(_format_report_message(body)))
    except Exception as exc:  # noqa: BLE001 — report already printed; send failure must not crash the cron
        logger.warning("signal_report_notify_failed", error=str(exc))


def main() -> None:
    """CLI entry point — load outcomes for the window and print the report."""
    args = _parse_args()
    today = market_today()
    if not is_trading_day(today):
        logger.info("signal_report.skip_non_trading_day", date=today.isoformat())
        return

    from_date = _parse_date(args.from_date, "from")
    to_date = _parse_date(args.to_date, "to")

    store = SignalStore(settings.db_path)
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
    _notify(report)

    logger.info(
        "signal_report_generated",
        outcomes=len(outcomes),
        phase=args.phase or "all",
        from_date=from_date.isoformat() if from_date else None,
        to_date=to_date.isoformat() if to_date else None,
    )


if __name__ == "__main__":
    setup_logging()
    main()
