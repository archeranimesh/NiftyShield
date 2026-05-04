#!/usr/bin/env python3
"""Single-command base leg entry for the 3-Track Nifty Long Comparison framework.

Live-fetch auto mode: connects to Upstox, fetches all live prices, auto-selects
the best proxy strike (delta ≈ 0.90), prints a confirmation table, and records
all three base legs to the DB on --confirm.

Usage:
    # Preview (no DB write) — default:
    python scripts/paper_3track_entry.py

    # Record to DB after reviewing the preview table:
    python scripts/paper_3track_entry.py --confirm

    # Override expiry (if BOD auto-detect is wrong):
    python scripts/paper_3track_entry.py --expiry 2026-05-29 --confirm

    # Tag as Cycle 2:
    python scripts/paper_3track_entry.py --cycle 2 --confirm

    # YAML-based offline entry — RESERVED, NOT YET IMPLEMENTED:
    # python scripts/paper_3track_entry.py --config config/paper/3track_entry.yaml
    # When implemented, config files must live in config/paper/ (NOT data/paper/).
    # data/ is for runtime outputs only. config/ is for operator-authored input files.

Diagnostics:
    LOG_LEVEL=DEBUG python scripts/paper_3track_entry.py   # full trace
"""

import logging
import math
import os
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.client.upstox_market import UpstoxMarketClient
from src.instruments.lookup import InstrumentLookup, parse_expiry
from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade
from src.paper.store import PaperStore

# ── Constants ────────────────────────────────────────────────────────────────

NIFTYBEES_KEY = "NSE_EQ|INF204KB14I2"
NIFTY_UNDERLYING = "NSE_INDEX|Nifty 50"
LOT_SIZE = 65           # Nifty 50, effective Jan 2026 — verify before each cycle
PROXY_DELTA_MIN = 0.85
PROXY_DELTA_MAX = 0.95
PROXY_TARGET_DELTA = 0.90
PROXY_OI_MIN = 5_000
PROXY_SPREAD_MAX = 5.0

# DTE bands for multi-expiry proxy search
PROXY_MONTHLY_DTE = (15, 45)       # front-month expiry
PROXY_QUARTERLY_DTE = (46, 200)    # next quarterly (Jun / Sep)
PROXY_YEARLY_DTE = (201, 420)      # year-end expiry (Dec)
SPAN_MARGIN_ESTIMATE = Decimal("150000")
DEFAULT_BOD = Path("data/instruments/NSE.json.gz")
DEFAULT_DB = Path("data/portfolio/portfolio.sqlite")

logger = logging.getLogger(__name__)


# ── Data model ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LivePrices:
    """All live-fetched prices for one 3-track entry cycle."""
    entry_date: date
    expiry: str
    nifty_spot: Decimal
    lot_size: int
    cycle: int
    niftybees_ltp: Decimal
    niftybees_qty: int
    futures_key: str
    futures_price: Decimal
    proxy_strike: float
    proxy_price: Decimal        # mid + slippage (recorded price)
    proxy_actual_delta: Decimal
    proxy_instrument_key: str
    proxy_oi: int
    proxy_bid: float
    proxy_ask: float
    proxy_candidates: list  # ranked list of all candidates (for display only)


# ── Step A: derive expiry from BOD ───────────────────────────────────────────

def derive_expiry(lookup: InstrumentLookup, today: date) -> str:
    """Derive the target monthly expiry from BOD futures. Prefers 30-45 DTE."""
    logger.debug("Searching BOD for NIFTY futures to derive expiry (today=%s)", today)
    futures = lookup.search_futures("NIFTY", max_results=10)
    logger.debug("BOD search_futures returned %d results", len(futures))

    if not futures:
        raise ValueError(
            "No NIFTY futures found in BOD file. "
            "Ensure data/instruments/NSE.json.gz is current. "
            "Use --expiry YYYY-MM-DD to override."
        )

    candidates: list[tuple[date, str]] = []
    for inst in futures:
        parsed = parse_expiry(inst.get("expiry"))
        if not parsed:
            logger.debug("Skipping futures with unparseable expiry: %r", inst.get("expiry"))
            continue
        exp_date = date.fromisoformat(parsed)
        if exp_date <= today:
            logger.debug("Skipping past expiry %s", parsed)
            continue
        dte = (exp_date - today).days
        candidates.append((exp_date, parsed))
        logger.debug("Candidate expiry: %s  DTE=%d", parsed, dte)

    if not candidates:
        raise ValueError(
            f"No future NIFTY expiry in BOD (today={today}). "
            "BOD file may be stale. Use --expiry YYYY-MM-DD."
        )
    candidates.sort()

    # Prefer 30–45 DTE
    for exp_date, parsed in candidates:
        dte = (exp_date - today).days
        if 30 <= dte <= 45:
            logger.info("Auto-selected expiry %s (DTE=%d, in 30-45 DTE window)", parsed, dte)
            return parsed

    # Fallback: nearest future expiry
    exp_date, parsed = candidates[0]
    dte = (exp_date - today).days
    logger.warning(
        "No expiry in 30-45 DTE window found. "
        "Falling back to nearest future expiry %s (DTE=%d). "
        "Use --expiry YYYY-MM-DD to override.",
        parsed, dte,
    )
    return parsed


# ── Step B: proxy candidate selection ────────────────────────────────────────

def _safe_float(val: Any) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def filter_proxy_candidates(raw_chain: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract CE rows from raw option chain in the 0.85–0.95 delta band."""
    rows: list[dict[str, Any]] = []
    for entry in raw_chain:
        strike = _safe_float(entry.get("strike_price"))
        opt = entry.get("call_options") or {}
        greeks = opt.get("option_greeks") or {}
        mktdata = opt.get("market_data") or {}
        key = opt.get("instrument_key", "")
        delta = _safe_float(greeks.get("delta"))

        if not (PROXY_DELTA_MIN <= abs(delta) <= PROXY_DELTA_MAX):
            continue
        if not key:
            logger.debug("Strike %.0f: no instrument_key, skipping", strike)
            continue

        bid = _safe_float(mktdata.get("bid_price"))
        ask = _safe_float(mktdata.get("ask_price"))
        ltp = _safe_float(mktdata.get("ltp"))
        mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else ltp
        oi = int(_safe_float(mktdata.get("oi")))

        rows.append({
            "strike": strike, "delta": delta,
            "iv": _safe_float(greeks.get("iv")),
            "ltp": ltp, "mid": mid, "bid": bid, "ask": ask,
            "oi": oi, "instrument_key": key,
            "option_type": "CE",
        })
        logger.debug(
            "Proxy candidate: strike=%.0f delta=%.4f OI=%d spread=%.2f mid=%.2f",
            strike, delta, oi, ask - bid, mid,
        )

    rows.sort(key=lambda r: abs(r["delta"]), reverse=True)
    logger.info(
        "Found %d proxy candidates in delta %.2f–%.2f", len(rows), PROXY_DELTA_MIN, PROXY_DELTA_MAX
    )
    return rows


def auto_select_proxy(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Rank candidates: round-100 strikes first, then by bid-ask spread ascending.

    Ranking key (ascending):
      1. is_non_round — 0 for multiples of 100 (preferred), 1 for 50-increment strikes
      2. spread       — tighter spread wins within each tier
      3. delta proximity to PROXY_TARGET_DELTA — tiebreaker only

    Sorts `rows` in place so callers see the final ranked order.
    """
    if not rows:
        raise ValueError(
            f"No CE strikes found with delta in [{PROXY_DELTA_MIN}, {PROXY_DELTA_MAX}]. "
            "The chain may be empty or the expiry too close. Try --expiry with another date."
        )

    def _rank_key(r: dict[str, Any]) -> tuple:
        spread = r["ask"] - r["bid"] if (r["ask"] > 0 and r["bid"] > 0) else 9_999.0
        is_non_round = int(r["strike"]) % 100 != 0
        # Bucket spreads into ₹2 windows so candidates within the same spread
        # tier compete on OI (higher OI wins) rather than on sub-rupee differences.
        spread_bucket = int(spread / 2)
        delta_dist = abs(abs(r["delta"]) - PROXY_TARGET_DELTA)
        return (is_non_round, spread_bucket, -r["oi"], spread, delta_dist)

    rows.sort(key=_rank_key)
    for i, r in enumerate(rows):
        r["rank"] = i + 1

    best = rows[0]
    logger.info(
        "Auto-selected proxy: strike=%.0f delta=%.4f OI=%d spread=%.2f key=%s",
        best["strike"], best["delta"], best["oi"],
        best["ask"] - best["bid"], best["instrument_key"],
    )
    return best


def compute_proxy_entry_price(row: dict[str, Any]) -> Decimal:
    """Entry price = mid + slippage. Slippage = max(₹0.50, 0.50 × spread)."""
    spread = row["ask"] - row["bid"] if (row["ask"] > 0 and row["bid"] > 0) else 0.0
    slippage = max(0.50, 0.50 * spread)
    price = Decimal(str(round(row["mid"] + slippage, 2)))
    logger.debug(
        "Proxy entry price: mid=%.2f bid=%.2f ask=%.2f spread=%.2f slippage=%.2f → ₹%s",
        row["mid"], row["bid"], row["ask"], spread, slippage, price,
    )
    return price


# ── Step C: orchestrate all live fetches ─────────────────────────────────────

def collect_candidate_expiries(
    lookup: InstrumentLookup, today: date
) -> dict[str, str]:
    """Return one expiry per DTE band from BOD: monthly, quarterly, yearly.

    Scans all NIFTY CE/PE entries and picks the nearest expiry in each band:
      monthly:   DTE 15–45   (front-month rollover window)
      quarterly: DTE 46–200  (next Jun / Sep quarter-end)
      yearly:    DTE 201–420 (Dec year-end contract)

    Returns a dict like {"monthly": "2026-05-26", "quarterly": "2026-06-30", ...}.
    Categories with no matching expiry in BOD are omitted silently.
    """
    from src.instruments.lookup import parse_expiry as _parse

    seen: set[str] = set()
    for inst in lookup._instruments:
        if inst.get("segment") != "NSE_FO":
            continue
        if inst.get("instrument_type") not in ("CE", "PE"):
            continue
        if inst.get("underlying_symbol", "").upper() != "NIFTY":
            continue
        exp = _parse(inst.get("expiry"))
        if exp:
            seen.add(exp)

    result: dict[str, str] = {}
    for exp in sorted(seen):
        dte = (date.fromisoformat(exp) - today).days
        if dte < PROXY_MONTHLY_DTE[0]:
            continue
        if dte <= PROXY_MONTHLY_DTE[1] and "monthly" not in result:
            result["monthly"] = exp
        elif PROXY_QUARTERLY_DTE[0] <= dte <= PROXY_QUARTERLY_DTE[1] and "quarterly" not in result:
            result["quarterly"] = exp
        elif PROXY_YEARLY_DTE[0] <= dte <= PROXY_YEARLY_DTE[1] and "yearly" not in result:
            result["yearly"] = exp

    logger.info(
        "Proxy expiry candidates: %s",
        {k: f"{v} DTE={(date.fromisoformat(v) - today).days}" for k, v in result.items()},
    )
    return result

def fetch_live_prices(
    client: UpstoxMarketClient,
    lookup: InstrumentLookup,
    futures_expiry: str,
    today: date,
    cycle: int,
    lot_size: int,
    force_proxy_expiry: str | None = None,
) -> LivePrices:
    """Fetch all prices for a 3-track entry.

    API calls:
      - One get_option_chain_sync per proxy expiry category (up to 3: monthly /
        quarterly / yearly), or just the forced expiry when --expiry is given.
      - One get_ltp_sync for NiftyBees + front-month futures.

    Proxy selection ranks candidates across all expiries: round-100 strikes
    first, then tightest bid-ask spread, then delta proximity to 0.90.
    """
    # 1. Determine proxy expiry candidates
    if force_proxy_expiry:
        proxy_expiries: dict[str, str] = {"override": force_proxy_expiry}
    else:
        proxy_expiries = collect_candidate_expiries(lookup, today)

    if not proxy_expiries:
        raise ValueError(
            "No suitable NIFTY option expiries found in BOD "
            f"(bands: monthly DTE {PROXY_MONTHLY_DTE}, "
            f"quarterly DTE {PROXY_QUARTERLY_DTE}, yearly DTE {PROXY_YEARLY_DTE})."
        )

    # 2. Fetch option chains and collect candidates across all expiries
    nifty_spot: Decimal | None = None
    all_candidates: list[dict[str, Any]] = []

    for exp_type, exp_date in proxy_expiries.items():
        dte = (date.fromisoformat(exp_date) - today).days
        logger.info(
            "Fetching option chain: type=%-10s expiry=%s DTE=%d",
            exp_type, exp_date, dte,
        )
        try:
            raw_chain = client.get_option_chain_sync(NIFTY_UNDERLYING, exp_date)
        except Exception as exc:
            logger.warning(
                "Chain fetch failed for %s (%s, DTE=%d): %s — skipping",
                exp_type, exp_date, dte, exc,
            )
            continue

        if not raw_chain:
            logger.warning("Empty chain for %s (%s) — skipping", exp_type, exp_date)
            continue

        logger.debug("  %s chain: %d strike entries", exp_type, len(raw_chain))

        # Spot from the first successful chain
        if nifty_spot is None:
            spot_raw = _safe_float((raw_chain[0]).get("underlying_spot_price"))
            if spot_raw > 0:
                nifty_spot = Decimal(str(round(spot_raw, 2)))
                logger.info("Nifty spot from %s chain: ₹%s", exp_type, nifty_spot)

        cands = filter_proxy_candidates(raw_chain)
        for c in cands:
            c["expiry"] = exp_date
            c["dte"] = dte
            c["expiry_type"] = exp_type
        all_candidates.extend(cands)
        logger.info("  → %d candidates from %s (%s, DTE=%d)", len(cands), exp_type, exp_date, dte)

    if nifty_spot is None or nifty_spot <= 0:
        raise ValueError(
            "underlying_spot_price missing in all option chain responses. "
            "Run with LOG_LEVEL=DEBUG to inspect."
        )

    if not all_candidates:
        raise ValueError(
            f"No CE candidates in delta [{PROXY_DELTA_MIN}, {PROXY_DELTA_MAX}] "
            f"across expiries {list(proxy_expiries.values())}. "
            "Market may be closed or delta band too narrow."
        )

    # Proxy selection across all expiries
    candidates = all_candidates
    proxy_row = auto_select_proxy(candidates)
    proxy_price = compute_proxy_entry_price(proxy_row)

    # 3. Futures key from BOD (always front-month, independent of proxy expiry)
    logger.info("Looking up NIFTY futures key from BOD (expiry=%s)", futures_expiry)
    fut_list = lookup.search_futures("NIFTY", expiry=futures_expiry, max_results=5)
    logger.debug(
        "search_futures('NIFTY', expiry=%s) → %d results", futures_expiry, len(fut_list)
    )

    if not fut_list:
        raise ValueError(
            f"No NIFTY futures in BOD for expiry={futures_expiry}. "
            "BOD file may not include this expiry. Verify data/instruments/NSE.json.gz."
        )
    futures_key = fut_list[0].get("instrument_key", "")
    if not futures_key:
        raise ValueError(
            f"Futures instrument found but instrument_key is empty: {fut_list[0]}. "
            "BOD file may be malformed."
        )
    logger.info("Futures key: %s", futures_key)

    # 3. LTPs
    ltp_keys = [NIFTYBEES_KEY, futures_key]
    logger.info("Fetching LTP for %s", ltp_keys)
    try:
        ltps = client.get_ltp_sync(ltp_keys)
    except Exception as exc:
        logger.error("LTP fetch failed for keys=%s — %s", ltp_keys, exc, exc_info=True)
        raise
    logger.debug("LTP response: %s", ltps)

    niftybees_raw = ltps.get(NIFTYBEES_KEY, 0.0)
    futures_raw = ltps.get(futures_key, 0.0)

    if niftybees_raw <= 0:
        raise ValueError(
            f"NiftyBees LTP is {niftybees_raw!r} (zero or missing). "
            f"Full LTP response: {ltps}. Market may be closed or key may be wrong."
        )
    if futures_raw <= 0:
        raise ValueError(
            f"Futures LTP is {futures_raw!r} (zero or missing). "
            f"Full LTP response: {ltps}. Market may be closed or futures key may be stale."
        )

    niftybees_ltp = Decimal(str(round(niftybees_raw, 2)))
    futures_price = Decimal(str(round(futures_raw, 2)))
    logger.info("NiftyBees LTP: ₹%s | Futures LTP: ₹%s", niftybees_ltp, futures_price)

    # Compute qty
    niftybees_qty = math.floor((lot_size * float(nifty_spot)) / float(niftybees_ltp))
    logger.info(
        "NiftyBees qty: floor(%d × %.2f / %.2f) = %d",
        lot_size, float(nifty_spot), float(niftybees_ltp), niftybees_qty,
    )
    if niftybees_qty <= 0:
        raise ValueError(
            f"NiftyBees qty computed as {niftybees_qty}. "
            f"nifty_spot={nifty_spot}, niftybees_ltp={niftybees_ltp}. "
            "Check that both prices are reasonable."
        )

    return LivePrices(
        entry_date=today, expiry=proxy_row["expiry"],
        nifty_spot=nifty_spot, lot_size=lot_size, cycle=cycle,
        niftybees_ltp=niftybees_ltp, niftybees_qty=niftybees_qty,
        futures_key=futures_key, futures_price=futures_price,
        proxy_strike=proxy_row["strike"],
        proxy_price=proxy_price,
        proxy_actual_delta=Decimal(str(round(proxy_row["delta"], 4))),
        proxy_instrument_key=proxy_row["instrument_key"],
        proxy_oi=proxy_row["oi"],
        proxy_bid=proxy_row["bid"],
        proxy_ask=proxy_row["ask"],
        proxy_candidates=candidates,
    )


# ── Gates ────────────────────────────────────────────────────────────────────

def compute_gate_results(p: LivePrices) -> dict[str, str]:
    """Return OI and spread gate display strings (warn-only, not blocking)."""
    spread = p.proxy_ask - p.proxy_bid
    oi_ok = p.proxy_oi >= PROXY_OI_MIN
    spread_ok = spread <= PROXY_SPREAD_MAX

    if not oi_ok:
        logger.warning(
            "Proxy OI gate WARN: OI=%d < minimum %d. "
            "Liquidity may be thin — verify the order book before confirming.",
            p.proxy_oi, PROXY_OI_MIN,
        )
    if not spread_ok:
        logger.warning(
            "Proxy spread gate WARN: spread=₹%.2f > maximum ₹%.2f. "
            "Wide spread increases slippage cost — verify before confirming.",
            spread, PROXY_SPREAD_MAX,
        )

    return {
        "oi": f"{'✅ PASS' if oi_ok else '⚠️  WARN'}  OI={p.proxy_oi:,} (min {PROXY_OI_MIN:,})",
        "spread": f"{'✅ PASS' if spread_ok else '⚠️  WARN'}  spread=₹{spread:.2f} (max ₹{PROXY_SPREAD_MAX:.2f})",
    }


# ── Build trades ─────────────────────────────────────────────────────────────

def build_trades(p: LivePrices) -> list[PaperTrade]:
    """Build the three base-leg PaperTrade objects from live prices."""
    nee = p.nifty_spot * Decimal(str(p.lot_size))
    tag = f"Cycle {p.cycle}."
    surplus = nee - SPAN_MARGIN_ESTIMATE

    spot = PaperTrade(
        strategy_name="paper_nifty_spot",
        leg_role="base_etf",
        instrument_key=NIFTYBEES_KEY,
        trade_date=p.entry_date,
        action=TradeAction.BUY,
        quantity=p.niftybees_qty,
        price=p.niftybees_ltp,
        notes=(
            f"Spot base: NEE qty={p.niftybees_qty}. "
            f"Nifty spot={p.nifty_spot}, lot_size={p.lot_size}. {tag}"
        ),
    )
    notional_fut = p.futures_price * Decimal(str(p.lot_size))
    futures = PaperTrade(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        instrument_key=p.futures_key,
        trade_date=p.entry_date,
        action=TradeAction.BUY,
        quantity=p.lot_size,
        price=p.futures_price,
        notes=(
            f"Futures base: 1 lot. Notional=₹{notional_fut:,.0f}. "
            f"SPAN ~₹1.5L. Surplus notional=₹{surplus:,.0f}. {tag}"
        ),
    )
    proxy = PaperTrade(
        strategy_name="paper_nifty_proxy",
        leg_role="base_ditm_call",
        instrument_key=p.proxy_instrument_key,
        trade_date=p.entry_date,
        action=TradeAction.BUY,
        quantity=p.lot_size,
        price=p.proxy_price,
        notes=(
            f"Proxy base: Deep ITM CE delta={p.proxy_actual_delta}, "
            f"strike={p.proxy_strike:.0f}, expiry={p.expiry}. "
            f"Target delta 0.90. {tag}"
        ),
    )
    logger.debug("Built %d PaperTrade objects", 3)
    return [spot, futures, proxy]


# ── Preview output ────────────────────────────────────────────────────────────

def print_preview(p: LivePrices, gates: dict[str, str], confirmed: bool) -> None:
    """Print the formatted confirmation / recorded table."""
    nee = p.nifty_spot * Decimal(str(p.lot_size))
    mode = "RECORDED TO DB" if confirmed else "PREVIEW — not yet written to DB"
    W = 72

    print(f"\n{'═' * W}")
    print(f"  3-Track Entry | {p.entry_date} | Cycle {p.cycle} | {mode}")
    print(f"  Nifty Spot: ₹{p.nifty_spot:,.2f}  |  NEE: ₹{nee:,.0f}  (lot_size={p.lot_size})")
    print(f"  Proxy expiry: {p.expiry}")
    print(f"{'═' * W}")
    print(f"  {'Track':<22} {'Leg':<18} {'Qty':>6} {'Price':>10} {'Notional':>14}")
    print(f"  {'─' * 70}")

    rows = [
        ("A  Spot (NiftyBees)", "base_etf",
         p.niftybees_qty, p.niftybees_ltp, p.niftybees_ltp * p.niftybees_qty),
        ("B  Futures", "base_futures",
         p.lot_size, p.futures_price, p.futures_price * p.lot_size),
        (f"C  Proxy δ={p.proxy_actual_delta}", "base_ditm_call",
         p.lot_size, p.proxy_price, p.proxy_price * p.lot_size),
    ]
    for track, leg, qty, price, notional in rows:
        print(f"  {track:<22} {leg:<18} {qty:>6} {float(price):>10.2f} ₹{float(notional):>12,.0f}")

    # Ranked proxy candidate table (top 10)
    print(f"{'═' * W}")
    total = len(p.proxy_candidates)
    print(f"  Proxy candidates — delta {PROXY_DELTA_MIN}–{PROXY_DELTA_MAX} "
          f"(showing top 10 of {total}, ranked: round-100 first, spread↑ OI↓)")
    print(f"  {'Rk':>3}  {'Expiry':<12}  {'Strike':>7}  {'Type':>4}  {'Delta':>6}  "
          f"{'OI':>9}  {'Bid':>8}  {'Ask':>8}  {'Sprd':>6}  {'R':>2}")
    print(f"  {'─' * 76}")
    for c in p.proxy_candidates[:10]:
        c_spread = c["ask"] - c["bid"]
        is_round = int(c["strike"]) % 100 == 0
        is_selected = c["strike"] == p.proxy_strike and c.get("expiry") == p.expiry
        marker = " ◀" if is_selected else ""
        round_tag = "✓" if is_round else ""
        opt_type = c.get("option_type", "CE")
        print(
            f"  {c['rank']:>3}  {c.get('expiry', p.expiry):<12}  {c['strike']:>7.0f}  "
            f"{opt_type:>4}  {c['delta']:>6.4f}  {c['oi']:>9,}  "
            f"{c['bid']:>8.2f}  {c['ask']:>8.2f}  ₹{c_spread:>5.2f}  {round_tag:>2}{marker}"
        )
    spread = p.proxy_ask - p.proxy_bid
    print(f"{'─' * W}")
    print(f"  Selected  expiry={p.expiry}  key={p.proxy_instrument_key}")
    print(f"  OI gate    : {gates['oi']}")
    print(f"  Spread gate: {gates['spread']}")
    print(f"{'═' * W}")

    if not confirmed:
        print("  ➜  Re-run with --confirm to write all three legs to DB.\n")
    else:
        print("  ✅  All three base legs recorded.\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    """CLI entry point."""
    # Logging setup: respect LOG_LEVEL env var
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    import argparse
    parser = argparse.ArgumentParser(
        description=(
            "3-Track Nifty Long Comparison — live auto entry.\n"
            "Fetches all prices from Upstox, auto-selects the best proxy strike,\n"
            "prints a confirmation table, then records on --confirm.\n\n"
            "YAML-based offline entry (--config) is RESERVED but not yet implemented.\n"
            "When implemented, configs will live in config/paper/ (NOT data/paper/)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--confirm", action="store_true",
        help="Write all three base legs to DB. Default: preview only.",
    )
    parser.add_argument(
        "--expiry", type=str, default=None, metavar="YYYY-MM-DD",
        help="Pin proxy search to this single expiry. Futures always uses front-month.",
    )
    parser.add_argument(
        "--cycle", type=int, default=1,
        help="Cycle number tag for the notes field (default: 1).",
    )
    parser.add_argument(
        "--bod-path", type=Path, default=DEFAULT_BOD,
        help=f"BOD instruments JSON path (default: {DEFAULT_BOD})",
    )
    parser.add_argument(
        "--db-path", type=Path, default=DEFAULT_DB,
        help=f"SQLite DB path (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--config", type=Path, default=None, metavar="CONFIG",
        help=(
            "YAML config file path — NOT YET IMPLEMENTED. "
            "Raises NotImplementedError. Config files must live in config/paper/."
        ),
    )
    args = parser.parse_args()

    if args.config is not None:
        raise NotImplementedError(
            "--config (YAML-based offline entry) is not yet implemented. "
            "Use the live-fetch mode (no --config flag). "
            "When implemented, configs must live in config/paper/, NOT data/paper/."
        )

    today = date.today()
    logger.info("3-Track entry starting (today=%s, cycle=%d)", today, args.cycle)

    # Build client
    try:
        client = UpstoxMarketClient()
        logger.info("UpstoxMarketClient initialised")
    except ValueError as exc:
        logger.error("Failed to initialise Upstox client: %s", exc)
        logger.error("Ensure UPSTOX_ANALYTICS_TOKEN is set in your .env file.")
        sys.exit(1)

    # Load BOD
    logger.info("Loading BOD instruments from %s", args.bod_path)
    try:
        lookup = InstrumentLookup.from_file(args.bod_path)
        logger.info("BOD loaded: %s", args.bod_path)
    except Exception as exc:
        logger.error("Failed to load BOD file %s: %s", args.bod_path, exc, exc_info=True)
        sys.exit(1)

    # Futures expiry — always front-month (from BOD futures)
    try:
        futures_expiry = derive_expiry(lookup, today)
    except ValueError as exc:
        logger.error("Futures expiry derivation failed: %s", exc)
        sys.exit(1)

    # Proxy expiry override — if given, restricts proxy search to that single expiry
    force_proxy_expiry: str | None = None
    if args.expiry:
        try:
            date.fromisoformat(args.expiry)
        except ValueError:
            logger.error("--expiry must be YYYY-MM-DD, got: %r", args.expiry)
            sys.exit(1)
        force_proxy_expiry = args.expiry
        logger.info("Proxy expiry forced to: %s (monthly/quarterly/yearly scan disabled)", force_proxy_expiry)

    # Fetch all live prices (proxy searched across monthly + quarterly + yearly unless forced)
    try:
        prices = fetch_live_prices(
            client, lookup, futures_expiry, today, args.cycle, LOT_SIZE,
            force_proxy_expiry=force_proxy_expiry,
        )
    except Exception as exc:
        logger.error("fetch_live_prices failed: %s", exc, exc_info=True)
        sys.exit(1)

    gates = compute_gate_results(prices)

    # Write to DB if --confirm
    if args.confirm:
        trades = build_trades(prices)
        store = PaperStore(args.db_path)
        for trade in trades:
            store.record_trade(trade)
            logger.info(
                "Recorded: strategy=%s leg=%s qty=%d price=%s",
                trade.strategy_name, trade.leg_role, trade.quantity, trade.price,
            )
        logger.info("All 3 base legs written to %s", args.db_path)

    print_preview(prices, gates, confirmed=args.confirm)


if __name__ == "__main__":
    main()
