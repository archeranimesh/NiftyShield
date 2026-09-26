#!/usr/bin/env python3
"""Combined launcher for confirmed Telegram-message scratch probes.

Every confirmed message format in `docs/plan/telegram-markdown-migration/strategy-rollout/
stories.md` (ROLL-1, ROLL-2, ROLL-6 through ROLL-16) has a live reference implementation
under `scratch/` — a scratch script with a `main()` that prints the rendered MarkdownV2
source and, when `--send` is passed, actually posts it to Telegram via
`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`. ROLL-3 (strategy close/roll notifications) and
ROLL-4 (approval requests) are backbone-only escaping audits with no format redesign, so
they have no scratch script and are not menu options here.

Option 14 (EOD PT Summary) belongs to a separate, sibling epic —
`docs/plan/eod-pt-summary/` (task PT-1), not `telegram-markdown-migration` — which is why it
isn't named in that epic's stories.md. Its scratch script
(`2026-08-13_eod_pt_summary.py`) is real and already validated against live data (matches
Animesh's actual broker output, per the script's own docstring), it just hasn't been
formally promoted into `src/` yet (PT-1/PT-2/PT-3 are still unchecked in that epic's
tasks.md). Unlike the ROLL-* scripts it queries the live/mock broker + DB rather than
rendering hardcoded sample data, takes `--date`/`--dry-run`/`--db-path`/`--bod-path`
instead of a scenario name, and sends 2-3 separate Telegram messages per run instead of
one.

This script does not import or re-implement any of them — it just shells out to
`python3 -m scratch.<module>` (or `python3 scratch/<file>.py` as a fallback) with whatever
scenario/flags you choose, so each script's own on-device dependency handling (aiohttp,
src.config.settings) stays exactly as authored.

Usage:
    python3 scratch/send_menu.py            # interactive menu
    python3 scratch/send_menu.py --list      # list options and exit
    python3 scratch/send_menu.py 7           # run option 7 directly (print-only)
    python3 scratch/send_menu.py 7 --send    # run option 7 and actually send
    python3 scratch/send_menu.py 7 critical_day3 --send   # pass a scenario name through
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCRATCH_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRATCH_DIR.parent


def _resolve_python() -> str:
    """Prefer the project's own .venv interpreter (has aiohttp/src.config.settings)
    over whatever `python3` this launcher itself happens to be running under."""
    venv_python = PROJECT_ROOT / ".venv" / "bin" / "python3"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


PYTHON = _resolve_python()


@dataclass(frozen=True)
class MessageOption:
    key: str
    roll: str
    label: str
    script: str
    # None = script has no scenario concept (fixed sample data); "--scenario" = uses the
    # argparse --scenario flag; "positional" = takes scenario as sys.argv[1].
    scenario_style: str | None
    scenarios: tuple[str, ...] = field(default_factory=tuple)
    default_scenario: str | None = None


OPTIONS: list[MessageOption] = [
    MessageOption(
        "1",
        "ROLL-1",
        "IC EOD Audit (V2 monthly)",
        "2026-08-07_ic_eod_audit_v2_telegram_format.py",
        "--scenario",
        (),
        "profit",
    ),
    MessageOption(
        "2",
        "ROLL-2",
        "IC Monthly Comparison (V1 vs V2)",
        "2026-08-07_ic_monthly_comparison_telegram_format.py",
        None,
    ),
    MessageOption(
        "3",
        "ROLL-6",
        "EOD Paper Summary",
        "2026-08-08_eod_paper_summary_format.py",
        None,
    ),
    MessageOption(
        "4",
        "ROLL-7",
        "Re-entry Blocked/Eligible Notice",
        "2026-08-08_reentry_notice_format.py",
        "positional",
        (),
        "blocked_dte",
    ),
    MessageOption(
        "5",
        "ROLL-8",
        "Generic Strategy WARN Event Alert",
        "2026-08-08_strategy_event_alert_format.py",
        "positional",
        (),
        "delta_breach",
    ),
    MessageOption(
        "6",
        "ROLL-9",
        "Three-Track Base-Leg Roll Notification",
        "2026-08-10_3track_roll_notification_format.py",
        "positional",
        (),
        "futures_clean_pass",
    ),
    MessageOption(
        "7",
        "ROLL-10",
        "Proxy Delta CRITICAL Alert (dev script)",
        "2026-08-10_proxy_delta_critical_alert_format.py",
        "positional",
        (),
        "critical_day3",
    ),
    MessageOption(
        "8",
        "ROLL-11",
        "System Healthcheck Alert",
        "2026-08-10_healthcheck_alert_format.py",
        "positional",
        (),
        "multi_issue",
    ),
    MessageOption(
        "9",
        "ROLL-12",
        "Position Health Check Alert",
        "2026-08-10_position_health_alert_format.py",
        "positional",
        (),
        "mixed",
    ),
    MessageOption(
        "10",
        "ROLL-13",
        "3-Track Base Entry Bootstrap Notification",
        "2026-08-11_3track_base_entry_format.py",
        "positional",
        (),
        "all_three",
    ),
    MessageOption(
        "11",
        "ROLL-14",
        "3-Track Overlay Entry Bootstrap Notification",
        "2026-08-11_3track_overlay_entry_format.py",
        "positional",
        (),
        "collar_bootstrap",
    ),
    MessageOption(
        "12",
        "ROLL-15",
        "3-Track Settlement/Roll Command Message",
        "2026-08-11_3track_settlement_roll_format.py",
        "positional",
        (),
        "base_futures_expiring",
    ),
    MessageOption(
        "13",
        "ROLL-16",
        "Proxy Delta CRITICAL Alert (production _run duplicate)",
        "2026-08-11_3track_proxy_delta_critical_alert_format.py",
        "positional",
        (),
        "critical_day3",
    ),
    MessageOption(
        "14",
        "PT-1",
        "EOD PT Summary (cross-strategy positions, live DB/broker — "
        "eod-pt-summary epic, not telegram-markdown-migration)",
        "2026-08-13_eod_pt_summary.py",
        None,
    ),
]


def print_menu() -> None:
    print("\nTelegram Markdown Migration — scratch message probes\n")
    for opt in OPTIONS:
        scen = f" (default scenario: {opt.default_scenario})" if opt.default_scenario else ""
        print(f"  {opt.key:>2}. [{opt.roll}] {opt.label}{scen}")
    print("\n  q. quit")


def run_option(opt: MessageOption, extra_args: list[str]) -> int:
    script_path = SCRATCH_DIR / opt.script
    if not script_path.exists():
        print(f"!! script not found: {script_path}")
        return 1

    cmd = [PYTHON, str(script_path), *extra_args]
    print(f"\n$ {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=SCRATCH_DIR.parent)
    return result.returncode


def resolve_option(token: str) -> MessageOption | None:
    for opt in OPTIONS:
        if opt.key == token or opt.roll.lower() == token.lower():
            return opt
    return None


def main() -> int:
    argv = sys.argv[1:]

    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    if argv and argv[0] == "--list":
        print_menu()
        return 0

    if argv:
        opt = resolve_option(argv[0])
        if opt is None:
            print(f"!! unknown option: {argv[0]!r}. Pass --list to see valid options.")
            return 1
        return run_option(opt, argv[1:])

    # Interactive mode
    while True:
        print_menu()
        choice = input("\nSelect an option (number, ROLL-id, or q): ").strip()
        if choice.lower() in ("q", "quit", "exit"):
            return 0
        opt = resolve_option(choice)
        if opt is None:
            print(f"!! unknown option: {choice!r}")
            continue

        extra_args: list[str] = []
        if opt.scenario_style == "positional":
            scen = input(
                f"Scenario [{opt.default_scenario}] (blank = default, '?' = list scenarios): "
            ).strip()
            if scen == "?":
                run_option(opt, ["--list-scenarios"])
                continue
            if scen:
                extra_args.append(scen)
        elif opt.scenario_style == "--scenario":
            scen = input(
                f"Scenario [{opt.default_scenario}] (blank = default, '?' = list scenarios): "
            ).strip()
            if scen == "?":
                run_option(opt, ["--list-scenarios"])
                continue
            if scen:
                extra_args += ["--scenario", scen]

        send = input("Actually send to Telegram? [y/N]: ").strip().lower()
        if send == "y":
            extra_args.append("--send")

        run_option(opt, extra_args)


if __name__ == "__main__":
    raise SystemExit(main())
