"""CLI: live Nifty option chain → filter by |delta| range → strike/IV/key table.

Optionally prints ready-to-paste ``record_paper_trade.py`` commands when
``--dry-run`` is given alongside ``--strategy`` / ``--leg`` / ``--qty``.

Works on the raw Upstox V2 option chain response so that ``instrument_key``
(not preserved by the parsed ``OptionChain`` model) is available in the output.

Usage — table only:
    python scripts/find_strike_by_delta.py \\
        --expiry 2026-05-29 \\
        --delta-min 0.20 --delta-max 0.35

Filter PE only with dry-run commands:
    python scripts/find_strike_by_delta.py \\
        --expiry 2026-05-29 \\
        --delta-min 0.20 --delta-max 0.35 \\
        --option-type PE \\
        --strategy paper_csp_nifty_v1 --leg short_put \\
        --qty 75 --action SELL --dry-run

Underlying defaults to ``NSE_INDEX|Nifty 50``; override with ``--underlying``.
Delta range is always expressed as absolute (positive) values — sign is inferred
from the option side.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.client.upstox_market import UpstoxMarketClient

UNDERLYING_DEFAULT = "NSE_INDEX|Nifty 50"
DEFAULT_LOT_SIZE = 75  # current Nifty lot size


# ── Data helpers ──────────────────────────────────────────────────────────────


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Coerce *val* to float; return *default* on any failure.

    Args:
        val: Raw value (float, str, None, …).
        default: Fallback when coercion fails.

    Returns:
        Coerced float, or *default*.
    """
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _sides_for(option_type: str) -> list[str]:
    """Return the list of option sides implied by *option_type*.

    Args:
        option_type: ``"CE"``, ``"PE"``, or ``"BOTH"``.

    Returns:
        List containing ``"CE"``, ``"PE"``, or both.
    """
    if option_type == "CE":
        return ["CE"]
    if option_type == "PE":
        return ["PE"]
    return ["CE", "PE"]


def _infer_leg(option_type: str, action: str) -> str:
    """Infer a sensible leg-role label from side and action.

    Args:
        option_type: ``"CE"`` or ``"PE"``.
        action: ``"BUY"`` or ``"SELL"``.

    Returns:
        Label such as ``"short_put"``; falls back to ``"leg"`` for unknown combos.
    """
    mapping = {
        ("CE", "SELL"): "short_call",
        ("CE", "BUY"): "long_call",
        ("PE", "SELL"): "short_put",
        ("PE", "BUY"): "long_put",
    }
    return mapping.get((option_type, action), "leg")


# ── Core logic (importable, no I/O) ──────────────────────────────────────────


def filter_strikes_by_delta(
    chain_data: list[dict[str, Any]],
    option_type: str,
    delta_min: float,
    delta_max: float,
) -> list[dict[str, Any]]:
    """Filter raw Upstox option chain entries by absolute delta range.

    Operates on the raw list returned by
    ``UpstoxMarketClient.get_option_chain_sync`` so that ``instrument_key``
    (absent from the parsed ``OptionChain`` model) is preserved per row.

    Args:
        chain_data: Raw strike list from the Upstox V2 option chain endpoint.
        option_type: ``"CE"``, ``"PE"``, or ``"BOTH"``.
        delta_min: Lower bound for |delta| (inclusive), e.g. ``0.20``.
        delta_max: Upper bound for |delta| (inclusive), e.g. ``0.35``.

    Returns:
        List of flat row dicts sorted by |delta| descending.  Each row has keys:
        ``side``, ``strike``, ``delta``, ``iv``, ``ltp``, ``mid``, ``bid``,
        ``ask``, ``oi``, ``instrument_key``.
    """
    sides = _sides_for(option_type)
    rows: list[dict[str, Any]] = []

    for entry in chain_data:
        strike = _safe_float(entry.get("strike_price"))
        for side in sides:
            raw_key = "call_options" if side == "CE" else "put_options"
            opt = entry.get(raw_key) or {}
            greeks = opt.get("option_greeks") or {}
            mktdata = opt.get("market_data") or {}
            instrument_key = opt.get("instrument_key", "")

            delta = _safe_float(greeks.get("delta"))
            if not (delta_min <= abs(delta) <= delta_max):
                continue
            if not instrument_key:
                continue

            ltp = _safe_float(mktdata.get("ltp"))
            bid = _safe_float(mktdata.get("bid_price"))
            ask = _safe_float(mktdata.get("ask_price"))
            mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else ltp

            rows.append({
                "side": side,
                "strike": strike,
                "delta": delta,
                "iv": _safe_float(greeks.get("iv")),
                "ltp": ltp,
                "mid": mid,
                "bid": bid,
                "ask": ask,
                "oi": int(_safe_float(mktdata.get("oi"))),
                "instrument_key": instrument_key,
            })

    rows.sort(key=lambda r: abs(r["delta"]), reverse=True)
    return rows


def format_table(
    rows: list[dict[str, Any]],
    underlying_spot: float = 0.0,
    expiry: str = "",
) -> str:
    """Format matching strike rows as a fixed-width table string.

    Args:
        rows: Output of :func:`filter_strikes_by_delta`.
        underlying_spot: Spot price for the header line (optional).
        expiry: Expiry date string for the header line (optional).

    Returns:
        Multi-line string ready for ``print()``.
    """
    if not rows:
        return "  No strikes found in the requested delta range."

    header_parts: list[str] = []
    if expiry:
        header_parts.append(f"expiry: {expiry}")
    if underlying_spot:
        header_parts.append(f"spot: ₹{underlying_spot:,.2f}")
    header_line = (
        "  Nifty 50  " + "  |  ".join(header_parts) if header_parts else ""
    )

    col_hdr = (
        f"  {'SIDE':<5} {'STRIKE':>8}  {'DELTA':>7}  {'IV%':>6}  "
        f"{'LTP':>8}  {'MID':>8}  {'BID':>8}  {'ASK':>8}  {'OI':>8}  KEY"
    )
    sep = "  " + "─" * (len(col_hdr) - 2)

    lines: list[str] = []
    if header_line:
        lines.append(header_line)
    lines.append(col_hdr)
    lines.append(sep)

    for r in rows:
        sign = "+" if r["delta"] >= 0 else ""
        lines.append(
            f"  {r['side']:<5} {r['strike']:>8.0f}  "
            f"{sign}{r['delta']:>6.4f}  {r['iv']:>6.2f}  "
            f"{r['ltp']:>8.2f}  {r['mid']:>8.2f}  "
            f"{r['bid']:>8.2f}  {r['ask']:>8.2f}  "
            f"{r['oi']:>8d}  {r['instrument_key']}"
        )

    return "\n".join(lines)


def build_record_command(
    row: dict[str, Any],
    *,
    strategy: str,
    leg: str,
    action: str,
    qty: int,
    trade_date: str,
) -> str:
    """Build a ready-to-paste ``record_paper_trade.py`` CLI command for one row.

    Uses mid-price (bid+ask)/2 when both are non-zero; falls back to ltp.
    Price is rounded to 2 decimal places.

    Args:
        row: A row dict from :func:`filter_strikes_by_delta`.
        strategy: ``--strategy`` value (must start with ``paper_``).
        leg: ``--leg`` value, e.g. ``short_put``.
        action: ``BUY`` or ``SELL``.
        qty: Quantity in units.
        trade_date: ISO date string, e.g. ``2026-05-03``.

    Returns:
        Multi-line shell command string with a comment header showing
        side, strike, delta, and IV.
    """
    price = round(row["mid"] if row["mid"] > 0 else row["ltp"], 2)
    delta_str = f"{row['delta']:+.4f}"
    iv_str = f"{row['iv']:.2f}%"

    return (
        f"# {row['side']} {row['strike']:.0f} | delta={delta_str} | iv={iv_str}\n"
        f"python scripts/record_paper_trade.py \\\n"
        f"    --strategy {strategy} \\\n"
        f"    --leg {leg} \\\n"
        f"    --key \"{row['instrument_key']}\" \\\n"
        f"    --date {trade_date} \\\n"
        f"    --action {action} \\\n"
        f"    --qty {qty} \\\n"
        f"    --price {price}"
    )


# ── CLI ───────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Fetch a live Nifty option chain and filter strikes by |delta| range. "
            "Prints a strike/IV/key table and, with --dry-run, ready-to-paste "
            "record_paper_trade.py commands."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--expiry",
        required=True,
        metavar="YYYY-MM-DD",
        help="Option expiry date, e.g. 2026-05-29.",
    )
    p.add_argument(
        "--delta-min",
        type=float,
        default=0.20,
        metavar="FLOAT",
        help="Lower bound for |delta| (inclusive). Default: 0.20.",
    )
    p.add_argument(
        "--delta-max",
        type=float,
        default=0.35,
        metavar="FLOAT",
        help="Upper bound for |delta| (inclusive). Default: 0.35.",
    )
    p.add_argument(
        "--option-type",
        choices=["CE", "PE", "BOTH"],
        default="BOTH",
        help="Filter by option side. Default: BOTH.",
    )
    p.add_argument(
        "--underlying",
        default=UNDERLYING_DEFAULT,
        help=f'Underlying instrument key. Default: "{UNDERLYING_DEFAULT}".',
    )

    dry_grp = p.add_argument_group(
        "dry-run options",
        "Provide these to emit ready-to-paste record_paper_trade.py commands.",
    )
    dry_grp.add_argument(
        "--strategy",
        default="paper_csp_nifty_v1",
        help=(
            'Paper strategy name (must start with "paper_"). '
            "Default: paper_csp_nifty_v1."
        ),
    )
    dry_grp.add_argument(
        "--leg",
        default=None,
        help=(
            'Leg role label, e.g. "short_put". '
            "Auto-inferred from --option-type + --action when omitted."
        ),
    )
    dry_grp.add_argument(
        "--qty",
        type=int,
        default=DEFAULT_LOT_SIZE,
        help=f"Quantity in units. Default: {DEFAULT_LOT_SIZE} (1 Nifty lot).",
    )
    dry_grp.add_argument(
        "--action",
        choices=["BUY", "SELL"],
        default="SELL",
        help="Trade action. Default: SELL.",
    )
    dry_grp.add_argument(
        "--date",
        dest="trade_date",
        default=str(date.today()),
        metavar="YYYY-MM-DD",
        help="Trade execution date. Default: today.",
    )
    dry_grp.add_argument(
        "--dry-run",
        action="store_true",
        help="Print ready-to-paste record_paper_trade.py commands below the table.",
    )
    return p.parse_args()


def main() -> None:
    """CLI entry point: fetch chain, filter, print table + optional dry-run commands."""
    args = _parse_args()

    if args.delta_min < 0 or args.delta_max < 0:
        print(
            "ERROR: --delta-min and --delta-max must be non-negative.",
            file=sys.stderr,
        )
        sys.exit(1)
    if args.delta_min > args.delta_max:
        print(
            "ERROR: --delta-min must be ≤ --delta-max.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not args.strategy.startswith("paper_"):
        print(
            f"ERROR: --strategy must start with 'paper_', got: {args.strategy!r}",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        date.fromisoformat(args.expiry)
    except ValueError:
        print(
            f"ERROR: --expiry must be YYYY-MM-DD, got: {args.expiry!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        client = UpstoxMarketClient()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        f"Fetching option chain: {args.underlying}  expiry={args.expiry} …",
        flush=True,
    )
    try:
        raw_data = client.get_option_chain_sync(args.underlying, args.expiry)
    except Exception as exc:
        print(f"ERROR: option chain fetch failed — {exc}", file=sys.stderr)
        sys.exit(1)

    if not raw_data:
        print(
            "ERROR: API returned empty data — check underlying key and expiry date.",
            file=sys.stderr,
        )
        sys.exit(1)

    underlying_spot = _safe_float(
        (raw_data[0] if raw_data else {}).get("underlying_spot_price")
    )

    rows = filter_strikes_by_delta(
        raw_data,
        option_type=args.option_type,
        delta_min=args.delta_min,
        delta_max=args.delta_max,
    )

    print()
    print(format_table(rows, underlying_spot=underlying_spot, expiry=args.expiry))

    if not rows or not args.dry_run:
        sys.exit(0)

    # Infer leg per-row when BOTH sides are shown and no explicit --leg given
    fixed_leg = args.leg or (
        _infer_leg(args.option_type, args.action)
        if args.option_type != "BOTH"
        else None
    )

    print()
    banner = f"─── Dry-run ({args.action} · {args.strategy}) "
    print(banner + "─" * max(0, 72 - len(banner)))
    for row in rows:
        row_leg = fixed_leg or _infer_leg(row["side"], args.action)
        print()
        print(
            build_record_command(
                row,
                strategy=args.strategy,
                leg=row_leg,
                action=args.action,
                qty=args.qty,
                trade_date=args.trade_date,
            )
        )
    print()


if __name__ == "__main__":
    main()
