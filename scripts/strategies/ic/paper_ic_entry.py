# scripts/strategies/ic/paper_ic_entry.py
"""CLI for Iron Condor entry.

Gates on IVR, checks open positions, determines mode, fetches live option
chain, selects short/long strikes based on config, applies liquidity and
portfolio delta gates, prints/executes record_paper_trade commands, and
sends a Telegram notification.
"""

# fmt: off
from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import structlog
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.strategies.ic.ic_entry_gates import (
    _post_expiry_gate,
    ic_relevant_strategy_names,
    make_gate_violation,
)
from src.backtest.ivr import compute_ivr
from src.backtest.vix_ingest import fetch_vix_latest, load_vix_series
from src.client.upstox_market import UpstoxMarketClient
from src.config import settings
from src.instruments.lookup import InstrumentLookup
from src.instruments.strike_selector import (
    _apply_liquidity_gate,
    filter_strikes_by_delta,
    rank_strikes,
)
from src.intraday.market_store import IntradayMarketStore
from src.notifications.telegram_gateway import TelegramGateway
from src.paper.constants import (
    DEFAULT_BOD_PATH,
    DEFAULT_DB_PATH,
    LOT_SIZE,
    STRATEGY_CSP,
)
from src.paper.store import PaperStore
from src.risk.delta_tracker import PortfolioDeltaTracker
from src.strategy.ic_expiry_config import CONFIGS

load_dotenv()

_SCRIPT_NAME = "scripts.strategies.ic.paper_ic_entry"
logger = structlog.get_logger(_SCRIPT_NAME)


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Coerce *val* to float; return *default* on any failure."""
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_price(val: Any) -> Decimal | None:
    """Coerce *val* to Decimal; return None on any failure."""
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, TypeError, ValueError):
        return None


def extract_strike_row(entry: dict[str, Any], option_type: str) -> dict[str, Any] | None:
    """Extract price and delta info for a single strike side."""
    strike = entry.get("strike_price")
    raw_key = "call_options" if option_type == "CE" else "put_options"
    opt = entry.get(raw_key) or {}
    greeks = opt.get("option_greeks") or {}
    mktdata = opt.get("market_data") or {}
    instrument_key = opt.get("instrument_key", "")
    if not instrument_key:
        return None

    delta = _safe_float(greeks.get("delta"))
    ltp = _safe_price(mktdata.get("ltp"))
    if ltp is None:
        return None

    bid = _safe_price(mktdata.get("bid_price")) or Decimal("0")
    ask = _safe_price(mktdata.get("ask_price")) or Decimal("0")
    mid = (bid + ask) / Decimal("2") if (bid > Decimal("0") and ask > Decimal("0")) else ltp

    return {
        "side": option_type,
        "strike": float(strike) if strike is not None else 0.0,
        "delta": delta,
        "iv": _safe_float(greeks.get("iv")),
        "ltp": ltp,
        "mid": mid,
        "bid": bid,
        "ask": ask,
        "oi": int(_safe_float(mktdata.get("oi"))),
        "instrument_key": instrument_key,
    }


def get_chain_price_for_strike(
    chain: list[dict[str, Any]], strike: float, option_type: str
) -> dict[str, Any]:
    """Retrieve extracted strike row for specific strike/type from chain."""
    for entry in chain:
        if abs(entry.get("strike_price", 0.0) - strike) < 0.01:
            row = extract_strike_row(entry, option_type)
            if row is not None:
                return row
    raise ValueError(f"Strike {strike} {option_type} not found in chain or has no price")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Iron Condor entry helper.")
    parser.add_argument(
        "--expiry-type",
        required=True,
        choices=["weekly", "monthly", "leaps", "yearly"],
        help="Which expiry bucket to trade.",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print commands; do not execute (default: on).",
    )
    parser.add_argument(
        "--force-entry",
        action="store_true",
        help="Skip IVR gate and portfolio-delta gate; log WARNING per bypass.",
    )
    parser.add_argument(
        "--log-only-gates",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Threshold gates (IVR, DTE window, liquidity floor, portfolio-"
            "delta cap) record a GateViolation and let entry proceed instead "
            "of blocking (default: on). Structural gates (duplicate, "
            "post-expiry, unresolved instrument keys, stale/missing chain "
            "data) always hard-block regardless of this flag."
        ),
    )
    parser.add_argument(
        "--bod-path",
        type=Path,
        default=DEFAULT_BOD_PATH,
        help=f"Path to BOD instruments JSON file (default: {DEFAULT_BOD_PATH}).",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to paper trading DB (default: {DEFAULT_DB_PATH}).",
    )
    return parser.parse_args()


async def run() -> None:
    """Run the Iron Condor entry workflow."""
    args = parse_args()
    config = CONFIGS[args.expiry_type]

    # Step 2: Duplicate guard (STRUCTURAL — never bypassed)
    store = PaperStore(args.db_path)
    open_positions = store.get_positions(config.strategy_name)
    if any(pos.net_qty != 0 for pos in open_positions):
        print(
            f"ERROR: active position already exists for {config.strategy_name}",
            file=sys.stderr,
        )
        sys.exit(1)

    gate_violations = []

    # Step 2b: Post-expiry gate (monthly only) — block entry before last-Tuesday settlement
    if args.expiry_type == "monthly":
        _post_expiry_gate()

    # Step 3: Mode detection
    csp_positions = store.get_positions(STRATEGY_CSP)
    if any(pos.net_qty != 0 for pos in csp_positions):
        mode = "concurrent"
    else:
        mode = "standalone"

    # Step 4: Delta targets
    if mode == "concurrent":
        put_target = config.short_put_delta - Decimal("0.06")
        call_target = config.short_call_delta + Decimal("0.03")
    else:
        put_target = config.short_put_delta
        call_target = config.short_call_delta

    # Step 5: IVR gate
    vix_data_dir = Path("data/historical/ohlc/india_vix")
    ivr = None
    if vix_data_dir.exists():
        try:
            series = load_vix_series(vix_data_dir)
            vix_today = IntradayMarketStore(args.db_path).get_latest_vix_today()
            if vix_today is None:
                vix_today = fetch_vix_latest()
            if vix_today is not None:
                ivr = compute_ivr(vix_today, series)
        except Exception as exc:
            # Intentional: broad catch to prevent VIX data issues from crashing
            # the script; IVR gate will fail cleanly or bypass if forced.
            logger.warning("vix.load_failed", error=str(exc))
    else:
        logger.warning("vix.dir_missing", path=str(vix_data_dir))

    # ivr=None (stale/missing VIX window) is STRUCTURAL — always hard-blocks
    # unless force_entry (legacy bypass), never bypassed by log-only-gates.
    if ivr is None:
        if args.force_entry:
            logger.warning("force_entry.ivr_bypass", ivr=ivr, gate=config.ivr_gate)
        else:
            print(
                "ERROR: India VIX IVR is None (insufficient data). Stop.",
                file=sys.stderr,
            )
            sys.exit(1)
    # Tracks whether ivr was below gate and entry proceeded anyway (via
    # --force-entry or --log-only-gates) — used later to force the SELL leg
    # subprocess calls through record_paper_trade.py's own independent R3
    # gate, which would otherwise re-block what this script already allowed.
    ivr_below_gate = ivr is not None and ivr < float(config.ivr_gate)
    if ivr is not None and ivr < float(config.ivr_gate):
        # THRESHOLD gate.
        if args.force_entry:
            logger.warning("force_entry.ivr_bypass", ivr=ivr, gate=config.ivr_gate)
        elif args.log_only_gates:
            logger.warning(
                "gate.ivr_violation_logged", ivr=ivr, gate=float(config.ivr_gate)
            )
            gate_violations.append(
                make_gate_violation(
                    gate_name="ivr",
                    threshold=str(config.ivr_gate),
                    actual=f"{ivr:.4f}",
                    strategy_name=config.strategy_name,
                )
            )
        else:
            print(
                f"ERROR: India VIX IVR = {ivr:.2f} below gate threshold of {config.ivr_gate:.2f}.",
                file=sys.stderr,
            )
            sys.exit(1)

    if ivr is not None:
        print(f"INFO: India VIX IVR = {ivr:.2f} (gate={config.ivr_gate})")

    # Step 6: DTE window check
    if not args.bod_path.exists():
        print(f"ERROR: BOD file not found at {args.bod_path}", file=sys.stderr)
        sys.exit(1)

    try:
        lookup = InstrumentLookup.from_file(args.bod_path)
        expiries = lookup.get_expiry_candidates(
            underlying="NIFTY",
            today=date.today(),
            preference=[config.expiry_bucket],
        )
    except Exception as exc:
        # Intentional: broad catch for BOD loading/expiry resolution to ensure
        # exit 1 failure is reported to caller.
        print(
            f"ERROR: failed to load BOD or resolve expiries: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    expiry_str = None
    for label, exp_str in expiries:
        if label == config.expiry_bucket:
            expiry_str = exp_str
            break

    if expiry_str is None:
        print(
            f"ERROR: no {config.expiry_bucket} expiry candidate found. Stop.",
            file=sys.stderr,
        )
        sys.exit(1)

    expiry_date = date.fromisoformat(expiry_str)
    dte = (expiry_date - date.today()).days
    if dte < config.dte_warn_lo or dte > config.dte_warn_hi:
        logger.warning(
            "dte.outside_range",
            dte=dte,
            min_dte=config.dte_warn_lo,
            max_dte=config.dte_warn_hi,
        )
        if args.log_only_gates:
            gate_violations.append(
                make_gate_violation(
                    gate_name="dte_window",
                    threshold=f"[{config.dte_warn_lo}, {config.dte_warn_hi}]",
                    actual=str(dte),
                    strategy_name=config.strategy_name,
                )
            )
    else:
        print(f"INFO: selected expiry = {expiry_str} (DTE={dte})")

    # Step 7: Live chain fetch
    try:
        client = UpstoxMarketClient(settings.upstox_analytics_token)
        raw_chain = client.get_option_chain_sync("NSE_INDEX|Nifty 50", expiry_str)
    except Exception as exc:
        # Intentional: broad catch for live network client to ensure failure
        # exits gracefully with diagnostic message.
        print(
            f"ERROR: failed to fetch option chain for {expiry_str}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not raw_chain:
        print(f"ERROR: option chain empty for {expiry_str}", file=sys.stderr)
        sys.exit(1)

    # Step 8: Strike selection (4 legs)
    delta_range_val = config.delta_range
    put_min = float(put_target - delta_range_val)
    put_max = float(put_target + delta_range_val)
    call_min = float(call_target - delta_range_val)
    call_max = float(call_target + delta_range_val)

    short_put_candidates = filter_strikes_by_delta(raw_chain, "PE", put_min, put_max)
    ranked_put = rank_strikes(short_put_candidates)
    if not ranked_put:
        print("ERROR: failed to resolve leg short_put", file=sys.stderr)
        sys.exit(1)
    short_put = ranked_put[0]

    short_call_candidates = filter_strikes_by_delta(raw_chain, "CE", call_min, call_max)
    ranked_call = rank_strikes(short_call_candidates)
    if not ranked_call:
        print("ERROR: failed to resolve leg short_call", file=sys.stderr)
        sys.exit(1)
    short_call = ranked_call[0]

    # Resolve long legs
    long_put_strike = float(short_put["strike"]) - config.wing_width_points
    long_call_strike = float(short_call["strike"]) + config.wing_width_points

    long_put_candidates = lookup.search_options(
        underlying="NIFTY",
        strike=long_put_strike,
        option_type="PE",
        expiry=expiry_str,
    )
    if not long_put_candidates:
        print("ERROR: failed to resolve leg long_put", file=sys.stderr)
        sys.exit(1)
    long_put_key = long_put_candidates[0]["instrument_key"]

    long_call_candidates = lookup.search_options(
        underlying="NIFTY",
        strike=long_call_strike,
        option_type="CE",
        expiry=expiry_str,
    )
    if not long_call_candidates:
        print("ERROR: failed to resolve leg long_call", file=sys.stderr)
        sys.exit(1)
    long_call_key = long_call_candidates[0]["instrument_key"]

    # Step 9: Liquidity gate (THRESHOLD)
    if not _apply_liquidity_gate([short_put]):
        if args.log_only_gates:
            logger.warning("gate.liquidity_violation_logged", leg="short_put")
            gate_violations.append(
                make_gate_violation(
                    gate_name="liquidity_short_put",
                    threshold="liquidity_gate_pass",
                    actual="failed",
                    strategy_name=config.strategy_name,
                )
            )
        else:
            print("ERROR: short_put failed liquidity gate", file=sys.stderr)
            sys.exit(1)
    if not _apply_liquidity_gate([short_call]):
        if args.log_only_gates:
            logger.warning("gate.liquidity_violation_logged", leg="short_call")
            gate_violations.append(
                make_gate_violation(
                    gate_name="liquidity_short_call",
                    threshold="liquidity_gate_pass",
                    actual="failed",
                    strategy_name=config.strategy_name,
                )
            )
        else:
            print("ERROR: short_call failed liquidity gate", file=sys.stderr)
            sys.exit(1)

    # Step 10: Portfolio delta check
    # Fetch spot to determine current delta & projected delta
    ltp_map = client.get_ltp_sync(["NSE_INDEX|Nifty 50"])
    nifty_spot = ltp_map.get("NSE_INDEX|Nifty 50")
    if nifty_spot is None:
        print(
            "ERROR: failed to fetch live Nifty 50 spot price.",
            file=sys.stderr,
        )
        sys.exit(1)

    strategies_list = ic_relevant_strategy_names(store.get_strategy_names())
    all_open_pos = []
    for strat in strategies_list:
        all_open_pos.extend([p for p in store.get_positions(strat) if p.net_qty != 0])

    tracker = PortfolioDeltaTracker()
    portfolio_delta = tracker.aggregate_delta(all_open_pos, Decimal(str(nifty_spot)), LOT_SIZE)
    current_delta_lots = portfolio_delta.total_delta_lots

    ic_delta_lots = Decimal(str(abs(short_put["delta"]))) - Decimal(str(abs(short_call["delta"])))
    projected_total = current_delta_lots + ic_delta_lots

    if not args.force_entry:
        if projected_total < Decimal("-0.05") or projected_total > Decimal("0.25"):
            # Attempt one-strike OTM adjustment
            adjusted = False
            sorted_chain = sorted(raw_chain, key=lambda e: e.get("strike_price", 0.0))
            strikes = [e.get("strike_price", 0.0) for e in sorted_chain]

            if projected_total > Decimal("0.25"):
                # Shift short put one strike further OTM (lower strike)
                try:
                    idx = strikes.index(short_put["strike"])
                    if idx > 0:
                        adj_entry = sorted_chain[idx - 1]
                        adj_put = extract_strike_row(adj_entry, "PE")
                        if adj_put and _apply_liquidity_gate([adj_put]):
                            new_ic_delta = Decimal(str(abs(adj_put["delta"]))) - Decimal(
                                str(abs(short_call["delta"]))
                            )
                            if (
                                Decimal("-0.05")
                                <= (current_delta_lots + new_ic_delta)
                                <= Decimal("0.25")
                            ):
                                # Success
                                short_put = adj_put
                                long_put_strike = (
                                    float(short_put["strike"]) - config.wing_width_points
                                )
                                long_put_candidates = lookup.search_options(
                                    underlying="NIFTY",
                                    strike=long_put_strike,
                                    option_type="PE",
                                    expiry=expiry_str,
                                )
                                if long_put_candidates:
                                    long_put_key = long_put_candidates[0]["instrument_key"]
                                    adjusted = True
                                    print(
                                        f"INFO: Portfolio delta gate "
                                        f"adjusted short_put to "
                                        f"{short_put['strike']}"
                                    )
                except ValueError:
                    pass

            elif projected_total < Decimal("-0.05"):
                # Shift short call one strike further OTM (higher strike)
                try:
                    idx = strikes.index(short_call["strike"])
                    if idx < len(strikes) - 1:
                        adj_entry = sorted_chain[idx + 1]
                        adj_call = extract_strike_row(adj_entry, "CE")
                        if adj_call and _apply_liquidity_gate([adj_call]):
                            new_ic_delta = Decimal(str(abs(short_put["delta"]))) - Decimal(
                                str(abs(adj_call["delta"]))
                            )
                            if (
                                Decimal("-0.05")
                                <= (current_delta_lots + new_ic_delta)
                                <= Decimal("0.25")
                            ):
                                # Success
                                short_call = adj_call
                                long_call_strike = (
                                    float(short_call["strike"]) + config.wing_width_points
                                )
                                long_call_candidates = lookup.search_options(
                                    underlying="NIFTY",
                                    strike=long_call_strike,
                                    option_type="CE",
                                    expiry=expiry_str,
                                )
                                if long_call_candidates:
                                    long_call_key = long_call_candidates[0]["instrument_key"]
                                    adjusted = True
                                    print(
                                        f"INFO: Portfolio delta gate "
                                        f"adjusted short_call to "
                                        f"{short_call['strike']}"
                                    )
                except ValueError:
                    pass

            if not adjusted:
                if args.log_only_gates:
                    logger.warning(
                        "gate.portfolio_delta_violation_logged",
                        projected_total=str(projected_total),
                    )
                    gate_violations.append(
                        make_gate_violation(
                            gate_name="portfolio_delta",
                            threshold="[-0.05, 0.25]",
                            actual=f"{projected_total:.4f}",
                            strategy_name=config.strategy_name,
                        )
                    )
                else:
                    print(
                        f"ERROR: Portfolio delta check failed. "
                        f"Projected={projected_total:.3f} lots "
                        f"(outside [-0.05, 0.25]). Stop.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
    else:
        if projected_total < Decimal("-0.05") or projected_total > Decimal("0.25"):
            logger.warning("force_entry.delta_bypass", projected_total=projected_total)

    # Persist all threshold-gate violations collected above (log-only mode).
    for violation in gate_violations:
        try:
            store.record_gate_violation(violation)
        except Exception as exc:  # noqa: BLE001 — persistence failure must not block entry
            logger.warning(
                "gate_violation.persist_failed", gate_name=violation.gate_name, error=str(exc)
            )

    # Get prices for long options now that the final strikes are locked
    long_put = get_chain_price_for_strike(raw_chain, long_put_strike, "PE")
    long_call = get_chain_price_for_strike(raw_chain, long_call_strike, "CE")

    # Step 11: Build and print/execute commands
    legs = [
        ("short_put", "SELL", short_put["instrument_key"], short_put["mid"]),
        ("long_put_hedge", "BUY", long_put_key, long_put["mid"]),
        ("short_call", "SELL", short_call["instrument_key"], short_call["mid"]),
        ("long_call_hedge", "BUY", long_call_key, long_call["mid"]),
    ]

    cmds = []
    for role, action, key, price in legs:
        cmd = [
            "python",
            "-m",
            "scripts.record.record_paper_trade",
            "--strategy",
            config.strategy_name,
            "--leg",
            role,
            "--key",
            key,
            "--action",
            action,
            "--qty",
            str(LOT_SIZE),
            "--price",
            str(price),
        ]
        # record_paper_trade.py has no --ivr flag — it computes ivr_at_entry
        # itself and enforces its own independent R3 gate (hard-blocks SELL
        # at ivr<0.25 unless --force-entry). If this script already decided
        # to proceed despite ivr<gate (via --force-entry or log-only-gates),
        # pass --force-entry on SELL legs only, so the downstream gate
        # doesn't re-block an entry already approved upstream. BUY hedge
        # legs are left alone so record_paper_trade's own portfolio-delta
        # check still runs on them.
        if action == "SELL" and ivr_below_gate:
            cmd.append("--force-entry")
        cmds.append(cmd)

    if args.dry_run:
        print("\n[DRY-RUN] Commands to execute:")
        for cmd in cmds:
            print(" ".join(cmd))
    else:
        for cmd in cmds:
            print(f"Executing: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)

        # Step 12: Telegram notification (live mode only)
        net_credit = (short_put["mid"] + short_call["mid"]) - (long_put["mid"] + long_call["mid"])
        msg = (
            f"✅ IC Entry — {args.expiry_type} ({config.strategy_name})\n"
            f"Mode: {mode}\n"
            f"IVR: {ivr:.2f}  DTE: {dte}  Nifty: {nifty_spot:,.0f}\n\n"
            f"Short Put  {int(short_put['strike'])}PE  "
            f"δ={abs(short_put['delta']):.3f}  mid=₹{short_put['mid']:.2f}\n"
            f"Long Put   {int(long_put_strike)}PE   (hedge)\n"
            f"Short Call {int(short_call['strike'])}CE "
            f"δ={abs(short_call['delta']):.3f}  mid=₹{short_call['mid']:.2f}\n"
            f"Long Call  {int(long_call_strike)}CE  (hedge)\n\n"
            f"Net credit: ₹{net_credit:.2f}/lot  "
            f"(₹{net_credit * LOT_SIZE:,.0f} for {LOT_SIZE} units)"
        )
        try:
            tg = TelegramGateway(
                bot_token=settings.telegram_bot_token,
                chat_id=settings.telegram_chat_id,
                db_path=str(args.db_path),
            )
            await tg.send_notification(msg)
        except Exception as exc:
            # Intentional: telegram delivery failure is non-fatal; log warning and
            # proceed without failing the script.
            logger.warning("telegram.send_failed", error=str(exc))


def main() -> None:
    """CLI entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
