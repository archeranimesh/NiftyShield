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
from src.portfolio.models import AssetType, DailySnapshot, PortfolioSummary, Strategy  # noqa: E402


# ── Pure helper functions — no I/O, no side effects ──────────────
# Importable without .env, DB, or network. Tests use these directly.


def _etf_current_value(strategies: list[Strategy], prices: dict[str, float]) -> Decimal:
    """Mark-to-market value of all EQUITY legs across strategies.

    ETF legs are assets — value is qty × current LTP.
    Falls back to entry price if LTP is missing (e.g. market closed).

    Args:
        strategies: All loaded Strategy objects.
        prices: instrument_key → LTP from the batch fetch.

    Returns:
        Total ETF value as Decimal.
    """
    total = Decimal("0")
    for strategy in strategies:
        for leg in strategy.legs:
            if leg.asset_type == AssetType.EQUITY:
                ltp = prices.get(leg.instrument_key, leg.entry_price)
                total += Decimal(str(ltp)) * Decimal(str(leg.quantity))
    return total


def _etf_cost_basis(strategies: list[Strategy]) -> Decimal:
    """Total entry cost of all EQUITY legs (qty × entry_price).

    Args:
        strategies: All loaded Strategy objects.

    Returns:
        Sum of entry costs as Decimal.
    """
    return sum(
        Decimal(str(leg.entry_price)) * Decimal(str(leg.quantity))
        for strategy in strategies
        for leg in strategy.legs
        if leg.asset_type == AssetType.EQUITY
    )


def _build_prev_prices(
    strategies: list[Strategy],
    prev_snapshots: dict[int, DailySnapshot],
) -> dict[str, float]:
    """Build instrument_key → LTP dict from previous-day snapshots.

    Uses the leg_id → instrument_key mapping derived from strategy legs to
    translate the prev_snapshots keyed by leg_id into a prices dict keyed by
    instrument_key — the same format used by _etf_current_value and
    _compute_strategy_pnl_from_prices.

    Args:
        strategies: Strategy objects with DB-assigned leg IDs.
        prev_snapshots: {leg_id: DailySnapshot} from get_prev_snapshots().

    Returns:
        {instrument_key: float(ltp)} for all legs that have a prev-day row.
    """
    leg_id_to_key: dict[int, str] = {
        leg.id: leg.instrument_key
        for strategy in strategies
        for leg in strategy.legs
        if leg.id is not None
    }
    return {
        leg_id_to_key[leg_id]: float(snap.ltp)
        for leg_id, snap in prev_snapshots.items()
        if leg_id in leg_id_to_key
    }


def _compute_prev_mf_pnl(
    prev_nav_snaps: list,  # list[MFNavSnapshot]
    holdings: dict,        # dict[str, MFHolding]
) -> object | None:
    """Reconstruct a PortfolioPnL from stored NAV snapshots and current holdings.

    Used by both live and historical paths to compute the previous day's MF
    value for day-change delta. Imports are deferred (consistent with the
    rest of the module).

    Args:
        prev_nav_snaps: NAV snapshots from the prior date.
        holdings: Current net holdings from MFStore.get_holdings().

    Returns:
        PortfolioPnL for the prior date, or None if no matching schemes.
    """
    from src.mf.tracker import _aggregate, _scheme_pnl  # noqa: PLC2701

    if not prev_nav_snaps or not holdings:
        return None
    schemes = [
        _scheme_pnl(holdings[s.amfi_code], s.nav)
        for s in prev_nav_snaps
        if s.amfi_code in holdings
    ]
    if not schemes:
        return None
    return _aggregate(prev_nav_snaps[0].snapshot_date, schemes)


def _build_portfolio_summary(
    snap_date: date,
    strategies: list[Strategy],
    prices: dict[str, float],
    strategy_pnls: dict[str, object],
    mf_pnl: object | None,
    prev_snapshots: dict[int, DailySnapshot] | None = None,
    prev_mf_pnl: object | None = None,
    dhan_summary: object | None = None,
) -> PortfolioSummary:
    """Compute combined portfolio values into a PortfolioSummary.

    Owns all arithmetic — ETF mark-to-market, options net P&L, MF totals,
    Dhan equity/bond, combined aggregates, and day-change deltas.
    Pure: no I/O, no side effects.

    Args:
        snap_date: The snapshot date (stored in PortfolioSummary.snapshot_date).
        strategies: All loaded Strategy objects.
        prices: instrument_key → LTP (current day).
        strategy_pnls: strategy name → StrategyPnL (from compute_pnl).
        mf_pnl: Completed MF PortfolioPnL, or None if the MF fetch failed.
        prev_snapshots: {leg_id: DailySnapshot} from get_prev_snapshots(), or None.
        prev_mf_pnl: PortfolioPnL for the prior date, or None.
        dhan_summary: DhanPortfolioSummary, or None if Dhan unavailable.

    Returns:
        Fully populated PortfolioSummary dataclass.
    """
    etf_value = _etf_current_value(strategies, prices)
    etf_basis = _etf_cost_basis(strategies)

    options_pnl = sum(
        (p.total_pnl for p in strategy_pnls.values() if p),  # type: ignore[union-attr]
        Decimal("0"),
    )

    mf_available = mf_pnl is not None
    mf_value = mf_pnl.total_current_value if mf_pnl else Decimal("0")  # type: ignore[union-attr]
    mf_invested = mf_pnl.total_invested if mf_pnl else Decimal("0")  # type: ignore[union-attr]
    mf_pnl_amt = mf_pnl.total_pnl if mf_pnl else Decimal("0")  # type: ignore[union-attr]
    mf_pnl_pct = mf_pnl.total_pnl_pct if mf_pnl else None  # type: ignore[union-attr]

    # ── Dhan components (default to 0 when unavailable) ───────────
    dhan_available = dhan_summary is not None
    dhan_eq_value = dhan_summary.equity_value if dhan_summary else Decimal("0")  # type: ignore[union-attr]
    dhan_eq_basis = dhan_summary.equity_basis if dhan_summary else Decimal("0")  # type: ignore[union-attr]
    dhan_eq_pnl = dhan_summary.equity_pnl if dhan_summary else Decimal("0")  # type: ignore[union-attr]
    dhan_eq_pnl_pct = dhan_summary.equity_pnl_pct if dhan_summary else None  # type: ignore[union-attr]
    dhan_eq_day_delta = dhan_summary.equity_day_delta if dhan_summary else None  # type: ignore[union-attr]
    dhan_bd_value = dhan_summary.bond_value if dhan_summary else Decimal("0")  # type: ignore[union-attr]
    dhan_bd_basis = dhan_summary.bond_basis if dhan_summary else Decimal("0")  # type: ignore[union-attr]
    dhan_bd_pnl = dhan_summary.bond_pnl if dhan_summary else Decimal("0")  # type: ignore[union-attr]
    dhan_bd_pnl_pct = dhan_summary.bond_pnl_pct if dhan_summary else None  # type: ignore[union-attr]
    dhan_bd_day_delta = dhan_summary.bond_day_delta if dhan_summary else None  # type: ignore[union-attr]

    total_value = mf_value + etf_value + options_pnl + dhan_eq_value + dhan_bd_value
    total_invested = mf_invested + etf_basis + dhan_eq_basis + dhan_bd_basis
    total_pnl = mf_pnl_amt + (etf_value - etf_basis) + options_pnl + dhan_eq_pnl + dhan_bd_pnl
    total_pnl_pct = (
        (total_pnl / total_invested * 100).quantize(Decimal("0.01"))
        if total_invested
        else Decimal("0")
    )

    # ── Day-change deltas (None when prior data unavailable) ──────
    etf_day_delta: Decimal | None = None
    options_day_delta: Decimal | None = None
    mf_day_delta: Decimal | None = None
    finrakshak_day_delta: Decimal | None = None

    if prev_snapshots:
        prev_prices = _build_prev_prices(strategies, prev_snapshots)
        prev_etf_value = _etf_current_value(strategies, prev_prices)
        prev_prices_dec = {k: Decimal(str(v)) for k, v in prev_prices.items()}
        prev_options_pnl = sum(
            (_compute_strategy_pnl_from_prices(s, prev_prices_dec).total_pnl
             for s in strategies),
            Decimal("0"),
        )
        etf_day_delta = etf_value - prev_etf_value
        options_day_delta = options_pnl - prev_options_pnl

        # Finrakshak delta isolated — needed for hedge effectiveness reporting
        frak_strat = next(
            (s for s in strategies if getattr(s, "name", None) == "finrakshak"), None
        )
        curr_frak = strategy_pnls.get("finrakshak")
        if frak_strat is not None and curr_frak is not None:
            prev_frak_pnl = _compute_strategy_pnl_from_prices(frak_strat, prev_prices_dec)
            finrakshak_day_delta = curr_frak.total_pnl - prev_frak_pnl.total_pnl  # type: ignore[union-attr]

    if prev_mf_pnl is not None and mf_pnl is not None:
        mf_day_delta = mf_value - prev_mf_pnl.total_current_value  # type: ignore[union-attr]

    any_delta = (
        etf_day_delta is not None
        or mf_day_delta is not None
        or dhan_eq_day_delta is not None
        or dhan_bd_day_delta is not None
    )
    total_day_delta: Decimal | None = None
    if any_delta:
        total_day_delta = (
            (mf_day_delta or Decimal("0"))
            + (etf_day_delta or Decimal("0"))
            + (options_day_delta or Decimal("0"))
            + (dhan_eq_day_delta or Decimal("0"))
            + (dhan_bd_day_delta or Decimal("0"))
        )

    return PortfolioSummary(
        snapshot_date=snap_date,
        mf_value=mf_value,
        mf_invested=mf_invested,
        mf_pnl=mf_pnl_amt,
        mf_pnl_pct=mf_pnl_pct,
        mf_available=mf_available,
        etf_value=etf_value,
        etf_basis=etf_basis,
        options_pnl=options_pnl,
        total_value=total_value,
        total_invested=total_invested,
        total_pnl=total_pnl,
        total_pnl_pct=total_pnl_pct,
        mf_day_delta=mf_day_delta,
        etf_day_delta=etf_day_delta,
        options_day_delta=options_day_delta,
        total_day_delta=total_day_delta,
        finrakshak_day_delta=finrakshak_day_delta,
        dhan_equity_value=dhan_eq_value,
        dhan_equity_basis=dhan_eq_basis,
        dhan_equity_pnl=dhan_eq_pnl,
        dhan_equity_pnl_pct=dhan_eq_pnl_pct,
        dhan_equity_day_delta=dhan_eq_day_delta,
        dhan_bond_value=dhan_bd_value,
        dhan_bond_basis=dhan_bd_basis,
        dhan_bond_pnl=dhan_bd_pnl,
        dhan_bond_pnl_pct=dhan_bd_pnl_pct,
        dhan_bond_day_delta=dhan_bd_day_delta,
        dhan_available=dhan_available,
    )


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
) -> str:
    """Build the combined portfolio summary as a formatted string.

    Restructured into sections: Equity → Bonds → Derivatives → Total.
    When prev data is supplied, a Δday column is appended. If no prev data
    is available the Δday column is omitted entirely.

    Args:
        strategies: All loaded Strategy objects.
        prices: instrument_key → LTP (current day).
        strategy_pnls: strategy name → StrategyPnL (from compute_pnl).
        mf_pnl: Completed MF PortfolioPnL, or None if the MF fetch failed.
        prev_snapshots: {leg_id: DailySnapshot} from get_prev_snapshots(), or None.
        prev_mf_pnl: PortfolioPnL for the prior date, or None.
        snap_date: Snapshot date stored in the summary (defaults to today).
        dhan_summary: DhanPortfolioSummary, or None if Dhan unavailable.

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
    )

    def _delta(d: Decimal | None) -> str:
        return f"  Δday: {d:>+12,.0f}" if d is not None else ""

    def _pnl_str(pnl: Decimal, pct: Decimal | None) -> str:
        pct_part = f" ({pct:+}%)" if pct is not None else ""
        return f"P&L: {pnl:>+11,.0f}{pct_part}"

    lines: list[str] = []

    # ── Equity section ────────────────────────────────────────────
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
    lines.append(
        f"                        (basis ₹{summary.etf_basis:,.0f})"
    )

    if summary.dhan_available and summary.dhan_equity_value > 0:
        lines.append(
            f"  Dhan Equity         : ₹{summary.dhan_equity_value:>14,.0f}"
            f"{_delta(summary.dhan_equity_day_delta)}"
        )
        lines.append(
            f"                        {_pnl_str(summary.dhan_equity_pnl, summary.dhan_equity_pnl_pct)}"
        )

    eq_subtotal = summary.mf_value + summary.etf_value + summary.dhan_equity_value
    lines.append("  ───────────────────────────────────────────────────────")
    lines.append(f"  Equity subtotal     : ₹{eq_subtotal:>14,.0f}")

    # ── Bonds section ─────────────────────────────────────────────
    lines.append("")
    lines.append("  ── Bonds ──────────────────────────────────────────────")

    if summary.dhan_available and summary.dhan_bond_value > 0:
        lines.append(
            f"  Dhan Bonds          : ₹{summary.dhan_bond_value:>14,.0f}"
            f"{_delta(summary.dhan_bond_day_delta)}"
        )
        lines.append(
            f"                        {_pnl_str(summary.dhan_bond_pnl, summary.dhan_bond_pnl_pct)}"
        )
        lines.append("  ───────────────────────────────────────────────────────")
        lines.append(f"  Bonds subtotal      : ₹{summary.dhan_bond_value:>14,.0f}")
    elif not summary.dhan_available:
        lines.append("  Dhan Bonds          :          [unavailable]")
    else:
        lines.append("  (no bond holdings)")

    # ── Derivatives section ───────────────────────────────────────
    lines.append("")
    lines.append("  ── Derivatives ────────────────────────────────────────")
    lines.append(
        f"  Options net P&L     : {summary.options_pnl:>+15,.0f}"
        f"{_delta(summary.options_day_delta)}"
    )

    # ── Total section ─────────────────────────────────────────────
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
) -> None:
    """Print the combined portfolio value across MF, ETF, options, and Dhan.

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
    """
    print(_format_combined_summary(
        strategies, prices, strategy_pnls, mf_pnl, prev_snapshots, prev_mf_pnl,
        snap_date, dhan_summary,
    ))


# ── Pure helper — no I/O, importable in tests ────────────────────


def _compute_strategy_pnl_from_prices(
    strategy: "Strategy", prices: "dict[str, Decimal]"
) -> "StrategyPnL":
    """Compute StrategyPnL from a pre-built prices dict (no live fetch).

    Used by the historical query path to reconstruct P&L from stored LTPs
    without touching the market client.

    Args:
        strategy: Strategy object with legs already loaded.
        prices: instrument_key → Decimal LTP. Falls back to leg.entry_price
            when a key is absent (same fallback as PortfolioTracker.compute_pnl).

    Returns:
        StrategyPnL with per-leg breakdown.
    """
    from src.portfolio.tracker import LegPnL, StrategyPnL

    leg_pnls = []
    for leg in strategy.legs:
        ltp = prices.get(leg.instrument_key, leg.entry_price)
        leg_pnls.append(
            LegPnL(
                leg=leg,
                current_price=ltp,
                pnl=leg.pnl(ltp),
                pnl_percent=leg.pnl_percent(ltp),
            )
        )
    return StrategyPnL(strategy_name=strategy.name, legs=leg_pnls)


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
    from src.mf.tracker import PortfolioPnL, _aggregate, _scheme_pnl  # noqa: PLC2701
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
            _scheme_pnl(holdings[s.amfi_code], s.nav)
            for s in nav_snaps
            if s.amfi_code in holdings
        ]
        mf_pnl = _aggregate(snap_date, schemes) if schemes else None
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

    _print_combined_summary(
        strategies, prices, strategy_pnls, mf_pnl,
        prev_snapshots=prev_snapshots,
        prev_mf_pnl=prev_mf_pnl,
        snap_date=snap_date,
        dhan_summary=dhan_summary,
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

    # ── Combined portfolio summary ────────────────────────────────
    summary_text = _format_combined_summary(
        strategies, prices, strategy_pnls, mf_pnl,
        prev_snapshots=prev_snapshots,
        prev_mf_pnl=prev_mf_pnl,
        snap_date=snap_date,
        dhan_summary=dhan_summary,
    )
    print(summary_text)

    # ── Telegram notification (non-fatal, skipped if env vars absent) ─
    from src.notifications.telegram import build_notifier

    notifier = build_notifier()
    if notifier:
        date_str = snap_date.strftime("%Y-%m-%d")
        _total_pnl = (
            sum((p.total_pnl for p in strategy_pnls.values() if p), Decimal("0"))
            + (mf_pnl.total_pnl if mf_pnl else Decimal("0"))
            + (_etf_current_value(strategies, prices) - _etf_cost_basis(strategies))
        )
        _emoji = "🟢" if _total_pnl >= 0 else "🔴"

        # Build summary object once to extract protection verdict for header
        from src.portfolio.models import PortfolioSummary as _PS  # noqa: F401
        _summary_obj = _build_portfolio_summary(
            snap_date=snap_date,
            strategies=strategies,
            prices=prices,
            strategy_pnls=strategy_pnls,
            mf_pnl=mf_pnl,
            prev_snapshots=prev_snapshots,
            prev_mf_pnl=prev_mf_pnl,
            dhan_summary=dhan_summary,
        )
        _prot_lines = _format_protection_stats(_summary_obj)
        _prot_header = ""
        if _prot_lines:
            _net = _summary_obj.mf_day_delta + _summary_obj.finrakshak_day_delta  # type: ignore[operator]
            _prot_header = f"\n  Hedge: {'✅ Protected' if _net >= 0 else '⚠️  Exposed'}  ({_net:+,.0f})"

        message = f"{_emoji} NiftyShield snapshot {date_str}{_prot_header}\n{summary_text}"
        if not notifier.send(message):
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
    sys.exit(main())
