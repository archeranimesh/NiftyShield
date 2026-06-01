#!/usr/bin/env python3
"""Start NiftyShield monitor daemon if it is not already running or is stale.

Designed to run daily at 9:15 AM IST (Mon–Fri):
    15 09 * * 1-5  python -m scripts.start_monitor
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure the root of the project is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import settings  # noqa: E402
from src.paper.store import PaperStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Start Monitor Daemon")
    parser.add_argument(
        "--db-path",
        default=settings.db_path,
        help="Path to the SQLite database file",
    )
    args = parser.parse_args()

    store = PaperStore(args.db_path)
    heartbeat = store.get_heartbeat()

    should_start = False
    if heartbeat is None:
        print("No heartbeat record found. Starting daemon...")
        should_start = True
    else:
        # Check if heartbeat is stale (> 5 minutes old)
        try:
            last_beat = datetime.fromisoformat(heartbeat["last_beat"])
            # Ensure last_beat is timezone-aware
            if last_beat.tzinfo is None:
                last_beat = last_beat.replace(tzinfo=timezone.utc)

            now_dt = datetime.now(timezone.utc)
            age_seconds = (now_dt - last_beat).total_seconds()

            # Check if process is actually running (if pid exists)
            pid = heartbeat.get("pid")
            process_exists = False
            if pid:
                try:
                    os.kill(pid, 0)
                    process_exists = True
                except OSError:
                    process_exists = False

            is_stale = age_seconds > 300
            is_shutdown = heartbeat.get("last_event") == "SHUTDOWN"
            if is_stale or not process_exists or is_shutdown:
                print(
                    f"Stale heartbeat or dead process "
                    f"(age: {age_seconds:.1f}s, pid: {pid}, "
                    f"exists: {process_exists}). Starting daemon..."
                )
                should_start = True
            else:
                print(
                    f"Daemon is already running "
                    + f"(age: {age_seconds:.1f}s, pid: {pid})."
                )
        except Exception as e:  # Intentional: Ignore errors, start daemon
            print(
                f"Error checking heartbeat: {e}. "
                + "Defaulting to start daemon..."
            )
            should_start = True

    if should_start:
        cmd = [sys.executable, "-m", "scripts.monitor_daemon"]
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        print("Daemon launched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
