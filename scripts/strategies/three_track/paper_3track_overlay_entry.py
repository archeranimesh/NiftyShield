#!/usr/bin/env python3
"""Record overlay legs across all three tracks from a pre-filled overlay_entry.yaml.

Reads the YAML written by scripts/lookup/find_overlay_strikes.py, validates it, enforces blocked
combinations (Futures + standalone Covered Call), and records the appropriate legs
for paper_nifty_spot, paper_nifty_futures, and paper_nifty_proxy.

Leg role naming (per strategy spec):
    overlay_pp              — Protective Put (BUY PE)
    overlay_cc              — Covered Call   (SELL CE)
    overlay_collar_put      — Collar put leg (BUY PE)
    overlay_collar_call     — Collar call leg (SELL CE)

Blocked combination (hard rule — never recorded):
    paper_nifty_futures + standalone overlay_cc
    Futures + short call = synthetic short put = unlimited downside (MISSION.md Principle I).

Usage:
    python scripts/paper_3track_overlay_entry.py --dry-run
    python scripts/paper_3track_overlay_entry.py
    python scripts/paper_3track_overlay_entry.py --config data/paper/cycle2_overlay.yaml
"""

import argparse

# ruff: noqa: E402
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import structlog
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.models.portfolio import TradeAction
from src.paper.constants import (
    DEFAULT_DB_PATH,
    STRATEGY_FUTURES,
    STRATEGY_PROXY,
    STRATEGY_SPOT,
)
from src.paper.models import PaperTrade
from src.paper.store import PaperStore
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.strategies.three_track.paper_3track_overlay_entry"
logger = structlog.get_logger(_SCRIPT_NAME)

DEFAULT_CONFIG = Path("data/paper/overlay_entry.yaml")

# Tracks and whether each may carry a standalone covered call
_TRACKS = [STRATEGY_SPOT, STRATEGY_FUTURES, STRATEGY_PROXY]
_CC_BLOCKED = {STRATEGY_FUTURES}  # Futures + standalone CC is permanently blocked

_COLLAR_PUT_ROLE = "overlay_collar_put"
_COLLAR_CALL_ROLE = "overlay_collar_call"
_COLLAR_ROLES = frozenset({_COLLAR_PUT_ROLE, _COLLAR_CALL_ROLE})


def _validate_collar_pairs(overlay_trades: list["OverlayTrade"]) -> None:
    """Ensure every strategy with a collar leg has both put and call present.

    A partial collar (put without call or call without put) is never permitted
    at the entry/close layer. This guard catches any code path that would
    produce a half-collar before any DB write occurs.

    Args:
        overlay_trades: Trades about to be submitted.

    Raises:
        SystemExit: If any strategy has only one collar leg.
    """
    from collections import defaultdict

    by_strategy: dict[str, set[str]] = defaultdict(set)
    for ot in overlay_trades:
        if ot.trade.leg_role in _COLLAR_ROLES:
            by_strategy[ot.trade.strategy_name].add(ot.trade.leg_role)

    for strategy, roles in by_strategy.items():
        if roles != _COLLAR_ROLES:
            missing = _COLLAR_ROLES - roles
            print(
                f"ERROR: partial collar for {strategy} — missing {missing}. "
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


def build_overlay_trades(cfg: OverlayConfig) -> tuple[list[OverlayTrade], list[str]]:
    """Build PaperTrade objects for all applicable tracks, enforcing blocked combos.

    Futures + standalone Covered Call is permanently blocked. When overlay_type='cc',
    paper_nifty_futures is skipped and a warning is returned.

    Args:
        cfg: Validated OverlayConfig.

    Returns:
        Tuple of (list of OverlayTrade, list of warning strings).
    """
    trades: list[OverlayTrade] = []
    warnings: list[str] = []
    cycle_tag = (
        f"Cycle {cfg.cycle}. Expiry={cfg.expiry} ({cfg.expiry_type}, DTE={cfg.dte_at_entry})."
    )

    for strategy in _TRACKS:
        # Enforce blocked combo: Futures + standalone CC
        if strategy in _CC_BLOCKED and cfg.overlay_type == "cc":
            warnings.append(
                f"  ⚠  BLOCKED: {strategy} + standalone overlay_cc skipped. "
                "Futures + short call = synthetic short put (MISSION.md Principle I)."
            )
            continue

        if cfg.overlay_type == "pp":
            trades.append(
                OverlayTrade(
                    trade=PaperTrade(
                        strategy_name=strategy,
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
                    strategy=strategy,
                    leg_role="overlay_pp",
                )
            )

        elif cfg.overlay_type == "cc":
            trades.append(
                OverlayTrade(
                    trade=PaperTrade(
                        strategy_name=strategy,
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
                    strategy=strategy,
                    leg_role="overlay_cc",
                )
            )

        elif cfg.overlay_type == "collar":
            # Collar — both legs must be entered together per spec
            trades.append(
                OverlayTrade(
                    trade=PaperTrade(
                        strategy_name=strategy,
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
                    strategy=strategy,
                    leg_role="overlay_collar_put",
                )
            )
            trades.append(
                OverlayTrade(
                    trade=PaperTrade(
                        strategy_name=strategy,
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
                    strategy=strategy,
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
    args = parser.parse_args()
    setup_logging()

    cfg = load_overlay_config(args.config)
    overlay_trades, warnings = build_overlay_trades(cfg)

    if not overlay_trades:
        print("ERROR: no trades to record — all tracks were blocked.", file=sys.stderr)
        sys.exit(1)

    # Guard: collar legs must always be submitted as a complete pair per strategy.
    # Raises SystemExit before any DB write if only one collar leg is present.
    if cfg.overlay_type == "collar":
        _validate_collar_pairs(overlay_trades)

    if not args.dry_run:
        store = PaperStore(args.db_path)

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

    print_summary(cfg, overlay_trades, warnings, args.dry_run)


if __name__ == "__main__":
    main()
