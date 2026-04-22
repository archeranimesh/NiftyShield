"""Record daily price snapshots for all portfolio strategies.

Two modes of operation:
  Live mode (default, no --date):
    Fetches live LTPs from Upstox V3 API, records to SQLite, exits.
    Designed for cron — no interactive prompts, returns exit code 0/1.

  Historical mode (--date YYYY-MM-DD):
    Reads already-recorded daily_snapshots and mf_nav_snapshots rows for that
    date from the local SQLite DB and prints the P&L summary. No API calls,
    no network, no .env required. Useful for reviewing past snapshots.

Architecture (TODO 5 refactor):
    Pure computation  →  src/portfolio/summary.py
    Pure formatting   →  src/portfolio/formatting.py
    I/O orchestration →  this file (_async_main, _historical_main, main)

    All I/O-triggering imports (dotenv, create_client, stores, tracker) are
    deferred into _async_main() / _historical_main() so the src/ modules
    remain importable in tests without side effects.

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
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Pure-computation helpers only need these types at import time — no I/O.
from src.market_calendar.holidays import is_trading_day, prev_trading_day  # noqa: E402
from src.models.portfolio import DailySnapshot, Strategy  # noqa: E402
from src.portfolio.formatting import (  # noqa: E402
    _format_combined_summary,
    _format_protection_stats,
)
from src.portfolio.summary import (  # noqa: E402
    _build_portfolio_summary,
    _build_prev_prices,
    _compute_prev_mf_pnl,
    _compute_strategy_pnl_from_prices,
    _etf_cost_basis,
    _etf_current_value,
)


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
    nuvama_options_summary: object | None = None,
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
        nuvama_options_summary: NuvamaOptionsSummary, or None if unavailable.
    """
    print(_format_combined_summary(
        strategies, prices, strategy_pnls, mf_pnl, prev_snapshots, prev_mf_pnl,
        snap_date, dhan_summary, nuvama_summary, nuvama_options_summary,
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
    if underlying_price is not None:
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

    # ── Nuvama options from stored snapshots (non-fatal) ─────────
    nuvama_options_summary = None
    try:
        from src.nuvama.options_reader import build_options_summary
        from src.nuvama.models import NuvamaOptionPosition

        options_rows = nuvama_store.get_options_snapshot_for_date(snap_date)
        if options_rows:
            pos_list = [
                NuvamaOptionPosition(
                    trade_symbol=r["trade_symbol"],
                    instrument_name=r["instrument_name"],
                    net_qty=r["net_qty"],
                    avg_price=Decimal(r["avg_price"]),
                    ltp=Decimal(r["ltp"]),
                    unrealized_pnl=Decimal(r["unrealized_pnl"]),
                    realized_pnl_today=Decimal(r["realized_pnl_today"]),
                )
                for r in options_rows
            ]
            cumulative_map = nuvama_store.get_cumulative_realized_pnl(before_date=snap_date)
            high, low, n_high, n_low = nuvama_store.get_intraday_extremes(snap_date)
            nuvama_options_summary = build_options_summary(
                pos_list, 
                snap_date, 
                cumulative_map,
                intraday_high=high,
                intraday_low=low,
                nifty_high=n_high,
                nifty_low=n_low
            )
            print(f"  Nuvama options: {len(pos_list)} holding(s) from stored snapshot")
        else:
            print(f"  No Nuvama options snapshots found for {snap_date.isoformat()}.")
    except Exception as e:  # noqa: BLE001
        print(f"  WARNING: Nuvama options historical lookup failed — {e}")

    _print_combined_summary(
        strategies, prices, strategy_pnls, mf_pnl,
        prev_snapshots=prev_snapshots,
        prev_mf_pnl=prev_mf_pnl,
        snap_date=snap_date,
        dhan_summary=dhan_summary,
        nuvama_summary=nuvama_summary,
        nuvama_options_summary=nuvama_options_summary,
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

    run_id = uuid.uuid4().hex[:8]
    print(f"  run_id={run_id}")

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
        print(f"  WARNING [{run_id}]: Dhan holdings pre-fetch failed — {e}")

    print(f"  Strategies: {len(strategies)}, Instruments: {len(all_keys)}")

    # ── Fetch all LTPs in one batch (Nifty spot piggybacked) ─────
    try:
        prices = await client.get_ltp(list(all_keys | {NIFTY_INDEX_KEY}))
    except LTPFetchError as e:
        print(f"  ERROR: LTP fetch failed — {e}")
        print("  Aborting: cannot record snapshots with stale/zero prices.")
        return 1

    underlying_price = prices.get(NIFTY_INDEX_KEY)
    if underlying_price is not None:
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
        # Previous day's MF value for day-change delta (non-fatal).
        # We look back to prev_trading_day(snap_date), not snap_date itself.
        # morning_nav.py corrects yesterday's row to yesterday's actual NAV;
        # daily_snapshot at 15:45 writes today's row with yesterday's NAV
        # (AMFI not yet published).  Without this offset, both rows have the
        # same NAV and the delta collapses to 0.
        prev_nav_snaps = mf_store.get_prev_nav_snapshots(prev_trading_day(snap_date))
        holdings = mf_store.get_holdings()
        prev_mf_pnl = _compute_prev_mf_pnl(prev_nav_snaps, holdings)
    except Exception as e:  # noqa: BLE001
        print(f"  WARNING [{run_id}]: MF snapshot failed — {e}")

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
            print(f"  WARNING [{run_id}]: Dhan portfolio enrichment failed — {e}")

    # ── Nuvama bond portfolio snapshot (non-fatal) ────────────────
    nuvama_summary = None
    try:
        from src.auth.nuvama_verify import load_api_connect
        from src.nuvama.reader import fetch_nuvama_portfolio
        from src.nuvama.store import NuvamaStore

        nuvama_store = NuvamaStore(db_path)
        positions = nuvama_store.get_positions()
        if positions:
            try:
                from src.auth.nuvama_verify import load_api_connect
                nuvama_api_instance = load_api_connect()
                nuvama_summary = fetch_nuvama_portfolio(nuvama_api_instance, positions, snap_date)
                nuvama_store.record_all_snapshots(list(nuvama_summary.holdings), snap_date)
                print(
                    f"  Nuvama bonds: {len(nuvama_summary.holdings)} holding(s)  "
                    f"₹{nuvama_summary.total_value:,.0f}  "
                    f"P&L {nuvama_summary.total_pnl:+,.0f}"
                )
            except (ValueError, FileNotFoundError) as e:
                print(f"  Nuvama bonds: skipped — {e}")
                nuvama_api_instance = None
        else:
            print("  Nuvama bonds: skipped — no positions seeded.")
    except Exception as e:  # noqa: BLE001
        print(f"  WARNING [{run_id}]: Nuvama bond snapshot failed — {e}")
        nuvama_api_instance = None

    # ── Nuvama options portfolio snapshot (non-fatal) ─────────────
    nuvama_options_summary = None
    try:
        from src.nuvama.options_reader import parse_options_positions, build_options_summary

        if 'nuvama_api_instance' not in locals() or nuvama_api_instance is None:
            from src.auth.nuvama_verify import load_api_connect
            nuvama_api_instance = load_api_connect()

        raw_netpos = nuvama_api_instance.NetPosition()
        options_pos = parse_options_positions(raw_netpos)
        if options_pos:
            nuvama_store.record_all_options_snapshots(options_pos, snap_date)
            cumulative_map = nuvama_store.get_cumulative_realized_pnl(before_date=snap_date)
            high, low, n_high, n_low = nuvama_store.get_intraday_extremes(snap_date)
            nuvama_options_summary = build_options_summary(
                options_pos, 
                snap_date, 
                cumulative_map,
                intraday_high=high,
                intraday_low=low,
                nifty_high=n_high,
                nifty_low=n_low
            )
            print(
                f"  Nuvama options: {len(options_pos)} position(s)  "
                f"Unrealized P&L {nuvama_options_summary.total_unrealized_pnl:+,.0f}  "
                f"Net P&L {nuvama_options_summary.net_pnl:+,.0f}"
            )
        else:
            print("  Nuvama options: skipped — no active positions found.")
    except (ValueError, FileNotFoundError) as e:
        print(f"  Nuvama options: skipped — {e}")
    except Exception as e:  # noqa: BLE001
        print(f"  WARNING [{run_id}]: Nuvama options snapshot failed — {e}")

    # ── Combined portfolio summary ────────────────────────────────
    summary_text = _format_combined_summary(
        strategies, prices, strategy_pnls, mf_pnl,
        prev_snapshots=prev_snapshots,
        prev_mf_pnl=prev_mf_pnl,
        snap_date=snap_date,
        dhan_summary=dhan_summary,
        nuvama_summary=nuvama_summary,
        nuvama_options_summary=nuvama_options_summary,
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
    if not is_trading_day(snap_date):
        print(f"[{now}] Market holiday ({snap_date.isoformat()}) — skipping snapshot.")
        return 0

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
