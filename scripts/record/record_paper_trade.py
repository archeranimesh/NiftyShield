"""CLI for recording a single paper trade into the paper_trades ledger.

Supports four modes of instrument resolution:
1. Direct Key: Provide --key "NSE_FO|12345" and --price.
2. Auto-expiry (Live Chain): Provide --expiry YYYY-MM-DD. Fetches live LTP and
   delta-ranked strikes (like find_strike_by_delta), picking rank via --index N.
3. BOD Lookup: Provide --underlying, --strike, --option-type, --expiry to
   resolve a key from the offline BOD JSON (data/instruments/NSE.json.gz).
4. Close Shorthand: Use --close to auto-resolve the instrument key from the
   current open short position in the DB and fetch live LTP for the price.

Dry-run is on by default — use ``--no-dry-run`` to actually write to the DB.

Usage Examples:
    # Explicit key:
    python scripts/record_paper_trade.py --key "NSE_FO|12345" --price 120.5 --no-dry-run

    # Live chain pick (rank 1):
    python scripts/record_paper_trade.py --expiry 2026-05-29 --delta-min 0.15 --no-dry-run

    # Close current short position at live LTP:
    python scripts/record_paper_trade.py --strategy paper_nifty_spot --leg overlay_pp --close --no-dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from scripts.lookup.find_strike_by_delta import (
    DEFAULT_LOT_SIZE,
    UNDERLYING_DEFAULT,
    format_table,
)
from src.backtest.ivr import compute_ivr
from src.backtest.vix_ingest import fetch_vix_latest, load_vix_series
from src.client.upstox_market import UpstoxMarketClient
from src.instruments.lookup import InstrumentLookup
from src.instruments.strike_selector import (
    _apply_liquidity_gate,
    filter_strikes_by_delta,
    rank_strikes,
)
from src.intraday.market_store import IntradayMarketStore
from src.models.portfolio import TradeAction
from src.paper._utils import safe_float
from src.paper.constants import DEFAULT_BOD_PATH, DEFAULT_DB_PATH, LOT_SIZE, STRATEGY_CSP
from src.paper.models import PaperTrade
from src.paper.store import PaperStore
from src.risk.delta_tracker import PortfolioDeltaTracker
from src.risk.entry_gate import check_entry_allowed

load_dotenv()

DEFAULT_VIX_DIR = Path("data/historical/ohlc/india_vix")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Record a single paper trade into the paper_trades ledger. "
            "--strategy must start with 'paper_'.  Provide either --key "
            "(direct instrument key), --expiry (live chain lookup), or "
            "lookup flags (--underlying / --strike / --option-type / --expiry)."
        )
    )
    parser.add_argument(
        "--strategy",
        default=STRATEGY_CSP,
        help=f'Paper strategy name — must start with "paper_". Default: {STRATEGY_CSP}.',
    )
    parser.add_argument(
        "--leg",
        default="short_put",
        help='Leg role label, e.g. "short_put". Default: short_put.',
    )

    # ── Chain lookup mode ─────────────────────────────────────────────────────
    chain_group = parser.add_argument_group(
        "chain lookup",
        "Auto-select strike from live option chain (mutually exclusive with --key and --underlying).",
    )
    chain_group.add_argument(
        "--expiry",
        default=None,
        metavar="YYYY-MM-DD",
        help="Fetch live option chain and auto-select best strike for this expiry.",
    )
    chain_group.add_argument(
        "--delta-min",
        type=float,
        default=0.20,
        metavar="FLOAT",
        help="Lower |delta| bound for chain filter. Default: 0.20.",
    )
    chain_group.add_argument(
        "--delta-max",
        type=float,
        default=0.35,
        metavar="FLOAT",
        help="Upper |delta| bound for chain filter. Default: 0.35.",
    )
    chain_group.add_argument(
        "--option-type",
        choices=["CE", "PE", "BOTH"],
        default=None,
        help="Option side for chain filter. Default: PE.",
    )
    chain_group.add_argument(
        "--index",
        type=int,
        default=1,
        metavar="N",
        help="Select the Nth-ranked candidate from the chain (1-based). Default: 1.",
    )
    # ──────────────────────────────────────────────────────────────────────────

    # ── Instrument identification (one of two lookup modes) ───────────────────
    key_group = parser.add_argument_group(
        "direct key", "Provide the Upstox instrument key directly"
    )
    key_group.add_argument(
        "--key",
        default=None,
        help='Upstox instrument key, e.g. "NSE_FO|12345"',
    )

    lookup_group = parser.add_argument_group(
        "instrument lookup",
        "Auto-resolve instrument key from the offline BOD JSON "
        "(mutually exclusive with --key and --expiry)",
    )
    lookup_group.add_argument(
        "--underlying",
        default=None,
        help='Underlying symbol for option lookup, e.g. "NIFTY"',
    )
    lookup_group.add_argument(
        "--strike",
        type=float,
        default=None,
        help="Strike price, e.g. 23000",
    )
    lookup_group.add_argument(
        "--bod-path",
        type=Path,
        default=DEFAULT_BOD_PATH,
        help=f"Path to Upstox BOD JSON file (default: {DEFAULT_BOD_PATH})",
    )
    # ──────────────────────────────────────────────────────────────────────────

    parser.add_argument(
        "--date",
        dest="trade_date",
        default=str(date.today()),
        help="Execution date in YYYY-MM-DD format. Default: today.",
    )
    parser.add_argument(
        "--action",
        choices=["BUY", "SELL"],
        default="SELL",
        help="BUY or SELL. Default: SELL.",
    )
    parser.add_argument(
        "--qty",
        type=int,
        default=DEFAULT_LOT_SIZE,
        help=f"Units transacted (positive integer). Default: {DEFAULT_LOT_SIZE}.",
    )
    parser.add_argument("--price", default=None, help="Execution price per unit.")
    parser.add_argument(
        "--notes",
        default="",
        help="Optional annotation (slippage assumption, decision rationale, etc.)",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--vix-data-dir",
        type=Path,
        default=DEFAULT_VIX_DIR,
        help=f"Path to the India VIX Parquet directory (default: {DEFAULT_VIX_DIR})",
    )
    parser.add_argument(
        "--close",
        action="store_true",
        default=False,
        help=(
            "Buy-to-close shorthand: implies --action BUY. "
            "Use when closing an existing short leg (e.g. roll-close of a CSP). "
            "Mutually exclusive with --action."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Preview the PaperTrade without inserting into the DB (default: on). "
            "Use --no-dry-run to write."
        ),
    )
    parser.add_argument(
        "--force-entry",
        action="store_true",
        default=False,
        help="Force execution even if IVR checks fail the entry gate (R3 block override).",
    )
    return parser.parse_args()


def _resolve_from_chain(args: argparse.Namespace) -> tuple[str, str] | None:
    """Fetch live option chain, rank candidates, return (instrument_key, price).

    Prints the ranked table (mirroring find_strike_by_delta output) and the
    selected row so the user can verify before the DB write.

    Args:
        args: Parsed CLI arguments (uses expiry, delta_min, delta_max,
              option_type, index, underlying=UNDERLYING_DEFAULT).

    Returns:
        (instrument_key, price_str) for the selected rank, or None on failure
        (caller should sys.exit(1)).
    """
    try:
        client = UpstoxMarketClient()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return None

    # Resolve expiries
    expiries: list[tuple[str, str]] = []  # (label, expiry_str)
    if args.expiry:
        expiries = [("manual", args.expiry)]
    else:
        try:
            lookup = InstrumentLookup.from_file(args.bod_path)
            # Preference for CSP: monthly -> quarterly -> yearly
            # TODO: derive symbol from args.underlying
            expiries = lookup.get_expiry_candidates(underlying="NIFTY", today=date.today())
        # Intentional: catch all API connectivity issues during chain fetch.
        except Exception as exc:
            print(f"ERROR: failed to load BOD or resolve expiries — {exc}", file=sys.stderr)
            return None

    if not expiries:
        print("ERROR: no eligible expiries found (DTE 15–420).", file=sys.stderr)
        return None

    all_rows: list[dict[str, Any]] = []
    underlying_spot = 0.0

    for label, expiry in expiries:
        print(
            f"Fetching live chain: {UNDERLYING_DEFAULT}  expiry={expiry} ({label}) …",
            flush=True,
        )
        try:
            raw_data = client.get_option_chain_sync(UNDERLYING_DEFAULT, expiry)
            if not raw_data:
                print(f"  WARNING: API returned empty data for {expiry} — skipping.")
                continue

            if underlying_spot <= 0.0:
                underlying_spot = safe_float(raw_data[0].get("underlying_spot_price", 0.0))

            option_type = args.option_type or "PE"
            rows = filter_strikes_by_delta(
                raw_data,
                option_type=option_type,
                delta_min=args.delta_min,
                delta_max=args.delta_max,
            )
            # Annotate rows with expiry and label
            for r in rows:
                r["expiry"] = expiry
                r["expiry_label"] = label

            all_rows.extend(rows)

        # Intentional: prevent a single processing failure from crashing the sweep.
        except Exception as exc:
            print(f"  WARNING: fetch failed for {expiry} — {exc} — skipping.")
            continue

    if not all_rows:
        print(
            "ERROR: no strikes found across all candidate expiries (empty data).", file=sys.stderr
        )
        return None

    ranked = rank_strikes(all_rows)
    filtered = _apply_liquidity_gate(ranked)
    if not filtered:
        print("ERROR: GATE FAIL — no candidate strikes passed the liquidity gate.", file=sys.stderr)
        return None

    pick_idx = min(args.index - 1, len(filtered) - 1)
    if args.index - 1 > len(filtered) - 1:
        print(
            f"WARNING: --index {args.index} out of range; clamping to rank {len(filtered)}.",
            file=sys.stderr,
        )

    selected = filtered[pick_idx]

    print()
    print(
        format_table(
            filtered,
            underlying_spot=underlying_spot,
            expiry=args.expiry or "Multiple (auto)",
            selected_key=selected["instrument_key"],
        )
    )

    price = round(selected["mid"] if selected["mid"] > 0 else selected["ltp"], 2)
    print(
        f"\n# Selected: {selected['side']} {selected['strike']:.0f} | "
        f"delta={selected['delta']:+.4f} | iv={selected['iv']:.2f}% | "
        f"expiry={selected['expiry']} ({selected['expiry_label']}) | price=₹{price}"
    )

    return selected["instrument_key"], str(price)


def _resolve_from_position(args: argparse.Namespace) -> str | None:
    """Resolve instrument key from the current open position in the DB.

    Args:
        args: Parsed CLI arguments (uses db_path, strategy, leg).

    Returns:
        Resolved instrument_key string, or None if no open short position.
    """
    store = PaperStore(args.db_path)
    pos = store.get_position(args.strategy, args.leg)

    if pos.net_qty >= 0:
        print(
            f"ERROR: no open short position to close for {args.strategy} / {args.leg} "
            f"(net qty = {pos.net_qty}).",
            file=sys.stderr,
        )
        return None

    print(f"Resolved key from position: {pos.instrument_key}")
    return pos.instrument_key


def _resolve_instrument_key(args: argparse.Namespace) -> str | None:
    """Resolve instrument key from --key or from BOD lookup flags.

    Returns the resolved key, or None after printing an error/ambiguity message
    (caller should exit 1).

    Args:
        args: Parsed CLI arguments.

    Returns:
        Resolved instrument_key string, or None on failure.
    """
    # Auto-key from DB — --close provided AND (no key AND no underlying provided)
    if args.close and not args.key and not args.underlying:
        key = _resolve_from_position(args)
        if key is not None:
            return key
        return None

    # Chain mode — --expiry provided OR (no key AND no underlying provided)
    # We need to distinguish between chain-mode --expiry and lookup-mode --expiry.
    # Chain mode is active if --underlying is NOT set AND --key is NOT set.
    if not args.key and not args.underlying:
        result = _resolve_from_chain(args)
        if result is None:
            return None
        key, price_str = result
        # Inject resolved price back into args so main() can use it
        args.price = price_str
        return key

    # Direct key — no lookup needed
    if args.key:
        if args.underlying or args.strike or args.option_type or args.expiry:
            print(
                "ERROR: --key and lookup flags (--underlying/--strike/--option-type/"
                "--expiry) are mutually exclusive.",
                file=sys.stderr,
            )
            return None
        return args.key

    # Lookup mode — --underlying is the minimum required field
    if not args.underlying:
        print(
            "ERROR: provide either --key or at least --underlying for instrument lookup.",
            file=sys.stderr,
        )
        return None

    if not args.bod_path.exists():
        print(
            f"ERROR: BOD file not found at {args.bod_path}.\n"
            "Download it with:\n"
            "  curl -o data/instruments/NSE.json.gz "
            "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
            file=sys.stderr,
        )
        return None

    try:
        lookup = InstrumentLookup.from_file(args.bod_path)
    # Intentional: catch all BOD file loading/parsing errors.
    except Exception as exc:
        print(f"ERROR: failed to load BOD file — {exc}", file=sys.stderr)
        return None

    results = lookup.search_options(
        underlying=args.underlying,
        strike=args.strike,
        option_type=args.option_type,
        expiry=args.expiry,
    )

    if not results:
        filters = []
        if args.strike:
            filters.append(f"strike={args.strike}")
        if args.option_type:
            filters.append(f"type={args.option_type}")
        if args.expiry:
            filters.append(f"expiry={args.expiry}")
        filter_str = ", ".join(filters) if filters else "no filters"
        print(
            f"ERROR: no instruments found for underlying={args.underlying!r} "
            f"({filter_str}).\n"
            "Check spelling, ensure the BOD file is fresh, and verify the expiry date.",
            file=sys.stderr,
        )
        return None

    if len(results) == 1:
        inst = results[0]
        key = inst.get("instrument_key", "")
        sym = inst.get("trading_symbol", "")
        print(f"Resolved instrument: {sym}  ({key})")
        return key

    # Multiple matches — print them and ask user to be more specific
    print(
        f"Multiple instruments matched for {args.underlying!r} (showing up to {len(results)}):\n",
        file=sys.stderr,
    )
    for i, inst in enumerate(results, 1):
        key = inst.get("instrument_key", "")
        sym = inst.get("trading_symbol", "")
        strike = inst.get("strike_price", "")
        expiry = inst.get("expiry", "")
        itype = inst.get("instrument_type", "")
        print(
            f"  {i:2d}. {sym:<28} strike={strike:<8} type={itype}  expiry={expiry}  key={key}",
            file=sys.stderr,
        )
    print(
        "\nRe-run with --key <key> from the list above, or add "
        "--strike / --option-type / --expiry to narrow results.",
        file=sys.stderr,
    )
    return None


_PRICE_DRIFT_TOLERANCE_PCT = Decimal("0.10")  # 10% — Animesh-approved (BUG-008)


def _evaluate_price_drift(
    claimed_price: Decimal,
    live_price: Decimal,
    tolerance_pct: Decimal = _PRICE_DRIFT_TOLERANCE_PCT,
) -> tuple[bool, str]:
    """Compare a caller-supplied ``--price`` against a freshly fetched live price.

    Pure function — no I/O. Re-validates a price that may have been frozen at
    dry-run generation time (BUG-008: a dry-run's printed ``--price`` can be
    stale by the time the command is actually executed).

    Args:
        claimed_price: Price passed via --price (what the trade will be recorded at).
        live_price: Freshly fetched LTP for the same instrument.
        tolerance_pct: Fractional tolerance (0.10 = 10%) before drift hard-blocks.

    Returns:
        (allowed, message). allowed=False means drift exceeded tolerance — the
        caller must sys.exit(1) unless --force-entry overrides. message is ""
        when drift is negligible (< half of tolerance), a WARNING string when
        drift is elevated but still allowed, or an ERROR string when blocked.
    """
    if claimed_price <= 0:
        # Malformed/zero price — handled by PaperTrade model validation downstream.
        return True, ""
    drift_pct = abs(live_price - claimed_price) / claimed_price
    if drift_pct > tolerance_pct:
        return False, (
            f"ERROR: price drift {drift_pct:.1%} exceeds tolerance "
            f"({tolerance_pct:.0%}) — claimed=₹{claimed_price}, live=₹{live_price}. "
            "Use --force-entry to override."
        )
    if drift_pct > tolerance_pct / 2:
        return True, (
            f"WARNING: price drift {drift_pct:.1%} — claimed=₹{claimed_price}, live=₹{live_price}."
        )
    return True, ""


def _get_ivr_and_enforce(
    trade_date: date,
    action: TradeAction,
    vix_data_dir: Path,
    db_path: Path,
    force_entry: bool = False,
) -> float | None:
    """Fetch live VIX, load historical window, compute IVR, enforce R3 gates.

    For today's trades: checks intraday_market_snapshots first (already fetched
    by the intraday tracker every 15 min — no duplicate API call). Falls back to
    a live Upstox API call only when the DB has no today-IST snapshot.
    For back-dated trades: looks up the Parquet for that date's close.

    The 252-day historical window always comes from the Parquet. If the Parquet
    has insufficient history, IVR returns None — bootstrap with vix_ingest.py.

    On SELL with IVR < 0.25 and no force_entry, prints error to stderr and exits 1.
    On SELL with IVR < 0.25 and force_entry, prints warning to stderr and returns IVR.

    Args:
        trade_date: Date of the trade execution.
        action: BUY or SELL.
        vix_data_dir: Path to the India VIX Parquet directory.
        db_path: Path to the shared SQLite database (for intraday snapshots).
        force_entry: If True, override low IVR block.

    Returns:
        Computed IVR value or None if data is insufficient.
    """
    today = date.today()

    # ── Resolve vix_today ────────────────────────────────────────────────────
    if trade_date == today:
        # 1. Prefer intraday DB — already fetched by the tracker, no API call.
        vix_today = IntradayMarketStore(db_path).get_latest_vix_today()
        if vix_today is not None:
            print(f"INFO: India VIX from intraday snapshot = {vix_today:.2f}", file=sys.stderr)
        else:
            # 2. Fall back to live API fetch (pre-market, tracker not running, etc.)
            vix_today = fetch_vix_latest()
            if vix_today is None:
                print(
                    "WARNING: Could not fetch live India VIX "
                    "(check UPSTOX_ANALYTICS_TOKEN). IVR skipped.",
                    file=sys.stderr,
                )
                return None
            print(f"INFO: Live India VIX = {vix_today:.2f}", file=sys.stderr)
    else:
        # Back-dated trade — look up Parquet for that specific date.
        if not vix_data_dir.exists():
            print(
                f"WARNING: VIX data directory not found at {vix_data_dir}. IVR skipped.",
                file=sys.stderr,
            )
            return None
        series = load_vix_series(vix_data_dir)
        if trade_date not in series.index:
            print(
                f"WARNING: No VIX data for {trade_date} in Parquet. IVR skipped.",
                file=sys.stderr,
            )
            return None
        vix_today = series[trade_date]

    # ── Load 252-day historical window from Parquet ──────────────────────────
    historical = pd.Series(dtype="float64")
    if vix_data_dir.exists():
        full_series = load_vix_series(vix_data_dir)
        historical = full_series[full_series.index < trade_date]

    ivr = compute_ivr(vix_today, historical)
    if ivr is None:
        print(
            f"WARNING: Insufficient VIX history ({len(historical)}/252 days). "
            "IVR skipped — run vix_ingest.py to bootstrap.",
            file=sys.stderr,
        )
        return None

    # ── R3 Entry Gate Warnings & Enforcement (SELL only) ──────────────────────
    if action == TradeAction.SELL:
        if ivr < 0.25:
            if not force_entry:
                print(
                    f"ERROR: R3 blocked — low IVR ({ivr:.2f}). Use --force-entry to override.",
                    file=sys.stderr,
                )
                sys.exit(1)
            else:
                print(
                    f"WARNING: R3 override — Low IVR ({ivr:.2f}) forced.",
                    file=sys.stderr,
                )
        elif 0.25 <= ivr <= 0.50:
            print(
                f"ATTENTION: IVR is {ivr:.2f} (R3 Entry Window). "
                "Ensure sufficient premium/margin for potential expansion.",
                file=sys.stderr,
            )
        else:
            print(
                f"WARNING: High IVR ({ivr:.2f}). "
                "Elevated vol regime — premium rich but tail risk is elevated.",
                file=sys.stderr,
            )

    return ivr


def main() -> None:
    """CLI entry point. Validates, optionally inserts, prints position summary."""
    args = _parse_args()

    # Enforce paper_ prefix before attempting model construction
    if not args.strategy.startswith("paper_"):
        print(
            f"ERROR: --strategy must start with 'paper_', got: {args.strategy!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    # --close implies BUY; reject combination with explicit --action
    if args.close:
        if args.action != "SELL":  # SELL is the argparse default — any other value means explicit
            print(
                "ERROR: --close and --action are mutually exclusive; "
                "--close already implies --action BUY.",
                file=sys.stderr,
            )
            sys.exit(1)
        args.action = "BUY"

    # Resolve instrument key (direct --key or BOD lookup)
    instrument_key = _resolve_instrument_key(args)
    if instrument_key is None:
        sys.exit(1)

    try:
        trade_date = date.fromisoformat(args.trade_date)
    except ValueError:
        print(
            f"ERROR: --date must be YYYY-MM-DD, got: {args.trade_date}",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.expiry:
        try:
            date.fromisoformat(args.expiry)
        except ValueError:
            print(
                f"ERROR: --expiry must be YYYY-MM-DD, got: {args.expiry}",
                file=sys.stderr,
            )
            sys.exit(1)

    # BUG-008: track whether --price was caller-supplied (vs. auto-fetched from
    # live LTP below) — only a caller-supplied price can be *stale*, so only
    # that case needs a drift re-check against a fresh LTP fetch.
    price_was_explicit = args.price is not None

    if args.price is None:
        if args.close:
            # Auto-price from LTP
            try:
                client = UpstoxMarketClient()
                ltp_dict = client.get_ltp_sync([instrument_key])
                if instrument_key not in ltp_dict:
                    print(f"ERROR: LTP not found for {instrument_key}", file=sys.stderr)
                    sys.exit(1)

                price = ltp_dict[instrument_key]
                rounded_price = round(price, 2)
                print(f"Auto-price: LTP=₹{rounded_price}")
                args.price = str(rounded_price)
            except ValueError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                sys.exit(1)
            # Intentional: prevent LTP fetch failure from crashing the script.
            except Exception as exc:
                print(f"ERROR: failed to fetch LTP — {exc}", file=sys.stderr)
                sys.exit(1)
        elif args.key or args.underlying:
            print(
                "ERROR: --price is required when not in chain mode (auto-expiry).",
                file=sys.stderr,
            )
            sys.exit(1)

    # BUG-008: re-validate a caller-supplied --price against a fresh live LTP.
    # A dry-run's printed --price is a snapshot taken at generation time; if the
    # printed command is executed later, that price may no longer reflect the
    # market. Only matters at actual execution (--no-dry-run) — a dry-run
    # preview never writes to the DB, so there is nothing to protect yet, and
    # skipping it here avoids a live network call on every preview. --close
    # already fetches a live LTP above, so it's exempt too.
    if price_was_explicit and not args.close and not args.dry_run:
        live_price: Decimal | None = None
        try:
            drift_client = UpstoxMarketClient()
            drift_ltp_dict = drift_client.get_ltp_sync([instrument_key])
            raw_live_price = drift_ltp_dict.get(instrument_key)
            if raw_live_price is not None:
                live_price = Decimal(str(raw_live_price))
        # Intentional: an unverifiable live price warns, it does not block —
        # unlike the --close auto-price path, a price was already supplied here.
        # Also catches malformed LTP responses (non-numeric value → Decimal
        # conversion failure), not just fetch/network failures.
        except Exception as exc:
            print(f"WARNING: could not verify live price for drift check — {exc}", file=sys.stderr)

        if live_price is None:
            print(
                "WARNING: live LTP unavailable — proceeding with caller-supplied "
                "--price unverified.",
                file=sys.stderr,
            )
        else:
            allowed, message = _evaluate_price_drift(Decimal(args.price), live_price)
            if message:
                print(message, file=sys.stderr)
            if not allowed:
                if args.force_entry:
                    print(
                        "WARNING: price drift block overridden via --force-entry.",
                        file=sys.stderr,
                    )
                else:
                    sys.exit(1)

    ivr_at_entry = _get_ivr_and_enforce(
        trade_date,
        TradeAction(args.action),
        args.vix_data_dir,
        args.db_path,
        force_entry=args.force_entry,
    )

    # IC strategies (paper_ic_nifty_v1_*/v2_*) are exempt from this account-wide
    # check: per explicit product decision (2026-07-03, DECISIONS.md "IC entries
    # judged in isolation"), an IC's hedge-leg BUYs must never be influenced by
    # unrelated strategies' (CSP, futures, proxy, spot) open positions. Other
    # strategies (e.g. CSP rolls) are unaffected and still go through this gate.
    if (
        args.action == "BUY"
        and not args.close
        and not args.force_entry
        and not args.strategy.startswith("paper_ic_")
    ):
        try:
            market_client = UpstoxMarketClient()
            ltp_dict = market_client.get_ltp_sync(["NSE_INDEX|Nifty 50"])
            if "NSE_INDEX|Nifty 50" in ltp_dict:
                nifty_spot = ltp_dict["NSE_INDEX|Nifty 50"]
            else:
                print(
                    "ERROR: failed to fetch live Nifty spot price (key missing in LTP response).",
                    file=sys.stderr,
                )
                sys.exit(1)
        except Exception as exc:
            print(f"ERROR: failed to fetch live Nifty spot price — {exc}", file=sys.stderr)
            sys.exit(1)

        store = PaperStore(args.db_path)
        strategies = store.get_strategy_names()
        positions = []
        for strat in strategies:
            strat_positions = store.get_positions(strat)
            positions.extend([p for p in strat_positions if p.net_qty != 0])

        tracker = PortfolioDeltaTracker()
        portfolio_delta = tracker.aggregate_delta(positions, nifty_spot, LOT_SIZE)
        is_protective = instrument_key.endswith("PE")

        trade_delta_lots = Decimal(args.qty) / Decimal(LOT_SIZE)
        allowed, reason = check_entry_allowed(portfolio_delta, trade_delta_lots, is_protective)
        if not allowed:
            print(reason, file=sys.stderr)
            sys.exit(1)
        elif reason.startswith("WARNING:"):
            print(reason)

    try:
        trade = PaperTrade(
            strategy_name=args.strategy,
            leg_role=args.leg,
            instrument_key=instrument_key,
            trade_date=trade_date,
            action=TradeAction(args.action),
            quantity=args.qty,
            price=Decimal(args.price),
            notes=args.notes,
            ivr_at_entry=ivr_at_entry,
        )
    # Intentional: top-level catch for trade recording failure.
    except Exception as exc:
        print(f"ERROR: invalid trade data — {exc}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("Dry run — paper trade NOT inserted:\n")
        print(f"  strategy  : {trade.strategy_name}")
        print(f"  leg_role  : {trade.leg_role}")
        print(f"  key       : {trade.instrument_key}")
        print(f"  date      : {trade.trade_date}")
        print(f"  action    : {trade.action.value}")
        print(f"  quantity  : {trade.quantity}")
        print(f"  price     : ₹{trade.price}")
        ivr_display = (
            f"{trade.ivr_at_entry:.2f}"
            if trade.ivr_at_entry is not None
            else "None (VIX data missing — R3 gate skipped)"
        )
        print(f"  ivr_entry : {ivr_display}")
        print(f"  is_paper  : {trade.is_paper}")
        if trade.notes:
            print(f"  notes     : {trade.notes}")
        return

    store = PaperStore(args.db_path)
    if store.record_trade(trade):
        if ivr_at_entry is not None and ivr_at_entry < 0.25 and args.force_entry:
            try:
                from datetime import datetime, timezone

                from src.paper.models import ExitSignal

                store.create_exit_event(
                    strategy_name=trade.strategy_name,
                    leg_name=trade.leg_role,
                    trade_id=trade.instrument_key or "unknown",
                    event_time=datetime.now(timezone.utc),
                    detected_by="MANUAL",
                    exit_signal=ExitSignal.MANUAL_OVERRIDE,
                    severity="WARNING",
                    entry_price=trade.price,
                    notes=f"R3 override: forced entry at low IVR {ivr_at_entry:.2f}",
                )
            except Exception as exc:
                print(f"WARNING: failed to write MANUAL_OVERRIDE event — {exc}", file=sys.stderr)

    pos = store.get_position(trade.strategy_name, trade.leg_role)
    if pos.net_qty == 0:
        print(f"{trade.strategy_name} / {trade.leg_role}: position closed (net qty = 0)")
    else:
        direction = "short" if pos.net_qty < 0 else "long"
        ref_price = pos.avg_sell_price if pos.net_qty < 0 else pos.avg_cost
        print(
            f"{trade.strategy_name} / {trade.leg_role}: "
            f"{pos.net_qty} units ({direction}) @ avg ₹{ref_price:.2f}"
        )


if __name__ == "__main__":
    main()
