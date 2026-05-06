"""Combined intraday tracker — Dhan options + Nuvama options.

Replaces the previous Nuvama-only */5 cron with a single combined entry:
    */15 9-15 * * 1-5  cd /path/to/NiftyShield && python -m scripts.intraday_tracker >> logs/intraday.log 2>&1

Execution order:
    1. Dhan  — sync, no SDK side-effects, safe to run first.
    2. Nuvama — async; SDK launches a non-daemon background thread on init.
    3. os._exit() — terminates the Nuvama SDK background thread, which would
       otherwise block process exit indefinitely.

Both individual scripts retain their own __main__ guards for standalone use.

Frequency note: changed from */5 (Nuvama-only) to */15 (combined). Dhan option
positions change on trade events, not tick-by-tick; 15-min granularity is adequate
for the intraday P&L curve. Revert to two separate cron entries if the trackers
need different frequencies in future — that is a one-line cron change.
"""

from __future__ import annotations

import asyncio
import os


async def main() -> int:
    """Run Dhan tracker then Nuvama tracker in sequence.

    Returns:
        max(dhan_exit, nuvama_exit) — non-zero if either tracker failed.
    """
    from scripts.dhan_intraday_tracker import main as dhan_main
    from scripts.nuvama_intraday_tracker import main as nuvama_main

    # Dhan first — sync, no SDK thread pollution.
    dhan_exit = dhan_main()

    # Nuvama second — SDK launches background thread after this returns.
    nuvama_exit = await nuvama_main()

    return max(dhan_exit, nuvama_exit)


if __name__ == "__main__":
    code = asyncio.run(main())
    # os._exit is required: kills the Nuvama SDK non-daemon background thread
    # that would otherwise block process exit indefinitely.
    os._exit(code)
