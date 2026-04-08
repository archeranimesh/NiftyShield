"""Smoke-test script: send a sample message via the Telegram notifier.

Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from .env and sends a
short test message. Use this to verify bot credentials and chat ID
before the cron integration kicks in.

Usage:
    python -m scripts.send_test_telegram

Exit codes:
    0  — message delivered successfully
    1  — env vars missing or API call failed
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.notifications.telegram import build_notifier  # noqa: E402


def main() -> int:
    """Send a test message and report success/failure."""
    notifier = build_notifier()
    if notifier is None:
        print(
            "ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in .env.\n"
            "Add both variables and try again."
        )
        return 1

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = (
        f"NiftyShield test message — {now}\n"
        "\n"
        "  ── Combined Portfolio ─────────────────────────────────\n"
        "  MF current value    : ₹   58,21,000  P&L:  +4,21,000 (+7.80%)\n"
        "  ETF current value   : ₹    6,08,360  (basis ₹6,08,000)\n"
        "  Options net P&L     :         +3,250\n"
        "  ───────────────────────────────────────────────────────\n"
        "  Total value         : ₹   64,32,610\n"
        "  Total invested      : ₹   60,08,000\n"
        "  Total P&L           :     +4,24,610  (+7.07%)\n"
        "\n"
        "If you can read this, the bot is configured correctly."
    )

    print(f"Sending test message at {now} …")
    ok = notifier.send(message)
    if ok:
        print("  ✓ Message delivered. Check your Telegram chat.")
        return 0
    else:
        print("  ✗ Delivery failed — check logs for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
