"""Pure portfolio summary formatting — no I/O, no side effects.

Converts a PortfolioSummary (or the raw inputs needed to build one) into
human-readable multi-line strings for console output and Telegram messages.

All functions here are fully unit-testable without a DB, network, or .env.
Extracted from scripts/daily_snapshot.py (TODO 5).

Two public functions:
    _format_protection_stats  — FinRakshak hedge effectiveness lines
    _format_combined_summary  — full combined portfolio summary string
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.models.portfolio import DailySnapshot, PortfolioSummary, Strategy
from src.portfolio.summary import _build_portfolio_summary
from src.utils.number_formatting import fmt_inr


def _format_protection_stats(summary: PortfolioSummary) -> list[str]:
    """Build FinRakshak hedge effectiveness lines for the snapshot output.

    Compares MF day-change against FinRakshak day-change to answer:
    "did the hedge offset the day's MF move?"

    Returns an empty list when either delta is unavailable (first run,
    or finrakshak not in the portfolio on that date).

    Args:
        summary: Fully computed PortfolioSummary.

    Returns:
        List of formatted lines (ready to extend into a lines: list[str]).
        Empty list when insufficient data.
    """
    if summary.mf_day_delta is None or summary.finrakshak_day_delta is None:
        return []

    net = summary.mf_day_delta + summary.finrakshak_day_delta
    verdict = "✅ Protected" if net >= 0 else "⚠️  Exposed"
    return [
        "",
        "  ── FinRakshak Protection ──────────────────────────────",
        f"  MF Δday             : {fmt_inr(summary.mf_day_delta, sign=True, width=15)}",
        f"  FinRakshak Δday     : {fmt_inr(summary.finrakshak_day_delta, sign=True, width=15)}",
        "  ───────────────────────────────────────────────────────",
        f"  Net (MF + hedge)    : {fmt_inr(net, sign=True, width=15)}  {verdict}",
    ]


def _format_combined_summary(
    strategies: list[Strategy],
    prices: dict[str, float],
    strategy_pnls: dict[str, object],
    mf_pnl: object | None,
    prev_snapshots: dict[int, DailySnapshot] | None = None,
    prev_mf_pnl: object | None = None,
    snap_date: date | None = None,
    dhan_summary: object | None = None,
    nuvama_summary: object | None = None,
    nuvama_options_summary: object | None = None,
) -> str:
    """Build the combined portfolio summary as a formatted string.

    Two layouts depending on whether prior-day data is available:

    Waterfall (has_deltas=True, standard after first run):
      Header → Today's change waterfall by segment → Hedge effectiveness
      (FinRakshak inline after waterfall) → single context line with
      total value + all-time P&L.

    Fallback (has_deltas=False, first run):
      Header → Equity / Bonds / Derivatives / Total sections (values +
      P&L %) → FinRakshak protection appended if both deltas available.

    The returned string always starts with the status header line so it
    can be sent to Telegram directly without a separate subject line.

    Args:
        strategies: All loaded Strategy objects.
        prices: instrument_key → LTP (current day).
        strategy_pnls: strategy name → StrategyPnL (from compute_pnl).
        mf_pnl: Completed MF PortfolioPnL, or None if the MF fetch failed.
        prev_snapshots: {leg_id: DailySnapshot} from get_prev_snapshots(), or None.
        prev_mf_pnl: PortfolioPnL for the prior date, or None.
        snap_date: Snapshot date stored in the summary (defaults to today).
        dhan_summary: DhanPortfolioSummary, or None if Dhan unavailable.
        nuvama_summary: NuvamaBondSummary, or None if Nuvama unavailable.
        nuvama_options_summary: NuvamaOptionsSummary, or None if unavailable.

    Returns:
        Multi-line formatted summary string (no trailing newline).
    """
    summary = _build_portfolio_summary(
        snap_date=snap_date or date.today(),
        strategies=strategies,
        prices=prices,
        strategy_pnls=strategy_pnls,
        mf_pnl=mf_pnl,
        prev_snapshots=prev_snapshots,
        prev_mf_pnl=prev_mf_pnl,
        dhan_summary=dhan_summary,
        nuvama_summary=nuvama_summary,
        nuvama_options_summary=nuvama_options_summary,
    )

    has_deltas = summary.total_day_delta is not None
    date_str = summary.snapshot_date.strftime("%Y-%m-%d")
    if has_deltas:
        status_emoji = "🟢" if summary.total_day_delta >= 0 else "🔴"
    else:
        status_emoji = "🟢" if summary.total_pnl >= 0 else "🔴"

    lines: list[str] = []

    # ── Header (included in both paths; used directly as Telegram message) ──
    lines.append(f"{status_emoji} NiftyShield | {date_str}")

    if has_deltas:
        # ── Waterfall: contribution to today's change ──────────────────
        eq_subtotal = summary.mf_value + summary.etf_value + summary.dhan_equity_value
        bonds_subtotal = summary.dhan_bond_value + summary.nuvama_bond_value
        eq_day = (
            (summary.mf_day_delta or Decimal("0"))
            + (summary.etf_day_delta or Decimal("0"))
            + (summary.dhan_equity_day_delta or Decimal("0"))
        )
        bd_day = (
            (summary.dhan_bond_day_delta or Decimal("0"))
            + (summary.nuvama_bond_day_delta or Decimal("0"))
        )
        options_day = summary.options_day_delta or Decimal("0")
        equity_pct = int(eq_subtotal / summary.total_value * 100) if summary.total_value else 0
        bonds_pct = int(bonds_subtotal / summary.total_value * 100) if summary.total_value else 0
        SEP = "  " + "─" * 34

        lines += [
            "",
            f"📊 Today: {fmt_inr(summary.total_day_delta, sign=True)}",
            "",
        ]
        lines.append(
            f"  {'Equity':<14} {fmt_inr(eq_day, sign=True, width=12)}"
            f"  {'▲' if eq_day >= 0 else '▼'}  {equity_pct}%"
        )
        if summary.mf_available:
            lines.append(
                f"  {'├ MF':<14} {fmt_inr(summary.mf_day_delta or Decimal('0'), sign=True, width=12)}"
            )
        else:
            lines.append("  ├ MF                  [failed]")
        lines.append(
            f"  {'├ ETF':<14} {fmt_inr(summary.etf_day_delta or Decimal('0'), sign=True, width=12)}"
        )
        if summary.dhan_available and summary.dhan_equity_value > 0:
            lines.append(
                f"  {'└ Dhan Equity':<14} "
                f"{fmt_inr(summary.dhan_equity_day_delta or Decimal('0'), sign=True, width=12)}"
            )
        lines.append(
            f"  {'Bonds':<14} {fmt_inr(bd_day, sign=True, width=12)}"
            f"  {'▲' if bd_day >= 0 else '▼'}  {bonds_pct}%"
        )
        if summary.nuvama_available and summary.nuvama_bond_value > 0:
            lines.append(
                f"  {'├ Nuvama Bonds':<14} "
                f"{fmt_inr(summary.nuvama_bond_day_delta or Decimal('0'), sign=True, width=12)}"
            )
        elif not summary.nuvama_available:
            lines.append("  ├ Nuvama Bonds        [unavailable]")
        if summary.dhan_available and summary.dhan_bond_value > 0:
            lines.append(
                f"  {'└ Dhan Bonds':<14} "
                f"{fmt_inr(summary.dhan_bond_day_delta or Decimal('0'), sign=True, width=12)}"
            )
        elif not summary.dhan_available:
            lines.append("  └ Dhan Bonds          [unavailable]")
        lines.append(
            f"  {'Derivatives':<14} {fmt_inr(options_day, sign=True, width=12)}"
            f"  {'▲' if options_day >= 0 else '▼'}"
        )
        lines.append(f"  {'├ Finideas P&L':<14} {fmt_inr(summary.options_pnl, sign=True, width=12)}")
        if summary.nuvama_options_available:
            lines.append(f"  {'└ Nuvama P&L':<14} {fmt_inr(summary.nuvama_options_pnl, sign=True, width=12)}")
        else:
            lines.append(f"  {'└ Nuvama P&L':<14} [unavailable]")
        lines.append(SEP)
        lines.append(f"  {'Net':<14} {fmt_inr(summary.total_day_delta, sign=True, width=12)}  {status_emoji}")

        # ── Hedge (FinRakshak) — inline after waterfall ────────────────
        if summary.mf_day_delta is not None and summary.finrakshak_day_delta is not None:
            net = summary.mf_day_delta + summary.finrakshak_day_delta
            verdict = "✅ Protected" if net >= 0 else "⚠️  Exposed"
            lines += [
                "",
                "🛡 Hedge (FinRakshak)",
                f"  MF Δ        {fmt_inr(summary.mf_day_delta, sign=True, width=14)}",
                f"  Hedge Δ     {fmt_inr(summary.finrakshak_day_delta, sign=True, width=14)}",
                SEP,
                f"  Net         {fmt_inr(net, sign=True, width=14)}  {verdict}",
            ]
            if summary.nuvama_options_available:
                lines.append("")
                lines.append(f"  Nuvama M2M P&L      {fmt_inr(summary.nuvama_options_unrealized, sign=True, width=14)}")
                lines.append(f"  Nuvama Realized     {fmt_inr(summary.nuvama_options_realized, sign=True, width=14)}")

        # ── Context line: total value + all-time P&L (signal vs scoreboard) ──
        lines += [
            "",
            f"💰 Total: ₹{fmt_inr(summary.total_value)}  |  "
            f"P&L {fmt_inr(summary.total_pnl, sign=True)} ({summary.total_pnl_pct:+}%) all-time",
        ]
        if not summary.mf_available:
            lines.append("  NOTE: MF fetch failed — MF value excluded from total")
        if not summary.dhan_available:
            lines.append("  NOTE: Dhan unavailable — Dhan values excluded from total")
        if not summary.nuvama_available:
            lines.append("  NOTE: Nuvama unavailable — Nuvama bonds excluded from total")

    else:
        # ── Fallback: no prior-day data — show portfolio values ────────
        def _delta(d: Decimal | None) -> str:
            return f"  Δday: {fmt_inr(d, sign=True, width=12)}" if d is not None else ""

        def _pnl_str(pnl: Decimal, pct: Decimal | None) -> str:
            pct_part = f" ({pct:+}%)" if pct is not None else ""
            return f"P&L: {fmt_inr(pnl, sign=True, width=11)}{pct_part}"

        eq_subtotal = summary.mf_value + summary.etf_value + summary.dhan_equity_value
        bonds_subtotal = summary.dhan_bond_value + summary.nuvama_bond_value

        # ── Equity section ─────────────────────────────────────────────
        lines.append("")
        lines.append("  ── Equity ─────────────────────────────────────────────")
        if summary.mf_available:
            lines.append(
                f"  MF (mutual funds)   : ₹{fmt_inr(summary.mf_value, width=14)}"
                f"{_delta(summary.mf_day_delta)}"
            )
            lines.append(
                f"                        {_pnl_str(summary.mf_pnl, summary.mf_pnl_pct)}"
            )
        else:
            lines.append(
                f"  MF (mutual funds)   :          [failed]{_delta(summary.mf_day_delta)}"
            )
        lines.append(
            f"  Finideas ETF        : ₹{fmt_inr(summary.etf_value, width=14)}"
            f"{_delta(summary.etf_day_delta)}"
        )
        lines.append(f"                        (basis ₹{fmt_inr(summary.etf_basis)})")
        if summary.dhan_available and summary.dhan_equity_value > 0:
            lines.append(
                f"  Dhan Equity         : ₹{fmt_inr(summary.dhan_equity_value, width=14)}"
                f"{_delta(summary.dhan_equity_day_delta)}"
            )
            lines.append(
                f"                        {_pnl_str(summary.dhan_equity_pnl, summary.dhan_equity_pnl_pct)}"
            )
        lines.append("  ───────────────────────────────────────────────────────")
        lines.append(f"  Equity subtotal     : ₹{fmt_inr(eq_subtotal, width=14)}")

        # ── Bonds section ──────────────────────────────────────────────
        lines.append("")
        lines.append("  ── Bonds ──────────────────────────────────────────────")
        _has_any_bonds = False
        if summary.dhan_available and summary.dhan_bond_value > 0:
            lines.append(
                f"  Dhan Bonds          : ₹{fmt_inr(summary.dhan_bond_value, width=14)}"
                f"{_delta(summary.dhan_bond_day_delta)}"
            )
            lines.append(
                f"                        {_pnl_str(summary.dhan_bond_pnl, summary.dhan_bond_pnl_pct)}"
            )
            _has_any_bonds = True
        elif not summary.dhan_available:
            lines.append("  Dhan Bonds          :          [unavailable]")
        if summary.nuvama_available and summary.nuvama_bond_value > 0:
            lines.append(
                f"  Nuvama Bonds        : ₹{fmt_inr(summary.nuvama_bond_value, width=14)}"
                f"{_delta(summary.nuvama_bond_day_delta)}"
            )
            lines.append(
                f"                        {_pnl_str(summary.nuvama_bond_pnl, summary.nuvama_bond_pnl_pct)}"
            )
            _has_any_bonds = True
        elif not summary.nuvama_available:
            lines.append("  Nuvama Bonds        :          [unavailable]")
        if _has_any_bonds:
            lines.append("  ───────────────────────────────────────────────────────")
            lines.append(f"  Bonds subtotal      : ₹{fmt_inr(bonds_subtotal, width=14)}")
        elif summary.dhan_available and summary.nuvama_available:
            lines.append("  (no bond holdings)")

        # ── Derivatives section ─────────────────────────────────────────
        lines.append("")
        lines.append("  ── Derivatives ────────────────────────────────────────")
        lines.append(
            f"  Upstox options P&L  : {fmt_inr(summary.options_pnl, sign=True, width=15)}"
            f"{_delta(summary.options_day_delta)}"
        )
        if summary.nuvama_options_available:
            lines.append(
                f"  Nuvama options P&L  : {fmt_inr(summary.nuvama_options_pnl, sign=True, width=15)}"
                f"{_delta(summary.nuvama_options_day_delta)}"
            )

        # ── Total section ───────────────────────────────────────────────
        lines.append("")
        lines.append("  ═══════════════════════════════════════════════════════")
        lines.append(
            f"  Total value         : ₹{fmt_inr(summary.total_value, width=14)}"
            f"{_delta(summary.total_day_delta)}"
        )
        lines.append(f"  Total invested      : ₹{fmt_inr(summary.total_invested, width=14)}")
        lines.append(
            f"  Total P&L           : {fmt_inr(summary.total_pnl, sign=True, width=15)}"
            f"  ({summary.total_pnl_pct:+}%)"
        )
        if not summary.mf_available:
            lines.append("  NOTE: MF fetch failed — MF value excluded from total")
        if not summary.dhan_available:
            lines.append("  NOTE: Dhan unavailable — Dhan values excluded from total")
        if not summary.nuvama_available:
            lines.append("  NOTE: Nuvama unavailable — Nuvama bonds excluded from total")

        # FinRakshak protection appended at end in fallback mode
        lines.extend(_format_protection_stats(summary))

    return "\n".join(lines)
