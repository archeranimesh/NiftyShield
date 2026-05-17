#!/usr/bin/env python3
"""Live-fetch overlay entry for the 3-Track Nifty Long Comparison framework.

Auto-selects the best expiry (quarterly → yearly → monthly preference) and
the best OTM strike (highest OI within the tightest ₹2 spread bucket), prints
a confirmation table, and records overlay legs on --yes or --dry-run.

Overlay types:
    pp      — Protective Put  (BUY PE)       applied to all three tracks
    cc      — Covered Call    (SELL CE)       spot + proxy only; futures BLOCKED
    collar  — Collar          (BUY PE + SELL CE)  all three tracks

Usage:
    # Dry-run preview — no DB write:
    python -m scripts.paper_3track_overlay --overlay pp --date 2026-05-07 --dry-run

    # Confirm and write:
    python -m scripts.paper_3track_overlay --overlay collar --date 2026-05-07 --yes

    # Restrict to specific tracks:
    python -m scripts.paper_3track_overlay --overlay pp --tracks futures proxy --date 2026-05-07 --yes

    # Force-write even if an existing open overlay with a different expiry is found:
    python -m scripts.paper_3track_overlay --overlay pp --date 2026-05-07 --yes --force

Cron / automation:
    --yes skips the interactive confirmation prompt (blocked-combo checks still run).

Diagnostics:
    LOG_LEVEL=DEBUG python -m scripts.paper_3track_overlay ...
"""

from __future__ import annotations

import argparse
import logging
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
from src.instruments.lookup import InstrumentLookup, parse_expiry as _pe
from src.models.portfolio import TradeAction
from src.paper.constants import (
    CC_OTM_MAX,
    CC_OTM_MIN,
    CC_TARGET_OTM,
    DEFAULT_BOD_PATH,
    DEFAULT_DB_PATH,
    LOT_SIZE,
    NIFTY_UNDERLYING,
    OVERLAY_ROLL_DTE,
    PP_OTM_MAX,
    PP_OTM_MIN,
    PP_TARGET_OTM,
    SPREAD_PCT_MAX,
)
from src.paper.models import PaperTrade
from src.paper.store import PaperStore
from src.paper._utils import safe_float
from src.paper._display import BASE_LABELS, OVERLAY_LABELS

# ── Constants ────────────────────────────────────────────────────────────────

ALL_TRACKS = ["paper_nifty_spot", "paper_nifty_futures", "paper_nifty_proxy"]

# Futures track is permanently blocked from standalone covered calls
_CC_BLOCKED_TRACKS = {"paper_nifty_futures"}

logger = logging.getLogger(__name__)


# ── Overlay candidate row ────────────────────────────────────────────────────

@dataclass
class OverlayRow:
    """One selected overlay leg ready to display and record."""
    strategy: str
    leg_role: str
    option_type: str     # "PE" or "CE"
    action: TradeAction
    strike: float
    instrument_key: str
    price: Decimal       # mid price at fetch time
    spread_pct: float | None
    oi: int
    expiry: str
    expiry_label: str    # "quarterly", "yearly", "monthly", "fallback"
    dte: int


# ── Pure helpers ─────────────────────────────────────────────────────────────

def _safe(val: Any, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _otm_pct(strike: float, spot: float, option_type: str) -> float:
    """Return the OTM fraction for a strike relative to spot.

    PE: (spot - strike) / spot   (positive when strike < spot)
    CE: (strike - spot) / spot   (positive when strike > spot)
    """
    if option_type == "PE":
        return (spot - strike) / spot
    return (strike - spot) / spot


def _rank_overlay_key(r: dict, target_otm: float) -> tuple:
    """5-tuple ranking key for overlay candidates (ascending — lower wins).

    1. is_non_round  — multiples of 100 preferred over 50-increment strikes
    2. spread_bucket — tighter ₹2 spread tier wins
    3. -oi           — highest OI wins within the same spread tier
    4. spread        — exact spread tiebreaker inside a bucket
    5. otm_dist      — proximity to target OTM — final tiebreaker only
    """
    bid = safe_float(r.get("bid"))
    ask = safe_float(r.get("ask"))
    spread = ask - bid if (bid > 0 and ask > 0) else 9_999.0
    is_non_round = int(safe_float(r.get("strike"))) % 100 != 0
    spread_bucket = int(spread / 2)
    otm_dist = abs(safe_float(r.get("otm_pct")) - target_otm)
    return (is_non_round, spread_bucket, -int(safe_float(r.get("oi"))), spread, otm_dist)


def _extract_chain_candidates(
    chain_data: list[dict],
    option_type: str,    # "PE" or "CE"
    spot: float,
    otm_min: float,
    otm_max: float,
    expiry: str,
    expiry_label: str,
) -> list[dict]:
    """Extract and annotate candidates from raw chain data within the OTM band."""
    raw_key = "put_options" if option_type == "PE" else "call_options"
    rows: list[dict] = []

    for entry in chain_data:
        strike = _safe(entry.get("strike_price"))
        opt = entry.get(raw_key) or {}
        key = opt.get("instrument_key", "")
        if not key:
            continue

        otm = _otm_pct(strike, spot, option_type)
        if not (otm_min <= otm <= otm_max):
            continue

        md = opt.get("market_data") or {}
        g  = opt.get("option_greeks") or {}
        bid = _safe(md.get("bid_price"))
        ask = _safe(md.get("ask_price"))
        ltp = _safe(md.get("ltp"))
        mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else ltp
        oi  = int(_safe(md.get("oi")))
        spread_pct = (
            round((ask - bid) / mid * 100, 2)
            if mid > 0 and bid > 0 and ask > 0
            else None
        )

        rows.append({
            "strike": strike,
            "instrument_key": key,
            "option_type": option_type,
            "bid": bid, "ask": ask, "ltp": ltp, "mid": mid,
            "oi": oi,
            "otm_pct": otm,
            "spread_pct": spread_pct,
            "delta": _safe(g.get("delta")),
            "expiry": expiry,
            "expiry_label": expiry_label,
        })

    logger.debug(
        "Chain candidates (%s, %s): %d in OTM %.0f%%–%.0f%% band",
        option_type, expiry, len(rows), otm_min * 100, otm_max * 100,
    )
    return rows


def _select_best_candidate(
    candidates: list[dict],
    target_otm: float,
    option_type: str,
    index: int = 0,
) -> dict:
    """Pick the Nth-ranked overlay candidate using _rank_overlay_key.

    Args:
        candidates: Pool of filtered candidates for this option_type.
        target_otm: Target OTM fraction used as final tiebreaker in ranking.
        option_type: "PE" or "CE".
        index: 0-based rank index to select (default 0 = top-ranked).
               Clamped to len(candidates)-1 if out of range.
    """
    if not candidates:
        raise ValueError(
            f"No {option_type} candidates found in OTM band after filtering all expiries."
        )
    candidates.sort(key=lambda r: _rank_overlay_key(r, target_otm))
    idx = min(index, len(candidates) - 1)
    if idx != index:
        logger.warning(
            "--index %d out of range for %s (%d candidates) — using index %d",
            index + 1, option_type, len(candidates), idx + 1,
        )
    best = candidates[idx]
    logger.info(
        "Selected %s rank=%d: strike=%.0f expiry=%s spread_pct=%s OI=%d",
        option_type, idx + 1, best["strike"], best["expiry"], best["spread_pct"], best["oi"],
    )
    return best


# ── Expiry selection ─────────────────────────────────────────────────────────

def _collect_expiry_candidates(
    lookup: InstrumentLookup, today: date
) -> list[tuple[str, str]]:
    """Return (label, expiry_date) pairs in preference order: quarterly → yearly → monthly.

    Labels and DTE bands mirror find_overlay_strikes.py:
      quarterly: DTE 46–200
      yearly:    DTE 201–420
      monthly:   DTE 15–45 (always included as final fallback)
    """
    seen: set[str] = set()
    for inst in lookup._instruments:
        if inst.get("segment") != "NSE_FO":
            continue
        if inst.get("instrument_type") not in ("CE", "PE"):
            continue
        if inst.get("underlying_symbol", "").upper() != "NIFTY":
            continue
        exp = _pe(inst.get("expiry"))
        if exp:
            seen.add(exp)

    quarterly = yearly = monthly = None
    for exp in sorted(seen):
        dte = (date.fromisoformat(exp) - today).days
        if dte < 15:
            continue
        if 46 <= dte <= 200 and quarterly is None:
            quarterly = exp
        elif 201 <= dte <= 420 and yearly is None:
            yearly = exp
        elif 15 <= dte <= 45 and monthly is None:
            monthly = exp

    result: list[tuple[str, str]] = []
    if quarterly:
        result.append(("quarterly", quarterly))
    if yearly:
        result.append(("yearly", yearly))
    if monthly:
        result.append(("monthly", monthly))

    logger.info(
        "Overlay expiry candidates: %s",
        {label: f"{exp} DTE={(date.fromisoformat(exp) - today).days}" for label, exp in result},
    )
    return result


async def _fetch_candidates_for_expiries(
    client: UpstoxMarketClient,
    expiry_candidates: list[tuple[str, str]],
    option_type: str,
    spot: float,
    otm_min: float,
    otm_max: float,
) -> tuple[list[dict], list[dict]]:
    """Fetch chains for all candidate expiries; return (gate_passers, all_candidates).

    Gate passers are rows whose spread_pct <= SPREAD_PCT_MAX — these are preferred.
    All candidates (including gate failures) are returned as fallback pool.
    """
    gate_passers: list[dict] = []
    all_candidates: list[dict] = []

    for label, expiry in expiry_candidates:
        dte = (date.fromisoformat(expiry) - date.today()).days
        logger.info("Fetching chain: %s (%s, DTE=%d)", expiry, label, dte)
        try:
            chain = await client.get_option_chain(NIFTY_UNDERLYING, expiry)
        # Intentional: isolate per-expiry chain fetch failures.
        except Exception as exc:
            logger.warning("Chain fetch failed for %s (%s): %s — skipping", label, expiry, exc)
            continue

        rows = _extract_chain_candidates(chain, option_type, spot, otm_min, otm_max, expiry, label)
        all_candidates.extend(rows)

        passers = [r for r in rows if r["spread_pct"] is not None and r["spread_pct"] <= SPREAD_PCT_MAX]
        gate_passers.extend(passers)
        logger.info("  → %d rows, %d pass spread gate (≤%.1f%%)", len(rows), len(passers), SPREAD_PCT_MAX)

    return gate_passers, all_candidates


# ── Safety check ─────────────────────────────────────────────────────────────

def _check_existing_overlay(
    store: PaperStore,
    strategy: str,
    leg_role: str,
) -> PaperTrade | None:
    """Return any existing open overlay trade for this (strategy, leg_role), or None.

    An 'open' overlay has a net_qty > 0 (more BUYs than SELLs, or net SELL for CC).
    Returns the most recent BUY trade as a proxy for the live open position.
    """
    trades = store.get_trades(strategy, leg_role)
    if not trades:
        return None
    # Compute net qty to decide if position is open.
    # last_trade is updated on every iteration — not only on BUY — so that
    # open SELL positions (CC, overlay_collar_call) are correctly returned.
    net = 0
    last_trade: PaperTrade | None = None
    for t in trades:
        if t.action == TradeAction.BUY:
            net += t.quantity
        else:
            net -= t.quantity
        last_trade = t  # track regardless of direction
    return last_trade if net != 0 else None


# ── Trade building ───────────────────────────────────────────────────────────

_LEG_ROLES: dict[str, list[str]] = {
    "pp":     ["overlay_pp"],
    "cc":     ["overlay_cc"],
    "collar": ["overlay_collar_put", "overlay_collar_call"],
}

_OPTION_TYPE_FOR_ROLE: dict[str, str] = {
    "overlay_pp":           "PE",
    "overlay_cc":           "CE",
    "overlay_collar_put":   "PE",
    "overlay_collar_call":  "CE",
}

_ACTION_FOR_ROLE: dict[str, TradeAction] = {
    "overlay_pp":           TradeAction.BUY,
    "overlay_cc":           TradeAction.SELL,
    "overlay_collar_put":   TradeAction.BUY,
    "overlay_collar_call":  TradeAction.SELL,
}


def _build_trade(
    strategy: str,
    leg_role: str,
    best: dict,
    entry_date: date,
    lot_size: int,
) -> PaperTrade:
    """Construct a PaperTrade from a selected overlay candidate row."""
    action = _ACTION_FOR_ROLE[leg_role]
    price = Decimal(str(round(best["mid"], 2)))
    notes = (
        f"Overlay {leg_role}: strike={best['strike']:.0f}, "
        f"expiry={best['expiry']} ({best['expiry_label']}, DTE={best.get('dte', '?')}), "
        f"spread_pct={best['spread_pct']}%, OI={best['oi']:,}. "
        f"{'Fallback expiry.' if best['expiry_label'] == 'fallback' else ''}"
    ).strip()
    return PaperTrade(
        strategy_name=strategy,
        leg_role=leg_role,
        instrument_key=best["instrument_key"],
        trade_date=entry_date,
        action=action,
        quantity=lot_size,
        price=price,
        notes=notes,
    )


# ── Confirmation display ─────────────────────────────────────────────────────

def _print_candidate_table(
    leg_role: str,
    option_type: str,
    pool: list[dict],
    best_key: str,
    target_otm: float,
    otm_min: float,
    otm_max: float,
) -> None:
    """Print ranked overlay candidate table (top 10), mirroring entry script output."""
    # Sort by rank key so ranks are stable regardless of fetch order
    ranked = sorted(pool, key=lambda r: _rank_overlay_key(r, target_otm))
    total = len(ranked)
    W = 96
    print(
        f"\n  Overlay candidates ({option_type}, {leg_role}) — "
        f"OTM {otm_min*100:.0f}%–{otm_max*100:.0f}%  "
        f"(showing top 10 of {total}, ranked: round-100 first, spread↑ OI↓)"
    )
    print(
        f"  {'Rk':>3}  {'Expiry':<12}  {'Label':<12}  {'Strike':>7}  {'OTM%':>5}  "
        f"{'OI':>9}  {'Bid':>8}  {'Ask':>8}  {'Sprd%':>6}  {'G':>1}"
    )
    print(f"  {'─' * (W - 2)}")
    for i, c in enumerate(ranked[:10], start=1):
        spread_pct = c.get("spread_pct")
        gate = "✓" if spread_pct is not None and spread_pct <= SPREAD_PCT_MAX else "✗"
        is_selected = c["instrument_key"] == best_key
        marker = " ◀" if is_selected else ""
        sprd_str = f"{spread_pct:.1f}%" if spread_pct is not None else "  N/A"
        print(
            f"  {i:>3}  {c['expiry']:<12}  {c['expiry_label']:<12}  {c['strike']:>7.0f}  "
            f"{c['otm_pct']*100:>4.1f}%  {c['oi']:>9,}  "
            f"{c['bid']:>8.2f}  {c['ask']:>8.2f}  {sprd_str:>6}  {gate}{marker}"
        )


def _print_confirmation_table(
    overlay_type: str,
    rows: list[OverlayRow],
    entry_date: date,
    expiry: str,
    dte: int,
    mode: str,
) -> None:
    W = 104
    print(f"\n{'═' * W}")
    print(f"  Overlay: {overlay_type.upper()}  |  Date: {entry_date}  |  {mode}")
    print(f"  Expiry selected: {expiry} ({rows[0].expiry_label if rows else '?'}, DTE={dte})")
    print(f"{'═' * W}")
    print(
        f"  {'Track':<28} {'Strategy':<26} {'Leg':<22} "
        f"{'Type':>4}  {'Str':>7} {'Act':>4} {'Qty':>4} {'Price':>8}  {'Sprd%':>6}  {'OI':>9}"
    )
    print(f"  {'─' * (W - 2)}")

    for r in rows:
        label = BASE_LABELS.get(r.strategy, r.strategy)
        leg_display = OVERLAY_LABELS.get(r.leg_role, r.leg_role)
        sprd = f"{r.spread_pct:.1f}%" if r.spread_pct is not None else "  N/A"
        print(
            f"  {label:<28} {r.strategy:<26} {leg_display:<22} "
            f"{r.option_type:>4}  {r.strike:>7.0f} {r.action.value:>4} {LOT_SIZE:>4} "
            f"₹{float(r.price):>7.2f}  {sprd:>6}  {r.oi:>9,}"
        )
    print(f"{'═' * W}")


# ── Main orchestration ───────────────────────────────────────────────────────

async def _run(args: argparse.Namespace) -> None:
    """Core async logic — separated for testability."""
    overlay_type: str = args.overlay
    entry_date: date = args.date or date.today()

    # Resolve effective track list BEFORE any guard
    effective_tracks: list[str] = args.tracks if args.tracks else list(ALL_TRACKS)

    # Hard block: futures + standalone CC — auto-exclude and warn, do not abort
    if overlay_type == "cc":
        blocked = [t for t in effective_tracks if t in _CC_BLOCKED_TRACKS]
        if blocked:
            for t in blocked:
                print(
                    f"  ⚠  BLOCKED: {t} + standalone overlay_cc skipped "
                    "(synthetic short put risk — MISSION.md Principle I)."
                )
            effective_tracks = [t for t in effective_tracks if t not in _CC_BLOCKED_TRACKS]
        if not effective_tracks:
            print(
                "ERROR: No eligible tracks remain after applying CC block. "
                "All requested tracks are blocked for standalone covered call.",
                file=sys.stderr,
            )
            sys.exit(1)

    # Build client
    try:
        client = UpstoxMarketClient()
    except ValueError as exc:
        logger.error("Failed to initialise Upstox client: %s", exc)
        logger.error("Ensure UPSTOX_ANALYTICS_TOKEN is set in .env")
        sys.exit(1)

    # Load BOD for expiry candidates
    try:
        lookup = InstrumentLookup.from_file(args.bod_path)
    # Intentional: catch all BOD load/parsing errors.
    except Exception as exc:
        logger.error("Failed to load BOD %s: %s", args.bod_path, exc)
        sys.exit(1)

    expiry_candidates = _collect_expiry_candidates(lookup, entry_date)
    if not expiry_candidates:
        logger.error(
            "No NIFTY option expiries found in BOD (DTE 15–420). "
            "Is %s current?", args.bod_path
        )
        sys.exit(1)

    # Fetch spot from first successful chain (needed for OTM filtering)
    spot: float = 0.0
    try:
        first_chain = await client.get_option_chain(NIFTY_UNDERLYING, expiry_candidates[0][1])
        if first_chain:
            spot = _safe(first_chain[0].get("underlying_spot_price"))
    # Intentional: catch all live price fetch failures.
    except Exception as exc:
        logger.error("Could not fetch spot price: %s", exc)
        sys.exit(1)
    if spot <= 0:
        logger.error("Spot price is zero — chain may be empty. Abort.")
        sys.exit(1)
    logger.info("Nifty spot: %.2f", spot)

    # Per leg-role: fetch candidates and select best
    store = PaperStore(args.db_path)
    logger.info("DB path (resolved): %s", args.db_path.resolve())
    overlay_rows: list[OverlayRow] = []

    for leg_role in _LEG_ROLES[overlay_type]:
        option_type = _OPTION_TYPE_FOR_ROLE[leg_role]
        otm_min = PP_OTM_MIN if option_type == "PE" else CC_OTM_MIN
        otm_max = PP_OTM_MAX if option_type == "PE" else CC_OTM_MAX
        target_otm = PP_TARGET_OTM if option_type == "PE" else CC_TARGET_OTM

        gate_passers, all_candidates = await _fetch_candidates_for_expiries(
            client, expiry_candidates, option_type, spot, otm_min, otm_max
        )

        pool = gate_passers if gate_passers else all_candidates
        if not pool:
            logger.error(
                "No %s candidates found in OTM %.0f%%–%.0f%% band across all expiries.",
                option_type, otm_min * 100, otm_max * 100,
            )
            sys.exit(1)
        if not gate_passers:
            logger.warning(
                "No expiry passed the %.1f%% spread gate for %s — using monthly fallback.",
                SPREAD_PCT_MAX, option_type,
            )
            # Mark all as fallback
            for r in pool:
                r["expiry_label"] = "fallback"

        pick_idx = (args.index - 1) if getattr(args, "index", 1) > 1 else 0
        best = _select_best_candidate(pool, target_otm, option_type, index=pick_idx)
        best_expiry = best["expiry"]
        best_dte = (date.fromisoformat(best_expiry) - entry_date).days
        best["dte"] = best_dte

        _print_candidate_table(
            leg_role=leg_role,
            option_type=option_type,
            pool=pool,
            best_key=best["instrument_key"],
            target_otm=target_otm,
            otm_min=otm_min,
            otm_max=otm_max,
        )

        for strategy in effective_tracks:
            # Safety check: existing open overlay with a DIFFERENT expiry
            existing = _check_existing_overlay(store, strategy, leg_role)
            if existing is not None:
                existing_expiry = _pe(existing.instrument_key) or ""
                if existing_expiry and existing_expiry != best_expiry:
                    if not args.force:
                        print(
                            f"ERROR: {strategy} already has an open {leg_role} "
                            f"(expiry={existing_expiry}). "
                            f"Selected expiry={best_expiry} differs. "
                            "Pass --force to override.",
                            file=sys.stderr,
                        )
                        sys.exit(1)
                    logger.warning(
                        "--force: overriding existing %s %s (expiry=%s) with %s",
                        strategy, leg_role, existing_expiry, best_expiry,
                    )

            overlay_rows.append(OverlayRow(
                strategy=strategy,
                leg_role=leg_role,
                option_type=option_type,
                action=_ACTION_FOR_ROLE[leg_role],
                strike=best["strike"],
                instrument_key=best["instrument_key"],
                price=Decimal(str(round(best["mid"], 2))),
                spread_pct=best["spread_pct"],
                oi=best["oi"],
                expiry=best_expiry,
                expiry_label=best["expiry_label"],
                dte=best_dte,
            ))

    if not overlay_rows:
        print("ERROR: No trades to record — all tracks produced no candidates.", file=sys.stderr)
        sys.exit(1)

    # Representative expiry for header (first row — all same for PP/CC; collar may differ)
    header_expiry = overlay_rows[0].expiry
    header_dte    = overlay_rows[0].dte
    mode = "DRY RUN — nothing written to DB" if args.dry_run else "PREVIEW"

    _print_confirmation_table(overlay_type, overlay_rows, entry_date, header_expiry, header_dte, mode)

    # Proceed?
    if not args.dry_run:
        if not args.yes:
            answer = input("\nProceed? [y/N]: ").strip().lower()
            if answer != "y":
                print("Aborted — nothing written.")
                return

        # Collar atomicity: build all PaperTrade objects first, then write.
        # If writing the Nth trade fails, all previously written trades are deleted.
        trades_to_write: list[PaperTrade] = []
        for r in overlay_rows:
            trades_to_write.append(_build_trade(r.strategy, r.leg_role, {
                "mid": float(r.price), "instrument_key": r.instrument_key,
                "strike": r.strike, "expiry": r.expiry, "expiry_label": r.expiry_label,
                "dte": r.dte, "spread_pct": r.spread_pct, "oi": r.oi,
            }, entry_date, LOT_SIZE))

        try:
            inserted_trades, skipped_trades = store.record_trades(trades_to_write)
            for trade in inserted_trades:
                logger.info(
                    "Recorded: %s %s %s qty=%d price=%s",
                    trade.strategy_name, trade.leg_role, trade.action.value,
                    trade.quantity, trade.price,
                )
            for trade in skipped_trades:
                logger.warning(
                    "SKIPPED (duplicate): %s %s %s — already exists for %s",
                    trade.strategy_name, trade.leg_role, trade.action.value,
                    trade.trade_date,
                )
        # Intentional: top-level catch for trade recording failure.
        except Exception as exc:
            logger.error("Write failed for batch: %s — rolled back automatically by DB", exc)
            print(f"ERROR: Write failed — all trades rolled back. Reason: {exc}", file=sys.stderr)
            sys.exit(1)

        if skipped_trades:
            print(
                f"\n  ⚠  {len(skipped_trades)} trade(s) skipped — already exist in DB for this "
                f"(strategy, leg_role, date, action). Use --force to override expiry conflicts."
            )
        status = f"RECORDED TO DB — {len(inserted_trades)} new, {len(skipped_trades)} skipped"
        _print_confirmation_table(
            overlay_type, overlay_rows, entry_date, header_expiry, header_dte, status
        )


def main() -> None:
    """CLI entry point."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description=(
            "Live-fetch overlay entry for the 3-Track framework.\n"
            "Auto-selects expiry (quarterly preferred) and OTM strike (highest OI).\n"
            "Prints confirmation table; records on --yes."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--overlay", required=True, choices=["pp", "cc", "collar"],
        help="Overlay type: pp (protective put), cc (covered call), collar (both).",
    )
    parser.add_argument(
        "--date", default=None, type=date.fromisoformat, metavar="YYYY-MM-DD",
        help="Entry date (default: today).",
    )
    parser.add_argument(
        "--tracks", nargs="+",
        choices=["spot", "futures", "proxy"],
        metavar="TRACK",
        help=(
            "Tracks to apply overlay to (default: all three). "
            "Values: spot → paper_nifty_spot, futures → paper_nifty_futures, "
            "proxy → paper_nifty_proxy."
        ),
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="Skip interactive confirmation prompt (blocked-combo checks still run).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print proposed trades; do not write to DB.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Override existing open overlay with a different expiry.",
    )
    parser.add_argument(
        "--index", type=int, default=1, metavar="N",
        help=(
            "Select the Nth-ranked candidate from the dry-run table (default: 1). "
            "For collar, the same rank N is applied to both PE and CE legs independently."
        ),
    )
    parser.add_argument(
        "--db-path", type=Path, default=DEFAULT_DB_PATH,
        help=f"SQLite DB path (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--bod-path", type=Path, default=DEFAULT_BOD_PATH,
        help=f"BOD instruments JSON path (default: {DEFAULT_BOD_PATH})",
    )
    args = parser.parse_args()

    # Map short track names → strategy names
    _TRACK_MAP = {
        "spot":    "paper_nifty_spot",
        "futures": "paper_nifty_futures",
        "proxy":   "paper_nifty_proxy",
    }
    if args.tracks:
        args.tracks = [_TRACK_MAP[t] for t in args.tracks]

    import asyncio
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
