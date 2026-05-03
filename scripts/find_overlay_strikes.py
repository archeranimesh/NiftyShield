#!/usr/bin/env python3
"""Find and evaluate overlay strikes across candidate expiries for the 3-Track framework.

Fetches the live Nifty option chain for each candidate expiry, evaluates the <=3%
spread gate (quarterly -> yearly -> monthly preference order), and writes a
pre-filled overlay_entry.yaml ready for paper_3track_overlay_entry.py.

Usage:
    # Protective Put — quarterly preferred
    python scripts/find_overlay_strikes.py \\
        --overlay-type pp \\
        --nifty-spot 24000 \\
        --monthly 2026-05-29 --quarterly 2026-06-26 --yearly 2026-12-25

    # Covered Call
    python scripts/find_overlay_strikes.py \\
        --overlay-type cc \\
        --nifty-spot 24000 \\
        --monthly 2026-05-29 --quarterly 2026-06-26

    # Collar (both legs — uses max(put_spread, call_spread) for gate)
    python scripts/find_overlay_strikes.py \\
        --overlay-type collar \\
        --nifty-spot 24000 \\
        --monthly 2026-05-29 --quarterly 2026-06-26 --yearly 2026-12-25

Output is written to data/paper/overlay_entry.yaml (override with --output).
Review the prices before recording — they are mid prices at the time of this query.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.client.upstox_market import UpstoxMarketClient

UNDERLYING = "NSE_INDEX|Nifty 50"
SPREAD_GATE = 3.0          # percent
STRIKE_STEP = 50           # Nifty strikes move in 50-point increments
DEFAULT_PUT_OTM_PCT = 9.0  # 9% OTM for protective put
DEFAULT_CALL_OTM_PCT = 4.0 # 4% OTM for covered call
DEFAULT_OUTPUT = Path("data/paper/overlay_entry.yaml")


# ── Pure helpers (importable, no I/O) ─────────────────────────────────────────

def compute_target_strike(spot: float, otm_pct: float, side: str) -> float:
    """Compute the nearest STRIKE_STEP-multiple OTM strike.

    Args:
        spot: Nifty spot price.
        otm_pct: Percentage OTM (positive), e.g. 9.0 for 9% OTM.
        side: 'PE' (put below spot) or 'CE' (call above spot).

    Returns:
        Nearest 50-point multiple OTM strike.
    """
    if side == "PE":
        raw = spot * (1 - otm_pct / 100)
    else:
        raw = spot * (1 + otm_pct / 100)
    return round(raw / STRIKE_STEP) * STRIKE_STEP


def _safe(val: Any, default: float = 0.0) -> float:
    """Coerce val to float, return default on failure."""
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def find_chain_entry(
    chain_data: list[dict[str, Any]], side: str, target_strike: float
) -> dict[str, Any] | None:
    """Find the chain entry whose strike is closest to target_strike for the given side.

    Args:
        chain_data: Raw Upstox option chain list.
        side: 'CE' or 'PE'.
        target_strike: Desired strike (OTM target).

    Returns:
        Flat dict with strike, instrument_key, bid, ask, mid, ltp, oi, iv, delta.
        None if no matching entry with a valid instrument_key is found.
    """
    raw_key = "call_options" if side == "CE" else "put_options"
    best: dict[str, Any] | None = None
    best_diff = float("inf")

    for entry in chain_data:
        strike = _safe(entry.get("strike_price"))
        opt = entry.get(raw_key) or {}
        inst_key = opt.get("instrument_key", "")
        if not inst_key:
            continue
        diff = abs(strike - target_strike)
        if diff < best_diff:
            best_diff = diff
            md = opt.get("market_data") or {}
            g = opt.get("option_greeks") or {}
            bid = _safe(md.get("bid_price"))
            ask = _safe(md.get("ask_price"))
            ltp = _safe(md.get("ltp"))
            mid = (bid + ask) / 2 if bid > 0 and ask > 0 else ltp
            best = {
                "strike": strike,
                "instrument_key": inst_key,
                "bid": bid,
                "ask": ask,
                "ltp": ltp,
                "mid": mid,
                "oi": int(_safe(md.get("oi"))),
                "iv": _safe(g.get("iv")),
                "delta": _safe(g.get("delta")),
                "spread_pct": (
                    round((ask - bid) / mid * 100, 2)
                    if mid > 0 and bid > 0 and ask > 0
                    else None
                ),
            }
    return best


@dataclass
class ExpiryEval:
    """Spread evaluation for one expiry."""

    expiry: str
    dte: int
    put: dict[str, Any] | None    # find_chain_entry result
    call: dict[str, Any] | None   # find_chain_entry result (None for PP-only)
    gate_spread: float | None     # max(put_spread, call_spread) or single spread
    passes_gate: bool


def evaluate_expiry(
    chain_data: list[dict[str, Any]],
    expiry: str,
    overlay_type: str,
    target_put_strike: float,
    target_call_strike: float,
    entry_date: date,
) -> ExpiryEval:
    """Evaluate one expiry for an overlay type.

    Args:
        chain_data: Raw chain for this expiry.
        expiry: Expiry date string YYYY-MM-DD.
        overlay_type: 'pp', 'cc', or 'collar'.
        target_put_strike: Computed OTM put strike target.
        target_call_strike: Computed OTM call strike target.
        entry_date: Entry date (for DTE calculation).

    Returns:
        ExpiryEval with spread info and gate result.
    """
    exp_date = date.fromisoformat(expiry)
    dte = (exp_date - entry_date).days

    put_entry = (
        find_chain_entry(chain_data, "PE", target_put_strike)
        if overlay_type in ("pp", "collar")
        else None
    )
    call_entry = (
        find_chain_entry(chain_data, "CE", target_call_strike)
        if overlay_type in ("cc", "collar")
        else None
    )

    spreads = [
        e["spread_pct"]
        for e in [put_entry, call_entry]
        if e is not None and e["spread_pct"] is not None
    ]
    gate_spread = max(spreads) if spreads else None
    passes = gate_spread is not None and gate_spread <= SPREAD_GATE

    return ExpiryEval(
        expiry=expiry,
        dte=dte,
        put=put_entry,
        call=call_entry,
        gate_spread=gate_spread,
        passes_gate=passes,
    )


# ── Table formatting ──────────────────────────────────────────────────────────

def format_eval_table(
    evals: list[ExpiryEval],
    overlay_type: str,
    chosen_expiry: str,
    spot: float,
) -> str:
    """Format expiry evaluation results as a fixed-width table.

    Args:
        evals: List of ExpiryEval objects (one per candidate expiry).
        overlay_type: 'pp', 'cc', or 'collar'.
        chosen_expiry: The expiry selected by the gate.
        spot: Nifty spot for the header.

    Returns:
        Multi-line string ready for print().
    """
    lines = [
        f"  Nifty 50  spot: ₹{spot:,.2f}  |  overlay: {overlay_type.upper()}  "
        f"|  gate: spread ≤ {SPREAD_GATE}%",
        "",
    ]

    has_put = overlay_type in ("pp", "collar")
    has_call = overlay_type in ("cc", "collar")

    # Header
    hdr = f"  {'EXPIRY':<12} {'DTE':>4}  {'GATE':>6}"
    if has_put:
        hdr += f"  {'PUT_STR':>8}  {'P_SPRD%':>7}  {'P_MID':>8}  {'P_OI':>7}"
    if has_call:
        hdr += f"  {'CALL_STR':>8}  {'C_SPRD%':>7}  {'C_MID':>8}  {'C_OI':>7}"
    hdr += "  CHOSEN"
    lines.append(hdr)
    lines.append("  " + "─" * (len(hdr) - 2))

    for ev in evals:
        gate_str = f"{ev.gate_spread:.1f}%" if ev.gate_spread is not None else "  N/A "
        row = f"  {ev.expiry:<12} {ev.dte:>4}  {gate_str:>6}"
        if has_put:
            if ev.put:
                sp = f"{ev.put['spread_pct']:.1f}%" if ev.put["spread_pct"] is not None else "  N/A"
                row += f"  {ev.put['strike']:>8.0f}  {sp:>7}  {ev.put['mid']:>8.2f}  {ev.put['oi']:>7,}"
            else:
                row += "  " + " " * 42
        if has_call:
            if ev.call:
                sp = f"{ev.call['spread_pct']:.1f}%" if ev.call["spread_pct"] is not None else "  N/A"
                row += f"  {ev.call['strike']:>8.0f}  {sp:>7}  {ev.call['mid']:>8.2f}  {ev.call['oi']:>7,}"
            else:
                row += "  " + " " * 42
        chosen_marker = "  ✓" if ev.expiry == chosen_expiry else ""
        lines.append(row + chosen_marker)

    return "\n".join(lines)


# ── YAML writer ───────────────────────────────────────────────────────────────

def write_overlay_yaml(
    path: Path,
    chosen: ExpiryEval,
    overlay_type: str,
    entry_date: date,
    cycle: int,
    lot_size: int,
    expiry_label: str,
) -> None:
    """Write a pre-filled overlay_entry.yaml for paper_3track_overlay_entry.py.

    Args:
        path: Output file path.
        chosen: The ExpiryEval that passed the gate (or fallback).
        overlay_type: 'pp', 'cc', or 'collar'.
        entry_date: Overlay entry date.
        cycle: Cycle number (must match 3track_entry.yaml).
        lot_size: Nifty lot size.
        expiry_label: 'monthly', 'quarterly', or 'yearly'.
    """
    data: dict[str, Any] = {
        "overlay": {
            "type": overlay_type,
            "date": entry_date.isoformat(),
            "cycle": cycle,
            "lot_size": lot_size,
            "expiry": chosen.expiry,
            "expiry_type": expiry_label,
            "dte_at_entry": chosen.dte,
        }
    }

    if chosen.put:
        data["overlay"].update({
            "put_strike": chosen.put["strike"],
            "put_instrument_key": chosen.put["instrument_key"],
            "put_price": round(chosen.put["mid"], 2),
            "put_spread_pct": chosen.put["spread_pct"],
            "put_oi": chosen.put["oi"],
        })
    else:
        data["overlay"].update({
            "put_strike": 0, "put_instrument_key": "", "put_price": 0.0,
            "put_spread_pct": None, "put_oi": 0,
        })

    if chosen.call:
        data["overlay"].update({
            "call_strike": chosen.call["strike"],
            "call_instrument_key": chosen.call["instrument_key"],
            "call_price": round(chosen.call["mid"], 2),
            "call_spread_pct": chosen.call["spread_pct"],
            "call_oi": chosen.call["oi"],
        })
    else:
        data["overlay"].update({
            "call_strike": 0, "call_instrument_key": "", "call_price": 0.0,
            "call_spread_pct": None, "call_oi": 0,
        })

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(
            "# Auto-generated by find_overlay_strikes.py\n"
            "# Prices are mid prices at query time — verify before recording.\n"
            "# Run: python scripts/paper_3track_overlay_entry.py --dry-run\n\n"
        )
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    print(f"\n  Written: {path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Find OTM overlay strikes, evaluate spread gate across candidate expiries, "
            "and write overlay_entry.yaml for paper_3track_overlay_entry.py."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--overlay-type",
        choices=["pp", "cc", "collar"],
        required=True,
        help="Overlay type: pp (protective put), cc (covered call), collar (both).",
    )
    p.add_argument(
        "--nifty-spot",
        type=float,
        required=True,
        metavar="PRICE",
        help="Current Nifty 50 spot price (used to compute OTM strikes).",
    )
    p.add_argument(
        "--monthly",
        metavar="YYYY-MM-DD",
        help="Monthly expiry date (fallback).",
    )
    p.add_argument(
        "--quarterly",
        metavar="YYYY-MM-DD",
        help="Quarterly expiry date (first preference).",
    )
    p.add_argument(
        "--yearly",
        metavar="YYYY-MM-DD",
        help="Yearly expiry date (second preference).",
    )
    p.add_argument(
        "--put-otm-pct",
        type=float,
        default=DEFAULT_PUT_OTM_PCT,
        metavar="FLOAT",
        help=f"Put OTM%% (default: {DEFAULT_PUT_OTM_PCT} → ~9%% OTM).",
    )
    p.add_argument(
        "--call-otm-pct",
        type=float,
        default=DEFAULT_CALL_OTM_PCT,
        metavar="FLOAT",
        help=f"Call OTM%% (default: {DEFAULT_CALL_OTM_PCT} → ~4%% OTM).",
    )
    p.add_argument(
        "--cycle",
        type=int,
        default=1,
        help="Cycle number (must match 3track_entry.yaml). Default: 1.",
    )
    p.add_argument(
        "--lot-size",
        type=int,
        default=65,
        help="Nifty lot size (default: 65, effective January 2026).",
    )
    p.add_argument(
        "--date",
        dest="entry_date",
        default=str(date.today()),
        metavar="YYYY-MM-DD",
        help="Entry date. Default: today.",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output YAML path (default: {DEFAULT_OUTPUT}).",
    )
    return p.parse_args()


def main() -> None:
    """CLI entry point."""
    args = _parse_args()

    # Build candidate expiry list in preference order: quarterly → yearly → monthly
    candidates: list[tuple[str, str]] = []  # (label, expiry_date)
    if args.quarterly:
        candidates.append(("quarterly", args.quarterly))
    if args.yearly:
        candidates.append(("yearly", args.yearly))
    if args.monthly:
        candidates.append(("monthly", args.monthly))

    if not candidates:
        print("ERROR: provide at least one of --monthly, --quarterly, --yearly.", file=sys.stderr)
        sys.exit(1)

    entry_date = date.fromisoformat(args.entry_date)
    target_put = compute_target_strike(args.nifty_spot, args.put_otm_pct, "PE")
    target_call = compute_target_strike(args.nifty_spot, args.call_otm_pct, "CE")

    print(f"\nOverlay: {args.overlay_type.upper()}")
    if args.overlay_type in ("pp", "collar"):
        print(f"  Put target:  {args.put_otm_pct}% OTM → strike ~{target_put:.0f}")
    if args.overlay_type in ("cc", "collar"):
        print(f"  Call target: {args.call_otm_pct}% OTM → strike ~{target_call:.0f}")

    try:
        client = UpstoxMarketClient()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    evals: list[ExpiryEval] = []
    spot = args.nifty_spot

    for label, expiry in candidates:
        print(f"\nFetching chain: {UNDERLYING}  expiry={expiry} ({label}) …", flush=True)
        try:
            chain_data = client.get_option_chain_sync(UNDERLYING, expiry)
        except Exception as exc:
            print(f"  WARNING: fetch failed — {exc}")
            # Push a blank eval so the table shows the gap
            evals.append(ExpiryEval(expiry=expiry, dte=0, put=None, call=None,
                                    gate_spread=None, passes_gate=False))
            continue

        if chain_data:
            spot = _safe(chain_data[0].get("underlying_spot_price")) or spot

        ev = evaluate_expiry(
            chain_data, expiry, args.overlay_type,
            target_put, target_call, entry_date
        )
        evals.append(ev)

    # Choose best: first that passes the gate in preference order
    chosen_ev: ExpiryEval | None = next((e for e in evals if e.passes_gate), None)
    chosen_label = "monthly"  # default fallback label

    if chosen_ev is None:
        # Fall back to last candidate (monthly)
        chosen_ev = evals[-1]
        fallback_msg = (
            f"\n  All candidate expiries failed the {SPREAD_GATE}% spread gate. "
            "Falling back to last candidate (monthly)."
        )
        print(fallback_msg)
    else:
        # Find the label for the chosen expiry
        for label, expiry in candidates:
            if expiry == chosen_ev.expiry:
                chosen_label = label
                break

    print()
    print(format_eval_table(evals, args.overlay_type, chosen_ev.expiry, spot))

    write_overlay_yaml(
        path=args.output,
        chosen=chosen_ev,
        overlay_type=args.overlay_type,
        entry_date=entry_date,
        cycle=args.cycle,
        lot_size=args.lot_size,
        expiry_label=chosen_label,
    )

    print(
        f"\n  Next step:\n"
        f"    python scripts/paper_3track_overlay_entry.py --dry-run\n"
        f"    python scripts/paper_3track_overlay_entry.py\n"
    )


if __name__ == "__main__":
    main()
