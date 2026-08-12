#!/usr/bin/env python3
"""Record overlay legs into the shared, track-independent overlay namespace.

Reads the YAML written by scripts/lookup/find_overlay_strikes.py, validates it, and records
the appropriate leg(s) under STRATEGY_OVERLAY ("paper_nifty_overlay"). Overlay is
track-independent (S1r/S2r, 2026-07-29, DECISIONS.md round 5) — there is exactly one physical
overlay position per leg role, never one per 3-track base (Spot/Futures/Proxy). Comparison
against a given track's coverage/P&L is computed at query time only
(src/portfolio/overlay_coverage.py), never by writing duplicate per-track trade rows.

Leg role naming (per strategy spec):
    overlay_pp              — Protective Put (BUY PE)
    overlay_cc              — Covered Call   (SELL CE)
    overlay_collar_put      — Collar put leg (BUY PE)
    overlay_collar_call     — Collar call leg (SELL CE)

Usage:
    python scripts/paper_3track_overlay_entry.py --dry-run
    python scripts/paper_3track_overlay_entry.py
    python scripts/paper_3track_overlay_entry.py --config data/paper/cycle2_overlay.yaml
    python scripts/paper_3track_overlay_entry.py --auto-cc --dry-run
    python scripts/paper_3track_overlay_entry.py --auto-cc
    python scripts/paper_3track_overlay_entry.py --auto-pp --dry-run
    python scripts/paper_3track_overlay_entry.py --auto-pp
    python scripts/paper_3track_overlay_entry.py --auto-collar --dry-run
    python scripts/paper_3track_overlay_entry.py --auto-collar

NOTE: unlike paper_ic_entry.py, --dry-run here is a plain store_true flag (no
--no-dry-run counterpart) — omitting the flag entirely means live (writes to DB).
This is pre-existing behavior for the manual/YAML entry path too, not something
this change introduced; flagged separately as worth a follow-up decision.

Cron example (--auto-cc live path unblocked 2026-08-02 — CC1/CC2/EC-5 all landed,
EC-5's tests confirmed green on live host same day, see DECISIONS.md):
    30 10 * * 3  cd /path/to/NiftyShield && python scripts/strategies/three_track/paper_3track_overlay_entry.py --auto-cc

Cron example (--auto-pp live path unblocked 2026-08-03 — PP1/PP2 both landed,
see docs/plan/3track-consolidation/tasks.md PP2/PP3). Daily cadence (not CC's
weekly Wednesday), off the existing snapshot cron, since --auto-pp itself
short-circuits to a no-op (exit 0) whenever a fresh (DTE > 5) put is already
open — a daily invocation is idempotent by construction, same reasoning as S6's
bootstrap entry scripts:
    35 15 * * 1-5  cd /path/to/NiftyShield && python scripts/strategies/three_track/paper_3track_overlay_entry.py --auto-pp

Cron example (--auto-collar live path unblocked 2026-08-04 — Collar1/Collar2/Collar3a all
landed, no decision gate remains open; paper trading, operator explicitly accepted the risk
of unexercised-live code over a dry-run-only default, see DECISIONS.md). Bootstrap only —
one-time-per-position via the existing generic _has_open_overlay_leg gate (S6), so any cadence
is idempotent by construction; mirrors CC's weekly Wednesday slot since collar's call leg reuses
CC's band:
    30 10 * * 3  cd /path/to/NiftyShield && python scripts/strategies/three_track/paper_3track_overlay_entry.py --auto-collar
"""

import argparse

# ruff: noqa: E402
import asyncio
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import structlog
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from scripts.lookup.find_strike_by_delta import _select_delta_candidates, run_collar_mode
from scripts.strategies.ic.ic_entry_gates import make_gate_violation
from src.backtest.ivr import compute_ivr
from src.backtest.vix_ingest import load_vix_series
from src.client.upstox_market import UpstoxMarketClient
from src.config import settings
from src.instruments.lookup import InstrumentLookup, parse_expiry
from src.instruments.strike_selector import (
    _apply_liquidity_gate,
    filter_strikes_by_delta,
    rank_strikes,
)
from src.models.portfolio import TradeAction
from src.notifications.telegram import build_notifier
from src.paper.constants import (
    DEFAULT_BOD_PATH,
    DEFAULT_DB_PATH,
    NIFTY_UNDERLYING,
    NIFTYBEES_KEY,
    STRATEGY_CC_OVERLAY,
    STRATEGY_COLLAR_OVERLAY,
    STRATEGY_OVERLAY,
    STRATEGY_PP_OVERLAY,
    STRATEGY_SPOT,
)
from src.paper.models import GateViolation, PaperTrade
from src.paper.store import PaperStore
from src.risk.collateral_gate import check_collateral_capacity
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.strategies.three_track.paper_3track_overlay_entry"
logger = structlog.get_logger(_SCRIPT_NAME)

# One-time bootstrap marker leg per overlay type (S6) — its presence under
# STRATEGY_OVERLAY means this overlay was already entered and must not refire.
_PRIMARY_LEG_ROLE = {
    "pp": "overlay_pp",
    "cc": "overlay_cc",
    "collar": "overlay_collar_put",
}

DEFAULT_CONFIG = Path("data/paper/overlay_entry.yaml")

# Matches keys like "NSE_FO|NIFTY29MAY2026PE" -> group 1 = "29MAY2026" — same
# pattern as PPOverlayV1._EXPIRY_RE (src/strategy/pp_overlay_v1.py), duplicated
# here rather than imported since this is a standalone script-side lookup
# against paper_trades rows, not a strategy-object method.
_PP_EXPIRY_RE = re.compile(r"NSE_FO\|NIFTY(\d{2}[A-Za-z]{3}\d{4})(PE|CE)", re.IGNORECASE)

# Matches PPOverlayV1.reentry_ivr_threshold — PP's re-entry IVR gate is
# inverted vs CSP/CC/collar: blocks when IVR is too HIGH (don't buy protection
# at peak post-crash vol), not too low.
_PP_REENTRY_IVR_THRESHOLD = 0.60

# ROLL_ELIGIBLE threshold in ExitSignalEngine.evaluate_pp — kept in lockstep
# per PP3's story requirement so the entry script's routine-roll trigger and
# the exit-signal engine's roll trigger never drift apart.
_PP_ROLL_DTE_THRESHOLD = 5

_COLLAR_PUT_ROLE = "overlay_collar_put"
_COLLAR_CALL_ROLE = "overlay_collar_call"
_COLLAR_ROLES = frozenset({_COLLAR_PUT_ROLE, _COLLAR_CALL_ROLE})


# Fallback only — used if a selected strike's instrument_key can't be
# resolved back against the BOD file (should not happen in practice, since
# the strike was itself selected from a BOD-backed chain). Nifty's current
# lot size is 65 (was 75 before a lot-size revision — that staleness is
# exactly the bug this fallback exists to not repeat). Kept in sync with
# _NIFTY_LOT_SIZE_FALLBACK in src/strategy/nifty_track_comparison_v1.py;
# both should be replaced by a single shared constant if Nifty's lot size
# changes again.
_NIFTY_LOT_SIZE_FALLBACK = 65


def _resolve_lot_size(lookup: InstrumentLookup, instrument_key: str) -> int:
    """Resolve the live lot size for *instrument_key* from the BOD file.

    Hardcoding lot_size at strike-selection time silently drifted stale
    after a Nifty lot-size revision (auto CC/Collar/PP builders all shipped
    with lot_size=75 baked in — see DECISIONS.md 2026-08-10). Reading it
    from the same BOD record the strike was selected from keeps entries in
    lockstep with whatever lot size is currently live.

    Args:
        lookup: BOD-backed instrument lookup, already loaded for this run.
        instrument_key: The selected strike's instrument_key.

    Returns:
        The instrument's lot_size, or ``_NIFTY_LOT_SIZE_FALLBACK`` if the
        BOD record is missing or has no lot_size field.
    """
    inst = lookup.get_by_key(instrument_key)
    lot_size = inst.get("lot_size") if inst is not None else None
    if lot_size is None or int(lot_size) <= 0:
        logger.warning(
            "lot_size.bod_lookup_failed_using_fallback",
            instrument_key=instrument_key,
            bod_lot_size=lot_size,
            fallback=_NIFTY_LOT_SIZE_FALLBACK,
        )
        return _NIFTY_LOT_SIZE_FALLBACK
    return int(lot_size)


def _validate_collar_pairs(
    overlay_trades: list["OverlayTrade"],
    existing_call_role: str | None = None,
) -> None:
    """Ensure a collar entry has both put and call present.

    A partial collar (put without call or call without put) is never permitted
    at the entry/close layer.  Exception: if the call leg was intentionally
    omitted because an open overlay_cc already exists on the same key (dedup
    guard), the put-only entry is valid — the existing CC serves as the collar
    call.

    Args:
        overlay_trades: Trades about to be submitted.
        existing_call_role: leg_role of an already-open short call on the same
            call_instrument_key under STRATEGY_OVERLAY, if any (from
            ``_query_open_call_role``).  Used to exempt a put-only submission
            where the call was skipped due to dedup.

    Raises:
        SystemExit: If the collar leg set is incomplete with no dedup exemption.
    """
    roles = {ot.trade.leg_role for ot in overlay_trades if ot.trade.leg_role in _COLLAR_ROLES}
    if not roles or roles == _COLLAR_ROLES:
        return

    missing = _COLLAR_ROLES - roles
    # Exempt: put-only because call was skipped (existing overlay_cc covers it)
    if missing == {_COLLAR_CALL_ROLE} and existing_call_role == "overlay_cc":
        return

    print(
        f"ERROR: partial collar — missing {missing}. "
        "Both overlay_collar_put and overlay_collar_call must be submitted together.",
        file=sys.stderr,
    )
    sys.exit(1)


@dataclass
class OverlayConfig:
    """Validated overlay entry config."""

    overlay_type: str  # 'pp', 'cc', 'collar'
    entry_date: date
    cycle: int
    lot_size: int
    expiry: str
    expiry_type: str
    dte_at_entry: int
    # PP leg
    put_strike: float
    put_instrument_key: str
    put_price: Decimal
    put_spread_pct: float | None
    put_oi: int
    # CC leg
    call_strike: float
    call_instrument_key: str
    call_price: Decimal
    call_spread_pct: float | None
    call_oi: int


def auto_cc_bootstrap(
    bod_path: Path,
    *,
    log_only_gates: bool = True,
) -> tuple[OverlayConfig | None, GateViolation | None]:
    """Automate CC entry (fetch chain, apply gates, select strike).

    Args:
        bod_path: Path to the BOD instrument JSON file.
        log_only_gates: When True (default), a below-threshold IVR is
            recorded as a GateViolation instead of hard-blocking entry —
            same contract as ``auto_pp_bootstrap``'s param of the same name
            (paper-trading phase, no real capital at risk; see DECISIONS.md
            2026-08-07). When False, restores the original hard-block.

    Returns:
        Tuple of (OverlayConfig or None, GateViolation or None). cfg is None
        on any structural failure (BOD load, no monthly expiry, DTE < 14,
        history-unavailable, chain fetch, no eligible strike) — these are
        never gated by log_only_gates, they always abort. The GateViolation
        is populated only when the IVR gate would have blocked under strict
        mode.
    """
    today = date.today()
    try:
        lookup = InstrumentLookup.from_file(bod_path)
        expiries = lookup.get_expiry_candidates(
            underlying="NIFTY",
            today=today,
            preference=["monthly"],
        )
    except Exception as exc:
        logger.error("auto_cc.bod_load_failed", error=str(exc))
        return None, None

    expiry_str = None
    for label, exp_str in expiries:
        if label == "monthly":
            expiry_str = exp_str
            break

    if not expiry_str:
        logger.error("auto_cc.no_monthly_expiry_found")
        return None, None

    # Gate 1: DTE >= 14 (structural — never bypassed by log_only_gates).
    expiry_date = date.fromisoformat(expiry_str)
    dte = (expiry_date - today).days
    if dte < 14:
        logger.error("auto_cc.dte_gate_failed", dte=dte)
        return None, None

    # Gate 2: IVR >= 0.25. THRESHOLD gate: log-only under --log-only-gates
    # (default on), matching auto_pp_bootstrap/ic_entry_gates.resolve_ivr's
    # pattern. Data unavailability (empty/short history) stays a STRUCTURAL
    # abort — never bypassed by log_only_gates.
    violation: GateViolation | None = None
    try:
        vix_series = load_vix_series(settings.vix_data_dir)
        if vix_series.empty or len(vix_series) < 252:
            logger.error("auto_cc.ivr_history_insufficient")
            return None, None

        vix_today = float(vix_series.iloc[-1])
        ivr = compute_ivr(vix_today, vix_series)

        if ivr is None:
            logger.error("auto_cc.ivr_history_insufficient")
            return None, None

        if ivr < 0.25:
            if log_only_gates:
                logger.warning("gate.ivr_cc_reentry_violation_logged", ivr=ivr, gate=0.25)
                violation = make_gate_violation(
                    gate_name="ivr_cc_reentry",
                    threshold="0.25",
                    actual=f"{ivr:.4f}",
                    strategy_name=STRATEGY_CC_OVERLAY,
                )
            else:
                logger.error("auto_cc.ivr_gate_failed", ivr=ivr)
                return None, None
    except Exception as exc:
        logger.error("auto_cc.ivr_check_failed", error=str(exc))
        return None, None

    # Fetch live chain
    try:
        client = UpstoxMarketClient(settings.upstox_analytics_token)
        raw_chain = client.get_option_chain_sync("NSE_INDEX|Nifty 50", expiry_str)
    except Exception as exc:
        logger.error("auto_cc.chain_fetch_failed", error=str(exc))
        return None, None

    if not raw_chain:
        logger.error("auto_cc.chain_empty")
        return None, None

    # Strike selection
    delta_candidates = _select_delta_candidates(option_type="CE")
    selected_row = None

    for candidate in delta_candidates:
        delta_min = max(0.0, candidate - 0.02)
        delta_max = candidate + 0.02
        rows = filter_strikes_by_delta(
            raw_chain,
            option_type="CE",
            delta_min=delta_min,
            delta_max=delta_max,
        )
        if not rows:
            continue

        ranked = rank_strikes(rows)
        filtered = _apply_liquidity_gate(ranked)
        if filtered:
            selected_row = filtered[0]
            break

    if not selected_row:
        logger.error("auto_cc.no_eligible_strike_found")
        return None, None

    call_price = Decimal(
        str(selected_row["mid"] if selected_row["mid"] > 0 else selected_row["ltp"])
    )

    cfg = OverlayConfig(
        overlay_type="cc",
        entry_date=today,
        cycle=1,  # Cycle doesn't matter for auto CC
        lot_size=_resolve_lot_size(lookup, selected_row["instrument_key"]),
        expiry=expiry_str,
        expiry_type="monthly",
        dte_at_entry=dte,
        put_strike=0.0,
        put_instrument_key="",
        put_price=Decimal("0"),
        put_spread_pct=None,
        put_oi=0,
        call_strike=float(selected_row["strike"]),
        call_instrument_key=selected_row["instrument_key"],
        call_price=call_price,
        call_spread_pct=float(selected_row["gate_spread"])
        if selected_row.get("gate_spread") is not None
        else None,
        call_oi=int(selected_row["oi"]),
    )
    return cfg, violation


def auto_collar_bootstrap(
    bod_path: Path,
    *,
    log_only_gates: bool = True,
) -> tuple[OverlayConfig | None, GateViolation | None]:
    """Automate first-ever Collar entry (fetch chain, apply gates, select both legs).

    Bootstrap only (Collar3b) — mirrors ``auto_cc_bootstrap``/``auto_pp_bootstrap``'s
    shape and gates (DTE >= 14, IVR >= 0.25), but selects *both* legs in one pass by
    reusing Collar1's ``run_collar_mode`` (coordinates CC1's call ladder and PP1's put
    ladder into the candidate cross-product) and applying Collar2's confirmed
    tiebreak: minimum ``|net_premium|`` among survivors of both bands. Routine
    reentry after a close is handled separately and automatically by
    ``CollarOverlayV1.apply_action``'s combined close+reenter action
    (``src/strategy/collar_entry.py``) — this function only covers the one case that
    isn't event-triggered: no Collar position exists yet at all.

    Args:
        bod_path: Path to the BOD instrument JSON file.
        log_only_gates: When True (default), a below-threshold IVR is
            recorded as a GateViolation instead of hard-blocking entry —
            same contract as ``auto_pp_bootstrap``/``auto_cc_bootstrap``'s
            param of the same name (paper-trading phase, no real capital at
            risk; see DECISIONS.md 2026-08-07). When False, restores the
            original hard-block.

    Returns:
        Tuple of (OverlayConfig or None, GateViolation or None). cfg has both
        put_* and call_* fields populated on success, or is None on any
        structural failure (BOD load, no monthly expiry, DTE < 14,
        history-unavailable, chain fetch, or no viable combo) — these are
        never gated by log_only_gates, they always abort. The GateViolation
        is populated only when the IVR gate would have blocked under strict
        mode.
    """
    today = date.today()
    try:
        lookup = InstrumentLookup.from_file(bod_path)
        expiries = lookup.get_expiry_candidates(
            underlying="NIFTY",
            today=today,
            preference=["monthly"],
        )
    except Exception as exc:
        logger.error("auto_collar.bod_load_failed", error=str(exc))
        return None, None

    expiry_str = None
    for label, exp_str in expiries:
        if label == "monthly":
            expiry_str = exp_str
            break

    if not expiry_str:
        logger.error("auto_collar.no_monthly_expiry_found")
        return None, None

    # Gate 1: DTE >= 14 (structural — never bypassed by log_only_gates).
    expiry_date = date.fromisoformat(expiry_str)
    dte = (expiry_date - today).days
    if dte < 14:
        logger.error("auto_collar.dte_gate_failed", dte=dte)
        return None, None

    # Gate 2: IVR >= 0.25 (same threshold as auto_cc_bootstrap/ReEntryMixin).
    # THRESHOLD gate: log-only under --log-only-gates (default on). Data
    # unavailability (empty/short history) stays a STRUCTURAL abort — never
    # bypassed by log_only_gates.
    violation: GateViolation | None = None
    try:
        vix_series = load_vix_series(settings.vix_data_dir)
        if vix_series.empty or len(vix_series) < 252:
            logger.error("auto_collar.ivr_history_insufficient")
            return None, None

        vix_today = float(vix_series.iloc[-1])
        ivr = compute_ivr(vix_today, vix_series)

        if ivr is None:
            logger.error("auto_collar.ivr_history_insufficient")
            return None, None

        if ivr < 0.25:
            if log_only_gates:
                logger.warning("gate.ivr_collar_reentry_violation_logged", ivr=ivr, gate=0.25)
                violation = make_gate_violation(
                    gate_name="ivr_collar_reentry",
                    threshold="0.25",
                    actual=f"{ivr:.4f}",
                    strategy_name=STRATEGY_COLLAR_OVERLAY,
                )
            else:
                logger.error("auto_collar.ivr_gate_failed", ivr=ivr)
                return None, None
    except Exception as exc:
        logger.error("auto_collar.ivr_check_failed", error=str(exc))
        return None, None

    # Fetch live chain
    try:
        client = UpstoxMarketClient(settings.upstox_analytics_token)
        raw_chain = client.get_option_chain_sync("NSE_INDEX|Nifty 50", expiry_str)
    except Exception as exc:
        logger.error("auto_collar.chain_fetch_failed", error=str(exc))
        return None, None

    if not raw_chain:
        logger.error("auto_collar.chain_empty")
        return None, None

    # Two-leg search: Collar1's run_collar_mode coordinates CC1's call ladder +
    # PP1's put ladder into the full candidate cross-product (never auto-selects).
    try:
        combos = run_collar_mode(
            raw_data_by_expiry={expiry_str: raw_chain},
            expiries=[("monthly", expiry_str)],
        )
    except RuntimeError as exc:
        logger.error("auto_collar.ladder_missing", error=str(exc))
        return None, None

    if not combos:
        logger.error("auto_collar.no_viable_combo_found")
        return None, None

    # Collar2 tiebreak: minimum |net_premium| among survivors of both bands.
    best = min(combos, key=lambda c: abs(c["net_premium"]))
    call_row, put_row = best["call"], best["put"]

    call_price = Decimal(str(call_row["mid"] if call_row.get("mid", 0) > 0 else call_row["ltp"]))
    put_price = Decimal(str(put_row["mid"] if put_row.get("mid", 0) > 0 else put_row["ltp"]))

    cfg = OverlayConfig(
        overlay_type="collar",
        entry_date=today,
        cycle=1,  # Cycle doesn't matter for auto collar
        lot_size=_resolve_lot_size(lookup, call_row["instrument_key"]),
        expiry=expiry_str,
        expiry_type="monthly",
        dte_at_entry=dte,
        put_strike=float(put_row["strike"]),
        put_instrument_key=put_row["instrument_key"],
        put_price=put_price,
        put_spread_pct=float(put_row["gate_spread"])
        if put_row.get("gate_spread") is not None
        else None,
        put_oi=int(put_row["oi"]),
        call_strike=float(call_row["strike"]),
        call_instrument_key=call_row["instrument_key"],
        call_price=call_price,
        call_spread_pct=float(call_row["gate_spread"])
        if call_row.get("gate_spread") is not None
        else None,
        call_oi=int(call_row["oi"]),
    )
    return cfg, violation


def _open_pp_dte(db_path: Path, bod_path: Path) -> int | None:
    """Return the DTE of the currently open overlay_pp position, or None if flat.

    Distinguishes PP3's two entry triggers:
      - None (no open overlay_pp row at all) -> bootstrap/gap-fill.
      - DTE <= _PP_ROLL_DTE_THRESHOLD -> routine roll; the fresh put must be
        bought the same day (no-gap requirement — operator: "i do not want
        unprotected day"), which means the outgoing (this row) and the
        incoming put are briefly both open under the same leg_role.
      - DTE > _PP_ROLL_DTE_THRESHOLD -> a fresh put already covers; nothing
        to do this run.

    Mirrors ``_query_open_call_role``'s standalone sqlite-net-qty pattern
    rather than going through ``PaperStore.get_positions`` (which is also
    filtered to ``net_qty != 0`` and would work, but this keeps the
    entry-script gate self-contained and consistent with the existing CC/
    collar dedup check in this file).

    Args:
        db_path: Path to the SQLite portfolio DB.
        bod_path: Path to the BOD instrument JSON file, used as the
            expiry-resolution fallback for numeric-only instrument keys
            (see BUG, 2026-08-13, below).

    Returns:
        Minimum DTE (calendar days) across any open ``overlay_pp`` rows, or
        None if no such row is open. Un-parseable instrument keys are
        skipped with a WARNING (never raise — a gate helper must not crash
        the entry run over one bad row).
    """
    import sqlite3

    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute(
            """
            SELECT instrument_key,
                   SUM(CASE WHEN action='SELL' THEN -quantity ELSE quantity END) AS net_qty
            FROM paper_trades
            WHERE strategy_name = ?
              AND leg_role = 'overlay_pp'
            GROUP BY instrument_key
            HAVING net_qty > 0
            """,
            (STRATEGY_OVERLAY,),
        )
        rows = cur.fetchall()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("open_pp_dte.query_failed", error=str(exc))
        return None

    if not rows:
        return None

    today = date.today()

    # Expiry resolution: regex-first (human-readable trading-symbol form),
    # BOD-lookup fallback for numeric-only keys. BUG (2026-08-13, found by
    # Animesh): _PP_EXPIRY_RE never matches real Upstox instrument keys
    # (NSE_FO|<numeric id>, e.g. NSE_FO|61604) -- only the synthetic
    # NIFTY<DDMonYYYY>PE/CE symbol form. Every open overlay_pp row is a real
    # numeric key, so this function always fell through to "unparseable",
    # always returned None, and main()'s "already have a fresh open
    # position, nothing to do" short-circuit never fired -- auto_pp_bootstrap
    # re-entered a brand new put on top of the still-open one every single
    # cron run since PP auto-entry shipped (confirmed live: two open
    # overlay_pp rows, 2026-08-11 and 2026-08-12, neither closed by the
    # other). Identical root cause/fix pattern to BUG-018/BUG-012
    # (src/strategy/ic_nifty_v2.py::_parse_expiry/_find_leg) -- this
    # function was never swept into that fix. See DECISIONS.md 2026-08-13.
    lookup: InstrumentLookup | None = None
    dtes: list[int] = []
    for instrument_key, _net_qty in rows:
        m = _PP_EXPIRY_RE.search(instrument_key)
        if m:
            try:
                expiry = datetime.strptime(m.group(1).upper(), "%d%b%Y").date()
            except ValueError:
                logger.warning("open_pp_dte.expiry_unparseable", instrument_key=instrument_key)
                continue
            dtes.append((expiry - today).days)
            continue

        if lookup is None:
            try:
                lookup = InstrumentLookup.from_file(bod_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "open_pp_dte.bod_load_failed", instrument_key=instrument_key, error=str(exc)
                )
                continue

        inst = lookup.get_by_key(instrument_key)
        expiry_str = parse_expiry(inst.get("expiry")) if inst else None
        if expiry_str is None:
            logger.warning(
                "open_pp_dte.expiry_unparseable",
                instrument_key=instrument_key,
                reason="not_found_in_bod" if inst is None else "no_expiry_field",
            )
            continue
        dtes.append((date.fromisoformat(expiry_str) - today).days)

    if not dtes:
        return None
    return min(dtes)


def auto_pp_bootstrap(
    bod_path: Path,
    *,
    log_only_gates: bool = True,
) -> tuple[OverlayConfig | None, GateViolation | None]:
    """Automate PP entry — bootstrap (no open put) or routine roll gap-fill.

    Caller (``main()``) must already have checked ``_open_pp_dte`` and
    short-circuited on a fresh (DTE > ``_PP_ROLL_DTE_THRESHOLD``) open
    position before calling this — this function only resolves the expiry/
    IVR/strike-selection path, it does not re-check the open-position gate.

    Args:
        bod_path: Path to the BOD instrument JSON file.
        log_only_gates: When True (default), a below/above-threshold IVR is
            recorded as a GateViolation instead of hard-blocking entry — the
            routine roll always proceeds same-day regardless (no-gap
            requirement); when False, restores the original hard-block.

    Returns:
        Tuple of (OverlayConfig or None, GateViolation or None). cfg is None
        on any structural failure (BOD load, no monthly expiry, DTE < 14,
        chain fetch, no eligible strike) — these are never gated by
        log_only_gates, they always abort. The GateViolation is populated
        only when the IVR gate would have blocked under strict mode.
    """
    today = date.today()

    try:
        lookup = InstrumentLookup.from_file(bod_path)
        expiries = lookup.get_expiry_candidates(
            underlying="NIFTY",
            today=today,
            preference=["monthly"],
        )
    except Exception as exc:
        logger.error("auto_pp.bod_load_failed", error=str(exc))
        return None, None

    expiry_str = None
    for label, exp_str in expiries:
        if label == "monthly":
            expiry_str = exp_str
            break

    if not expiry_str:
        logger.error("auto_pp.no_monthly_expiry_found")
        return None, None

    # Gate 1: DTE >= 14 (structural — matches ReEntryMixin's own floor).
    expiry_date = date.fromisoformat(expiry_str)
    dte = (expiry_date - today).days
    if dte < 14:
        logger.error("auto_pp.dte_gate_failed", dte=dte)
        return None, None

    # Gate 2: IVR — inverted threshold gate for PP (blocks when IVR too HIGH).
    # THRESHOLD gate: log-only under --log-only-gates (default on), matching
    # scripts/strategies/ic/ic_entry_gates.py::resolve_ivr's pattern. Data
    # unavailability (empty/short history) remains a STRUCTURAL abort —
    # never bypassed by log_only_gates.
    violation: GateViolation | None = None
    try:
        vix_series = load_vix_series(settings.vix_data_dir)
        if vix_series.empty or len(vix_series) < 252:
            logger.error("auto_pp.ivr_history_insufficient")
            return None, None

        vix_today = float(vix_series.iloc[-1])
        ivr = compute_ivr(vix_today, vix_series)
        if ivr is None:
            logger.error("auto_pp.ivr_history_insufficient")
            return None, None

        if ivr > _PP_REENTRY_IVR_THRESHOLD:
            if log_only_gates:
                logger.warning(
                    "gate.ivr_pp_reentry_violation_logged",
                    ivr=ivr,
                    gate=_PP_REENTRY_IVR_THRESHOLD,
                )
                violation = make_gate_violation(
                    gate_name="ivr_pp_reentry",
                    threshold=str(_PP_REENTRY_IVR_THRESHOLD),
                    actual=f"{ivr:.4f}",
                    strategy_name=STRATEGY_PP_OVERLAY,
                )
            else:
                logger.error("auto_pp.ivr_gate_failed", ivr=ivr)
                return None, None
    except Exception as exc:
        logger.error("auto_pp.ivr_check_failed", error=str(exc))
        return None, None

    # Fetch live chain
    try:
        client = UpstoxMarketClient(settings.upstox_analytics_token)
        raw_chain = client.get_option_chain_sync("NSE_INDEX|Nifty 50", expiry_str)
    except Exception as exc:
        logger.error("auto_pp.chain_fetch_failed", error=str(exc))
        return None, violation

    if not raw_chain:
        logger.error("auto_pp.chain_empty")
        return None, violation

    # Strike selection — PE ladder scoped to PP via the explicit overlay_type
    # flag (PP1, 2026-08-03): bare option_type="PE" alone resolves to CSP's
    # DELTA_CANDIDATES, ambiguous between CSP short-put and PP long-put use.
    delta_candidates = _select_delta_candidates(option_type="PE", overlay_type="pp")
    selected_row = None

    for candidate in delta_candidates:
        delta_min = max(0.0, candidate - 0.02)
        delta_max = candidate + 0.02
        rows = filter_strikes_by_delta(
            raw_chain,
            option_type="PE",
            delta_min=delta_min,
            delta_max=delta_max,
        )
        if not rows:
            continue

        ranked = rank_strikes(rows)
        filtered = _apply_liquidity_gate(ranked)
        if filtered:
            selected_row = filtered[0]
            break

    if not selected_row:
        logger.error("auto_pp.no_eligible_strike_found")
        return None, violation

    put_price = Decimal(
        str(selected_row["mid"] if selected_row["mid"] > 0 else selected_row["ltp"])
    )

    return (
        OverlayConfig(
            overlay_type="pp",
            entry_date=today,
            cycle=1,  # Cycle doesn't matter for auto PP
            lot_size=_resolve_lot_size(lookup, selected_row["instrument_key"]),
            expiry=expiry_str,
            expiry_type="monthly",
            dte_at_entry=dte,
            put_strike=float(selected_row["strike"]),
            put_instrument_key=selected_row["instrument_key"],
            put_price=put_price,
            put_spread_pct=float(selected_row["gate_spread"])
            if selected_row.get("gate_spread") is not None
            else None,
            put_oi=int(selected_row["oi"]),
            call_strike=0.0,
            call_instrument_key="",
            call_price=Decimal("0"),
            call_spread_pct=None,
            call_oi=0,
        ),
        violation,
    )


def load_overlay_config(path: Path) -> OverlayConfig:
    """Load and validate the overlay YAML config.

    Args:
        path: Path to overlay_entry.yaml (written by scripts/lookup/find_overlay_strikes.py).

    Returns:
        Validated OverlayConfig.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If any required field is missing or invalid.
    """
    with open(path) as f:
        raw = yaml.safe_load(f)

    ov = raw.get("overlay", {})

    def _get(key: str):
        val = ov.get(key)
        if val is None:
            raise ValueError(f"Missing required field [overlay].{key} in {path}")
        return val

    overlay_type = str(_get("type")).lower()
    if overlay_type not in ("pp", "cc", "collar"):
        raise ValueError(f"[overlay].type must be 'pp', 'cc', or 'collar', got {overlay_type!r}")

    date_str = str(_get("date"))
    entry_date = date.fromisoformat(date_str)
    cycle = int(_get("cycle"))
    lot_size = int(_get("lot_size"))
    expiry = str(_get("expiry"))
    expiry_type = str(ov.get("expiry_type", "monthly"))
    dte_at_entry = int(ov.get("dte_at_entry", 0))

    # PP fields — required for pp and collar
    put_strike = float(ov.get("put_strike", 0))
    put_key = str(ov.get("put_instrument_key", "")).strip()
    put_price = Decimal(str(ov.get("put_price", 0)))
    put_spread_pct = ov.get("put_spread_pct")
    put_oi = int(ov.get("put_oi", 0))

    # CC fields — required for cc and collar
    call_strike = float(ov.get("call_strike", 0))
    call_key = str(ov.get("call_instrument_key", "")).strip()
    call_price = Decimal(str(ov.get("call_price", 0)))
    call_spread_pct = ov.get("call_spread_pct")
    call_oi = int(ov.get("call_oi", 0))

    # Validate required fields per overlay type
    if overlay_type in ("pp", "collar"):
        if put_strike <= 0:
            raise ValueError("[overlay].put_strike must be > 0 for pp/collar.")
        if not put_key or not put_key.startswith("NSE_FO|"):
            raise ValueError(
                f"[overlay].put_instrument_key must start with 'NSE_FO|', got {put_key!r}"
            )
        if put_price <= Decimal("0"):
            raise ValueError(f"[overlay].put_price must be > 0, got {put_price}")

    if overlay_type in ("cc", "collar"):
        if call_strike <= 0:
            raise ValueError("[overlay].call_strike must be > 0 for cc/collar.")
        if not call_key or not call_key.startswith("NSE_FO|"):
            raise ValueError(
                f"[overlay].call_instrument_key must start with 'NSE_FO|', got {call_key!r}"
            )
        if call_price <= Decimal("0"):
            raise ValueError(f"[overlay].call_price must be > 0, got {call_price}")

    return OverlayConfig(
        overlay_type=overlay_type,
        entry_date=entry_date,
        cycle=cycle,
        lot_size=lot_size,
        expiry=expiry,
        expiry_type=expiry_type,
        dte_at_entry=dte_at_entry,
        put_strike=put_strike,
        put_instrument_key=put_key,
        put_price=put_price,
        put_spread_pct=float(put_spread_pct) if put_spread_pct is not None else None,
        put_oi=put_oi,
        call_strike=call_strike,
        call_instrument_key=call_key,
        call_price=call_price,
        call_spread_pct=float(call_spread_pct) if call_spread_pct is not None else None,
        call_oi=call_oi,
    )


@dataclass
class OverlayTrade:
    """A PaperTrade paired with a warning if a blocked combination was skipped."""

    trade: PaperTrade
    strategy: str
    leg_role: str


def _query_open_call_role(db_path: Path, call_instrument_key: str) -> str | None:
    """Return the leg_role of an already-open short call on *call_instrument_key*.

    A "short call" is any leg with a net negative quantity whose leg_role is
    ``overlay_cc`` or ``overlay_collar_call``, under the shared STRATEGY_OVERLAY
    namespace (there is only one overlay position per leg role — S1r).

    Args:
        db_path: Path to the SQLite portfolio DB.
        call_instrument_key: The instrument key of the call leg about to be entered.

    Returns:
        The existing leg_role (``"overlay_cc"`` or ``"overlay_collar_call"``) if
        an open short call already exists on this key, else None.
    """
    import sqlite3

    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute(
            """
            SELECT leg_role,
                   SUM(CASE WHEN action='SELL' THEN -quantity ELSE quantity END) AS net_qty
            FROM paper_trades
            WHERE strategy_name = ?
              AND instrument_key = ?
              AND leg_role IN ('overlay_cc', 'overlay_collar_call')
            GROUP BY leg_role
            HAVING net_qty < 0
            """,
            (STRATEGY_OVERLAY, call_instrument_key),
        )
        row = cur.fetchone()
        conn.close()
        if row:
            return row[0]
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "open_call_role.query_failed",
            instrument_key=call_instrument_key,
            error=str(exc),
        )
        return None


def build_overlay_trades(
    cfg: OverlayConfig,
    existing_call_role: str | None = None,
) -> tuple[list[OverlayTrade], list[str]]:
    """Build PaperTrade objects for the shared, track-independent overlay leg.

    Overlay legs live in a single namespace (``STRATEGY_OVERLAY``, S1r 2026-07-29) —
    there is exactly one physical overlay position per leg role, never one per
    3-track base (Spot/Futures/Proxy). This emits at most one OverlayTrade per leg
    (two for collar: put + call), never one per track.

    Collar/CC deduplication: if *existing_call_role* reports an already-open short
    call on the same call instrument key (under overlay_cc or overlay_collar_call),
    inserting a second call leg is skipped. Collar put legs are still inserted —
    the existing call serves as the collar call. This prevents the same physical
    contract appearing under two leg_roles.

    Args:
        cfg: Validated OverlayConfig.
        existing_call_role: leg_role of an already-open short call on the same
            call_instrument_key, from ``_query_open_call_role``. None if none.

    Returns:
        Tuple of (list of OverlayTrade, list of warning strings).
    """
    trades: list[OverlayTrade] = []
    warnings: list[str] = []
    cycle_tag = (
        f"Cycle {cfg.cycle}. Expiry={cfg.expiry} ({cfg.expiry_type}, DTE={cfg.dte_at_entry})."
    )

    if cfg.overlay_type == "pp":
        trades.append(
            OverlayTrade(
                trade=PaperTrade(
                    strategy_name=STRATEGY_OVERLAY,
                    leg_role="overlay_pp",
                    instrument_key=cfg.put_instrument_key,
                    trade_date=cfg.entry_date,
                    action=TradeAction.BUY,
                    quantity=cfg.lot_size,
                    price=cfg.put_price,
                    notes=(
                        f"Overlay PP: strike={cfg.put_strike:.0f}, "
                        f"spread={cfg.put_spread_pct}%, OI={cfg.put_oi:,}. {cycle_tag}"
                    ),
                ),
                strategy=STRATEGY_OVERLAY,
                leg_role="overlay_pp",
            )
        )

    elif cfg.overlay_type == "cc":
        # Dedup guard: skip if overlay_collar_call already open on same key
        if existing_call_role == "overlay_collar_call":
            warnings.append(
                "  ⚠  SKIPPED: overlay_cc — overlay_collar_call already "
                f"open on {cfg.call_instrument_key}. Collar call serves as CC."
            )
        else:
            trades.append(
                OverlayTrade(
                    trade=PaperTrade(
                        strategy_name=STRATEGY_OVERLAY,
                        leg_role="overlay_cc",
                        instrument_key=cfg.call_instrument_key,
                        trade_date=cfg.entry_date,
                        action=TradeAction.SELL,
                        quantity=cfg.lot_size,
                        price=cfg.call_price,
                        notes=(
                            f"Overlay CC: strike={cfg.call_strike:.0f}, "
                            f"spread={cfg.call_spread_pct}%, OI={cfg.call_oi:,}. {cycle_tag}"
                        ),
                    ),
                    strategy=STRATEGY_OVERLAY,
                    leg_role="overlay_cc",
                )
            )

    elif cfg.overlay_type == "collar":
        # Always enter the put leg.
        trades.append(
            OverlayTrade(
                trade=PaperTrade(
                    strategy_name=STRATEGY_OVERLAY,
                    leg_role="overlay_collar_put",
                    instrument_key=cfg.put_instrument_key,
                    trade_date=cfg.entry_date,
                    action=TradeAction.BUY,
                    quantity=cfg.lot_size,
                    price=cfg.put_price,
                    notes=(
                        f"Collar put: strike={cfg.put_strike:.0f}, "
                        f"spread={cfg.put_spread_pct}%, OI={cfg.put_oi:,}. {cycle_tag}"
                    ),
                ),
                strategy=STRATEGY_OVERLAY,
                leg_role="overlay_collar_put",
            )
        )
        # Dedup guard: skip collar_call if overlay_cc already open on same key.
        # The existing CC serves as the collar call — recording a second SELL on
        # the same contract would double-count the short position.
        if existing_call_role == "overlay_cc":
            warnings.append(
                "  ⚠  SKIPPED: overlay_collar_call — overlay_cc already "
                f"open on {cfg.call_instrument_key}. Existing CC serves as collar call."
            )
        else:
            trades.append(
                OverlayTrade(
                    trade=PaperTrade(
                        strategy_name=STRATEGY_OVERLAY,
                        leg_role="overlay_collar_call",
                        instrument_key=cfg.call_instrument_key,
                        trade_date=cfg.entry_date,
                        action=TradeAction.SELL,
                        quantity=cfg.lot_size,
                        price=cfg.call_price,
                        notes=(
                            f"Collar call: strike={cfg.call_strike:.0f}, "
                            f"spread={cfg.call_spread_pct}%, OI={cfg.call_oi:,}. {cycle_tag}"
                        ),
                    ),
                    strategy=STRATEGY_OVERLAY,
                    leg_role="overlay_collar_call",
                )
            )

    return trades, warnings


def print_summary(
    cfg: OverlayConfig,
    overlay_trades: list[OverlayTrade],
    warnings: list[str],
    dry_run: bool,
) -> None:
    """Print a formatted overlay entry summary.

    Args:
        cfg: Validated OverlayConfig.
        overlay_trades: Built overlay trades.
        warnings: Blocked combo warnings.
        dry_run: If True, label as preview.
    """
    mode = "DRY RUN — nothing written to DB" if dry_run else "RECORDED TO DB"
    print(f"\n{'═' * 70}")
    print(
        f"  Overlay Entry | {cfg.entry_date} | Cycle {cfg.cycle} | "
        f"{cfg.overlay_type.upper()} | {mode}"
    )
    print(
        f"  Expiry: {cfg.expiry} ({cfg.expiry_type}, DTE={cfg.dte_at_entry}) | "
        f"lot_size={cfg.lot_size}"
    )
    print(f"{'═' * 70}")
    print(f"  {'Strategy':<24} {'Leg':<22} {'Act':>4} {'Price':>10}")
    print(f"  {'─' * 64}")

    for ot in overlay_trades:
        t = ot.trade
        print(f"  {t.strategy_name:<24} {t.leg_role:<22} {t.action.value:>4} {t.price:>10.2f}")

    if warnings:
        print()
        for w in warnings:
            print(w)

    print(f"{'═' * 70}")
    if dry_run:
        print("\n  Re-run without --dry-run to write to DB.")
    print()


def _record_collar_trades(store: PaperStore, overlay_trades: list["OverlayTrade"]) -> None:
    """Record collar legs per strategy using a single atomic transaction per pair.

    Each strategy's put + call are committed together. If either leg conflicts with
    the unique constraint, both are skipped (ON CONFLICT DO NOTHING semantics via
    record_trades). A partial insert — put committed, call skipped — cannot occur.

    Args:
        store: PaperStore instance.
        overlay_trades: Must contain complete put+call pairs (validated before call).
    """
    from collections import defaultdict

    # Group by strategy, preserving put-before-call order from build_overlay_trades
    by_strategy: dict[str, list[OverlayTrade]] = defaultdict(list)
    for ot in overlay_trades:
        by_strategy[ot.trade.strategy_name].append(ot)

    for _strategy, ots in by_strategy.items():
        trades = [ot.trade for ot in ots]
        inserted, skipped = store.record_trades(trades)
        for t in inserted:
            logger.info("trade.INSERTED", strategy=t.strategy_name, leg=t.leg_role)
        for t in skipped:
            logger.info(
                "trade.SKIPPED",
                reason="conflict on strategy/leg/date/action",
                strategy=t.strategy_name,
                leg=t.leg_role,
            )


def _has_open_overlay_leg(store: PaperStore, leg_role: str) -> bool:
    """True if STRATEGY_OVERLAY already holds an open position for *leg_role*.

    Overlay entry is a one-time bootstrap per leg (S6, 2026-07-28 decision) —
    once entered, the position is maintained via ExitSignalEngine-driven
    monetize/roll/close actions, never re-entered by this script. This guards
    a cron-invoked re-run from double-entering the same overlay leg.

    Args:
        store: PaperStore to query.
        leg_role: The overlay leg_role to check (see ``_PRIMARY_LEG_ROLE``).

    Returns:
        True if an open position with this leg_role already exists.
    """
    return any(p.leg_role == leg_role for p in store.get_positions(STRATEGY_OVERLAY))


def _check_overlay_collateral_capacity(
    store: PaperStore, strategy_name: str, lots_requested: int
) -> None:
    """Warn-only NiftyBees collateral-capacity gate for overlay entry (RH-4, 2026-08-06).

    Never blocks entry — fetches live Nifty spot/NiftyBees LTP and delegates to
    ``check_collateral_capacity`` (aggregates open lots across CSP + this shared
    overlay namespace against ``compute_max_lots()``'s ceiling; logs a
    ``GateViolation`` on breach). Any failure (LTP fetch, gate itself) is caught
    and logged non-fatally — an advisory gate must never block a trade that
    already cleared its own strategy-specific gates.
    """
    try:
        client = UpstoxMarketClient(settings.upstox_analytics_token)
        ltp_map = client.get_ltp_sync([NIFTY_UNDERLYING, NIFTYBEES_KEY])
        nifty_spot_ltp = ltp_map.get(NIFTY_UNDERLYING)
        niftybees_ltp = ltp_map.get(NIFTYBEES_KEY)
        if nifty_spot_ltp is None or niftybees_ltp is None:
            logger.warning(
                "paper_3track_overlay_entry.collateral_gate_skipped_missing_ltp",
                nifty_spot_available=nifty_spot_ltp is not None,
                niftybees_ltp_available=niftybees_ltp is not None,
            )
            return
        check_collateral_capacity(
            store=store,
            strategy_name=strategy_name,
            lots_requested=lots_requested,
            nifty_spot=nifty_spot_ltp,
            niftybees_ltp=niftybees_ltp,
        )
    except Exception as exc:  # non-fatal — advisory gate must never block the trade
        logger.warning("paper_3track_overlay_entry.collateral_gate_failed", error=str(exc))


def _alert_bootstrap_failure(overlay_label: str, log_file: str) -> None:
    """Best-effort Telegram alert for a structural auto-bootstrap failure.

    auto_cc_bootstrap/auto_pp_bootstrap/auto_collar_bootstrap return cfg=None
    on any structural gate failure (BOD load, no monthly expiry, DTE<14,
    chain fetch, no eligible strike) and the caller in main() sys.exit(1)s
    right after — previously silent apart from a log line + stderr print,
    which is how the 2026-08-11 auto_pp.no_monthly_expiry_found failure went
    unnoticed until logs/pp_entry.log was checked manually four days after
    an unrelated ivr_check_failed streak. Mirrors paper_3track_roll.py's
    existing partial-roll failure alert. Deliberately generic (does not
    thread the specific gate-failure reason through) — the bootstrap
    functions only log a structured event, they don't return one; the alert
    exists to surface *that* a cycle was silently skipped, not to replace
    reading the log for *why*. Never raises — a notify failure must not
    mask the underlying gate failure, and must never block the cron
    script's sys.exit(1).

    Args:
        overlay_label: Human-readable overlay name for the alert, e.g. "PP".
        log_file: Log file to point the operator at, e.g. "logs/pp_entry.log".
    """
    notifier = build_notifier()
    if not notifier:
        return
    msg = (
        f"🔴 OVERLAY ENTRY FAILED — {overlay_label} auto-bootstrap\n"
        f"A structural gate blocked entry this cycle (no trade recorded).\n"
        f"Check {log_file} for the failing gate."
    )
    try:
        asyncio.run(notifier.send(msg))
    except Exception as exc:  # non-fatal — notify failure never masks the gate failure
        logger.warning("paper_3track_overlay_entry.failure_notify_failed", error=str(exc))


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Record overlay legs across all three tracks from overlay_entry.yaml. "
            "Run scripts/lookup/find_overlay_strikes.py first to generate the YAML."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"Path to overlay YAML config (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite DB (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing to DB.",
    )
    parser.add_argument(
        "--bod-path",
        type=Path,
        default=DEFAULT_BOD_PATH,
        help=f"Path to BOD instrument JSON (default: {DEFAULT_BOD_PATH})",
    )
    parser.add_argument(
        "--auto-cc",
        action="store_true",
        help="Automate CC entry (bypasses YAML config, fetches chain, applies gates).",
    )
    parser.add_argument(
        "--auto-pp",
        action="store_true",
        help=(
            "Automate PP entry (bypasses YAML config, fetches chain, applies gates). "
            "Bootstrap when no put is open; routine-roll gap-fill when the open put "
            f"has DTE <= {_PP_ROLL_DTE_THRESHOLD}; no-op (exit 0) otherwise."
        ),
    )
    parser.add_argument(
        "--auto-collar",
        action="store_true",
        help=(
            "Automate first-ever Collar entry (bootstrap only — routine reentry after "
            "a close is handled automatically by CollarOverlayV1.apply_action, not this "
            "flag). Live path unblocked 2026-08-04 — Collar1/Collar2/Collar3a all landed, "
            "no decision gate remains open (paper trading, operator accepted the risk of "
            "unexercised code over a dry-run-only default), see DECISIONS.md."
        ),
    )
    parser.add_argument(
        "--log-only-gates",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Applies to --auto-cc/--auto-pp/--auto-collar: record a "
            "below/above-threshold IVR gate as a GateViolation and proceed, "
            "instead of hard-blocking (default: on — paper-trading phase, "
            "no real capital at risk; matches IC's resolve_ivr pattern; "
            "see DECISIONS.md 2026-08-07)."
        ),
    )
    args = parser.parse_args()
    setup_logging()

    gate_violation: GateViolation | None = None

    if args.auto_cc:
        # --no-dry-run block lifted 2026-08-02: CC1 (delta ladder), CC2 (delta-band
        # decision), and EC-5 (DTE<=5 exit collapse) have all landed, and EC-5's tests
        # were confirmed green on a live host the same day (see DECISIONS.md, TODOS.md
        # item 6). See docs/plan/3track-consolidation/tasks.md CC5 for the closure note.
        cfg, gate_violation = auto_cc_bootstrap(args.bod_path, log_only_gates=args.log_only_gates)
        if cfg is None:
            print("ERROR: auto-CC bootstrap failed. Check logs.", file=sys.stderr)
            _alert_bootstrap_failure("CC", "logs/cc_entry.log")
            sys.exit(1)
    elif args.auto_pp:
        # --no-dry-run unblocked 2026-08-03: PP1 (delta ladder) and PP2 (delta-
        # targeted entry, monthly cadence decision) have both landed — see
        # docs/plan/3track-consolidation/tasks.md PP2/PP3.
        open_dte = _open_pp_dte(args.db_path, args.bod_path)
        if open_dte is not None and open_dte > _PP_ROLL_DTE_THRESHOLD:
            logger.info("auto_pp.fresh_position_open", dte=open_dte)
            print(
                f"SKIPPED: overlay_pp already open at DTE={open_dte} "
                f"(> {_PP_ROLL_DTE_THRESHOLD}) — nothing to do.",
                file=sys.stderr,
            )
            sys.exit(0)
        cfg, gate_violation = auto_pp_bootstrap(args.bod_path, log_only_gates=args.log_only_gates)
        if cfg is None:
            print("ERROR: auto-PP bootstrap failed. Check logs.", file=sys.stderr)
            _alert_bootstrap_failure("PP", "logs/pp_entry.log")
            sys.exit(1)
    elif args.auto_collar:
        cfg, gate_violation = auto_collar_bootstrap(
            args.bod_path, log_only_gates=args.log_only_gates
        )
        if cfg is None:
            print("ERROR: auto-collar bootstrap failed. Check logs.", file=sys.stderr)
            _alert_bootstrap_failure("Collar", "logs/collar_entry.log")
            sys.exit(1)
    else:
        cfg = load_overlay_config(args.config)
    store = PaperStore(args.db_path)

    # Bootstrap-only (S6): skip entirely if this overlay's marker leg is already
    # open. Overlay entry is a one-time bootstrap, never a recurring re-entry.
    primary_role = _PRIMARY_LEG_ROLE[cfg.overlay_type]
    already_bootstrapped = _has_open_overlay_leg(store, primary_role)

    if args.auto_pp:
        # PP3, 2026-08-03: the generic S6 gate above assumes at most one open
        # leg ever. PP's routine-roll trigger deliberately holds two puts
        # briefly — the outgoing (still open, DTE <= _PP_ROLL_DTE_THRESHOLD)
        # and the fresh one being entered here — to satisfy the "no
        # unprotected day" requirement. The PP-specific _open_pp_dte gate
        # above already distinguishes bootstrap/routine-roll from "fresh
        # position covers, nothing to do" (which exits before reaching this
        # line), so the generic one-time-bootstrap gate would incorrectly
        # re-block the routine-roll case here — bypass it for this path only.
        already_bootstrapped = False

    # Idempotency guard for CC overlay entry on paper_nifty_spot track
    if cfg.overlay_type == "cc":
        spot_positions = store.get_positions(STRATEGY_SPOT)
        if any(p.leg_role == "overlay_cc" and p.net_qty != 0 for p in spot_positions):
            logger.info(
                "paper_3track_overlay_entry.duplicate_position", strategy_name=STRATEGY_SPOT
            )
            print(f"SKIPPED: overlay_cc already open on {STRATEGY_SPOT}.", file=sys.stderr)
            sys.exit(0)

    # Check for an existing open short call on the same instrument to prevent
    # recording overlay_cc and overlay_collar_call on the same contract.
    existing_call_role: str | None = None
    if cfg.overlay_type in ("cc", "collar") and cfg.call_instrument_key:
        existing_call_role = _query_open_call_role(args.db_path, cfg.call_instrument_key)
        if existing_call_role:
            logger.info(
                "open_call_role.found",
                instrument_key=cfg.call_instrument_key,
                leg_role=existing_call_role,
            )

    overlay_trades, warnings = build_overlay_trades(cfg, existing_call_role=existing_call_role)

    if not overlay_trades:
        print("ERROR: no trades to record — overlay leg was blocked.", file=sys.stderr)
        sys.exit(1)

    # Guard: collar legs must always be submitted as a complete pair,
    # unless the call was intentionally skipped because overlay_cc already exists.
    if cfg.overlay_type == "collar":
        _validate_collar_pairs(overlay_trades, existing_call_role=existing_call_role)

    if not args.dry_run:
        if already_bootstrapped:
            logger.info(
                "paper_3track_overlay_entry.bootstrap_skipped",
                overlay_type=cfg.overlay_type,
                leg_role=primary_role,
            )
            print(
                f"SKIPPED: {primary_role} already open under {STRATEGY_OVERLAY} — "
                "overlay entry is a one-time bootstrap, not a recurring re-entry.",
                file=sys.stderr,
            )
        else:
            _check_overlay_collateral_capacity(
                store, STRATEGY_OVERLAY, lots_requested=len(overlay_trades)
            )
            if cfg.overlay_type == "collar":
                _record_collar_trades(store, overlay_trades)
            else:
                for ot in overlay_trades:
                    inserted = store.record_trade(ot.trade)
                    if inserted:
                        logger.info(
                            "trade.INSERTED",
                            strategy=ot.trade.strategy_name,
                            leg=ot.trade.leg_role,
                        )
                    else:
                        logger.info(
                            "trade.SKIPPED",
                            reason="conflict on strategy/leg/date/action",
                            strategy=ot.trade.strategy_name,
                            leg=ot.trade.leg_role,
                        )

            if gate_violation is not None:
                try:
                    store.record_gate_violation(gate_violation)
                except Exception as exc:  # non-fatal — a logging gate must never block the trade
                    logger.warning(
                        "paper_3track_overlay_entry.gate_violation_record_failed",
                        error=str(exc),
                    )

            notifier = build_notifier()
            if notifier:
                lines = [f"🟢 OVERLAY ENTRY — {cfg.overlay_type.upper()} bootstrap"]
                for ot in overlay_trades:
                    lines.append(f"{ot.leg_role}: {ot.trade.instrument_key} @ ₹{ot.trade.price}")
                if gate_violation is not None:
                    lines.append(
                        f"⚠ Gate logged: {gate_violation.gate_name} "
                        f"(threshold={gate_violation.threshold}, actual={gate_violation.actual})"
                    )
                msg = "\n".join(lines)
                try:
                    asyncio.run(notifier.send(msg))
                except Exception as exc:  # non-fatal — notify failure never blocks the trade
                    logger.warning("paper_3track_overlay_entry.notify_failed", error=str(exc))

    print_summary(cfg, overlay_trades, warnings, args.dry_run)


if __name__ == "__main__":
    main()
