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
    (dotenv, UpstoxMarketClient, stores, tracker) are deferred into the
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
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Pure-computation helpers only need these types at import time — no I/O.
from src.portfolio.models import AssetType, DailySnapshot, Strategy  # noqa: E402


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


def _print_combined_summary(
    strategies: list[Strategy],
    prices: dict[str, float],
    strategy_pnls: dict[str, object],
    mf_pnl: object | None,
    prev_snapshots: dict[int, DailySnapshot] | None = None,
    prev_mf_pnl: object | None = None,
) -> None:
    """Print the combined portfolio value across MF, ETF, and options.

    When prev_snapshots / prev_mf_pnl are supplied (non-empty), a Δday column
    is appended to the MF, ETF, and Options lines showing the change vs the
    most recent prior snapshot.  If no prev data is available the Δday column
    is omitted entirely — no zeros, no dashes.

    Args:
        strategies: All loaded Strategy objects.
        prices: instrument_key → LTP (current day).
        strategy_pnls: strategy name → StrategyPnL (from compute_pnl).
        mf_pnl: Completed MF PortfolioPnL, or None if the MF fetch failed.
        prev_snapshots: {leg_id: DailySnapshot} from get_prev_snapshots(), or None.
        prev_mf_pnl: PortfolioPnL for the prior date, or None.
    """
    etf_value = _etf_current_value(strategies, prices)
    etf_basis = _etf_cost_basis(strategies)

    # Options net P&L — sign already correct for short legs in compute_pnl
    options_pnl = sum(
        (p.total_pnl for p in strategy_pnls.values() if p),  # type: ignore[union-attr]
        Decimal("0"),
    )

    mf_value = mf_pnl.total_current_value if mf_pnl else Decimal("0")  # type: ignore[union-attr]
    mf_invested = mf_pnl.total_invested if mf_pnl else Decimal("0")  # type: ignore[union-attr]
    mf_pnl_amt = mf_pnl.total_pnl if mf_pnl else Decimal("0")  # type: ignore[union-attr]
    mf_pnl_pct = mf_pnl.total_pnl_pct if mf_pnl else None  # type: ignore[union-attr]

    total_value = mf_value + etf_value + options_pnl
    total_invested = mf_invested + etf_basis
    total_pnl = mf_pnl_amt + (etf_value - etf_basis) + options_pnl
    total_pnl_pct = (
        (total_pnl / total_invested * 100).quantize(Decimal("0.01"))
        if total_invested
        else Decimal("0")
    )

    # ── Day-change deltas (omitted entirely when prev data unavailable) ──
    etf_day_delta: Decimal | None = None
    options_day_delta: Decimal | None = None
    mf_day_delta: Decimal | None = None

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

    if prev_mf_pnl is not None and mf_pnl is not None:
        mf_day_delta = mf_value - prev_mf_pnl.total_current_value  # type: ignore[union-attr]

    # Total day delta: sum all non-None components; omit line if nothing available
    any_delta = etf_day_delta is not None or mf_day_delta is not None
    total_day_delta: Decimal | None = None
    if any_delta:
        total_day_delta = (
            (mf_day_delta or Decimal("0"))
            + (etf_day_delta or Decimal("0"))
            + (options_day_delta or Decimal("0"))
        )

    # ── Format helpers ────────────────────────────────────────────
    def _delta(d: Decimal | None) -> str:
        return f"  Δday: {d:>+12,.0f}" if d is not None else ""

    # ── Output ────────────────────────────────────────────────────
    print()
    print("  ── Combined Portfolio ─────────────────────────────────")

    if mf_pnl:
        mf_pnl_str = f"  P&L: {mf_pnl_amt:>+11,.0f} ({mf_pnl_pct:+}%)"
        print(f"  MF current value    : ₹{mf_value:>14,.0f}{_delta(mf_day_delta)}{mf_pnl_str}")
    else:
        print(f"  MF current value    :          [failed]{_delta(mf_day_delta)}")

    print(f"  ETF current value   : ₹{etf_value:>14,.0f}{_delta(etf_day_delta)}  (basis ₹{etf_basis:,.0f})")
    print(f"  Options net P&L     : {options_pnl:>+15,.0f}{_delta(options_day_delta)}")
    print("  ───────────────────────────────────────────────────────")
    print(f"  Total value         : ₹{total_value:>14,.0f}{_delta(total_day_delta)}")
    print(f"  Total invested      : ₹{total_invested:>14,.0f}")
    print(f"  Total P&L           : {total_pnl:>+15,.0f}  ({total_pnl_pct:+}%)")
    if not mf_pnl:
        print("  NOTE: MF fetch failed — MF value excluded from total")


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

    if not db_path.exists():
        print(f"  ERROR: DB not found at {db_path}")
        print("  Run 'python -m scripts.seed_portfolio' first.")
        return 1

    store = PortfolioStore(db_path)
    strategies = store.get_all_strategies()
    if not strategies:
        print("  ERROR: No strategies found in DB. Run seed_portfolio first.")
        return 1

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

    _print_combined_summary(
        strategies, prices, strategy_pnls, mf_pnl,
        prev_snapshots=prev_snapshots,
        prev_mf_pnl=prev_mf_pnl,
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
    from src.client.upstox_market import UpstoxMarketClient
    from src.mf.store import MFStore
    from src.mf.tracker import MFTracker
    from src.portfolio.store import PortfolioStore
    from src.portfolio.tracker import PortfolioTracker

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

    # Fetch prev-day snapshots early (before LTP fetch) — pure DB read, no network
    prev_snapshots = store.get_prev_snapshots(snap_date)

    # ── Initialize market client ─────────────────────────────────
    try:
        client = UpstoxMarketClient()
    except ValueError as e:
        print(f"  ERROR: {e}")
        return 1

    # ── Collect all unique instrument keys across strategies ──────
    NIFTY_INDEX_KEY = "NSE_INDEX|Nifty 50"

    all_keys = {leg.instrument_key for strategy in strategies for leg in strategy.legs}
    print(f"  Strategies: {len(strategies)}, Instruments: {len(all_keys)}")

    # ── Fetch all LTPs in one batch (Nifty spot piggybacked) ─────
    try:
        prices = client.get_ltp_sync(list(all_keys | {NIFTY_INDEX_KEY}))
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

    # ── Combined portfolio summary ────────────────────────────────
    _print_combined_summary(
        strategies, prices, strategy_pnls, mf_pnl,
        prev_snapshots=prev_snapshots,
        prev_mf_pnl=prev_mf_pnl,
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
