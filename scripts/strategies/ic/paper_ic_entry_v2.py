# scripts/strategies/ic/paper_ic_entry_v2.py
"""CLI for IronCondorV2 entry (monthly, delta-based wings).

Differences from paper_ic_entry.py (V1):
  - Long wings placed at config.long_wing_delta_target (10Δ) via chain scan,
    not fixed points.  config.long_wing_min_premium floor enforced on entry.
  - No standalone/concurrent mode split — V2 always uses nominal delta targets.
  - Portfolio-delta adjustment re-scans the chain for the 10Δ wing after
    shifting a short leg (V1 uses wing_width_points; would break here).
  - Only monthly expiry is supported in Phase 1 (CONFIGS_V2 has one preset).

Gates shared with V1 (via ic_entry_gates):
  - Duplicate position guard
  - IVR gate
  - Expiry resolution + DTE window check

Council ruling: docs/archive/council/strategy/2026-06-26_ic-v2-core-design.md Stage 3.
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
    check_duplicate,
    make_gate_violation,
    resolve_expiry,
    resolve_ivr,
)
from src.client.upstox_live import UpstoxLiveClient
from src.client.upstox_market import UpstoxMarketClient
from src.config import settings
from src.instruments.strike_selector import (
    _apply_liquidity_gate,
    filter_strikes_by_delta,
    rank_strikes,
)
from src.notifications.markdown import escape_markdown, mdcode
from src.notifications.telegram import build_notifier
from src.notifications.telegram_gateway import TelegramGateway
from src.paper.constants import (
    DEFAULT_BOD_PATH,
    DEFAULT_DB_PATH,
    LOT_SIZE,
)
from src.paper.store import PaperStore
from src.strategy.ic_expiry_config_v2 import CONFIGS_V2, IronCondorV2ExpiryConfig
from src.utils.logging import setup_logging

load_dotenv()

_SCRIPT_NAME = "scripts.strategies.ic.paper_ic_entry_v2"
logger = structlog.get_logger(_SCRIPT_NAME)

# IVR / DTE gate values for V2 monthly.
# These mirror V1 monthly (ic_expiry_config.py CONFIGS["monthly"]) — same
# market-regime requirements.  Kept here (not in IronCondorV2ExpiryConfig)
# to avoid polluting the strategy config with script-level gate concepts.
_V2_MONTHLY_IVR_GATE: Decimal = Decimal("0.25")
# DTE window recalibrated for post-Tuesday-expiry entry cadence.
# First Wednesday after last-Tuesday monthly expiry → 22–29 DTE to next expiry.
# IC-V2-13: changed from 30/45 → 20/32.
_V2_MONTHLY_DTE_WARN_LO: int = 20
_V2_MONTHLY_DTE_WARN_HI: int = 32


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    """Extract price and delta info for a single strike side from a raw chain entry."""
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
    """Retrieve extracted strike row for a specific strike/type from chain."""
    for entry in chain:
        if abs(entry.get("strike_price", 0.0) - strike) < 0.01:
            row = extract_strike_row(entry, option_type)
            if row is not None:
                return row
    raise ValueError(f"Strike {strike} {option_type} not found in chain or has no price")


def _find_long_wing(
    raw_chain: list[dict[str, Any]],
    option_type: str,
    config: IronCondorV2ExpiryConfig,
) -> dict[str, Any] | None:
    """Scan the chain for the best long wing at config.long_wing_delta_target.

    Applies both the delta floor (long_wing_delta_floor) and premium floor
    (long_wing_min_premium) per the D2 council ruling.

    Args:
        raw_chain: Live option chain list from Upstox.
        option_type: ``"PE"`` or ``"CE"``.
        config: V2 expiry config supplying delta and premium floors.

    Returns:
        Best matching strike row dict, or ``None`` if no candidate passes all floors.
    """
    lo = float(config.long_wing_delta_floor)
    hi = float(config.long_wing_delta_target) + float(config.delta_range)
    candidates = filter_strikes_by_delta(raw_chain, option_type, lo, hi)
    ranked = rank_strikes(candidates)
    for candidate in ranked:
        if candidate["mid"] >= config.long_wing_min_premium:
            return candidate
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="IronCondorV2 entry helper (monthly).")
    parser.add_argument(
        "--expiry-type",
        required=True,
        choices=list(CONFIGS_V2.keys()),
        help="Which V2 expiry bucket to trade (currently: monthly only).",
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


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------


async def run() -> None:
    """Run the IronCondorV2 entry workflow."""
    setup_logging()
    args = parse_args()
    config = CONFIGS_V2[args.expiry_type]
    strategy_name = f"paper_ic_nifty_v2_{config.expiry_type}"

    # Build a Telegram notifier for gate-failure alerts (non-fatal).
    _tg = build_notifier()

    def _gate_alert(msg: str) -> None:
        """Fire a Telegram gate-failure alert (sync wrapper, non-fatal).

        Schedules ``_tg.send`` as an asyncio task.  Any exception — including
        network failures — is swallowed so that telegram never blocks a gate exit.
        """
        if _tg is None:
            return
        try:
            asyncio.get_running_loop().create_task(_tg.send(msg))
        except Exception:  # noqa: BLE001
            pass

    # Step 2: Duplicate guard (shared gate, STRUCTURAL — never bypassed)
    store = PaperStore(args.db_path)
    check_duplicate(store, strategy_name, notifier=_gate_alert)
    gate_violations = []

    # Step 2b: Post-expiry gate — calendar-based (last Tuesday of current month)
    try:
        _post_expiry_gate()
    except SystemExit:
        _gate_alert(
            f"⚠️ IC V2 Entry BLOCKED — {strategy_name}\n"
            f"Gate: post_expiry_gate\n"
            f"Reason: Current month expiry not yet passed"
        )
        sys.exit(1)

    # Step 2c: Expiry resolution + DTE window check (shared gate, THRESHOLD)
    _, expiry_str, dte, dte_violation = resolve_expiry(
        args.bod_path,
        expiry_bucket=config.expiry_type,
        dte_warn_lo=_V2_MONTHLY_DTE_WARN_LO,
        dte_warn_hi=_V2_MONTHLY_DTE_WARN_HI,
        strategy_name=strategy_name,
        notifier=_gate_alert,
    )
    if dte_violation is not None and args.log_only_gates:
        gate_violations.append(dte_violation)

    # Step 3: IVR gate (shared gate, THRESHOLD)
    ivr, ivr_violation = resolve_ivr(
        args.db_path,
        _V2_MONTHLY_IVR_GATE,
        args.force_entry,
        notifier=_gate_alert,
        log_only_gates=args.log_only_gates,
        strategy_name=strategy_name,
    )
    if ivr_violation is not None:
        gate_violations.append(ivr_violation)
    # resolve_ivr() only returns a GateViolation on the log-only-gates path —
    # under --force-entry it bypasses silently with ivr_violation=None. Track
    # the raw below-gate condition too, since record_paper_trade.py's own
    # independent R3 gate needs --force-entry on SELL legs whenever ivr was
    # below gate here, regardless of which bypass path was taken.
    ivr_below_gate = ivr is not None and ivr < float(_V2_MONTHLY_IVR_GATE)

    # Step 5: Live chain fetch
    try:
        client = UpstoxMarketClient(settings.upstox_analytics_token)
        raw_chain = client.get_option_chain_sync("NSE_INDEX|Nifty 50", expiry_str)
    except Exception as exc:  # noqa: BLE001
        logger.error("ic_entry.chain_fetch_failed", expiry=expiry_str, error=str(exc))
        _gate_alert(
            f"⚠️ IC V2 Entry BLOCKED — {strategy_name}\n"
            f"Gate: chain_fetch\n"
            f"Reason: Live option chain fetch failed: {exc}"
        )
        sys.exit(1)

    if not raw_chain:
        logger.error("ic_entry.chain_empty", expiry=expiry_str)
        _gate_alert(
            f"⚠️ IC V2 Entry BLOCKED — {strategy_name}\n"
            f"Gate: chain_fetch\n"
            f"Reason: Live option chain empty for expiry {expiry_str}"
        )
        sys.exit(1)

    # Step 6: Short leg selection (25Δ put / 22Δ call, D1 ruling)
    put_lo = float(config.short_put_delta_target - config.delta_range)
    put_hi = float(config.short_put_delta_target + config.delta_range)
    call_lo = float(config.short_call_delta_target - config.delta_range)
    call_hi = float(config.short_call_delta_target + config.delta_range)

    short_put_candidates = filter_strikes_by_delta(raw_chain, "PE", put_lo, put_hi)
    ranked_put = rank_strikes(short_put_candidates)
    if not ranked_put:
        logger.error("ic_entry.leg_resolution_failed", leg="short_put")
        _gate_alert(
            f"⚠️ IC V2 Entry BLOCKED — {strategy_name}\n"
            f"Gate: leg_resolution\n"
            f"Reason: No short_put candidate in delta range [{put_lo:.2f}, {put_hi:.2f}]"
        )
        sys.exit(1)
    short_put = ranked_put[0]

    short_call_candidates = filter_strikes_by_delta(raw_chain, "CE", call_lo, call_hi)
    ranked_call = rank_strikes(short_call_candidates)
    if not ranked_call:
        logger.error("ic_entry.leg_resolution_failed", leg="short_call")
        _gate_alert(
            f"⚠️ IC V2 Entry BLOCKED — {strategy_name}\n"
            f"Gate: leg_resolution\n"
            f"Reason: No short_call candidate in delta range [{call_lo:.2f}, {call_hi:.2f}]"
        )
        sys.exit(1)
    short_call = ranked_call[0]

    # Step 7: Long wing selection (10Δ delta-based, D2 ruling)
    long_put = _find_long_wing(raw_chain, "PE", config)
    if long_put is None:
        _gate_alert(
            f"⚠️ IC V2 Entry BLOCKED — {strategy_name}\n"
            f"Gate: long_wing_floor\n"
            f"Reason: No put wing passes delta + premium floors "
            f"(floor=₹{config.long_wing_min_premium}, delta_floor={config.long_wing_delta_floor})"
        )
        logger.error(
            "ic_entry.long_wing_floor_blocked",
            leg="short_put",
            min_premium=float(config.long_wing_min_premium),
            delta_floor=float(config.long_wing_delta_floor),
        )
        sys.exit(1)

    long_call = _find_long_wing(raw_chain, "CE", config)
    if long_call is None:
        _gate_alert(
            f"⚠️ IC V2 Entry BLOCKED — {strategy_name}\n"
            f"Gate: long_wing_floor\n"
            f"Reason: No call wing passes delta + premium floors "
            f"(floor=₹{config.long_wing_min_premium}, delta_floor={config.long_wing_delta_floor})"
        )
        logger.error(
            "ic_entry.long_wing_floor_blocked",
            leg="short_call",
            min_premium=float(config.long_wing_min_premium),
            delta_floor=float(config.long_wing_delta_floor),
        )
        sys.exit(1)

    # Step 8: Liquidity gate on short legs (THRESHOLD)
    if not _apply_liquidity_gate([short_put]):
        if args.log_only_gates:
            logger.warning("gate.liquidity_violation_logged", leg="short_put")
            gate_violations.append(
                make_gate_violation(
                    gate_name="liquidity_short_put",
                    threshold="liquidity_gate_pass",
                    actual="failed",
                    strategy_name=strategy_name,
                )
            )
        else:
            logger.error("ic_entry.liquidity_gate_blocked", leg="short_put")
            _gate_alert(
                f"⚠️ IC V2 Entry BLOCKED — {strategy_name}\n"
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
                    strategy_name=strategy_name,
                )
            )
        else:
            logger.error("ic_entry.liquidity_gate_blocked", leg="short_call")
            _gate_alert(
                f"⚠️ IC V2 Entry BLOCKED — {strategy_name}\n"
                f"Gate: liquidity\n"
                f"Reason: short_call failed the liquidity gate"
            )
            sys.exit(1)

    # Step 9: Fetch spot (used only for the Telegram notification below).
    # Portfolio-level delta gating/self-adjustment removed 2026-07-03 per
    # explicit product decision: IC entries are judged on their own two short
    # legs only, never against other strategies' or other IC variants'
    # positions. See DECISIONS.md 2026-07-03 "IC entries judged in isolation."
    ltp_map = client.get_ltp_sync(["NSE_INDEX|Nifty 50"])
    nifty_spot = ltp_map.get("NSE_INDEX|Nifty 50")
    if nifty_spot is None:
        logger.error("ic_entry.spot_fetch_failed")
        _gate_alert(
            f"⚠️ IC V2 Entry BLOCKED — {strategy_name}\n"
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

    # Step 10: Build and print/execute record_paper_trade commands
    legs = [
        ("short_put",       "SELL", short_put["instrument_key"],  short_put["mid"]),
        ("long_put_hedge",  "BUY",  long_put["instrument_key"],   long_put["mid"]),
        ("short_call",      "SELL", short_call["instrument_key"], short_call["mid"]),
        ("long_call_hedge", "BUY",  long_call["instrument_key"],  long_call["mid"]),
    ]

    cmds = []
    for role, action, key, price in legs:
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
            action,
            "--qty",
            str(LOT_SIZE),
            "--price",
            str(price),
        ]
        # record_paper_trade.py computes ivr_at_entry itself and enforces its
        # own independent R3 gate (hard-blocks SELL at ivr < --ivr-gate unless
        # --force-entry). Always pass _V2_MONTHLY_IVR_GATE through so the
        # downstream gate stays pinned to this script's actual threshold
        # rather than record_paper_trade.py's own default — defense-in-depth
        # against the V1 weekly/monthly gate-mismatch bug (fixed 2026-07-08,
        # see paper_ic_entry.py), even though V2 is monthly-only today and the
        # two values currently happen to match (both 0.25).
        cmd.extend(["--ivr-gate", str(_V2_MONTHLY_IVR_GATE)])
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
            strategy=strategy_name,
            leg_count=len(cmds),
        )
        print("\n[DRY-RUN] Commands to execute:")
        for cmd in cmds:
            print(" ".join(cmd))
    else:
        logger.info(
            "ic_entry.executing_legs",
            strategy=strategy_name,
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

        # Step 11: Verify legs actually landed in the DB before reporting success.
        # subprocess exit code 0 is necessary but not sufficient — record_paper_trade.py
        # exits 0 on its own dry-run no-op path too, so a clean subprocess run alone
        # cannot distinguish "recorded" from "previewed and discarded." Re-query each
        # leg's position from the DB directly. Relies on the duplicate-entry guard
        # earlier in run() — these are fresh legs with no prior fills, so net_qty==0
        # unambiguously means "not persisted" here.
        missing_legs: list[str] = []
        verification_error: str | None = None
        try:
            for role, _action, _key, _price in legs:
                pos = store.get_position(strategy_name, role)
                if pos.net_qty == 0:
                    missing_legs.append(role)
        except Exception as exc:  # noqa: BLE001 — a DB read failure here must not be
            # silently swallowed: without this catch, an exception raised after the 4
            # subprocess calls already ran would crash the script with no Telegram
            # notification at all (neither ✅ nor ⚠️), leaving the operator blind to
            # whether legs were actually persisted.
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
                compensated, compensation_failed = _compensate_legs(persisted_legs, strategy_name)
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
                strategy_name=strategy_name,
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
                    escape_markdown(f"⚠️ IC V2 Entry — {args.expiry_type} (")
                    + mdcode(strategy_name)
                    + escape_markdown(
                        f")\n"
                        f"{detail}\n"
                        f"Check logs immediately."
                    )
                )
            except Exception as exc:  # noqa: BLE001 — telegram is non-fatal
                logger.warning("telegram.send_failed", error=str(exc))
            sys.exit(1)

        # Step 11b: Capture entry-cycle margin (non-fatal). Legs are confirmed
        # persisted above. Client construction is wrapped here too, not just the
        # broker call inside capture_entry_margin — UpstoxLiveClient() itself can
        # raise (missing UPSTOX_ANALYTICS_TOKEN) and legs are already persisted
        # at this point, so that must never crash the script before the success
        # notification.
        try:
            margin_legs = [(key, action, LOT_SIZE) for _role, action, key, _price in legs]
            await capture_entry_margin(
                broker=UpstoxLiveClient(),
                store=store,
                strategy_name=strategy_name,
                entry_date=date.today(),
                legs=margin_legs,
            )
        except Exception as exc:  # noqa: BLE001 — margin capture must never block a successful entry
            logger.warning("ic_entry.margin_capture_failed", error=str(exc))

        # Step 11c: Persist the original 4-leg entry credit (BUG-020 Phase 2).
        # Legs are confirmed persisted above. Non-fatal — a persistence failure
        # here must not block a successful entry; the profit-target branch
        # (BUG-020 Phase 3) falls back to its existing recompute behavior when
        # this value is absent.
        net_credit = (short_put["mid"] + short_call["mid"]) - (long_put["mid"] + long_call["mid"])
        try:
            store.set_original_entry_credit(strategy_name, net_credit)
        except Exception as exc:  # noqa: BLE001 — persistence failure must never block entry
            logger.warning("ic_entry.original_credit_persist_failed", error=str(exc))

        # Step 12: Telegram notification — only reached once all 4 legs are
        # confirmed present in the DB.
        wing_width_put = abs(short_put["strike"] - long_put["strike"])
        wing_width_call = abs(long_call["strike"] - short_call["strike"])
        msg = (
            escape_markdown(f"✅ IC V2 Entry — {args.expiry_type} (")
            + mdcode(strategy_name)
            + escape_markdown(
                f")\n"
                f"IVR: {ivr:.2f}  DTE: {dte}  Nifty: {nifty_spot:,.0f}\n\n"
                f"Short Put  {int(short_put['strike'])}PE  "
                f"δ={abs(short_put['delta']):.3f}  mid=₹{short_put['mid']:.2f}\n"
                f"Long Put   {int(long_put['strike'])}PE   "
                f"δ={abs(long_put['delta']):.3f}  width={wing_width_put:.0f}pts\n"
                f"Short Call {int(short_call['strike'])}CE "
                f"δ={abs(short_call['delta']):.3f}  mid=₹{short_call['mid']:.2f}\n"
                f"Long Call  {int(long_call['strike'])}CE  "
                f"δ={abs(long_call['delta']):.3f}  width={wing_width_call:.0f}pts\n\n"
                f"Net credit: ₹{net_credit:.2f}/lot  "
                f"(₹{net_credit * LOT_SIZE:,.0f} for {LOT_SIZE} units)"
            )
        )
        try:
            tg = TelegramGateway(
                bot_token=settings.telegram_bot_token,
                chat_id=settings.telegram_chat_id,
                db_path=str(args.db_path),
            )
            await tg.send_notification(msg)
        except Exception as exc:  # noqa: BLE001 — telegram is non-fatal
            logger.warning("telegram.send_failed", error=str(exc))


def main() -> None:
    """CLI entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
