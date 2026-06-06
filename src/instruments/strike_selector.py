"""Strike selector logic extracted from find_strike_by_delta CLI.

Contains helper functions and core logic for filtering, gating, and ranking option strikes
based on delta and liquidity parameters.
"""

from __future__ import annotations

from typing import Any


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

            rows.append(
                {
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
                }
            )

    rows.sort(key=lambda r: abs(r["delta"]), reverse=True)
    return rows


def _apply_liquidity_gate(
    ranked: list[dict[str, Any]], gate_pct: float = 0.05
) -> list[dict[str, Any]]:
    """Filter out strikes with a bid/ask spread > gate_pct of mid price.

    This is a semi-public helper used by recording and roll scripts to ensure
    liquidity constraints are satisfied.

    Args:
        ranked: List of ranked strikes.
        gate_pct: Maximum spread as a fraction of mid price (default: 0.05 for 5%).

    Returns:
        Filtered list of strikes.
    """
    filtered: list[dict[str, Any]] = []
    for r in ranked:
        bid = r.get("bid", 0.0)
        ask = r.get("ask", 0.0)
        mid = r.get("mid", 0.0)
        if bid > 0.0 and ask > 0.0 and mid > 0.0:
            spread = ask - bid
            spread_pct = spread / mid
            if spread_pct <= gate_pct:
                filtered.append(r)
    return filtered


def rank_strikes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank filtered strike rows by CSP entry preference.

    Ranking tuple (ascending — lower wins):
      1. is_non_round  — 0 for multiples of 100 (preferred), 1 otherwise
      2. spread_bucket — int((ask - bid) / 2) — tighter ₹2 bucket wins
      3. -oi           — highest OI within the same bucket
      4. spread        — exact spread as final tiebreaker

    Args:
        rows: Output of :func:`filter_strikes_by_delta`.

    Returns:
        New list sorted by preference with a ``rank`` field (1-based int)
        added to each row dict.
    """

    def _key(r: dict[str, Any]) -> tuple:
        spread = r["ask"] - r["bid"] if (r["ask"] > 0 and r["bid"] > 0) else 9_999.0
        is_non_round = int(r["strike"]) % 100 != 0
        spread_bucket = int(spread / 2)
        return (is_non_round, spread_bucket, -r["oi"], spread)

    sorted_rows = sorted(rows, key=_key)
    return [{**r, "rank": i + 1} for i, r in enumerate(sorted_rows)]
