import argparse
import datetime
from decimal import Decimal
from pathlib import Path

import structlog

from src.config import settings
from src.far_expiry.store import FarExpiryStore, stored_row_to_liquidity_row
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.dev.far_expiry_liquidity_report"
logger = structlog.get_logger(_SCRIPT_NAME)


def main() -> None:
    parser = argparse.ArgumentParser(description="Far expiry liquidity report.")
    parser.add_argument("--start-date", type=datetime.date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=datetime.date.fromisoformat, required=True)
    parser.add_argument("--expiry", type=datetime.date.fromisoformat, required=True)
    parser.add_argument("--source", type=str, default=None)
    parser.add_argument("--target-ce-delta", type=Decimal, default=Decimal("0.15"))
    parser.add_argument("--target-pe-delta", type=Decimal, default=Decimal("0.15"))

    args = parser.parse_args()

    if args.target_pe_delta < 0:
        parser.error("--target-pe-delta should be positive (or zero)")

    store = FarExpiryStore(Path(settings.db_path))

    rows = store.read_chain_snapshots(args.start_date, args.end_date, args.expiry, args.source)
    if not rows:
        print("No data found.")
        return

    by_date = {}
    for r in rows:
        by_date.setdefault(r.snapshot_date, []).append(r)

    print(
        f"{'Date':<12} | {'Non-0 Δ Rows':<12} | {'CE Strike':<9} | {'CE Quoted':<9} | {'CE Sprd%':<8} | {'CE OI':<7} | {'PE Strike':<9} | {'PE Quoted':<9} | {'PE Sprd%':<8} | {'PE OI':<7}"
    )
    print("-" * 115)

    for d, day_rows in sorted(by_date.items()):
        non_zero_delta = 0

        best_ce = None
        best_ce_diff = None
        best_pe = None
        best_pe_diff = None

        for r in day_rows:
            if r.delta is not None and r.delta != Decimal("0"):
                non_zero_delta += 1

                if r.option_type == "CE":
                    diff = abs(r.delta - args.target_ce_delta)
                    if best_ce_diff is None or diff < best_ce_diff:
                        best_ce_diff = diff
                        best_ce = r
                elif r.option_type == "PE":
                    diff = abs(r.delta - (-args.target_pe_delta))
                    if best_pe_diff is None or diff < best_pe_diff:
                        best_pe_diff = diff
                        best_pe = r

        ce_str = "-"
        ce_quoted = "-"
        ce_sprd = "-"
        ce_oi = "-"
        if best_ce is not None:
            ce_str = str(best_ce.strike)
            lr = stored_row_to_liquidity_row(best_ce)
            if lr.is_crossed_book:
                ce_quoted = "N"
                ce_sprd = "XBOOK"
            else:
                ce_quoted = "Y" if lr.is_quoted else "N"
                ce_sprd = (
                    f"{lr.spread_pct_mid * 100:.2f}%" if lr.spread_pct_mid is not None else "-"
                )
            ce_oi = str(best_ce.oi)

        pe_str = "-"
        pe_quoted = "-"
        pe_sprd = "-"
        pe_oi = "-"
        if best_pe is not None:
            pe_str = str(best_pe.strike)
            lr = stored_row_to_liquidity_row(best_pe)
            if lr.is_crossed_book:
                pe_quoted = "N"
                pe_sprd = "XBOOK"
            else:
                pe_quoted = "Y" if lr.is_quoted else "N"
                pe_sprd = (
                    f"{lr.spread_pct_mid * 100:.2f}%" if lr.spread_pct_mid is not None else "-"
                )
            pe_oi = str(best_pe.oi)

        print(
            f"{d.isoformat():<12} | {non_zero_delta:<12} | {ce_str:<9} | {ce_quoted:<9} | {ce_sprd:<8} | {ce_oi:<7} | {pe_str:<9} | {pe_quoted:<9} | {pe_sprd:<8} | {pe_oi:<7}"
        )


if __name__ == "__main__":
    setup_logging()
    main()
