"""Diagnostic repro: why does paper_ic_entry.py --expiry-type yearly fail with
ic_entry.leg_resolution_failed leg=short_put?

Context (2026-07-22 Cowork session): after fixing get_expiry_candidates so
"yearly" correctly resolves to the live Dec 2026 expiry (DTE 160, not the
bogus Jun/Dec 2027 rollover from an earlier over-correction), the entry
script still fails at strike selection:

    ic_entry.leg_resolution_failed leg=short_put

This happens downstream of both the IVR gate and the DTE window gate (both
non-blocking under the default --log-only-gates=True) — it's a hard
structural failure in filter_strikes_by_delta() finding zero PE rows in the
target delta band. Three candidate explanations, in order of likelihood:

  1. Real market condition: at 160 DTE, put skew is compressed enough that
     no live strike actually has |delta| in the yearly target band
     (0.12 +/- 0.05 standalone, or shifted -0.06/+0.03 if concurrent with
     an open CSP position -- this script prints which mode applies too).
  2. Data gap: Upstox doesn't populate option_greeks for some/all strikes
     on this far-dated contract (delta comes back None/0.0 and gets
     filtered out regardless of band).
  3. Bug: a sign/units issue in filter_strikes_by_delta's abs(delta) check,
     or the wrong side of the chain being read.

This script re-runs the exact same expiry resolution + chain fetch +
delta-filter path paper_ic_entry.py uses for --expiry-type yearly, and
prints the full delta distribution for both PE and CE (min/max/count,
how many strikes have populated vs missing greeks) instead of just the
pass/fail filter result -- so which of the three explanations applies
becomes visible.

Read-only. Makes one live Upstox API call (get_option_chain_sync). Does NOT
call record_paper_trade.py, place any order, or write to paper_trades.

Run from repo root with the project's normal venv active:
    python scratch/2026-07-22_ic_yearly_leg_resolution_repro.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# Allow running as a plain script (python scratch/foo.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decimal import Decimal  # noqa: E402

from src.client.upstox_market import UpstoxMarketClient  # noqa: E402
from src.config import settings  # noqa: E402
from src.instruments.lookup import InstrumentLookup  # noqa: E402
from src.instruments.strike_selector import filter_strikes_by_delta  # noqa: E402
from src.paper.constants import STRATEGY_CSP  # noqa: E402
from src.paper.store import PaperStore  # noqa: E402
from src.strategy.ic_expiry_config import CONFIGS  # noqa: E402

DEFAULT_BOD_PATH = Path("data/instruments/NSE.json.gz")
DEFAULT_DB_PATH = Path("data/portfolio/portfolio.sqlite")


def _safe_delta(entry: dict, side_key: str) -> float | None:
    opt = entry.get(side_key) or {}
    greeks = opt.get("option_greeks") or {}
    raw = greeks.get("delta")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def main() -> None:
    config = CONFIGS["yearly"]
    print(f"strategy_name = {config.strategy_name}")
    print(f"expiry_bucket = {config.expiry_bucket}")
    print(
        f"configured target deltas: short_put={config.short_put_delta} "
        f"short_call={config.short_call_delta} delta_range={config.delta_range}"
    )

    # --- Step 1: mode detection (mirrors paper_ic_entry.py Step 3) ---
    store = PaperStore(DEFAULT_DB_PATH)
    csp_positions = store.get_positions(STRATEGY_CSP)
    mode = "concurrent" if any(pos.net_qty != 0 for pos in csp_positions) else "standalone"
    print(f"\nmode = {mode}")

    if mode == "concurrent":
        put_target = config.short_put_delta - Decimal("0.06")
        call_target = config.short_call_delta + Decimal("0.03")
    else:
        put_target = config.short_put_delta
        call_target = config.short_call_delta

    put_min = float(put_target - config.delta_range)
    put_max = float(put_target + config.delta_range)
    call_min = float(call_target - config.delta_range)
    call_max = float(call_target + config.delta_range)
    print(f"put target band  = [{put_min:.4f}, {put_max:.4f}]")
    print(f"call target band = [{call_min:.4f}, {call_max:.4f}]")

    # --- Step 2: expiry resolution (mirrors paper_ic_entry.py Step 6) ---
    if not DEFAULT_BOD_PATH.exists():
        print(f"\nBOD file missing: {DEFAULT_BOD_PATH}")
        sys.exit(1)

    lookup = InstrumentLookup.from_file(DEFAULT_BOD_PATH)
    expiries = lookup.get_expiry_candidates(
        underlying="NIFTY", today=date.today(), preference=[config.expiry_bucket]
    )
    expiry_str = next((e for label, e in expiries if label == config.expiry_bucket), None)
    if expiry_str is None:
        print(f"\nNo '{config.expiry_bucket}' candidate resolved at all.")
        sys.exit(1)

    dte = (date.fromisoformat(expiry_str) - date.today()).days
    print(f"\nresolved expiry = {expiry_str}  (DTE {dte})")

    # --- Step 3: live chain fetch (mirrors paper_ic_entry.py Step 7) ---
    client = UpstoxMarketClient(settings.upstox_analytics_token)
    raw_chain = client.get_option_chain_sync("NSE_INDEX|Nifty 50", expiry_str)
    print(f"raw_chain: {len(raw_chain)} strike rows returned")

    if not raw_chain:
        print("Chain is EMPTY — Upstox returned no strikes for this expiry.")
        sys.exit(1)

    # --- Step 4: full delta distribution (the actual diagnostic) ---
    for side_label, raw_key in (("PE", "put_options"), ("CE", "call_options")):
        deltas = [_safe_delta(e, raw_key) for e in raw_chain]
        populated = [d for d in deltas if d is not None]
        missing_count = len(deltas) - len(populated)
        print(f"\n--- {side_label} ---")
        print(f"  strikes total          : {len(deltas)}")
        print(f"  greeks missing (None)  : {missing_count}")
        if populated:
            abs_deltas = sorted(abs(d) for d in populated)
            print(f"  |delta| min/max        : {abs_deltas[0]:.4f} / {abs_deltas[-1]:.4f}")
            print(
                "  |delta| distribution   : "
                + ", ".join(f"{d:.3f}" for d in abs_deltas[:: max(1, len(abs_deltas) // 15)])
            )
        else:
            print("  No strikes have populated greeks at all.")

    # --- Step 5: run the actual filter used by paper_ic_entry.py ---
    put_rows = filter_strikes_by_delta(raw_chain, "PE", put_min, put_max)
    call_rows = filter_strikes_by_delta(raw_chain, "CE", call_min, call_max)
    print(f"\nfilter_strikes_by_delta(PE, {put_min:.4f}, {put_max:.4f}) -> {len(put_rows)} rows")
    print(f"filter_strikes_by_delta(CE, {call_min:.4f}, {call_max:.4f}) -> {len(call_rows)} rows")
    if put_rows:
        print(f"  best PE candidate: strike={put_rows[0]['strike']} delta={put_rows[0]['delta']}")
    if call_rows:
        print(f"  best CE candidate: strike={call_rows[0]['strike']} delta={call_rows[0]['delta']}")


if __name__ == "__main__":
    main()
