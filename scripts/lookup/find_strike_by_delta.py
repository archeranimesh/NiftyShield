"""CLI: live Nifty option chain → filter by |delta| range → strike/IV/key table.

Prints ready-to-paste ``scripts.record.record_paper_trade`` commands by default (``--dry-run``
is on by default).  Use ``--no-dry-run`` to suppress the command block and show
the strike table only.

Works on the raw Upstox V2 option chain response so that ``instrument_key``
(not preserved by the parsed ``OptionChain`` model) is available in the output.

Usage — CSP Nifty v1 entry (all defaults apply, one arg needed):
    python -m scripts.lookup.find_strike_by_delta --expiry 2026-05-29

Table only (no command block):
    python -m scripts.lookup.find_strike_by_delta \
        --expiry 2026-05-29 --no-dry-run

Override option side or strategy:
    python -m scripts.lookup.find_strike_by_delta \
        --expiry 2026-05-29 \
        --option-type CE --strategy paper_other_v1 --action SELL

Underlying defaults to ``NSE_INDEX|Nifty 50``; override with ``--underlying``.
Delta range is always expressed as absolute (positive) values — sign is inferred
from the option side.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Any

import structlog

from src.utils.logging import setup_logging

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.client.upstox_market import UpstoxMarketClient
from src.instruments.strike_selector import (
    _apply_liquidity_gate,
    _safe_float,
    filter_strikes_by_delta,
    rank_strikes,
)
from src.paper.constants import LOT_SIZE, STRATEGY_CSP, STRATEGY_PP_OVERLAY

_SCRIPT_NAME = "scripts.lookup.find_strike_by_delta"
logger = structlog.get_logger(_SCRIPT_NAME)


UNDERLYING_DEFAULT = "NSE_INDEX|Nifty 50"
DEFAULT_LOT_SIZE = LOT_SIZE  # single source of truth: src/paper/constants.py

# Fallback sequence of absolute target deltas tried in order (ES12). CSP short-put ladder.
DELTA_CANDIDATES = [0.22, 0.25, 0.20]

# CC short-call ladder (CC1, 3track-consolidation). CONFIRMED — CC2 (docs/plan/
# 3track-consolidation/stories.md, resolved 2026-08-01, see DECISIONS.md) closed the entry
# delta band decision gate at 0.18-0.20, matching the existing values here; OI is the
# liquidity gate (already enforced by rank_strikes()/_apply_liquidity_gate). Round-strike
# preference within this band is CC4's separate, still-open scope, not CC2's.
# Still blocked on EC-5 (docs/plan/paper-exit-codification) landing before CC3 goes
# --no-dry-run.
CC_DELTA_CANDIDATES = [0.18, 0.20, 0.15]

# PP long-put protection ladder (PP1, 3track-consolidation). PROVISIONAL — these values are
# an experimentation/comparison starting point only, not an operator-confirmed entry band.
# PP2 (docs/plan/3track-consolidation/stories.md) is the actual decision gate; do not treat
# this ladder as live-ready until PP2 resolves it, same provisional→confirmed pattern CC1's
# comment followed before CC2 closed it. Ordering favors 0.20 first (deep enough OTM to keep
# the debit cheap) with 0.25/0.15 as fallbacks — deliberately not copied from CSP's or CC's
# ladders: PP is a long-debit purchase, not a short-premium sale. Confirmed (2026-08-03,
# not assumed) that src.instruments.strike_selector.rank_strikes()'s existing spread/OI/
# round-strike ranking stays unchanged for PP — it is already documented side-agnostic
# ("CSP, CC, PP, etc.") and its criteria (tight spread, high OI, round strikes) matter for
# an infrequently-touched protective leg's exit liquidity, not just entry-credit
# optimization; no PP-specific ranking tuple added.
PP_DELTA_CANDIDATES = [0.20, 0.25, 0.15]

# Defaults that mirror scripts.record.record_paper_trade — used to emit minimal commands.
DEFAULT_STRATEGY = STRATEGY_CSP
DEFAULT_ACTION = "SELL"
DEFAULT_LEG = "short_put"


def _reorder_cc_round500_first(
    gated_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None]:
    """Reorder CC's liquidity-gated candidates so round-₹500 strikes rank first (CC4).

    Round-500 strikes (24500, 25000, 25500, …) carry materially deeper OI than
    neighbouring round-100 strikes on the live chain — operator directive
    (docs/plan/3track-consolidation/stories.md CC4). This is a *preference*, not a
    hard filter: any round-500 candidate that already cleared
    :func:`_apply_liquidity_gate` is preferred over round-100 candidates; if none did,
    fall back to the best round-100 candidate (existing gate + rank order, untouched).
    Cushion bar (operator-resolved 2026-08-01): the existing liquidity gate itself —
    no separate OI/spread comparison between the two tiers. Internal ordering within
    each tier is unchanged (delta-proximity via the input's rank order, OI/spread as
    tiebreaker — both already applied by :func:`rank_strikes` before this call).

    CC-only — callers must gate this on ``option_type == "CE"`` themselves; this
    function never touches the shared :func:`rank_strikes`, so CSP/IC/PP paths are
    unaffected regardless of call-site placement.

    Args:
        gated_rows: Output of :func:`_apply_liquidity_gate`, already ranked.

    Returns:
        Tuple of (reordered rows, fallback_reason). ``fallback_reason`` is ``None``
        when at least one round-500 candidate is present (no fallback needed);
        otherwise a human-readable string explaining round-100 was used instead —
        callers should log this so a human reviewing the entry log can see why
        round-500 was skipped.
    """
    round_500 = [r for r in gated_rows if int(r["strike"]) % 500 == 0]
    others = [r for r in gated_rows if int(r["strike"]) % 500 != 0]
    if round_500:
        return round_500 + others, None
    if others:
        return others, "no round-500 strike passed the liquidity gate in this delta window"
    return [], None


def _find_candidates_for_ladder(
    raw_data_by_expiry: dict[str, Any],
    expiries: list[tuple[str, str]],
    option_type: str,
    ladder: list[float],
) -> list[dict[str, Any]]:
    """Find one best liquidity-gated candidate row per ladder rung.

    Unlike ``main()``'s single-selection fallback loop (which stops at the first
    rung with a passing candidate), this collects a candidate for *every* rung that
    has one — Collar1 needs the full set of viable call/put candidates to build the
    cross-product, not a single winner.

    Args:
        raw_data_by_expiry: Raw Upstox chain rows keyed by expiry string.
        expiries: ``(label, expiry)`` tuples already resolved for this run.
        option_type: ``"CE"`` or ``"PE"``.
        ladder: Target |delta| values to search, in order (e.g. ``CC_DELTA_CANDIDATES``).

    Returns:
        List of candidate rows (each the top-ranked, liquidity-gated row for its
        rung), annotated with ``target_delta``. Rungs with no passing candidate are
        omitted, not padded with ``None``.
    """
    candidates: list[dict[str, Any]] = []
    for target in ladder:
        rows: list[dict[str, Any]] = []
        for label, expiry in expiries:
            raw_data = raw_data_by_expiry.get(expiry)
            if not raw_data:
                continue
            delta_min = max(0.0, target - 0.02)
            delta_max = target + 0.02
            r = filter_strikes_by_delta(
                raw_data, option_type=option_type, delta_min=delta_min, delta_max=delta_max
            )
            for row in r:
                row["expiry"] = expiry
                row["expiry_label"] = label
            rows.extend(r)
        if not rows:
            continue
        gated = _apply_liquidity_gate(rank_strikes(rows))
        if gated:
            candidates.append({**gated[0], "target_delta": target})
    return candidates


def compute_net_collar_premium(call_row: dict[str, Any], put_row: dict[str, Any]) -> float:
    """Net premium of a collar combo: short-call credit minus long-put debit.

    Positive means the call funds more than the put costs (net credit); negative
    means the combo is a net debit. Uses mid price ``(bid+ask)/2`` when available,
    falling back to ``ltp`` — same convention as :func:`build_record_command`.

    Args:
        call_row: A candidate row for the short call leg (``overlay_collar_call``).
        put_row: A candidate row for the long put leg (``overlay_collar_put``).

    Returns:
        Net premium rounded to 2 decimal places.
    """
    call_price = call_row["mid"] if call_row.get("mid", 0) > 0 else call_row["ltp"]
    put_price = put_row["mid"] if put_row.get("mid", 0) > 0 else put_row["ltp"]
    return round(call_price - put_price, 2)


def build_collar_cross_product(
    call_candidates: list[dict[str, Any]],
    put_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Cross product of CC-ladder call candidates × PP-ladder put candidates.

    Does not auto-select a "best" combo — Collar1's scope is coordination and
    reporting only; the pick is left to operator/Collar2 judgment.

    Args:
        call_candidates: Output of :func:`_find_candidates_for_ladder` for CE.
        put_candidates: Output of :func:`_find_candidates_for_ladder` for PE.

    Returns:
        List of ``{"call": row, "put": row, "net_premium": float}`` dicts, one per
        pairing. Empty if either side has no candidates.
    """
    return [
        {"call": call, "put": put, "net_premium": compute_net_collar_premium(call, put)}
        for call in call_candidates
        for put in put_candidates
    ]


def format_collar_table(combos: list[dict[str, Any]]) -> str:
    """Format the collar candidate cross-product as a fixed-width table string.

    Args:
        combos: Output of :func:`build_collar_cross_product`.

    Returns:
        Multi-line string ready for ``print()``.
    """
    if not combos:
        return "  No viable collar combos found — check CC1/PP1 ladders and liquidity gate."

    col_hdr = (
        f"  {'CALL STRIKE':>11}  {'CALL Δ':>7}  {'PUT STRIKE':>10}  "
        f"{'PUT Δ':>7}  {'NET PREMIUM':>11}"
    )
    sep = "  " + "─" * (len(col_hdr) - 2)
    lines = [col_hdr, sep]
    for c in combos:
        lines.append(
            f"  {c['call']['strike']:>11.0f}  {c['call']['delta']:>+7.4f}  "
            f"{c['put']['strike']:>10.0f}  {c['put']['delta']:>+7.4f}  "
            f"{c['net_premium']:>11.2f}"
        )
    return "\n".join(lines)


def run_collar_mode(
    raw_data_by_expiry: dict[str, Any],
    expiries: list[tuple[str, str]],
    cc_ladder: list[float] | None = None,
    pp_ladder: list[float] | None = None,
) -> list[dict[str, Any]]:
    """Coordinate CC1's call ladder and PP1's put ladder into collar candidate combos.

    Collar1 (3track-consolidation): hard-depends on both CC1 and PP1 having shipped
    their respective delta ladders — there is no independent "collar ladder" to
    invent; this function's entire job is running both existing ladders and
    reporting the cross-product, never auto-selecting a single combo.

    Args:
        raw_data_by_expiry: Raw Upstox chain rows keyed by expiry string.
        expiries: ``(label, expiry)`` tuples already resolved for this run.
        cc_ladder: Call-side ladder; defaults to :data:`CC_DELTA_CANDIDATES`.
        pp_ladder: Put-side ladder; defaults to :data:`PP_DELTA_CANDIDATES`.

    Returns:
        Output of :func:`build_collar_cross_product`.

    Raises:
        RuntimeError: If either ladder is missing or empty — guards the hard
            CC1/PP1 dependency instead of silently running collar mode with no
            candidates on one side.
    """
    cc_ladder = CC_DELTA_CANDIDATES if cc_ladder is None else cc_ladder
    pp_ladder = PP_DELTA_CANDIDATES if pp_ladder is None else pp_ladder
    if not cc_ladder:
        raise RuntimeError(
            "Collar mode requires CC_DELTA_CANDIDATES (CC1) to be defined and non-empty — "
            "the call ladder must ship before collar mode can run."
        )
    if not pp_ladder:
        raise RuntimeError(
            "Collar mode requires PP_DELTA_CANDIDATES (PP1) to be defined and non-empty — "
            "the put ladder must ship before collar mode can run."
        )
    call_candidates = _find_candidates_for_ladder(raw_data_by_expiry, expiries, "CE", cc_ladder)
    put_candidates = _find_candidates_for_ladder(raw_data_by_expiry, expiries, "PE", pp_ladder)
    return build_collar_cross_product(call_candidates, put_candidates)


def _select_delta_candidates(option_type: str, overlay_type: str | None = None) -> list[float]:
    """Select the fallback delta-candidate ladder for the requested option side.

    CE (covered-call short calls) get their own ladder (CC1) — previously CC silently
    inherited CSP's short-put ladder regardless of `--option-type`, which is a different
    strategy's target deltas. PE keeps the existing CSP ladder unless the caller passes
    the explicit ``--overlay-type pp`` flag (PP1) — PE alone is ambiguous between CSP's
    short-put and PP's long-put, so the PP ladder is opt-in only, never inferred from
    `--option-type PE` by itself (operator-scoped deferral, see PP1 story: the collision
    only matters once CSP and PP are both live simultaneously, not evaluated yet). BOTH
    always keeps the CSP ladder — overlay-type selection is single-side by construction.

    Args:
        option_type: ``"CE"``, ``"PE"``, or ``"BOTH"`` (from ``--option-type``).
        overlay_type: ``"pp"`` to opt into the PP long-put ladder, ``"cc"`` (no-op —
            CE already resolves to ``CC_DELTA_CANDIDATES`` on its own), or ``None``.

    Returns:
        The candidate ladder to try in order.
    """
    if option_type == "CE":
        return CC_DELTA_CANDIDATES
    if option_type == "PE" and overlay_type == "pp":
        return PP_DELTA_CANDIDATES
    return DELTA_CANDIDATES


# ── Data helpers ──────────────────────────────────────────────────────────────


def _resolve_action(strategy: str, action: str | None) -> str:
    """Resolve the effective trade action, enforcing PP's long-only direction.

    Protective put (``STRATEGY_PP_OVERLAY``) is a protection-buying strategy — recording
    a ``SELL`` under it would be a naked short put booked under a name that implies
    protection, not a delta mismatch (PP1a, 3track-consolidation). PP must always
    resolve to ``BUY``, whether by omission (the confirmed 2026-07-28 bug) or by an
    explicit ``--action SELL`` override, which is treated as a hard error rather than
    silently corrected.

    Args:
        strategy: Resolved ``--strategy`` value (after any ``--track`` shortcut).
        action: Raw ``--action`` value, or ``None`` if the flag was omitted.

    Returns:
        ``"BUY"`` or ``"SELL"``.

    Raises:
        ValueError: If ``strategy`` is ``STRATEGY_PP_OVERLAY`` and ``action`` is
            explicitly ``"SELL"``.
    """
    if strategy == STRATEGY_PP_OVERLAY:
        if action == "SELL":
            raise ValueError(
                f"--action SELL is not valid for {STRATEGY_PP_OVERLAY!r} — "
                "protective put is a long-put strategy; use --action BUY (or omit --action)."
            )
        return "BUY"
    return action if action is not None else "SELL"


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


def format_table(
    rows: list[dict[str, Any]],
    underlying_spot: float = 0.0,
    expiry: str = "",
    selected_key: str = "",
) -> str:
    """Format matching strike rows as a fixed-width table string.

    Args:
        rows: Output of :func:`filter_strikes_by_delta`.
        underlying_spot: Spot price for the header line (optional).
        expiry: Expiry date string for the header line (optional).
        selected_key: Instrument key of the selected rank to highlight.

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
    header_line = "  Nifty 50  " + "  |  ".join(header_parts) if header_parts else ""

    col_hdr = (
        f"  {'Rk':>3}  {'EXPIRY':<12} {'LABEL':<10} {'SIDE':<5} {'STRIKE':>8}  "
        f"{'DELTA':>7}  {'IV%':>6}  {'LTP':>8}  {'MID':>8}  {'BID':>8}  "
        f"{'ASK':>8}  {'OI':>8}  KEY"
    )
    sep = "  " + "─" * (len(col_hdr) - 2)

    lines: list[str] = []
    if header_line:
        lines.append(header_line)
    lines.append(col_hdr)
    lines.append(sep)

    for r in rows:
        sign = "+" if r["delta"] >= 0 else ""
        marker = "  ◀" if r["instrument_key"] == selected_key else ""
        lines.append(
            f"  {r.get('rank', ''):>3}  {r.get('expiry', ''):<12} "
            f"{r.get('expiry_label', ''):<10} {r['side']:<5} {r['strike']:>8.0f}  "
            f"{sign}{r['delta']:>6.4f}  {r['iv']:>6.2f}  "
            f"{r['ltp']:>8.2f}  {r['mid']:>8.2f}  "
            f"{r['bid']:>8.2f}  {r['ask']:>8.2f}  "
            f"{r['oi']:>8d}  {r['instrument_key']}{marker}"
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
    """Build a ready-to-paste ``scripts.record.record_paper_trade`` CLI command for one row.

    Uses mid-price (bid+ask)/2 when both are non-zero; falls back to ltp.
    Price is rounded to 2 decimal places.

    Emits a minimal command — args that match ``scripts.record.record_paper_trade`` defaults
    (``DEFAULT_STRATEGY``, ``DEFAULT_ACTION``, ``DEFAULT_LEG``, ``DEFAULT_LOT_SIZE``)
    are omitted; ``--date`` is always omitted (defaults to today).  ``--no-dry-run``
    is always appended so the pasted command writes to the DB.

    Args:
        row: A row dict from :func:`filter_strikes_by_delta`.
        strategy: ``--strategy`` value (must start with ``paper_``).
        leg: ``--leg`` value, e.g. ``short_put``.
        action: ``BUY`` or ``SELL``.
        qty: Quantity in units.
        trade_date: ISO date string (kept for API compat; not emitted in output).

    Returns:
        Multi-line shell command string with a comment header showing
        side, strike, delta, and IV.
    """
    price = round(row["mid"] if row["mid"] > 0 else row["ltp"], 2)
    delta_str = f"{row['delta']:+.4f}"
    iv_str = f"{row['iv']:.2f}%"

    arg_parts: list[str] = []
    if strategy != DEFAULT_STRATEGY:
        arg_parts.append(f"--strategy {strategy}")
    if leg != DEFAULT_LEG:
        arg_parts.append(f"--leg {leg}")
    arg_parts.append(f'--key "{row["instrument_key"]}"')
    if action != DEFAULT_ACTION:
        arg_parts.append(f"--action {action}")
    if qty != DEFAULT_LOT_SIZE:
        arg_parts.append(f"--qty {qty}")
    arg_parts.append(f"--price {price}")
    arg_parts.append("--no-dry-run")

    cmd_body = " \\\n    ".join(arg_parts)
    return (
        f"# {row['side']} {row['strike']:.0f} | delta={delta_str} | iv={iv_str}\n"
        f"python -m scripts.record.record_paper_trade \\\n    {cmd_body}"
    )


# ── CLI ───────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Fetch a live Nifty option chain and filter strikes by |delta| range. "
            "Prints a strike/IV/key table and, with --dry-run, ready-to-paste "
            "scripts.record.record_paper_trade commands."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--expiry",
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="Option expiry date, e.g. 2026-05-29. Auto-selected if omitted.",
    )
    p.add_argument(
        "--bod-path",
        type=Path,
        default=Path("data/instruments/NSE.json.gz"),
        help="BOD instruments JSON path (used for auto-expiry).",
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
        default="PE",
        help="Filter by option side. Default: PE.",
    )
    p.add_argument(
        "--overlay-type",
        choices=["cc", "pp", "collar"],
        default=None,
        help=(
            "Explicit overlay ladder opt-in (PP1). 'pp' selects PP_DELTA_CANDIDATES for "
            "--option-type PE (bare PE without this flag stays on CSP's ladder). 'cc' is "
            "a no-op — --option-type CE already resolves to the CC ladder on its own. "
            "'collar' (Collar1) runs both CC's call ladder and PP's put ladder and reports "
            "the candidate cross-product with net premium — it does not auto-select a "
            "single combo; --option-type is ignored in this mode."
        ),
    )
    p.add_argument(
        "--underlying",
        default=UNDERLYING_DEFAULT,
        help=f'Underlying instrument key. Default: "{UNDERLYING_DEFAULT}".',
    )
    p.add_argument(
        "--index",
        type=int,
        default=1,
        metavar="N",
        help="Select the Nth-ranked candidate (1-based). Default: 1.",
    )

    dry_grp = p.add_argument_group(
        "dry-run options",
        "Provide these to emit ready-to-paste scripts.record.record_paper_trade commands.",
    )
    dry_grp.add_argument(
        "--strategy",
        default=DEFAULT_STRATEGY,
        help=f"Paper strategy namespace (default: {DEFAULT_STRATEGY}).",
    )
    p.add_argument(
        "--track",
        choices=["spot", "futures", "proxy"],
        help="Shortcut to set --strategy to paper_nifty_<track>.",
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
        default=None,
        help=(
            "Trade action. Default: SELL (BUY, non-overridable, for "
            f"{STRATEGY_PP_OVERLAY!r})."
        ),
    )
    dry_grp.add_argument(
        "--date",
        type=date.fromisoformat,
        default=date.today(),
        metavar="YYYY-MM-DD",
        help="Trade execution date. Default: today.",
    )
    dry_grp.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Print ready-to-paste scripts.record.record_paper_trade commands below the table "
            "(default: on). Use --no-dry-run to suppress."
        ),
    )
    return p.parse_args()


def main() -> None:
    """CLI entry point: fetch chain, filter, print table + optional dry-run commands."""
    args = _parse_args()

    if args.track:
        args.strategy = f"paper_nifty_{args.track}"

    try:
        args.action = _resolve_action(args.strategy, args.action)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

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
    if args.expiry:
        # Validated by argparse type=date.fromisoformat
        pass

    try:
        client = UpstoxMarketClient()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    # Resolve expiries
    expiries: list[tuple[str, str]] = []  # (label, expiry_str)
    if args.expiry:
        expiries = [("manual", str(args.expiry))]
    else:
        from src.instruments.lookup import InstrumentLookup

        try:
            lookup = InstrumentLookup.from_file(args.bod_path)
            # Preference for CSP: monthly -> quarterly -> yearly
            # TODO: derive symbol from args.underlying
            expiries = lookup.get_expiry_candidates(underlying="NIFTY", today=date.today())
        except Exception as exc:
            print(f"ERROR: failed to load BOD or resolve expiries — {exc}", file=sys.stderr)
            sys.exit(1)

    if not expiries:
        print("ERROR: no eligible expiries found (DTE 15–420).", file=sys.stderr)
        sys.exit(1)

    all_rows: list[dict[str, Any]] = []
    underlying_spot = 0.0
    raw_data_by_expiry = {}

    for label, expiry in expiries:
        print(
            f"Fetching option chain: {args.underlying}  expiry={expiry} ({label}) …",
            flush=True,
        )
        try:
            raw_data = client.get_option_chain_sync(args.underlying, expiry)
            if not raw_data:
                print(f"  WARNING: API returned empty data for {expiry} — skipping.")
                continue

            raw_data_by_expiry[expiry] = raw_data

            if underlying_spot == 0.0:
                underlying_spot = _safe_float(raw_data[0].get("underlying_spot_price"))

            rows = filter_strikes_by_delta(
                raw_data,
                option_type=args.option_type,
                delta_min=args.delta_min,
                delta_max=args.delta_max,
            )
            # Annotate rows with expiry and label
            for r in rows:
                r["expiry"] = expiry
                r["expiry_label"] = label

            all_rows.extend(rows)

        except Exception as exc:
            print(f"  WARNING: fetch failed for {expiry} — {exc} — skipping.")
            continue

    if args.overlay_type == "collar":
        try:
            combos = run_collar_mode(raw_data_by_expiry, expiries)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)
        print()
        print(format_collar_table(combos))
        print()
        print(
            "Collar mode reports the candidate cross-product only — no combo is "
            "auto-selected. Pick a pairing per operator/Collar2 judgment."
        )
        sys.exit(0)

    if not all_rows:
        print(
            "ERROR: no strikes found across all candidate expiries (empty data).", file=sys.stderr
        )
        sys.exit(1)

    # ── Candidate Selection Flow with Liquidity Gate (ES12) ──
    delta_candidates = _select_delta_candidates(args.option_type, args.overlay_type)
    selected_row = None
    requested_delta = delta_candidates[0]
    fallback_used = False

    for candidate in delta_candidates:
        candidate_rows = []
        for label, expiry in expiries:
            raw_data = raw_data_by_expiry.get(expiry)
            if not raw_data:
                continue
            delta_min = max(0.0, candidate - 0.02)
            delta_max = candidate + 0.02
            rows = filter_strikes_by_delta(
                raw_data,
                option_type=args.option_type,
                delta_min=delta_min,
                delta_max=delta_max,
            )
            for r in rows:
                r["expiry"] = expiry
                r["expiry_label"] = label
            candidate_rows.extend(rows)

        if not candidate_rows:
            continue

        ranked_candidate = rank_strikes(candidate_rows)
        filtered_candidate = _apply_liquidity_gate(ranked_candidate)

        round500_fallback_reason: str | None = None
        if args.option_type == "CE" and filtered_candidate:
            filtered_candidate, round500_fallback_reason = _reorder_cc_round500_first(
                filtered_candidate
            )
            if round500_fallback_reason:
                logger.warning(
                    "cc_round500_fallback",
                    reason=round500_fallback_reason,
                    candidate_delta=candidate,
                )
                print(
                    f"WARNING: CC round-500 fallback — {round500_fallback_reason}; "
                    "using best round-100 candidate instead.",
                    file=sys.stderr,
                )

        if filtered_candidate:
            pick_idx = min(args.index - 1, len(filtered_candidate) - 1)
            if args.index - 1 > len(filtered_candidate) - 1:
                print(
                    f"WARNING: --index {args.index} out of range; clamping to rank {len(filtered_candidate)}.",
                    file=sys.stderr,
                )
            selected_row = filtered_candidate[pick_idx]
            if candidate != requested_delta:
                fallback_used = True
            break

    if not selected_row:
        print("ERROR: GATE FAIL — no candidate strikes passed the liquidity gate.", file=sys.stderr)
        sys.exit(1)

    if fallback_used:
        print(
            f"WARNING: Fallback used. Selected delta {abs(selected_row['delta']):.4f} "
            f"vs requested delta {requested_delta:.4f}",
            file=sys.stderr,
        )

    ranked_all = rank_strikes(all_rows)

    print()
    selected_key = selected_row["instrument_key"]
    print(
        format_table(
            ranked_all,
            underlying_spot=underlying_spot,
            expiry=args.expiry or "Multiple (auto)",
            selected_key=selected_key,
        )
    )

    if not args.dry_run:
        sys.exit(0)

    # Infer leg per-row when BOTH sides are shown and no explicit --leg given
    fixed_leg = args.leg or (
        _infer_leg(args.option_type, args.action) if args.option_type != "BOTH" else None
    )

    print()
    banner = f"─── Rank {args.index} selected ({args.action} · {args.strategy}) "
    print(banner + "─" * max(0, 72 - len(banner)))

    row_leg = fixed_leg or _infer_leg(selected_row["side"], args.action)
    print()
    print(
        build_record_command(
            selected_row,
            strategy=args.strategy,
            leg=row_leg,
            action=args.action,
            qty=args.qty,
            trade_date=str(args.date),
        )
    )
    print()


if __name__ == "__main__":
    setup_logging()
    main()
