#!/usr/bin/env python3
"""6-month evaluation report + go-live gate for the signals paper track (SPT-7).

Run manually — no cron, unlike ``scripts/signal_report.py`` (the advisory-side
report). Aggregates ``paper_signal_entries`` / ``paper_signal_marks`` /
``paper_exit_events`` for ``strategy_name='paper_signal_track_v1'`` over a
``--from``/``--to`` window (default: first paper entry -> +6 calendar months),
grouped by ``ruleset_version`` (v1/v2 never pooled), then evaluates gates
G1-G9 + the operational checklist from the SPT-1 ruling (all-pass, no
composite score).

Usage:
    python -m scripts.signal_paper_report
    python -m scripts.signal_paper_report --from 2026-09-01 --to 2027-03-01

Judgment calls (spec gaps — SPT-4/SPT-5/SPT-6 are not built yet, so this report
is written entirely against SPT-2's schema/store methods + fixture-shaped data;
see docs/plan/signals-paper-track/stories.md SPT-7):

- ``SignalExitReason`` (TARGET/STOP_LOSS/TIME_EXIT/TRAILING_STOP) does not
  exist yet (SPT-5). Exit reason is read off ``paper_exit_events.exit_signal``
  (an ``ExitSignal`` value written today by any close-path caller) and mapped
  via ``_EXIT_REASON_MAP`` onto the future SPT-5 vocabulary; unmapped values
  fall into ``OTHER``. Revisit this map once SPT-5 ships its own enum.
- VIX regime (G3) and the VIX bucket use ``SignalPaperEntry.entry_vix`` only
  (the single value captured at entry) — ``paper_signal_marks`` carries no
  VIX column, so "VIX > 18 while a position was open" cannot be evaluated
  intraday from persisted data yet.
- Exit-side slippage is not persisted separately for this track (only
  ``entry_slippage`` is). G9's round-trip slippage assumes the exit leg pays
  the same modelled ``s`` as the entry leg: ratio = ``2 * entry_slippage / E``.
- "Missed ticks" (no due-interval concept exists pre-SPT-4) is approximated
  as any inter-mark gap > 60s (2x the planned 30s cadence) within a cycle.
- The operational "all exit paths covered by SPT-5 unit tests" checklist item
  is reported as a static claim, not evaluated — SPT-5 does not exist yet.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import mean, median, quantiles

import structlog

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.config import settings
from src.db import connect
from src.paper.constants import STRATEGY_SIGNAL_TRACK
from src.paper.models import SignalMark, SignalPaperEntry
from src.paper.store import PaperStore
from src.signals.store import SignalStore
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.signal_paper_report"
logger = structlog.get_logger(_SCRIPT_NAME)

load_dotenv()

_RULE = "─" * 60
_EXIT_REASON_MAP = {
    "PROFIT_TARGET": "TARGET",
    "LOSS_STOP": "STOP_LOSS",
    "TIME_STOP": "TIME_EXIT",
}
_STALE_GAP_S = 60  # 2x the planned 30s cadence — "missed tick" proxy


@dataclass(frozen=True)
class ClosedCycle:
    """One closed signals-paper-track round trip, joined for reporting."""

    entry: SignalPaperEntry
    exit_price: Decimal
    exit_date: date
    qty: int
    exit_reason: str | None
    marks: list[SignalMark]

    @property
    def pnl(self) -> Decimal:
        return (self.exit_price - self.entry.entry_premium) * self.qty


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Signals paper track — 6-month evaluation report + go-live gate.",
    )
    parser.add_argument("--from", dest="from_date", default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", default=None, metavar="YYYY-MM-DD")
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


def load_closed_cycles(db_path: str | Path) -> list[ClosedCycle]:
    """Join closed signals-paper-track entries to their SELL fill + exit event.

    Entries and SELL rows are paired by chronological order (the same
    invariant ``PaperStore.cumulative_pnl`` relies on: ``open_signal_entry``
    enforces one position at a time, so cycles never overlap). The exit
    reason is an exact join on ``paper_exit_events.trade_id``.
    """
    store = PaperStore(db_path)
    with connect(db_path) as conn:
        entries = conn.execute(
            """SELECT e.* FROM paper_signal_entries e
               JOIN paper_trades t ON t.id = e.trade_id
               WHERE t.state = 'CLOSED' AND t.strategy_name = ?
               ORDER BY e.signal_date, e.trade_id""",
            (STRATEGY_SIGNAL_TRACK,),
        ).fetchall()
        sells = conn.execute(
            """SELECT price, quantity, trade_date FROM paper_trades
               WHERE strategy_name = ? AND action = 'SELL'
               ORDER BY trade_date, id""",
            (STRATEGY_SIGNAL_TRACK,),
        ).fetchall()
        events = conn.execute(
            """SELECT trade_id, exit_signal FROM paper_exit_events
               WHERE strategy_name = ?""",
            (STRATEGY_SIGNAL_TRACK,),
        ).fetchall()
    events_by_trade = {row["trade_id"]: row["exit_signal"] for row in events}

    cycles = []
    for entry_row, sell_row in zip(entries, sells, strict=True):
        trade_id = entry_row["trade_id"]
        entry = store.get_entries(
            date.fromisoformat(entry_row["signal_date"]),
            date.fromisoformat(entry_row["signal_date"]),
        )
        matched = next((e for e in entry if e.trade_id == trade_id), None)
        if matched is None:  # pragma: no cover — defensive, ordering guarantees a match
            continue
        cycles.append(
            ClosedCycle(
                entry=matched,
                exit_price=Decimal(sell_row["price"]),
                exit_date=date.fromisoformat(sell_row["trade_date"]),
                qty=sell_row["quantity"],
                exit_reason=events_by_trade.get(str(trade_id)),
                marks=store.get_marks(trade_id),
            )
        )
    return cycles


def _default_window(cycles: list[ClosedCycle]) -> tuple[date, date]:
    """First paper entry -> +6 calendar months, or today's date if no entries."""
    if not cycles:
        today = date.today()
        return today, today
    first = min(c.entry.signal_date for c in cycles)
    return first, first + timedelta(days=183)


def _filter_window(cycles: list[ClosedCycle], from_: date, to: date) -> list[ClosedCycle]:
    return [c for c in cycles if from_ <= c.entry.signal_date <= to]


def _by_ruleset(cycles: list[ClosedCycle]) -> dict[str, list[ClosedCycle]]:
    grouped: dict[str, list[ClosedCycle]] = defaultdict(list)
    for c in cycles:
        grouped[c.entry.ruleset_version].append(c)
    return grouped


# ── metrics ──────────────────────────────────────────────────────────────────


def _pct(num: int, denom: int) -> float:
    return 100.0 * num / denom if denom else 0.0


def compute_metrics(cycles: list[ClosedCycle]) -> dict[str, object]:
    """Full metric set for one ruleset-version cohort of closed cycles."""
    pnls = [c.pnl for c in cycles]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total = sum(pnls, Decimal("0"))
    gross_win = sum(wins, Decimal("0"))
    gross_loss = -sum(losses, Decimal("0"))
    equity_curve, peak, max_dd = Decimal("0"), Decimal("0"), Decimal("0")
    streak = max_streak = 0
    for c in sorted(cycles, key=lambda c: c.exit_date):
        equity_curve += c.pnl
        peak = max(peak, equity_curve)
        max_dd = max(max_dd, peak - equity_curve)
        streak = streak + 1 if c.pnl < 0 else 0
        max_streak = max(max_streak, streak)

    by_action: dict[str, list[Decimal]] = defaultdict(list)
    for c in cycles:
        by_action[c.entry.trade_action].append(c.pnl)

    exit_hist: dict[str, int] = defaultdict(int)
    for c in cycles:
        exit_hist[_EXIT_REASON_MAP.get(c.exit_reason or "", "OTHER")] += 1

    return {
        "n": len(cycles),
        "total_pnl": total,
        "expectancy": mean(pnls) if pnls else Decimal("0"),
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else None,
        "win_rate": _pct(len(wins), len(cycles)),
        "win_rate_by_action": {
            a: _pct(sum(1 for p in ps if p > 0), len(ps)) for a, ps in by_action.items()
        },
        "avg_win": mean(wins) if wins else Decimal("0"),
        "avg_loss": mean(losses) if losses else Decimal("0"),
        "max_drawdown": max_dd,
        "longest_losing_streak": max_streak,
        "exit_reason_histogram": dict(exit_hist),
        "wins": len(wins),
        "losses": len(losses),
    }


def _incidents(cycles: list[ClosedCycle]) -> list[ClosedCycle]:
    """Trades losing > 1.5x the expected SL loss (gap-through / stale-data candidates)."""
    out = []
    for c in cycles:
        expected_sl_loss = c.entry.sl_pct * c.entry.entry_premium * c.qty
        if c.pnl < 0 and -c.pnl > Decimal("1.5") * expected_sl_loss:
            out.append(c)
    return out


def _inter_tick_jumps(cycles: list[ClosedCycle]) -> list[float]:
    jumps = []
    for c in cycles:
        marks = sorted(c.marks, key=lambda m: m.ts)
        for prev, cur in zip(marks, marks[1:], strict=False):
            jumps.append(float(abs(cur.mark - prev.mark) / c.entry.entry_premium))
    return jumps


def _missed_tick_count(cycles: list[ClosedCycle]) -> int:
    missed = 0
    for c in cycles:
        marks = sorted(c.marks, key=lambda m: m.ts)
        for prev, cur in zip(marks, marks[1:], strict=False):
            if (cur.ts - prev.ts).total_seconds() > _STALE_GAP_S:
                missed += 1
    return missed


def _slippage_ratios(cycles: list[ClosedCycle]) -> list[float]:
    return [
        float(2 * c.entry.entry_slippage / c.entry.entry_premium)
        for c in cycles
        if c.entry.entry_premium > 0
    ]


def _reconciliation_pct(cycles: list[ClosedCycle], signal_store: SignalStore) -> float:
    if not cycles:
        return 100.0
    matched = sum(1 for c in cycles if signal_store.get_outcome(c.entry.signal_date) is not None)
    return _pct(matched, len(cycles))


# ── gate ─────────────────────────────────────────────────────────────────────


def evaluate_gate(
    cycles: list[ClosedCycle], metrics: dict[str, object], signal_store: SignalStore
) -> dict[str, tuple[bool, str]]:
    """G1-G9 + operational checks. All-pass, no composite score.

    G7 (win rate) is deliberately absent from the pass/fail dict — the spec
    marks it "not gated, reported only" (stories.md SPT-7). It is reported via
    ``compute_metrics()["win_rate"]`` and surfaced explicitly as a checklist
    line in ``_render_group`` instead of a pass/fail gate.
    """
    exit_hist = metrics["exit_reason_histogram"]
    vix_over_18 = any(c.entry.entry_vix is not None and c.entry.entry_vix > 18 for c in cycles)
    slippage_ratios = _slippage_ratios(cycles)
    unresolved_overnight = sum(1 for c in cycles if c.exit_date != c.entry.signal_date)

    gates: dict[str, tuple[bool, str]] = {}
    gates["G1_window"] = (
        len(cycles) >= 40,
        f"{len(cycles)} closed trades (need >=50, hard floor 40)",
    )
    gates["G2_exit_path"] = (
        all(exit_hist.get(r, 0) >= 5 for r in ("STOP_LOSS", "TARGET", "TIME_EXIT")),
        f"exit histogram {exit_hist} (need >=5 each of STOP_LOSS/TARGET/TIME_EXIT)",
    )
    gates["G3_regime"] = (
        vix_over_18,
        "ok" if vix_over_18 else "no cycle with entry_vix > 18",
    )
    gates["G4_net_pnl"] = (
        metrics["total_pnl"] > 0,
        f"total P&L = {metrics['total_pnl']}",
    )
    gates["G5_expectancy"] = (
        metrics["expectancy"] > 0,
        f"expectancy = {metrics['expectancy']}",
    )
    pf = metrics["profit_factor"]
    gates["G6_profit_factor"] = (
        pf is not None and pf >= Decimal("1.20"),
        f"profit factor = {pf}",
    )
    dd_limit = Decimal("8") * -metrics["avg_loss"] if metrics["avg_loss"] < 0 else Decimal("0")
    gates["G8_drawdown"] = (
        dd_limit > 0 and metrics["max_drawdown"] <= dd_limit,
        f"max_drawdown={metrics['max_drawdown']} limit={dd_limit}",
    )
    median_slip = median(slippage_ratios) if slippage_ratios else 0.0
    gates["G9_cost_sanity"] = (
        median_slip < 0.08,
        f"median round-trip slippage = {median_slip:.2%}",
    )
    gates["OP_no_overnight"] = (
        unresolved_overnight == 0,
        f"{unresolved_overnight} overnight cycle(s)",
    )
    recon = _reconciliation_pct(cycles, signal_store)
    gates["OP_reconciliation"] = (
        recon >= 95.0,
        f"{recon:.1f}% matched to record_signal_outcome",
    )
    return gates


# ── report ───────────────────────────────────────────────────────────────────


def _render_group(version: str, cycles: list[ClosedCycle], signal_store: SignalStore) -> list[str]:
    metrics = compute_metrics(cycles)
    gate = evaluate_gate(cycles, metrics, signal_store)
    jumps = _inter_tick_jumps(cycles)
    incidents = _incidents(cycles)
    by_action = metrics["win_rate_by_action"]
    lines = [f"RULESET {version}", _RULE]
    lines += [
        f"  Closed trades          : {metrics['n']}",
        f"  Cumulative net P&L     : {metrics['total_pnl']}",
        f"  Expectancy/trade       : {metrics['expectancy']}",
        f"  Profit factor          : {metrics['profit_factor']}",
        f"  Win rate (G7, reported only, not gated): {metrics['win_rate']:.1f}%",
        f"    by action              : {by_action}",
        f"  Avg win / avg loss     : {metrics['avg_win']} / {metrics['avg_loss']}",
        f"  Max drawdown           : {metrics['max_drawdown']}",
        f"  Longest losing streak  : {metrics['longest_losing_streak']}",
        f"  Exit reason histogram  : {metrics['exit_reason_histogram']}",
        f"  Incidents (>1.5x SL)   : {len(incidents)}",
    ]
    if jumps:
        qs = quantiles(jumps, n=100) if len(jumps) >= 2 else [jumps[0]] * 99
        lines.append(f"  Inter-tick jump p50/p90: {qs[49]:.2%} / {qs[89]:.2%}")
    lines.append(f"  Missed-tick count      : {_missed_tick_count(cycles)}")
    lines.append("")
    lines.append("  GATE")
    all_pass = True
    for name, (passed, detail) in gate.items():
        all_pass &= passed
        lines.append(f"    [{'PASS' if passed else 'FAIL'}] {name}: {detail}")
    lines.append("    [CHECKLIST] OP_exit_paths_tested: SPT-5 does not exist yet — not evaluated")
    lines.append(f"  ALL-PASS: {'YES' if all_pass else 'NO'}")
    return lines


def main() -> None:
    """CLI entry point — load closed cycles for the window and print the report."""
    args = _parse_args()
    from_arg = _parse_date(args.from_date, "from")
    to_arg = _parse_date(args.to_date, "to")

    all_cycles = load_closed_cycles(settings.db_path)
    default_from, default_to = _default_window(all_cycles)
    from_date = from_arg or default_from
    to_date = to_arg or default_to

    cycles = _filter_window(all_cycles, from_date, to_date)
    if not cycles:
        print(f"No closed signals-paper-track cycles in window {from_date} -> {to_date}.")
        return

    signal_store = SignalStore(settings.db_path)
    out = [
        "Signals Paper Track — Evaluation Report",
        f"Period: {from_date.isoformat()} -> {to_date.isoformat()}",
        _RULE,
    ]
    for version, group in sorted(_by_ruleset(cycles).items()):
        out.extend(_render_group(version, group, signal_store))
        out.append("")
    report = "\n".join(out)
    print(report)

    logger.info(
        "signal_paper_report_generated",
        n_cycles=len(cycles),
        from_date=from_date.isoformat(),
        to_date=to_date.isoformat(),
    )


if __name__ == "__main__":
    setup_logging()
    main()
