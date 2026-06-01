#!/usr/bin/env python3
"""Stop NiftyShield monitor daemon.

Reads PID from daemon_heartbeat, sends SIGTERM, polls, and falls back to
SIGKILL.
Designed to run daily at 3:30 PM IST (Mon–Fri):
    30 15 * * 1-5  python -m scripts.stop_monitor
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path

# Ensure the root of the project is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import settings  # noqa: E402
from src.paper.store import PaperStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Stop Monitor Daemon")
    parser.add_argument(
        "--db-path",
        default=settings.db_path,
        help="Path to the SQLite database file",
    )
    args = parser.parse_args()

    store = PaperStore(args.db_path)
    heartbeat = store.get_heartbeat()

    if heartbeat is None:
        print("No heartbeat record found. Daemon does not seem to be running.")
        return 0

    pid = heartbeat.get("pid")
    if not pid:
        print("No PID found in heartbeat record.")
        return 0

    # Check if process is actually running
    try:
        os.kill(pid, 0)
    except OSError:
        print(f"Process with PID {pid} is not running.")
        return 0

    print(f"Sending SIGTERM to process {pid}...")
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        print(f"Failed to send SIGTERM: {e}")
        return 1

    # Poll for up to 30 seconds
    for sec in range(1, 31):
        try:
            os.kill(pid, 0)
            time.sleep(1)
        except OSError:
            print(f"Process {pid} terminated gracefully after {sec} seconds.")
            return 0

    print(f"Process {pid} still alive after 30 seconds. Sending SIGKILL...")
    try:
        os.kill(pid, signal.SIGKILL)
        # Verify it died
        time.sleep(0.5)
        try:
            os.kill(pid, 0)
            print(f"WARNING: Process {pid} still alive after SIGKILL.")
            return 1
        except OSError:
            print(f"Process {pid} killed forcefully.")
            return 0
    except OSError as e:
        print(f"Failed to send SIGKILL: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
