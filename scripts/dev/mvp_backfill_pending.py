#!/usr/bin/env python3
"""Sweep every PENDING MVP pick through the equity bhavcopy bootstrap + backfill resume.

For each pick in ``mvp_recommendations`` still PENDING: finds the earliest
``pick_date`` across them, bootstraps equity bhavcopy Parquet from that date
through today (covers every symbol in the store — ``equity_bhavcopy_bootstrap``
loads its own symbol list via ``MVPStore.get_distinct_symbols()``), then runs
``scripts.mvp backfill --resume <pick_id>`` for each pending pick in turn.

Usage:
    python -m scripts.dev.mvp_backfill_pending
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from src.mvp.models import PickStatus
from src.mvp.store import MVPStore

DB_PATH = Path("data/portfolio/portfolio.sqlite")


def main() -> None:
    store = MVPStore(DB_PATH)
    pending = store.list_picks(PickStatus.PENDING)
    if not pending:
        print("No PENDING picks.")
        return

    earliest = min(datetime.fromisoformat(p.pick_date).date() for p in pending)
    today = date.today()
    print(f"{len(pending)} PENDING picks. Bootstrapping bhavcopy {earliest} → {today} ...")

    bootstrap = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.pipeline.equity_bhavcopy_bootstrap",
            "--start",
            earliest.isoformat(),
            "--end",
            today.isoformat(),
        ]
    )
    if bootstrap.returncode != 0:
        print(f"Bootstrap failed (exit {bootstrap.returncode}); aborting resume sweep.")
        return

    for pick in pending:
        print(f"--- resuming {pick.pick_id[:8]} ({pick.symbol}) ---")
        result = subprocess.run(
            [sys.executable, "-m", "scripts.mvp", "backfill", "--resume", pick.pick_id]
        )
        if result.returncode != 0:
            print(f"  ✗ resume failed for {pick.pick_id[:8]} (exit {result.returncode})")


if __name__ == "__main__":
    main()
