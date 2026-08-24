#!/usr/bin/env python3
"""BUG-032 B032.4 — backfill the understated overlay_pp P&L snapshots.

Context
-------
`get_position()`'s ambiguous-match fallback silently dropped one leg's P&L
whenever the `overlay_pp` role had two open positions at once. That window
was exactly 2026-08-20 and 2026-08-21 (NSE_FO|61604, opened 2026-08-11,
overlapped with NSE_FO|74009, opened 2026-08-20; both closed 2026-08-24
under BUG-031's manual re-entry, which is unaffected — see below).

This recomputes, from the historical EOD option-chain Parquet snapshots
(`data/historical/option_chain/eod/2026/08/upstox_<date>_{monthly,weekly}.parquet`)
and the `paper_trades` ledger, what `_compute_overlay_leg_totals()` and
`_compute_overlay_pnl_snapshots()` (post BUG-032 fix, SHA 67d4010) would
have written on those two dates, and backfills:

  - `paper_leg_snapshots`   (paper_nifty_overlay, overlay_pp, 2026-08-20/21)
  - `paper_overlay_pnl_snapshots` (paper_nifty_overlay, pp, 2026-08-20/21,
    and 2026-08-24 — 2026-08-24's own total_pnl is untouched and already
    correct, verified below, but its `pnl_1d_abs` is derived from 2026-08-21's
    total_pnl and must cascade)

2026-08-24 itself needs NO leg_snapshot correction: it is a same-day
open+close for all three overlay_pp instruments that day, realized entirely
through `record_trade()` line items, not through the ambiguous
`get_position()` path — independently re-derived below from `paper_trades`
and it matches the already-stored realized_pnl exactly (-4538.625).

Deviation from the BUG-030 B030.4 precedent (documented, not accidental):
the precedent backfilled via `PaperStore.record_leg_snapshot()` /
`record_overlay_pnl_snapshot()`. This session's `.venv` (structlog/pydantic)
is unreachable from the device bridge that runs this script, so this uses
raw parameterized SQL against the exact same schema those methods write,
and enforces the same `total_pnl == unrealized_pnl + realized_pnl`
invariant those methods enforce (see `_assert_invariant` below) before
writing anything. Run this with the repo's real `.venv` instead if/when
that's available; the computed values do not depend on which path writes
them.

Usage
-----
    python3 scripts/dev/backfill_bug032_overlay_pp.py            # dry run
    python3 scripts/dev/backfill_bug032_overlay_pp.py --apply     # writes

Always run the dry run first and read the before/after table.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "portfolio" / "portfolio.sqlite"

STRATEGY_NAME = "paper_nifty_overlay"
LEG_ROLE = "overlay_pp"
OVERLAY_TYPE = "pp"

# (snapshot_date, [(instrument_key, net_qty, avg_cost, ltp), ...])
# net_qty/avg_cost reconstructed by hand from `paper_trades` (see module
# docstring's query); ltp sourced from the EOD Parquet chain snapshot for
# that date (weekly bucket for 61604's 2026-08-25 expiry, monthly bucket
# for 74009's 2026-09-29 expiry — confirmed by inspecting both files).
AFFECTED: dict[str, list[tuple[str, int, Decimal, Decimal]]] = {
    "2026-08-20": [
        ("NSE_FO|61604", 65, Decimal("58.85"), Decimal("18.90")),
        ("NSE_FO|74009", 65, Decimal("94.20"), Decimal("96.60")),
    ],
    "2026-08-21": [
        ("NSE_FO|61604", 65, Decimal("58.85"), Decimal("11.50")),
        # 74009: BUY 65@94.20 (08-20) + BUY 65@91.80 (08-21) -> net 130,
        # avg_cost = (65*94.20 + 65*91.80) / 130 = 93.00
        ("NSE_FO|74009", 130, Decimal("93.00"), Decimal("92.40")),
    ],
}

# 2026-08-24 close-day realized P&L, independently re-derived from
# paper_trades (ids 213-215) as a sanity check that it needs no backfill:
#   61604:  SELL 65@4.85,  avg_cost 58.85 -> (4.85-58.85)*65   = -3510.000
#   74009:  SELL 130@83.85, avg_cost 93.00 -> (83.85-93.00)*130 = -1189.500
#   74046:  BUY 65@97.375, SELL 65@99.85   -> (99.85-97.375)*65 =  160.875
#   total                                                       = -4538.625
EXPECTED_0824_TOTAL_PNL = Decimal("-4538.625")


def _safe_pct(numerator: Decimal, denominator: Decimal | None) -> Decimal:
    if not denominator:
        return Decimal("0")
    return numerator / denominator


def _mark_value(ltp: Decimal | None, net_qty: int) -> Decimal | None:
    if ltp is None:
        return None
    return ltp * abs(net_qty)


def _assert_invariant(unrealized: Decimal, realized: Decimal, total: Decimal) -> None:
    if total != unrealized + realized:
        raise ValueError(
            f"invariant violated: total_pnl {total} != unrealized {unrealized} "
            f"+ realized {realized}"
        )


def compute_corrected_leg_snapshots() -> dict[str, dict]:
    """Per affected date: aggregated unrealized_pnl, ltp=None (n>1), total_pnl."""
    out: dict[str, dict] = {}
    for snap_date, positions in AFFECTED.items():
        unrealized = sum(
            ((ltp - avg_cost) * net_qty for _, net_qty, avg_cost, ltp in positions),
            Decimal("0"),
        )
        realized = Decimal("0")  # no closes on either affected date
        total = unrealized + realized
        _assert_invariant(unrealized, realized, total)
        out[snap_date] = {
            "unrealized_pnl": unrealized,
            "realized_pnl": realized,
            "total_pnl": total,
            "ltp": None,  # n>1 open instruments -> NULL per the BUG-032 ruling
        }
    return out


def compute_corrected_overlay_pnl_snapshots(
    leg: dict[str, dict],
) -> dict[str, dict]:
    """pnl_1d_abs/pct + pnl_inception_abs/pct for 08-20, 08-21, and the 08-24
    cascade (08-24's own total_pnl is unchanged; only its pnl_1d_abs/pct,
    which are derived from 08-21, need re-deriving)."""
    out: dict[str, dict] = {}

    # --- 2026-08-19 baseline (unchanged, read-only reference) ---
    prev_0819_total_pnl = Decimal("685.75")
    prev_0819_ltp = Decimal("69.4")

    # --- 2026-08-20 ---
    entry_basis_0820 = sum(
        (avg_cost * net_qty for _, net_qty, avg_cost, _ in AFFECTED["2026-08-20"]),
        Decimal("0"),
    )
    pnl_inception_abs_0820 = leg["2026-08-20"]["total_pnl"]
    pnl_inception_pct_0820 = _safe_pct(pnl_inception_abs_0820, entry_basis_0820)
    pnl_1d_abs_0820 = pnl_inception_abs_0820 - prev_0819_total_pnl
    # _position_qty() at call-time returns TODAY's (08-20) live role qty
    # across both instruments = 65 + 65 = 130 (this is BUG-036's documented
    # "today's qty x yesterday's LTP" blend -- reproduced faithfully here,
    # not fixed, since BUG-036 is a separate, deferred follow-up).
    qty_today_0820 = sum(net_qty for _, net_qty, _, _ in AFFECTED["2026-08-20"])
    prev_mark_value_0820 = _mark_value(prev_0819_ltp, qty_today_0820) or Decimal("0")
    pnl_1d_pct_0820 = _safe_pct(pnl_1d_abs_0820, prev_mark_value_0820)
    out["2026-08-20"] = {
        "pnl_1d_abs": pnl_1d_abs_0820,
        "pnl_1d_pct": pnl_1d_pct_0820,
        "pnl_inception_abs": pnl_inception_abs_0820,
        "pnl_inception_pct": pnl_inception_pct_0820,
    }

    # --- 2026-08-21 ---
    entry_basis_0821 = sum(
        (avg_cost * net_qty for _, net_qty, avg_cost, _ in AFFECTED["2026-08-21"]),
        Decimal("0"),
    )
    pnl_inception_abs_0821 = leg["2026-08-21"]["total_pnl"]
    pnl_inception_pct_0821 = _safe_pct(pnl_inception_abs_0821, entry_basis_0821)
    pnl_1d_abs_0821 = pnl_inception_abs_0821 - pnl_inception_abs_0820
    # prev (08-20) ltp is now NULL (n>1 that day) -> _mark_value is None ->
    # prev_mark_value is 0 -> pnl_1d_pct falls back to 0. This IS the
    # "understates the denominator" symptom BUG-036 documents; left as-is.
    pnl_1d_pct_0821 = Decimal("0")
    out["2026-08-21"] = {
        "pnl_1d_abs": pnl_1d_abs_0821,
        "pnl_1d_pct": pnl_1d_pct_0821,
        "pnl_inception_abs": pnl_inception_abs_0821,
        "pnl_inception_pct": pnl_inception_pct_0821,
    }

    # --- 2026-08-24 cascade: only pnl_1d_abs changes (derived from 08-21's
    # corrected total_pnl); pnl_1d_pct was already 0 (prev ltp was already
    # NULL that day too under the OLD buggy value) and total_pnl/inception
    # are independently verified correct below, untouched. ---
    pnl_1d_abs_0824 = EXPECTED_0824_TOTAL_PNL - pnl_inception_abs_0821
    out["2026-08-24"] = {
        "pnl_1d_abs": pnl_1d_abs_0824,
        # pnl_1d_pct, pnl_inception_abs, pnl_inception_pct: unchanged
    }

    return out


def _row_leg_snapshot(con: sqlite3.Connection, snap_date: str) -> sqlite3.Row | None:
    con.row_factory = sqlite3.Row
    cur = con.execute(
        "SELECT * FROM paper_leg_snapshots WHERE strategy_name=? AND leg_role=? "
        "AND snapshot_date=?",
        (STRATEGY_NAME, LEG_ROLE, snap_date),
    )
    return cur.fetchone()


def _row_overlay_pnl(con: sqlite3.Connection, snap_date: str) -> sqlite3.Row | None:
    con.row_factory = sqlite3.Row
    cur = con.execute(
        "SELECT * FROM paper_overlay_pnl_snapshots WHERE strategy_name=? "
        "AND overlay_type=? AND snapshot_date=?",
        (STRATEGY_NAME, OVERLAY_TYPE, snap_date),
    )
    return cur.fetchone()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run).")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"ERROR: {DB_PATH} not found.", file=sys.stderr)
        return 1

    leg = compute_corrected_leg_snapshots()
    overlay = compute_corrected_overlay_pnl_snapshots(leg)

    con = sqlite3.connect(DB_PATH)
    try:
        print("=" * 100)
        print("paper_leg_snapshots — (paper_nifty_overlay, overlay_pp)")
        print("=" * 100)
        for snap_date, new in leg.items():
            old = _row_leg_snapshot(con, snap_date)
            print(f"\n{snap_date}")
            print(
                f"  OLD: unrealized={old['unrealized_pnl']!r} realized={old['realized_pnl']!r} "
                f"total={old['total_pnl']!r} ltp={old['ltp']!r}"
            )
            print(
                f"  NEW: unrealized={new['unrealized_pnl']} realized={new['realized_pnl']} "
                f"total={new['total_pnl']} ltp={new['ltp']}"
            )

        print()
        print("=" * 100)
        print("paper_overlay_pnl_snapshots — (paper_nifty_overlay, pp)")
        print("=" * 100)
        for snap_date, new in overlay.items():
            old = _row_overlay_pnl(con, snap_date)
            print(f"\n{snap_date}")
            print(
                f"  OLD: pnl_1d_abs={old['pnl_1d_abs']!r} pnl_1d_pct={old['pnl_1d_pct']!r} "
                f"pnl_inception_abs={old['pnl_inception_abs']!r} "
                f"pnl_inception_pct={old['pnl_inception_pct']!r}"
            )
            new_1d_abs = new.get("pnl_1d_abs", Decimal(old["pnl_1d_abs"]))
            new_1d_pct = new.get("pnl_1d_pct", Decimal(old["pnl_1d_pct"]))
            new_inc_abs = new.get("pnl_inception_abs", Decimal(old["pnl_inception_abs"]))
            new_inc_pct = new.get("pnl_inception_pct", Decimal(old["pnl_inception_pct"]))
            print(
                f"  NEW: pnl_1d_abs={new_1d_abs} pnl_1d_pct={new_1d_pct} "
                f"pnl_inception_abs={new_inc_abs} pnl_inception_pct={new_inc_pct}"
            )

        # sanity check: 2026-08-24's own total_pnl needs no change
        row_0824 = _row_leg_snapshot(con, "2026-08-24")
        stored_0824_total = Decimal(row_0824["total_pnl"])
        print()
        print("=" * 100)
        print("2026-08-24 sanity check (no leg_snapshot backfill needed)")
        print("=" * 100)
        print(f"  stored total_pnl   = {stored_0824_total}")
        print(f"  re-derived total   = {EXPECTED_0824_TOTAL_PNL}")
        if stored_0824_total != EXPECTED_0824_TOTAL_PNL:
            print("  MISMATCH -- do not proceed, investigate before applying.", file=sys.stderr)
            return 1
        print("  MATCH -- confirmed no backfill needed for 2026-08-24's own total_pnl.")

        if not args.apply:
            print("\nDry run only. Re-run with --apply to write these changes.")
            return 0

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup_path = DB_PATH.with_name(f"portfolio.bak_{ts}_pre-BUG032.4-backfill.sqlite")
        shutil.copy2(DB_PATH, backup_path)
        print(f"\nBacked up DB to {backup_path}")

        for snap_date, new in leg.items():
            con.execute(
                "UPDATE paper_leg_snapshots SET unrealized_pnl=?, realized_pnl=?, "
                "total_pnl=?, ltp=? WHERE strategy_name=? AND leg_role=? "
                "AND snapshot_date=?",
                (
                    str(new["unrealized_pnl"]),
                    str(new["realized_pnl"]),
                    str(new["total_pnl"]),
                    new["ltp"],
                    STRATEGY_NAME,
                    LEG_ROLE,
                    snap_date,
                ),
            )

        for snap_date in ("2026-08-20", "2026-08-21"):
            new = overlay[snap_date]
            con.execute(
                "UPDATE paper_overlay_pnl_snapshots SET pnl_1d_abs=?, pnl_1d_pct=?, "
                "pnl_inception_abs=?, pnl_inception_pct=? WHERE strategy_name=? "
                "AND overlay_type=? AND snapshot_date=?",
                (
                    str(new["pnl_1d_abs"]),
                    str(new["pnl_1d_pct"]),
                    str(new["pnl_inception_abs"]),
                    str(new["pnl_inception_pct"]),
                    STRATEGY_NAME,
                    OVERLAY_TYPE,
                    snap_date,
                ),
            )

        # 08-24 cascade: pnl_1d_abs only
        con.execute(
            "UPDATE paper_overlay_pnl_snapshots SET pnl_1d_abs=? WHERE strategy_name=? "
            "AND overlay_type=? AND snapshot_date=?",
            (
                str(overlay["2026-08-24"]["pnl_1d_abs"]),
                STRATEGY_NAME,
                OVERLAY_TYPE,
                "2026-08-24",
            ),
        )

        con.commit()
        print("\nApplied. Re-run without --apply to confirm the new stored values.")
    finally:
        con.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
