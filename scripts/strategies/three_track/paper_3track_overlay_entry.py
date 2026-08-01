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

Cron example (dry-run only until CC1/CC2/EC-5 resolved):
    15 15 * * 3  cd /path/to/NiftyShield && python scripts/strategies/three_track/paper_3track_overlay_entry.py --auto-cc --dry-run
"""

import argparse

# ruff: noqa: E402
import asyncio
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import structlog
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from scripts.lookup.find_strike_by_delta import _select_delta_candidates
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
from src.models.portfolio import TradeAction
from src.notifications.telegram import build_notifier
from src.paper.constants import (
    DEFAULT_BOD_PATH,
    DEFAULT_DB_PATH,
    STRATEGY_OVERLAY,
    STRATEGY_SPOT,
)
from src.paper.models import PaperTrade
from src.paper.store import PaperStore
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

_COLLAR_PUT_ROLE = "overlay_collar_put"
_COLLAR_CALL_ROLE = "overlay_collar_call"
_COLLAR_ROLES = frozenset({_COLLAR_PUT_ROLE, _COLLAR_CALL_ROLE})


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


def auto_cc_bootstrap(bod_path: Path) -> OverlayConfig | None:
    """Automate CC entry (fetch chain, apply gates, select strike)."""
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
        return None

    expiry_str = None
    for label, exp_str in expiries:
        if label == "monthly":
            expiry_str = exp_str
            break

    if not expiry_str:
        logger.error("auto_cc.no_monthly_expiry_found")
        return None

    # Gate 1: DTE >= 14
    expiry_date = date.fromisoformat(expiry_str)
    dte = (expiry_date - today).days
    if dte < 14:
        logger.error("auto_cc.dte_gate_failed", dte=dte)
        return None

    # Gate 2: IVR >= 0.25
    try:
        vix_series = load_vix_series(settings.vix_data_dir)
        vix_today = fetch_vix_latest()
        ivr = compute_ivr(vix_today, vix_series)
        if ivr is None or ivr < 0.25:
            logger.error("auto_cc.ivr_gate_failed", ivr=ivr)
            return None
    except Exception as exc:
        logger.error("auto_cc.ivr_check_failed", error=str(exc))
        return None

    # Fetch live chain
    try:
        client = UpstoxMarketClient(settings.upstox_analytics_token)
        raw_chain = client.get_option_chain_sync("NSE_INDEX|Nifty 50", expiry_str)
    except Exception as exc:
        logger.error("auto_cc.chain_fetch_failed", error=str(exc))
        return None

    if not raw_chain:
        logger.error("auto_cc.chain_empty")
        return None

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
        return None

    call_price = Decimal(
        str(selected_row["mid"] if selected_row["mid"] > 0 else selected_row["ltp"])
    )

    return OverlayConfig(
        overlay_type="cc",
        entry_date=today,
        cycle=1,  # Cycle doesn't matter for auto CC
        lot_size=75,
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
    args = parser.parse_args()
    setup_logging()

    if args.auto_cc:
        if not args.dry_run:
            print(
                "ERROR: --no-dry-run is temporarily blocked for auto-cc until CC1/CC2/EC-5 lands.",
                file=sys.stderr,
            )
            sys.exit(1)

        cfg = auto_cc_bootstrap(args.bod_path)
        if cfg is None:
            print("ERROR: auto-CC bootstrap failed. Check logs.", file=sys.stderr)
            sys.exit(1)
    else:
        cfg = load_overlay_config(args.config)
    store = PaperStore(args.db_path)

    # Bootstrap-only (S6): skip entirely if this overlay's marker leg is already
    # open. Overlay entry is a one-time bootstrap, never a recurring re-entry.
    primary_role = _PRIMARY_LEG_ROLE[cfg.overlay_type]
    already_bootstrapped = _has_open_overlay_leg(store, primary_role)

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

            notifier = build_notifier()
            if notifier:
                lines = [f"🟢 OVERLAY ENTRY — {cfg.overlay_type.upper()} bootstrap"]
                for ot in overlay_trades:
                    lines.append(f"{ot.leg_role}: {ot.trade.instrument_key} @ ₹{ot.trade.price}")
                msg = "\n".join(lines)
                try:
                    asyncio.run(notifier.send(msg))
                except Exception as exc:  # non-fatal — notify failure never blocks the trade
                    logger.warning("paper_3track_overlay_entry.notify_failed", error=str(exc))

    print_summary(cfg, overlay_trades, warnings, args.dry_run)


if __name__ == "__main__":
    main()
