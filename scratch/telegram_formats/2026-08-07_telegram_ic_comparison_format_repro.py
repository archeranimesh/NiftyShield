"""Diagnostic repro: verify IC monthly comparison Telegram message rendering.

Context (2026-08-07 Cowork session): the "IC Monthly Comparison" message built by
build_comparison_report() (scripts/strategies/ic/paper_ic_monthly_comparison.py)
appeared misaligned when pasted into Cowork chat. Before touching that function,
we need to confirm whether the misalignment is real (happens inside the actual
Telegram app, where the message is sent wrapped in <pre>/HTML by
TelegramNotifier.send()) or an artifact of copy-pasting monospace text into a
non-monospace chat surface.

This script sends one or more HARDCODED candidate message strings straight to the
configured Telegram chat via the real TelegramNotifier, so they can be visually
compared against build_comparison_report()'s actual layout logic without running
any strategy code or touching paper_trades / paper_leg_snapshots.

Read-only w.r.t. the DB — makes zero DB calls. Sends real Telegram messages
(counts against the configured message budget).

Run from repo root with the project's normal venv active:
    python -m scratch.2026-08-07_telegram_ic_comparison_format_repro
or:
    python scratch/2026-08-07_telegram_ic_comparison_format_repro.py

Feeds into: docs/plan/telegram-ic-comparison-formatting/ (story TBD, pending the
result of this repro).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running as a plain script (python scratch/foo.py) as well as -m.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.notifications.telegram import TelegramNotifier  # noqa: E402


def _build_side_by_side_report(
    report_date_str: str,
    rows: list[tuple[str, str, str] | tuple[str, str, str, bool, bool]],
    edge_line: str,
) -> str:
    """Side-by-side layout with DYNAMIC label width and right-aligned value columns.

    This is the direct fix for the reported bug: build_comparison_report() hand-
    counts literal spaces per label to hit a fixed 20-char budget, which silently
    breaks the moment a label is longer than what was counted by hand (exactly
    what happened with "Realized (inception)" / "Unrealized(inception)" colliding
    with the value column). Computing label_width = max(len(label)) removes the
    hand-counting step entirely, and column widths are similarly derived from the
    actual cell contents (including the header text) rather than assumed —
    correct by construction for any row/label set, including long free-text rows
    like "0 rolls + 0 locks".

    Each row is (label, v1_value, v2_value) or (label, v1_value, v2_value,
    v1_warn, v2_warn) where warn=True appends a red-circle emoji to that value.
    """
    label_width = max(len(r[0]) for r in rows) + 1  # +1 gap before the columns start

    v1_cells, v2_cells = [], []
    for row in rows:
        v1_val, v2_val = row[1], row[2]
        v1_warn = row[3] if len(row) > 3 else False
        v2_warn = row[4] if len(row) > 4 else False
        v1_cells.append(f"{v1_val}{' 🔴' if v1_warn else ''}")
        v2_cells.append(f"{v2_val}{' 🔴' if v2_warn else ''}")

    col1_width = max(len("V1 Monthly"), max(len(c) for c in v1_cells))
    col2_width = max(len("V2 Monthly"), max(len(c) for c in v2_cells))

    lines = [
        f"📊 IC Monthly Comparison — {report_date_str}",
        "",
        f"{'':<{label_width}}{'V1 Monthly':>{col1_width}}  {'V2 Monthly':>{col2_width}}",
        "─" * (label_width + col1_width + col2_width + 2),
    ]
    for row, v1_cell, v2_cell in zip(rows, v1_cells, v2_cells, strict=True):
        label = row[0]
        lines.append(f"{label:<{label_width}}{v1_cell:>{col1_width}}  {v2_cell:>{col2_width}}")
    lines += ["", edge_line]
    return "\n".join(lines)


# Candidate messages to verify. Add more variants here as needed — each is sent
# as a separate Telegram message so they can be compared side by side on-device.
CANDIDATES: dict[str, str] = {
    "side_by_side_right_aligned": _build_side_by_side_report(
        report_date_str="2026-08-06",
        rows=[
            ("Legs", "4/4", "3/4", False, True),
            ("Credit", "₹87", "₹129"),
            ("Captured", "-21%", "-1%"),
            ("Put Δ", "-0.03", "-0.20"),
            ("Call Δ", "0.33", "0.27"),
            ("DTE", "19", "19"),
            ("Flt (M)", "₹0", "₹0"),
            ("Bkd (M)", "₹0", "₹58"),
            ("Bkd (I)", "₹1,204", "₹58"),
            ("Flt (I)", "₹0", "₹0"),
            ("Lock zone", "N/A", "None"),
            ("Adj", "0 rolls", "0 rolls + 0 locks"),
            ("Signals", "—", "—"),
        ],
        edge_line="Edge so far:  V2 +₹58 vs V1",
    ),
}


def _section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


async def main() -> None:
    _section("0. Setup")
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        print(
            "!! TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in environment — "
            "cannot send. Aborting without sending anything."
        )
        return

    notifier = TelegramNotifier(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        budget=settings.telegram_message_budget,
    )
    print(f"Chat ID: {settings.telegram_chat_id}")
    print(f"Candidates to send: {list(CANDIDATES.keys())}")

    for name, text in CANDIDATES.items():
        _section(f"Sending candidate: {name}")
        print(text)
        ok = await notifier.send(text)
        print(f"  -> send() returned {ok}")
        if not ok:
            print("  !! send failed — check logs / budget / credentials before retrying")

    _section("Done — check the Telegram app on your phone/desktop for rendering")


if __name__ == "__main__":
    asyncio.run(main())
