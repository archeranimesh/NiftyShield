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

import structlog
from dotenv import load_dotenv

# Ensure the root of the project is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load environment before local imports
load_dotenv()

from src.config import settings  # noqa: E402
from src.paper.store import PaperStore  # noqa: E402
from src.utils.logging import setup_logging  # noqa: E402

logger = structlog.get_logger("scripts.stop_monitor")


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
        logger.info("No heartbeat record found. Daemon is not running.")
        return 0

    pid = heartbeat.get("pid")
    if not pid:
        logger.info("No PID found in heartbeat record.")
        return 0

    # Check if process is actually running
    try:
        os.kill(pid, 0)
    except OSError:
        logger.info("Process is not running.", pid=pid)
        return 0

    logger.info("Sending SIGTERM to process...", pid=pid)
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        logger.error("Failed to send SIGTERM", pid=pid, error=str(e))
        return 1

    # Poll for up to 30 seconds
    for sec in range(1, 31):
        try:
            os.kill(pid, 0)
            time.sleep(1)
        except OSError:
            logger.info(
                "Process terminated gracefully.",
                pid=pid,
                elapsed_seconds=sec,
            )
            return 0

    logger.warning(
        "Process still alive after 30 seconds. Sending SIGKILL...",
        pid=pid,
    )
    try:
        os.kill(pid, signal.SIGKILL)
        # Verify it died
        time.sleep(0.5)
        try:
            os.kill(pid, 0)
            logger.error("Process still alive after SIGKILL", pid=pid)
            return 1
        except OSError:
            logger.info("Process killed forcefully.", pid=pid)
            return 0
    except OSError as e:
        logger.error("Failed to send SIGKILL", pid=pid, error=str(e))
        return 1


if __name__ == "__main__":
    setup_logging()
    sys.exit(main())
