#!/usr/bin/env python3
"""Single-command base leg entry for the 3-Track Nifty Long Comparison framework.

Records all three base legs in one shot from a YAML config:
  paper_nifty_spot    → base_etf        (NiftyBees ETF)
  paper_nifty_futures → base_futures    (Nifty Futures, 1 lot)
  paper_nifty_proxy   → base_ditm_call  (Deep ITM Call, delta ≈ 0.90)

Usage:
    # Copy template and fill in today's prices:
    cp data/paper/3track_entry_template.yaml data/paper/3track_entry.yaml

    # Preview (no DB writes):
    python scripts/paper_3track_entry.py --dry-run

    # Record:
    python scripts/paper_3track_entry.py

    # Use a different config (e.g., Cycle 2):
    python scripts/paper_3track_entry.py --config data/paper/cycle2_entry.yaml
"""

import argparse
import math
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.instruments.lookup import InstrumentLookup
from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade
from src.paper.store import PaperStore

NIFTYBEES_KEY = "NSE_EQ|INF204KB14I2"
DEFAULT_CONFIG = Path("data/paper/3track_entry.yaml")
DEFAULT_BOD = Path("data/instruments/NSE.json.gz")
DEFAULT_DB = Path("data/portfolio/portfolio.sqlite")


@dataclass
class EntryConfig:
    """Validated entry config for one 3-track cycle."""

    entry_date: date
    lot_size: int
    nifty_spot: Decimal
    cycle: int
    niftybees_ltp: Decimal
    futures_key: str
    futures_price: Decimal
    proxy_strike: float
    proxy_expiry: str
    proxy_price: Decimal
    proxy_actual_delta: Decimal


def load_config(path: Path) -> EntryConfig:
    """Load and validate the entry YAML config.

    Args:
        path: Path to the YAML config file.

    Returns:
        Validated EntryConfig.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If any required field is missing or contains a placeholder.
    """
    with open(path) as f:
        raw = yaml.safe_load(f)

    def _get(section: str, key: str):
        val = raw.get(section, {}).get(key)
        if val is None:
            raise ValueError(f"Missing required field [{section}].{key} in {path}")
        return val

    # ── entry ──────────────────────────────────────────────────────────────
    date_str = str(_get("entry", "date"))
    if date_str in ("YYYY-MM-DD", ""):
        raise ValueError(
            "[entry].date is still a placeholder — fill in the entry date."
        )
    entry_date = date.fromisoformat(date_str)
    lot_size = int(_get("entry", "lot_size"))
    nifty_spot = Decimal(str(_get("entry", "nifty_spot")))
    cycle = int(raw.get("entry", {}).get("cycle", 1))

    # ── spot ───────────────────────────────────────────────────────────────
    niftybees_ltp = Decimal(str(_get("spot", "niftybees_ltp")))

    # ── futures ────────────────────────────────────────────────────────────
    futures_key = str(_get("futures", "instrument_key")).strip()
    futures_price = Decimal(str(_get("futures", "price")))

    # ── proxy ──────────────────────────────────────────────────────────────
    proxy_strike = float(_get("proxy", "strike"))
    proxy_expiry_str = str(_get("proxy", "expiry"))
    if proxy_expiry_str in ("YYYY-MM-DD", ""):
        raise ValueError(
            "[proxy].expiry is still a placeholder — fill in the expiry date."
        )
    proxy_expiry = proxy_expiry_str
    proxy_price = Decimal(str(_get("proxy", "price")))
    proxy_actual_delta = Decimal(str(_get("proxy", "actual_delta")))

    # ── sanity checks ──────────────────────────────────────────────────────
    if nifty_spot <= Decimal("0"):
        raise ValueError(f"[entry].nifty_spot must be > 0, got {nifty_spot}")
    if niftybees_ltp <= Decimal("0"):
        raise ValueError(f"[spot].niftybees_ltp must be > 0, got {niftybees_ltp}")
    if futures_price <= Decimal("0"):
        raise ValueError(f"[futures].price must be > 0, got {futures_price}")
    if not futures_key.startswith("NSE_FO|"):
        raise ValueError(
            f"[futures].instrument_key must start with 'NSE_FO|', got {futures_key!r}"
        )
    if proxy_strike <= 0:
        raise ValueError(f"[proxy].strike must be > 0, got {proxy_strike}")
    if proxy_price <= Decimal("0"):
        raise ValueError(f"[proxy].price must be > 0, got {proxy_price}")
    if not (Decimal("0") < proxy_actual_delta <= Decimal("1")):
        raise ValueError(
            f"[proxy].actual_delta must be in (0, 1], got {proxy_actual_delta}"
        )
    if proxy_actual_delta < Decimal("0.85"):
        raise ValueError(
            f"[proxy].actual_delta={proxy_actual_delta} is below 0.85 — "
            "entry constraint violated. Re-run find_strike_by_delta.py and pick a "
            "deeper strike."
        )

    return EntryConfig(
        entry_date=entry_date,
        lot_size=lot_size,
        nifty_spot=nifty_spot,
        cycle=cycle,
        niftybees_ltp=niftybees_ltp,
        futures_key=futures_key,
        futures_price=futures_price,
        proxy_strike=proxy_strike,
        proxy_expiry=proxy_expiry,
        proxy_price=proxy_price,
        proxy_actual_delta=proxy_actual_delta,
    )


def compute_niftybees_qty(
    nifty_spot: Decimal, lot_size: int, niftybees_ltp: Decimal
) -> int:
    """Compute NiftyBees quantity for 1 Nifty lot equivalent (NEE).

    Args:
        nifty_spot: Nifty 50 index spot price.
        lot_size: Nifty lot size.
        niftybees_ltp: NiftyBees ETF last traded price.

    Returns:
        Floor of (lot_size × nifty_spot) / niftybees_ltp.
    """
    return math.floor((lot_size * float(nifty_spot)) / float(niftybees_ltp))


def resolve_proxy_key(
    lookup: InstrumentLookup, strike: float, expiry: str
) -> str:
    """Resolve instrument key for the deep ITM call from the BOD file.

    Args:
        lookup: InstrumentLookup instance loaded from the BOD JSON.
        strike: Target strike price (CE).
        expiry: Expiry date as YYYY-MM-DD.

    Returns:
        Upstox instrument key string.

    Raises:
        ValueError: If no matching instrument is found in the BOD file.
    """
    results = lookup.search_options(
        underlying="NIFTY",
        strike=strike,
        option_type="CE",
        expiry=expiry,
        max_results=1,
    )
    if not results:
        raise ValueError(
            f"No CE instrument found for NIFTY strike={strike} expiry={expiry}. "
            "Verify the BOD file is current and the strike/expiry values are correct."
        )
    key = results[0].get("instrument_key")
    if not key:
        raise ValueError(
            f"Instrument found but has no instrument_key field: {results[0]}"
        )
    return key


def build_trades(
    cfg: EntryConfig, proxy_key: str, niftybees_qty: int
) -> list[PaperTrade]:
    """Build the three base leg PaperTrade objects from a validated config.

    Args:
        cfg: Validated EntryConfig.
        proxy_key: Resolved instrument key for the proxy deep ITM call.
        niftybees_qty: Computed NiftyBees quantity.

    Returns:
        List of three PaperTrade objects: [spot, futures, proxy].
    """
    nee = cfg.nifty_spot * Decimal(str(cfg.lot_size))
    cycle_tag = f"Cycle {cfg.cycle}."
    span_margin_estimate = Decimal("150000")

    spot = PaperTrade(
        strategy_name="paper_nifty_spot",
        leg_role="base_etf",
        instrument_key=NIFTYBEES_KEY,
        trade_date=cfg.entry_date,
        action=TradeAction.BUY,
        quantity=niftybees_qty,
        price=cfg.niftybees_ltp,
        notes=(
            f"Spot base: NEE qty={niftybees_qty}. "
            f"Nifty spot={cfg.nifty_spot}, lot_size={cfg.lot_size}. {cycle_tag}"
        ),
    )

    notional = cfg.futures_price * Decimal(str(cfg.lot_size))
    surplus = nee - span_margin_estimate
    futures = PaperTrade(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        instrument_key=cfg.futures_key,
        trade_date=cfg.entry_date,
        action=TradeAction.BUY,
        quantity=cfg.lot_size,
        price=cfg.futures_price,
        notes=(
            f"Futures base: 1 lot. Notional=₹{notional:,.0f}. "
            f"SPAN margin ~₹1.5L. Surplus notional=₹{surplus:,.0f}. {cycle_tag}"
        ),
    )

    proxy = PaperTrade(
        strategy_name="paper_nifty_proxy",
        leg_role="base_ditm_call",
        instrument_key=proxy_key,
        trade_date=cfg.entry_date,
        action=TradeAction.BUY,
        quantity=cfg.lot_size,
        price=cfg.proxy_price,
        notes=(
            f"Proxy base: Deep ITM CE delta={cfg.proxy_actual_delta}, "
            f"strike={cfg.proxy_strike}, expiry={cfg.proxy_expiry}. "
            f"Target delta 0.90. {cycle_tag}"
        ),
    )

    return [spot, futures, proxy]


def print_summary(
    cfg: EntryConfig,
    trades: list[PaperTrade],
    niftybees_qty: int,
    proxy_key: str,
    dry_run: bool,
) -> None:
    """Print a formatted entry summary table to stdout.

    Args:
        cfg: Validated EntryConfig.
        trades: The three PaperTrade objects built from the config.
        niftybees_qty: Computed NiftyBees quantity.
        proxy_key: Resolved proxy instrument key.
        dry_run: If True, label the output as a preview.
    """
    nee = cfg.nifty_spot * Decimal(str(cfg.lot_size))
    mode = "DRY RUN — nothing written to DB" if dry_run else "RECORDED TO DB"

    print(f"\n{'═' * 70}")
    print(f"  3-Track Entry | {cfg.entry_date} | Cycle {cfg.cycle} | {mode}")
    print(f"  Nifty Spot: ₹{cfg.nifty_spot:,.2f}  |  NEE: ₹{nee:,.0f}  (lot_size={cfg.lot_size})")
    print(f"{'═' * 70}")
    print(f"  {'Track':<20} {'Leg':<18} {'Qty':>6} {'Price':>10} {'Notional':>14}")
    print(f"  {'─' * 68}")

    rows = [
        (
            "A  Spot (NiftyBees)",
            "base_etf",
            niftybees_qty,
            cfg.niftybees_ltp,
            cfg.niftybees_ltp * niftybees_qty,
        ),
        (
            "B  Futures",
            "base_futures",
            cfg.lot_size,
            cfg.futures_price,
            cfg.futures_price * cfg.lot_size,
        ),
        (
            f"C  Proxy δ={cfg.proxy_actual_delta}",
            "base_ditm_call",
            cfg.lot_size,
            cfg.proxy_price,
            cfg.proxy_price * cfg.lot_size,
        ),
    ]
    for track, leg, qty, price, notional in rows:
        print(
            f"  {track:<20} {leg:<18} {qty:>6} {price:>10.2f} ₹{notional:>12,.0f}"
        )

    print(f"{'═' * 70}")
    print(f"  Proxy key  : {proxy_key}")
    print(
        f"  Next step  : python scripts/paper_track_snapshot.py "
        f"--underlying-price {cfg.nifty_spot} --dry-run"
    )
    if dry_run:
        print("\n  Re-run without --dry-run to write to DB.")
    print()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Record all three base legs for the 3-Track Nifty comparison in one command. "
            f"Default config: {DEFAULT_CONFIG}"
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"Path to YAML entry config (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--bod-path",
        type=Path,
        default=DEFAULT_BOD,
        help=f"Path to BOD instruments JSON (default: {DEFAULT_BOD})",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB,
        help=f"Path to SQLite DB (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the trades without writing to DB.",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)

    lookup = InstrumentLookup.from_file(args.bod_path)
    proxy_key = resolve_proxy_key(lookup, cfg.proxy_strike, cfg.proxy_expiry)
    niftybees_qty = compute_niftybees_qty(cfg.nifty_spot, cfg.lot_size, cfg.niftybees_ltp)

    if niftybees_qty <= 0:
        print("ERROR: computed NiftyBees qty is 0 — check nifty_spot and niftybees_ltp.")
        sys.exit(1)

    trades = build_trades(cfg, proxy_key, niftybees_qty)

    if not args.dry_run:
        store = PaperStore(args.db_path)
        for trade in trades:
            store.record_trade(trade)

    print_summary(cfg, trades, niftybees_qty, proxy_key, args.dry_run)


if __name__ == "__main__":
    main()
