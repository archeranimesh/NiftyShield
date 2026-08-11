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
    capture_entry_margin,
    make_gate_violation,
)
from src.backtest.ivr import compute_ivr
from src.backtest.vix_ingest import fetch_vix_latest, load_vix_series
from src.client.upstox_live import UpstoxLiveClient
from src.client.upstox_market import UpstoxMarketClient
from src.config import settings
from src.instruments.lookup import InstrumentLookup, format_option_label
from src.instruments.strike_selector import (
    _apply_liquidity_gate,
    filter_strikes_by_delta,
    rank_strikes,
)
from src.intraday.market_store import IntradayMarketStore
from src.notifications.telegram import build_notifier
from src.notifications.telegram_gateway import TelegramGateway
from src.paper.constants import (
    DEFAULT_BOD_PATH,
    DEFAULT_DB_PATH,
    LOT_SIZE,
    STRATEGY_CSP,
)
from src.paper.store import PaperStore
from src.strategy.ic_expiry_config import CONFIGS
from src.utils.logging import setup_logging

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


def _compensate_legs(
    persisted_legs: list[tuple[str, str, str, Decimal]],
    strategy_name: str,
) -> tuple[list[str], list[str]]:
    """Issue same-day compensating closes for legs already persisted mid-sequence.

    RH-1: the 4-leg entry sequence is 4 independent `record_paper_trade.py`
    subprocess calls with no shared transaction. If a middle leg fails (crash
    or silent no-op), the legs that already landed are left in the DB —
    a naked short with no offsetting hedge is a real risk-exposure bug, not
    bookkeeping. This reverses each already-persisted leg's action (SELL<->BUY)
    at its original entry price to zero out net_qty immediately; it is a
    compensating trade, not a market-price close — the goal is removing the
    exposure, not capturing P&L on it. `--force-entry` bypasses the R3 IVR
    gate and price-drift check, both of which are designed to guard fresh
    entries and would otherwise be able to block an urgent unwind.

    Returns:
        (compensated_roles, failed_roles) — roles whose reversing trade
        persisted successfully vs. roles where the compensating subprocess
        call itself failed (these require manual intervention).
    """
    compensated: list[str] = []
    failed: list[str] = []
    for role, action, key, price in persisted_legs:
        reverse_action = "BUY" if action == "SELL" else "SELL"
        cmd = [
            sys.executable,
            "-m",
            "scripts.record.record_paper_trade",
            "--strategy",
            strategy_name,
            "--leg",
            role,
            "--key",
            key,
            "--action",
            reverse_action,
            "--qty",
            str(LOT_SIZE),
            "--price",
            str(price),
            "--force-entry",
            "--no-dry-run",
        ]
        try:
            print(f"Compensating: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            compensated.append(role)
        except subprocess.CalledProcessError as exc:
            logger.error("ic_entry.compensation_failed", leg=role, error=str(exc))
            failed.append(role)
    return compensated, failed


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
    setup_logging()
    args = parse_args()
    config = CONFIGS[args.expiry_type]

    # Build a Telegram notifier for gate-failure alerts (non-fatal). Mirrors
    # paper_ic_entry_v2.py's _gate_alert exactly — V1 previously had no
    # gate-failure alerting at all (Telegram only fired on partial-execution
    # failure and final success), silently exiting on every structural gate
    # below. See DECISIONS.md 2026-08-11 "IC V1/V2 gate-failure alert audit".
    _tg = build_notifier()

    def _gate_alert(msg: str) -> None:
        """Fire a Telegram gate-failure alert (sync wrapper, non-fatal).

        Schedules ``_tg.send`` as an asyncio task. Any exception — including
        network failures — is swallowed so that telegram never blocks a gate
        exit.
        """
        if _tg is None:
            return
        try:
            asyncio.get_running_loop().create_task(_tg.send(msg))
        except Exception:  # noqa: BLE001
            pass

    # Step 2: Duplicate guard (STRUCTURAL — never bypassed)
    store = PaperStore(args.db_path)
    open_positions = store.get_positions(config.strategy_name)
    if any(pos.net_qty != 0 for pos in open_positions):
        logger.error("ic_entry.duplicate_position", strategy_name=config.strategy_name)
        _gate_alert(
            f"⚠️ IC Entry BLOCKED — {config.strategy_name}\n"
            f"Gate: duplicate\n"
            f"Reason: Active position already exists"
        )
        sys.exit(1)

    gate_violations = []

    # Step 2b: Post-expiry gate (monthly only) — block entry before last-Tuesday settlement
    if args.expiry_type == "monthly":
        try:
            _post_expiry_gate()
        except SystemExit:
            _gate_alert(
                f"⚠️ IC Entry BLOCKED — {config.strategy_name}\n"
                f"Gate: post_expiry_gate\n"
                f"Reason: Current month expiry not yet passed"
            )
            raise

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
            logger.error("ic_entry.ivr_data_unavailable")
            _gate_alert(
                f"⚠️ IC Entry BLOCKED — {config.strategy_name}\n"
                f"Gate: ivr\n"
                f"Reason: VIX data unavailable/stale"
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
            logger.error("ic_entry.ivr_gate_blocked", ivr=ivr, gate=float(config.ivr_gate))
            _gate_alert(
                f"⚠️ IC Entry BLOCKED — {config.strategy_name}\n"
                f"Gate: ivr\n"
                f"IVR: {ivr:.2f} / Gate: {float(config.ivr_gate):.2f}"
            )
            sys.exit(1)

    if ivr is not None:
        logger.info("ic_entry.ivr_resolved", ivr=ivr, gate=float(config.ivr_gate))

    # Step 6: DTE window check
    if not args.bod_path.exists():
        logger.error("ic_entry.bod_file_missing", bod_path=str(args.bod_path))
        _gate_alert(
            f"⚠️ IC Entry BLOCKED — {config.strategy_name}\n"
            f"Gate: resolve_expiry\n"
            f"Reason: BOD instruments file missing ({args.bod_path})"
        )
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
        logger.error("ic_entry.bod_load_failed", error=str(exc))
        _gate_alert(
            f"⚠️ IC Entry BLOCKED — {config.strategy_name}\n"
            f"Gate: resolve_expiry\n"
            f"Reason: BOD load/expiry resolution failed: {exc}"
        )
        sys.exit(1)

    expiry_str = None
    for label, exp_str in expiries:
        if label == config.expiry_bucket:
            expiry_str = exp_str
            break

    if expiry_str is None:
        logger.error("ic_entry.no_expiry_candidate", expiry_bucket=config.expiry_bucket)
        _gate_alert(
            f"⚠️ IC Entry BLOCKED — {config.strategy_name}\n"
            f"Gate: resolve_expiry\n"
            f"Reason: No '{config.expiry_bucket}' expiry candidate found"
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
        logger.info("ic_entry.expiry_selected", expiry=expiry_str, dte=dte)

    # Step 7: Live chain fetch
    try:
        client = UpstoxMarketClient(settings.upstox_analytics_token)
        raw_chain = client.get_option_chain_sync("NSE_INDEX|Nifty 50", expiry_str)
    except Exception as exc:
        # Intentional: broad catch for live network client to ensure failure
        # exits gracefully with diagnostic message.
        logger.error("ic_entry.chain_fetch_failed", expiry=expiry_str, error=str(exc))
        _gate_alert(
            f"⚠️ IC Entry BLOCKED — {config.strategy_name}\n"
            f"Gate: chain_fetch\n"
            f"Reason: Live option chain fetch failed: {exc}"
        )
        sys.exit(1)

    if not raw_chain:
        logger.error("ic_entry.chain_empty", expiry=expiry_str)
        _gate_alert(
            f"⚠️ IC Entry BLOCKED — {config.strategy_name}\n"
            f"Gate: chain_fetch\n"
            f"Reason: Live option chain empty for expiry {expiry_str}"
        )
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
        logger.error("ic_entry.leg_resolution_failed", leg="short_put")
        _gate_alert(
            f"⚠️ IC Entry BLOCKED — {config.strategy_name}\n"
            f"Gate: leg_resolution\n"
            f"Reason: No short_put candidate in delta range [{put_min:.2f}, {put_max:.2f}]"
        )
        sys.exit(1)
    short_put = ranked_put[0]

    short_call_candidates = filter_strikes_by_delta(raw_chain, "CE", call_min, call_max)
    ranked_call = rank_strikes(short_call_candidates)
    if not ranked_call:
        logger.error("ic_entry.leg_resolution_failed", leg="short_call")
        _gate_alert(
            f"⚠️ IC Entry BLOCKED — {config.strategy_name}\n"
            f"Gate: leg_resolution\n"
            f"Reason: No short_call candidate in delta range [{call_min:.2f}, {call_max:.2f}]"
        )
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
        logger.error("ic_entry.leg_resolution_failed", leg="long_put")
        _gate_alert(
            f"⚠️ IC Entry BLOCKED — {config.strategy_name}\n"
            f"Gate: leg_resolution\n"
            f"Reason: No long_put hedge found at strike {long_put_strike}"
        )
        sys.exit(1)
    long_put_key = long_put_candidates[0]["instrument_key"]

    long_call_candidates = lookup.search_options(
        underlying="NIFTY",
        strike=long_call_strike,
        option_type="CE",
        expiry=expiry_str,
    )
    if not long_call_candidates:
        logger.error("ic_entry.leg_resolution_failed", leg="long_call")
        _gate_alert(
            f"⚠️ IC Entry BLOCKED — {config.strategy_name}\n"
            f"Gate: leg_resolution\n"
            f"Reason: No long_call hedge found at strike {long_call_strike}"
        )
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
            logger.error("ic_entry.liquidity_gate_blocked", leg="short_put")
            _gate_alert(
                f"⚠️ IC Entry BLOCKED — {config.strategy_name}\n"
                f"Gate: liquidity\n"
                f"Reason: short_put failed the liquidity gate"
            )
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
            logger.error("ic_entry.liquidity_gate_blocked", leg="short_call")
            _gate_alert(
                f"⚠️ IC Entry BLOCKED — {config.strategy_name}\n"
                f"Gate: liquidity\n"
                f"Reason: short_call failed the liquidity gate"
            )
            sys.exit(1)

    # Step 10: Fetch spot (used only for the Telegram notification below).
    # Portfolio-level delta gating/self-adjustment removed 2026-07-03 per
    # explicit product decision: IC entries are judged on their own two short
    # legs only, never against other strategies' or other IC variants'
    # positions. See DECISIONS.md 2026-07-03 "IC entries judged in isolation."
    ltp_map = client.get_ltp_sync(["NSE_INDEX|Nifty 50"])
    nifty_spot = ltp_map.get("NSE_INDEX|Nifty 50")
    if nifty_spot is None:
        logger.error("ic_entry.spot_fetch_failed")
        _gate_alert(
            f"⚠️ IC Entry BLOCKED — {config.strategy_name}\n"
            f"Gate: spot_fetch\n"
            f"Reason: Nifty spot LTP fetch returned no data"
        )
        sys.exit(1)

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
            sys.executable,
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
        # record_paper_trade.py computes ivr_at_entry itself and enforces its
        # own independent R3 gate (hard-blocks SELL at ivr < --ivr-gate unless
        # --force-entry). Always pass this script's config.ivr_gate through so
        # the downstream gate matches the strategy's actual configured
        # threshold instead of falling back to its own hardcoded default —
        # weekly's gate (0.15) previously diverged silently from that
        # hardcoded 0.25, so a SELL at ivr=0.16 cleared this script's own gate
        # but still crashed downstream with an unhandled CalledProcessError
        # (found 2026-07-08).
        cmd.extend(["--ivr-gate", str(config.ivr_gate)])
        # If this script already decided to proceed despite ivr<gate (via
        # --force-entry or log-only-gates), pass --force-entry on SELL legs
        # only, so the downstream gate doesn't re-block an entry already
        # approved upstream. BUY hedge legs are left alone so
        # record_paper_trade's own portfolio-delta check still runs on them.
        if action == "SELL" and ivr_below_gate:
            cmd.append("--force-entry")
        # record_paper_trade.py's own --dry-run defaults to True (BooleanOptionalAction).
        # This script's --dry-run/--no-dry-run only controls whether *this* script
        # previews vs. executes the subprocess call — it must be forwarded explicitly,
        # otherwise every "executed" leg silently no-ops in the child process (found
        # 2026-07-03: zero rows ever written to paper_trades for any paper_ic_* strategy
        # despite Telegram reporting success on every run).
        cmd.append("--no-dry-run")
        cmds.append(cmd)

    if args.dry_run:
        logger.info(
            "ic_entry.dry_run_preview",
            strategy=config.strategy_name,
            leg_count=len(cmds),
        )
        print("\n[DRY-RUN] Commands to execute:")
        for cmd in cmds:
            print(" ".join(cmd))
    else:
        logger.info(
            "ic_entry.executing_legs",
            strategy=config.strategy_name,
            leg_count=len(cmds),
        )
        subprocess_error: str | None = None
        for cmd in cmds:
            print(f"Executing: {' '.join(cmd)}")
            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as exc:
                # RH-1: stop attempting further legs on first failure — do not
                # compound a partial basket. Verification below determines
                # exactly which legs (if any) actually landed before this
                # failure, regardless of whether it crashed or silently no-op'd.
                subprocess_error = str(exc)
                logger.error("ic_entry.leg_subprocess_failed", error=subprocess_error)
                break

        # Step 12: Verify legs actually landed in the DB before reporting success.
        # subprocess exit code 0 is necessary but not sufficient — record_paper_trade.py
        # exits 0 on its own dry-run no-op path too, so a clean subprocess run alone
        # cannot distinguish "recorded" from "previewed and discarded" (the exact
        # failure mode that silently no-op'd every prior IC entry). Re-query each leg's
        # position from the DB directly. Relies on the duplicate-entry guard earlier in
        # run() — these are fresh legs with no prior fills, so net_qty==0 unambiguously
        # means "not persisted" here (would need re-deriving for a reused-in-rolls context).
        missing_legs: list[str] = []
        verification_error: str | None = None
        try:
            for role, _action, key, _price in legs:
                pos = store.get_position(config.strategy_name, role, instrument_key=key)
                if pos.net_qty == 0:
                    missing_legs.append(role)
        except Exception as exc:  # noqa: BLE001 — a DB read failure here must not be
            # silently swallowed: without this catch, an exception raised after the 4
            # subprocess calls already ran would crash the script with no Telegram
            # notification at all (neither ✅ nor ⚠️), leaving the operator blind to
            # whether legs were actually persisted — the same blind spot this
            # verification step exists to close, just moved one line later.
            verification_error = str(exc)
            logger.error("ic_entry.verification_failed", error=verification_error)

        if missing_legs or verification_error is not None or subprocess_error is not None:
            if verification_error is not None:
                # RH-1: cannot safely compensate without knowing which legs are
                # actually persisted — a blind reversal here could close a leg
                # that was never opened, or miss one that was. Alert only.
                detail = (
                    f"Post-execution DB verification itself failed: {verification_error}. "
                    f"Compensation skipped — cannot determine which legs are persisted."
                )
                compensated, compensation_failed = [], []
            else:
                persisted_legs = [leg for leg in legs if leg[0] not in missing_legs]
                compensated, compensation_failed = _compensate_legs(
                    persisted_legs, config.strategy_name
                )
                subprocess_detail = (
                    f"Leg subprocess failed ({subprocess_error}). " if subprocess_error else ""
                )
                if not persisted_legs:
                    detail = f"{subprocess_detail}No legs were persisted — nothing to compensate."
                elif compensation_failed:
                    detail = (
                        f"{subprocess_detail}{len(missing_legs)}/4 legs NOT persisted: "
                        f"{', '.join(missing_legs)}. Compensation FAILED for "
                        f"{', '.join(compensation_failed)} — MANUAL INTERVENTION REQUIRED, "
                        f"naked exposure remains on those legs. "
                        f"Compensated OK: {', '.join(compensated) or 'none'}."
                    )
                else:
                    detail = (
                        f"{subprocess_detail}{len(missing_legs)}/4 legs NOT persisted: "
                        f"{', '.join(missing_legs)}. Compensating closes succeeded for all "
                        f"{len(persisted_legs)} already-persisted legs "
                        f"({', '.join(compensated) or 'none'}) — no naked exposure remains."
                    )
            logger.error(
                "ic_entry.legs_not_persisted",
                strategy_name=config.strategy_name,
                missing_legs=missing_legs,
                verification_error=verification_error,
                subprocess_error=subprocess_error,
                compensated=compensated,
                compensation_failed=compensation_failed,
            )
            try:
                tg = TelegramGateway(
                    bot_token=settings.telegram_bot_token,
                    chat_id=settings.telegram_chat_id,
                    db_path=str(args.db_path),
                )
                await tg.send_notification(
                    f"⚠️ IC Entry — {args.expiry_type} ({config.strategy_name})\n"
                    f"{detail}\n"
                    f"Check logs immediately."
                )
            except Exception as exc:  # noqa: BLE001 — telegram delivery is non-fatal
                logger.warning("telegram.send_failed", error=str(exc))
            sys.exit(1)

        # Step 12b: Capture entry-cycle margin (non-fatal). Legs are confirmed
        # persisted above; instrument keys/actions/qty mirror the `legs` tuples
        # built for the record_paper_trade subprocess calls. Client construction
        # is wrapped here too, not just the broker call inside
        # capture_entry_margin — UpstoxLiveClient() itself can raise (missing
        # UPSTOX_ANALYTICS_TOKEN) and legs are already persisted at this point,
        # so that must never crash the script before the success notification.
        try:
            margin_legs = [(key, action, LOT_SIZE) for _role, action, key, _price in legs]
            await capture_entry_margin(
                broker=UpstoxLiveClient(),
                store=store,
                strategy_name=config.strategy_name,
                entry_date=date.today(),
                legs=margin_legs,
            )
        except Exception as exc:  # noqa: BLE001 — margin capture must never block a successful entry
            logger.warning("ic_entry.margin_capture_failed", error=str(exc))

        # Step 12c: Persist the original 4-leg entry credit (BUG-021, mirrors
        # BUG-020 Phase 2 for IronCondorV2). Legs are confirmed persisted
        # above. Non-fatal — a persistence failure here must not block a
        # successful entry; the profit-target/loss-stop branch (BUG-021 fix
        # in ic_nifty_v1.py) falls back to its existing recompute behavior
        # when this value is absent.
        net_credit = (short_put["mid"] + short_call["mid"]) - (long_put["mid"] + long_call["mid"])
        try:
            store.set_original_entry_credit(config.strategy_name, net_credit)
        except Exception as exc:  # noqa: BLE001 — persistence failure must never block entry
            logger.warning("ic_entry.original_credit_persist_failed", error=str(exc))

        # Step 13: Telegram notification — only reached once all 4 legs are
        # confirmed present in the DB.
        msg = (
            f"✅ IC Entry — {args.expiry_type} ({config.strategy_name})\n"
            f"Mode: {mode}\n"
            f"IVR: {ivr:.2f}  DTE: {dte}  Nifty: {nifty_spot:,.0f}\n\n"
            f"Short Put  {format_option_label('NIFTY', short_put['strike'], 'PE', expiry_str)}  "
            f"δ={abs(short_put['delta']):.3f}  mid=₹{short_put['mid']:.2f}\n"
            f"Long Put   {format_option_label('NIFTY', long_put_strike, 'PE', expiry_str)}   "
            f"(hedge)  mid=₹{long_put['mid']:.2f}\n"
            f"Short Call {format_option_label('NIFTY', short_call['strike'], 'CE', expiry_str)} "
            f"δ={abs(short_call['delta']):.3f}  mid=₹{short_call['mid']:.2f}\n"
            f"Long Call  {format_option_label('NIFTY', long_call_strike, 'CE', expiry_str)}  "
            f"(hedge)  mid=₹{long_call['mid']:.2f}\n\n"
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
