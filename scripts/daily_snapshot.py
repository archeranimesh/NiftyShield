"""Record daily price snapshots for all portfolio strategies.

Two modes of operation:
  Live mode (default, no --date):
    Fetches live LTPs from Upstox V3 API, records to SQLite, exits.
    Designed for cron — no interactive prompts, returns exit code 0/1.

  Historical mode (--date YYYY-MM-DD):
    Reads already-recorded daily_snapshots and mf_nav_snapshots rows for that
    date from the local SQLite DB and prints the P&L summary. No API calls,
    no network, no .env required. Useful for reviewing past snapshots.

Import design:
    Only stdlib and the pure-computation helpers' types are imported at module
    level (Decimal, Path, Strategy, AssetType). All I/O-triggering imports
    (dotenv, create_client, stores, tracker) are deferred into the
    _async_main() / _historical_main() functions so that the pure helper
    functions are importable in tests with no side effects.

Usage:
    # Record today's snapshot (live fetch)
    python -m scripts.daily_snapshot

    # Query stored P&L for a past date (no API call)
    python -m scripts.daily_snapshot --date 2026-04-06

    # Custom DB path
    python -m scripts.daily_snapshot --db-path data/portfolio/portfolio.sqlite

Cron example (run at 3:45 PM IST on weekdays):
    45 15 * * 1-5 cd /path/to/NiftyShield && /path/to/python -m scripts.daily_snapshot >> logs/snapshot.log 2>&1
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Pure-computation helpers only need these types at import time — no I/O.
from src.models.portfolio import AssetType, DailySnapshot, PortfolioSummary, Strategy  # noqa: E402
from src.portfolio.summary import (  # noqa: E402
    _build_portfolio_summary,
    _build_prev_prices,
    _compute_prev_mf_pnl,
    _compute_strategy_pnl_from_prices,
    _etf_cost_basis,
    _etf_current_value,
)


# ── Pure helper functions — moved to src/portfolio/summary.py (TODO 5) ───────
# Re-exported here so callers and tests that import from this script keep
# working without change. Direct imports from src.portfolio.summary preferred
# for new code.


def _format_protection_stats(summary: "PortfolioSummary") -> list[str]:
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
        f"  MF Δday             : {summary.mf_day_delta:>+15,.0f}",
        f"  FinRakshak Δday     : {summary.finrakshak_day_delta:>+15,.0f}",
        "  ───────────────────────────────────────────────────────",
        f"  Net (MF + hedge)    : {net:>+15,.0f}  {verdict}",
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
            f"📊 Today: {summary.total_day_delta:>+,.0f}",
            "",
        ]
        lines.append(
            f"  {'Equity':<14} {eq_day:>+12,.0f}  {'▲' if eq_day >= 0 else '▼'}  {equity_pct}%"
        )
        if summary.mf_available:
            lines.append(
                f"  {'├ MF':<14} {(summary.mf_day_delta or Decimal('0')):>+12,.0f}"
            )
        else:
            lines.append("  ├ MF                  [failed]")
        lines.append(
            f"  {'├ ETF':<14} {(summary.etf_day_delta or Decimal('0')):>+12,.0f}"
        )
        if summary.dhan_available and summary.dhan_equity_value > 0:
            lines.append(
                f"  {'└ Dhan Equity':<14} {(summary.dhan_equity_day_delta or Decimal('0')):>+12,.0f}"
            )
        lines.append(
            f"  {'Bonds':<14} {bd_day:>+12,.0f}  {'▲' if bd_day >= 0 else '▼'}  {bonds_pct}%"
        )
        if summary.nuvama_available and summary.nuvama_bond_value > 0:
            lines.append(
                f"  {'├ Nuvama Bonds':<14} {(summary.nuvama_bond_day_delta or Decimal('0')):>+12,.0f}"
            )
        elif not summary.nuvama_available:
            lines.append("  ├ Nuvama Bonds        [unavailable]")
        if summary.dhan_available and summary.dhan_bond_value > 0:
            lines.append(
                f"  {'└ Dhan Bonds':<14} {(summary.dhan_bond_day_delta or Decimal('0')):>+12,.0f}"
            )
        elif not summary.dhan_available:
            lines.append("  └ Dhan Bonds          [unavailable]")
        lines.append(
            f"  {'Derivatives':<14} {options_day:>+12,.0f}  {'▲' if options_day >= 0 else '▼'}"
        )
        lines.append(SEP)
        lines.append(f"  {'Net':<14} {summary.total_day_delta:>+12,.0f}  {status_emoji}")

        # ── Hedge (FinRakshak) — inline after waterfall ────────────────
        if summary.mf_day_delta is not None and summary.finrakshak_day_delta is not None:
            net = summary.mf_day_delta + summary.finrakshak_day_delta
            verdict = "✅ Protected" if net >= 0 else "⚠️  Exposed"
            lines += [
                "",
                "🛡 Hedge (FinRakshak)",
                f"  MF Δ        {summary.mf_day_delta:>+14,.0f}",
                f"  Hedge Δ     {summary.finrakshak_day_delta:>+14,.0f}",
                SEP,
                f"  Net         {net:>+14,.0f}  {verdict}",
                f"  Options P&L {summary.options_pnl:>+14,.0f}",
            ]

        # ── Context line: total value + all-time P&L (signal vs scoreboard) ──
        lines += [
            "",
            f"💰 Total: ₹{summary.total_value:,.0f}  |  "
            f"P&L {summary.total_pnl:+,.0f} ({summary.total_pnl_pct:+}%) all-time",
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
            return f"  Δday: {d:>+12,.0f}" if d is not None else ""

        def _pnl_str(pnl: Decimal, pct: Decimal | None) -> str:
            pct_part = f" ({pct:+}%)" if pct is not None else ""
            return f"P&L: {pnl:>+11,.0f}{pct_part}"

        eq_subtotal = summary.mf_value + summary.etf_value + summary.dhan_equity_value
        bonds_subtotal = summary.dhan_bond_value + summary.nuvama_bond_value

        # ── Equity section ─────────────────────────────────────────────
        lines.append("")
        lines.append("  ── Equity ─────────────────────────────────────────────")
        if summary.mf_available:
            lines.append(
                f"  MF (mutual funds)   : ₹{summary.mf_value:>14,.0f}"
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
            f"  Finideas ETF        : ₹{summary.etf_value:>14,.0f}"
            f"{_delta(summary.etf_day_delta)}"
        )
        lines.append(f"                        (basis ₹{summary.etf_basis:,.0f})")
        if summary.dhan_available and summary.dhan_equity_value > 0:
            lines.append(
                f"  Dhan Equity         : ₹{summary.dhan_equity_value:>14,.0f}"
                f"{_delta(summary.dhan_equity_day_delta)}"
            )
            lines.append(
                f"                        {_pnl_str(summary.dhan_equity_pnl, summary.dhan_equity_pnl_pct)}"
            )
        lines.append("  ───────────────────────────────────────────────────────")
        lines.append(f"  Equity subtotal     : ₹{eq_subtotal:>14,.0f}")

        # ── Bonds section ──────────────────────────────────────────────
        lines.append("")
        lines.append("  ── Bonds ──────────────────────────────────────────────")
        _has_any_bonds = False
        if summary.dhan_available and summary.dhan_bond_value > 0:
            lines.append(
                f"  Dhan Bonds          : ₹{summary.dhan_bond_value:>14,.0f}"
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
                f"  Nuvama Bonds        : ₹{summary.nuvama_bond_value:>14,.0f}"
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
            lines.append(f"  Bonds subtotal      : ₹{bonds_subtotal:>14,.0f}")
        elif summary.dhan_available and summary.nuvama_available:
            lines.append("  (no bond holdings)")

        # ── Derivatives section ─────────────────────────────────────────
        lines.append("")
        lines.append("  ── Derivatives ────────────────────────────────────────")
        lines.append(
            f"  Options net P&L     : {summary.options_pnl:>+15,.0f}"
            f"{_delta(summary.options_day_delta)}"
        )

        # ── Total section ───────────────────────────────────────────────
        lines.append("")
        lines.append("  ═══════════════════════════════════════════════════════")
        lines.append(
            f"  Total value         : ₹{summary.total_value:>14,.0f}"
            f"{_delta(summary.total_day_delta)}"
        )
        lines.append(f"  Total invested      : ₹{summary.total_invested:>14,.0f}")
        lines.append(
            f"  Total P&L           : {summary.total_pnl:>+15,.0f}"
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


def _print_combined_summary(
    strategies: list[Strategy],
    prices: dict[str, float],
    strategy_pnls: dict[str, object],
    mf_pnl: object | None,
    prev_snapshots: dict[int, DailySnapshot] | None = None,
    prev_mf_pnl: object | None = None,
    snap_date: date | None = None,
    dhan_summary: object | None = None,
    nuvama_summary: object | None = None,
) -> None:
    """Print the combined portfolio summary including date header and all sections.

    Delegates to _format_combined_summary and prints the result.

    Args:
        strategies: All loaded Strategy objects.
        prices: instrument_key → LTP (current day).
        strategy_pnls: strategy name → StrategyPnL (from compute_pnl).
        mf_pnl: Completed MF PortfolioPnL, or None if the MF fetch failed.
        prev_snapshots: {leg_id: DailySnapshot} from get_prev_snapshots(), or None.
        prev_mf_pnl: PortfolioPnL for the prior date, or None.
        snap_date: Snapshot date stored in the summary (defaults to today).
        dhan_summary: DhanPortfolioSummary, or None if unavailable.
        nuvama_summary: NuvamaBondSummary, or None if unavailable.
    """
    print(_format_combined_summary(
        strategies, prices, strategy_pnls, mf_pnl, prev_snapshots, prev_mf_pnl,
        snap_date, dhan_summary, nuvama_summary,
    ))


# ── Historical query path — reads from DB, no API calls ──────────


def _historical_main(snap_date: date, db_path: Path) -> int:
    """Query stored snapshots for a past date and print the P&L summary.

    Reads daily_snapshots and mf_nav_snapshots rows that were already written
    by a previous live run. No network, no .env, no API token required.

    Args:
        snap_date: The date to query stored snapshots for.
        db_path: Path to the SQLite database.

    Returns:
        Exit code: 0 for success, 1 for any fatal error.
    """
    from src.mf.store import MFStore
    from src.mf.tracker import PortfolioPnL, aggregate_mf_pnl, compute_scheme_pnl
    from src.portfolio.store import PortfolioStore
    from src.portfolio.tracker import apply_trade_positions

    if not db_path.exists():
        print(f"  ERROR: DB not found at {db_path}")
        print("  Run 'python -m scripts.seed_portfolio' first.")
        return 1

    store = PortfolioStore(db_path)
    strategies = store.get_all_strategies()
    if not strategies:
        print("  ERROR: No strategies found in DB. Run seed_portfolio first.")
        return 1

    # ── Overlay trade-derived positions onto strategy leg definitions ─
    strategies = [
        apply_trade_positions(s, store.get_all_positions_for_strategy(s.name))
        for s in strategies
    ]

    snapshots_by_leg = store.get_snapshots_for_date(snap_date)
    if not snapshots_by_leg:
        print(f"  ERROR: No snapshots found for {snap_date.isoformat()}.")
        print("  Run without --date to record a live snapshot first.")
        return 1

    prev_snapshots = store.get_prev_snapshots(snap_date)

    # Build instrument_key → LTP from stored snapshots
    leg_id_to_key: dict[int, str] = {
        leg.id: leg.instrument_key  # type: ignore[misc]
        for strategy in strategies
        for leg in strategy.legs
        if leg.id is not None
    }
    prices: dict[str, float] = {
        leg_id_to_key[leg_id]: float(snap.ltp)
        for leg_id, snap in snapshots_by_leg.items()
        if leg_id in leg_id_to_key
    }

    # Nifty spot — pick from any snapshot that stored it
    underlying_price = next(
        (float(s.underlying_price) for s in snapshots_by_leg.values() if s.underlying_price),
        None,
    )
    if underlying_price:
        print(f"  Nifty spot (stored): {underlying_price:,.2f}")
    else:
        print("  Nifty spot: not recorded for this date.")

    # Compute P&L for each strategy from stored prices
    decimal_prices = {k: Decimal(str(v)) for k, v in prices.items()}
    strategy_pnls: dict[str, object] = {}
    for strategy in strategies:
        pnl = _compute_strategy_pnl_from_prices(strategy, decimal_prices)
        strategy_pnls[strategy.name] = pnl
        print(
            f"    {strategy.name}: "
            f"P&L: {pnl.total_pnl:+,.0f} ({pnl.total_pnl_percent:+.2f}%)"
        )

    # MF P&L from stored NAV snapshots
    mf_pnl: PortfolioPnL | None = None
    prev_mf_pnl: object | None = None
    mf_store = MFStore(db_path)
    nav_snaps = mf_store.get_nav_snapshots_for_date(snap_date)
    if nav_snaps:
        holdings = mf_store.get_holdings()
        schemes = [
            compute_scheme_pnl(holdings[s.amfi_code], s.nav)
            for s in nav_snaps
            if s.amfi_code in holdings
        ]
        mf_pnl = aggregate_mf_pnl(snap_date, schemes) if schemes else None
        if mf_pnl and mf_pnl.schemes:
            print(
                f"  MF portfolio ({len(mf_pnl.schemes)} schemes): "
                f"₹{mf_pnl.total_current_value:,.0f}  "
                f"P&L {mf_pnl.total_pnl:+,.0f} ({mf_pnl.total_pnl_pct:+}%)"
            )
        # Previous day's MF value for day-change delta
        prev_nav_snaps = mf_store.get_prev_nav_snapshots(snap_date)
        prev_mf_pnl = _compute_prev_mf_pnl(prev_nav_snaps, holdings)
    else:
        print(f"  No MF NAV snapshots found for {snap_date.isoformat()}.")

    # ── Dhan portfolio from stored snapshots (non-fatal) ──────────
    dhan_summary = None
    try:
        from src.dhan.store import DhanStore
        from src.dhan.reader import build_dhan_summary
        dhan_store = DhanStore(db_path)
        dhan_holdings = dhan_store.get_snapshot_for_date(snap_date)
        if dhan_holdings:
            prev_dhan = dhan_store.get_prev_snapshot(snap_date)
            dhan_summary = build_dhan_summary(dhan_holdings, snap_date, prev_dhan or None)
            print(f"  Dhan portfolio: {len(dhan_holdings)} holding(s) from stored snapshot")
        else:
            print(f"  No Dhan snapshots found for {snap_date.isoformat()}.")
    except Exception as e:  # noqa: BLE001
        print(f"  WARNING: Dhan historical lookup failed — {e}")

    # ── Nuvama bonds from stored snapshots (non-fatal) ───────────
    nuvama_summary = None
    try:
        from src.nuvama.store import NuvamaStore
        from src.nuvama.reader import build_nuvama_summary
        from src.nuvama.models import NuvamaBondHolding

        nuvama_store = NuvamaStore(db_path)
        nuvama_snaps = nuvama_store.get_snapshot_for_date(snap_date)
        positions = nuvama_store.get_positions()
        if nuvama_snaps and positions:
            # Reconstruct NuvamaBondHolding stubs from stored snapshot values.
            # chg_pct is not stored — use 0 so day_delta reads as 0 for historical.
            holdings_for_summary = [
                NuvamaBondHolding(
                    isin=isin,
                    company_name=isin,  # label not stored in snapshot; ISIN is sufficient
                    trading_symbol="",
                    exchange="",
                    qty=1,  # absorbed into current_value below
                    avg_price=positions.get(isin, current_value),
                    ltp=current_value,  # ltp × qty = current_value when qty=1
                    chg_pct=Decimal("0"),
                    hair_cut=Decimal("0"),
                )
                for isin, current_value in nuvama_snaps.items()
            ]
            nuvama_summary = build_nuvama_summary(holdings_for_summary, snap_date)
            print(f"  Nuvama bonds: {len(holdings_for_summary)} holding(s) from stored snapshot")
        else:
            print(f"  No Nuvama bond snapshots found for {snap_date.isoformat()}.")
    except Exception as e:  # noqa: BLE001
        print(f"  WARNING: Nuvama historical lookup failed — {e}")

    _print_combined_summary(
        strategies, prices, strategy_pnls, mf_pnl,
        prev_snapshots=prev_snapshots,
        prev_mf_pnl=prev_mf_pnl,
        snap_date=snap_date,
        dhan_summary=dhan_summary,
        nuvama_summary=nuvama_summary,
    )
    print("\n  Done.")
    return 0


# ── I/O-heavy entrypoint — all network/DB imports are local ──────


async def _async_main(snap_date: date, db_path: Path) -> int:
    """All async I/O for the daily snapshot run.

    All imports that trigger I/O (dotenv, stores, clients, tracker) are
    deferred to this function so the module-level helpers stay importable
    without a live .env or network connection.

    Args:
        snap_date: Date to record snapshots for.
        db_path: Path to the SQLite database.

    Returns:
        Exit code: 0 for success, 1 for any fatal error.
    """
    from dotenv import load_dotenv

    load_dotenv()

    from src.client.exceptions import LTPFetchError
    from src.client.factory import create_client
    from src.mf.store import MFStore
    from src.mf.tracker import MFTracker
    from src.portfolio.store import PortfolioStore
    from src.portfolio.tracker import PortfolioTracker, apply_trade_positions

    # ── Validate DB exists ───────────────────────────────────────
    if not db_path.exists():
        print(f"  ERROR: DB not found at {db_path}")
        print("  Run 'python -m scripts.seed_portfolio' first.")
        return 1

    store = PortfolioStore(db_path)
    strategies = store.get_all_strategies()

    if not strategies:
        print("  ERROR: No strategies found in DB. Run seed_portfolio first.")
        return 1

    # ── Overlay trade-derived positions onto strategy leg definitions ─
    # Replaces static qty/entry_price in Leg objects with the live reality
    # from the trades ledger. Appends legs that exist in trades but not in
    # the strategy definition (e.g. LIQUIDBEES). Pure — no network.
    strategies = [
        apply_trade_positions(s, store.get_all_positions_for_strategy(s.name))
        for s in strategies
    ]

    # Fetch prev-day snapshots early (before LTP fetch) — pure DB read, no network
    prev_snapshots = store.get_prev_snapshots(snap_date)

    # ── Initialize market client ─────────────────────────────────
    try:
        env = os.getenv("UPSTOX_ENV", "prod")
        client = create_client(env)
    except ValueError as e:
        print(f"  ERROR: {e}")
        return 1

    # ── Collect all unique instrument keys across strategies ──────
    NIFTY_INDEX_KEY = "NSE_INDEX|Nifty 50"

    all_keys = {leg.instrument_key for strategy in strategies for leg in strategy.legs}

    # ── Pre-fetch Dhan holdings (before LTP batch) — add their Upstox keys ──
    # Holdings are fetched now so their NSE_EQ|{ISIN} keys can be piggybacked
    # onto the single Upstox batch LTP call, avoiding Dhan's paid Data API.
    _dhan_holdings_prefetched: list = []
    _dhan_client_id: str = ""
    _dhan_token: str = ""
    _dhan_tracked_isins: set[str] = set()
    try:
        from src.auth.dhan_verify import load_dhan_credentials
        from src.dhan.reader import fetch_dhan_holdings, upstox_keys_for_holdings

        _dhan_client_id, _dhan_token = load_dhan_credentials()
        _dhan_tracked_isins = {
            leg.instrument_key.split("|", 1)[1]
            for s in strategies for leg in s.legs
            if leg.instrument_key.startswith("NSE_EQ|")
        }
        _dhan_holdings_prefetched = fetch_dhan_holdings(
            _dhan_client_id, _dhan_token, _dhan_tracked_isins
        )
        dhan_upstox_keys = upstox_keys_for_holdings(_dhan_holdings_prefetched)
        all_keys |= dhan_upstox_keys
        print(f"  Dhan: {len(_dhan_holdings_prefetched)} holding(s) — keys added to LTP batch")
    except ValueError as e:
        print(f"  Dhan: skipped — {e}")
    except Exception as e:  # noqa: BLE001
        print(f"  WARNING: Dhan holdings pre-fetch failed — {e}")

    print(f"  Strategies: {len(strategies)}, Instruments: {len(all_keys)}")

    # ── Fetch all LTPs in one batch (Nifty spot piggybacked) ─────
    try:
        prices = await client.get_ltp(list(all_keys | {NIFTY_INDEX_KEY}))
    except LTPFetchError as e:
        print(f"  ERROR: LTP fetch failed — {e}")
        print("  Aborting: cannot record snapshots with stale/zero prices.")
        return 1

    underlying_price = prices.get(NIFTY_INDEX_KEY)
    if underlying_price:
        print(f"  Nifty spot: {underlying_price:,.2f}")
    else:
        print("  WARNING: Could not fetch Nifty spot price.")

    missing = all_keys - set(prices.keys())
    if missing:
        print(f"  WARNING: No LTP for {len(missing)} instruments: {missing}")

    # ── Record snapshots and collect P&L — single event loop ─────
    tracker = PortfolioTracker(store, client)
    results = await tracker.record_all_strategies(
        snapshot_date=snap_date,
        underlying_price=underlying_price,
    )

    total_snaps = sum(results.values())
    print(f"  Recorded {total_snaps} snapshots:")

    strategy_pnls: dict[str, object] = {}
    for strategy in strategies:
        count = results.get(strategy.name, 0)
        pnl = await tracker.compute_pnl(strategy.name)
        strategy_pnls[strategy.name] = pnl
        if pnl:
            print(
                f"    {strategy.name}: {count} legs, "
                f"P&L: {pnl.total_pnl:+,.0f} ({pnl.total_pnl_percent:+.2f}%)"
            )
        else:
            print(f"    {strategy.name}: {count} legs")

    # ── MF portfolio snapshot (non-fatal) ─────────────────────────
    mf_pnl = None
    prev_mf_pnl: object | None = None
    try:
        mf_store = MFStore(db_path)
        mf_pnl = MFTracker(mf_store).record_snapshot(snap_date)
        if mf_pnl.schemes:
            print(
                f"  MF portfolio ({len(mf_pnl.schemes)} schemes): "
                f"₹{mf_pnl.total_current_value:,.0f}  "
                f"P&L {mf_pnl.total_pnl:+,.0f} ({mf_pnl.total_pnl_pct:+}%)"
            )
        else:
            print(
                "  MF portfolio: no holdings — skipped (run seed_mf_holdings.py first)"
            )
        # Previous day's MF value for day-change delta (non-fatal)
        prev_nav_snaps = mf_store.get_prev_nav_snapshots(snap_date)
        holdings = mf_store.get_holdings()
        prev_mf_pnl = _compute_prev_mf_pnl(prev_nav_snaps, holdings)
    except Exception as e:  # noqa: BLE001
        print(f"  WARNING: MF snapshot failed — {e}")

    # ── Dhan portfolio snapshot — enrich with Upstox prices (non-fatal) ──
    # Holdings were pre-fetched before the LTP batch; prices now available.
    dhan_summary = None
    if _dhan_holdings_prefetched:
        try:
            from src.dhan.reader import build_dhan_summary, enrich_with_upstox_prices
            from src.dhan.store import DhanStore

            enriched = enrich_with_upstox_prices(_dhan_holdings_prefetched, prices)

            dhan_store = DhanStore(db_path)
            prev_dhan = dhan_store.get_prev_snapshot(snap_date)
            dhan_summary = build_dhan_summary(enriched, snap_date, prev_dhan or None)

            all_dhan = list(dhan_summary.equity_holdings) + list(dhan_summary.bond_holdings)
            dhan_store.record_snapshot(all_dhan, snap_date)

            eq_count = len(dhan_summary.equity_holdings)
            bd_count = len(dhan_summary.bond_holdings)
            print(f"  Dhan portfolio: {eq_count} equity, {bd_count} bond holding(s)")
            if dhan_summary.equity_value > 0:
                print(
                    f"    Equity: ₹{dhan_summary.equity_value:,.0f}  "
                    f"P&L {dhan_summary.equity_pnl:+,.0f}"
                )
            if dhan_summary.bond_value > 0:
                print(
                    f"    Bonds:  ₹{dhan_summary.bond_value:,.0f}  "
                    f"P&L {dhan_summary.bond_pnl:+,.0f}"
                )
        except Exception as e:  # noqa: BLE001
            print(f"  WARNING: Dhan portfolio enrichment failed — {e}")

    # ── Nuvama bond portfolio snapshot (non-fatal) ────────────────
    nuvama_summary = None
    try:
        from src.auth.nuvama_verify import load_api_connect
        from src.nuvama.reader import fetch_nuvama_portfolio
        from src.nuvama.store import NuvamaStore

        nuvama_store = NuvamaStore(db_path)
        positions = nuvama_store.get_positions()
        if positions:
            nuvama_api = load_api_connect()
            nuvama_summary = fetch_nuvama_portfolio(nuvama_api, positions, snap_date)
            nuvama_store.record_all_snapshots(list(nuvama_summary.holdings), snap_date)
            print(
                f"  Nuvama bonds: {len(nuvama_summary.holdings)} holding(s)  "
                f"₹{nuvama_summary.total_value:,.0f}  "
                f"P&L {nuvama_summary.total_pnl:+,.0f}"
            )
        else:
            print("  Nuvama: skipped — no positions seeded (run seed_nuvama_positions.py --write)")
    except (ValueError, FileNotFoundError) as e:
        print(f"  Nuvama: skipped — {e}")
    except Exception as e:  # noqa: BLE001
        print(f"  WARNING: Nuvama bond snapshot failed — {e}")

    # ── Combined portfolio summary ────────────────────────────────
    summary_text = _format_combined_summary(
        strategies, prices, strategy_pnls, mf_pnl,
        prev_snapshots=prev_snapshots,
        prev_mf_pnl=prev_mf_pnl,
        snap_date=snap_date,
        dhan_summary=dhan_summary,
        nuvama_summary=nuvama_summary,
    )
    print(summary_text)

    # ── Telegram notification (non-fatal, skipped if env vars absent) ─
    # summary_text already contains the status header and hedge section,
    # so it can be sent directly without a separate subject line.
    from src.notifications.telegram import build_notifier

    notifier = build_notifier()
    if notifier:
        if not notifier.send(summary_text):
            print("  WARNING: Telegram notification failed (see logs).")
    else:
        import logging as _logging
        _logging.getLogger(__name__).debug(
            "Telegram notifier not configured — skipping (set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)"
        )

    print("\n  Done.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record daily portfolio snapshots or query historical P&L"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("data/portfolio/portfolio.sqlite"),
        help="Path to portfolio SQLite DB",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help=(
            "YYYY-MM-DD: query stored P&L for that date (no API call). "
            "Omit to run a live snapshot for today."
        ),
    )
    args = parser.parse_args()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if args.date:
        snap_date = date.fromisoformat(args.date)
        print(f"[{now}] Historical P&L query for {snap_date.isoformat()}")
        return _historical_main(snap_date, args.db_path)

    snap_date = date.today()
    print(f"[{now}] Daily snapshot for {snap_date.isoformat()}")
    return asyncio.run(_async_main(snap_date, args.db_path))


if __name__ == "__main__":
    # os._exit bypasses atexit and threading cleanup — necessary to kill the
    # APIConnect SDK's background Feed thread, which is non-daemon and would
    # otherwise block process exit indefinitely after a Nuvama fetch.
    # Same pattern as nuvama_verify.py and nuvama_login.py.
    import os as _os
    _code = main()
    _os._exit(_code)
