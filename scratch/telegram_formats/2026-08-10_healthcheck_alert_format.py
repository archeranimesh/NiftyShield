"""Scratch script — System Healthcheck alert Telegram message formatting.

Message #5 in docs/plan/telegram-markdown-migration/TODO.md's "Confirmed missing" queue —
`scripts/healthcheck.py::main`, lines 165-178 (confirmed via `search_graph` +
`get_code_snippet`, not the TODO.md grep excerpt alone):

    if has_issue:
        alert_body = "\n".join(messages)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        alert_msg = f"⚠️ NiftyShield Healthcheck — {now_str} IST\n{alert_body}"
        ...
        success = await notifier.send(alert_msg)

`messages` (list[str]) is built by `run_checks()` (same file, lines 35-120) — a fixed set of
5 checks, each appending ONE already-formatted string (✅/❌/⚠️ prefix baked in).

**backbone/ (MD-1..MD-5) status as of this session: NOT shipped** — confirmed via
`search_graph("mdcode")` / `search_graph("escape_markdown")`, both zero results. This script
inlines its own copy of `escape_markdown()`, matching MD-1's exact spec in
`docs/plan/telegram-markdown-migration/backbone/stories.md`.

**v1 draft (superseded, 2026-08-10):** a straight bold-headline + verbatim-escaped-line format
(one line per `run_checks()` message, unmodified wording). Rejected by Animesh in favor of the
v2 grouped/status-word shape below — see "Elimination trail".

**v2 — CONFIRMED SHAPE (2026-08-10, Animesh's exact counter-proposal, not yet on-device
verified — sandbox here has no working venv/aiohttp, see "Known sandbox limitation" below):**

    ⚠️ NIFTYSHIELD: DEGRADED [12:17]

    🚨 ACTION REQUIRED:
    ❌ Daily Snapshot: MISSING (Today)
    ⚠️ Paper NAV: MISSING (Today)
    ⚠️ Disk Space: LOW (450.2 MB)

    ✅ SYSTEMS NORMAL: DB Access, VIX Data

**Elimination trail:**
1. v1 rendered `run_checks()`'s existing message strings verbatim (one line each, raw
   `daily_snapshots`/`paper_nav_snapshots` keys, "no row for today"/"MB free" prose). Rejected —
   Animesh's counter-proposal groups by severity (issues vs normal) instead of listing every
   check in original order, renames raw snake_case keys to human labels ("Daily Snapshot" not
   "daily_snapshots" — also sidesteps needing to escape the underscore at all), collapses each
   line to a `Label: STATUS_WORD (detail)` shape instead of free prose, and folds all-normal
   checks into one compact inline summary line rather than one line per pass.
2. **This is NOT a drop-in re-render of the same `messages: list[str]` — it needs structured
   input.** Parsing "✅ DB: accessible" back into `(label="DB Access", severity=ok)` via string
   matching would repeat the exact brittle-string-parsing anti-pattern this epic already
   rejected once (`ROLL-7`'s `_check_reentry` `blocked_reason` splitting). The real
   implementation therefore needs `run_checks()` itself refactored to return
   `list[CheckResult]` (structured: key, label, severity, status_word, detail) instead of
   `list[str]` — `main()`'s message-building then consumes that structured list, and the
   existing plain-string `messages` return value would need an in-place format change (a
   breaking change to `run_checks()`'s signature/tests, not just to `main()`'s alert_msg
   f-string). Flagging explicitly for whoever picks up the real `ROLL-*` task — bigger lift
   than the v1 draft, same class of scope-increase `ROLL-7`/`ROLL-9` already hit in this epic.
3. Overall status word is a single fixed `DEGRADED` for any `has_issue=True` state — matches
   `run_checks()`'s existing boolean model (no distinct "critical vs warning-only" overall tier
   exists today, even though Animesh's example mixes a ❌ and two ⚠️ items under one `DEGRADED`
   headline). Not inventing a `DOWN`/`CRITICAL` overall tier in this task — would need its own
   design decision (e.g. "DOWN only if DB is inaccessible") that wasn't part of what was
   confirmed; flag as a possible future refinement, not assumed now.
4. Timestamp drops the date and the `IST` suffix from v1 (`[12:17]` only, no `YYYY-MM-DD` no
   `IST` label) — Animesh's example, taken as confirmed intentional (healthcheck fires same-day,
   date is redundant; IST is the project's only timezone, redundant to spell out every alert).
5. `[12:17]` — square brackets around the time are new punctuation not in v1; both `[` and `]`
   are MarkdownV2-reserved, escaped like everything else.

**Known sandbox limitation (this session):** `.venv` in the mounted repo folder is a symlink
back to the host machine's Python (`/Users/abhadra/...`), not usable inside this sandbox, and
the sandbox's own Python lacks `aiohttp`/`src.config.settings`'s dependencies. `--send` could
not be exercised from this session — Animesh needs to run this script from his own machine to
verify on-device rendering before this format is treated as fully confirmed.

Run from repo root with the project's normal venv active:
    python -m scratch.2026-08-10_healthcheck_alert_format <scenario> [--send]
    python -m scratch.2026-08-10_healthcheck_alert_format --list-scenarios
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import aiohttp

# Allow running as a plain script (python scratch/foo.py) as well as -m.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402

# ── Inline copy of MD-1's escape_markdown() (backbone/ not shipped yet — see module docstring) ──

MARKDOWNV2_RESERVED = "_*[]()~`>#+-=|{}.!"


def escape_markdown(text: str) -> str:
    """Backslash-escape MarkdownV2 reserved characters in free text.

    Mirrors docs/plan/telegram-markdown-migration/backbone/stories.md MD-1 spec exactly —
    inline copy pending the real src/notifications/markdown.py landing.
    """
    out = []
    for ch in text:
        if ch in MARKDOWNV2_RESERVED:
            out.append("\\")
        out.append(ch)
    return "".join(out)


Severity = Literal["ok", "warn", "critical"]

_SEVERITY_EMOJI: dict[Severity, str] = {"ok": "✅", "warn": "⚠️", "critical": "❌"}


@dataclass(frozen=True)
class CheckResult:
    """One healthcheck's structured outcome — what `run_checks()` would need to return
    instead of pre-formatted strings for the real implementation (see module docstring,
    Elimination trail #2)."""

    label: str
    severity: Severity
    status_word: str  # only meaningful when severity != "ok"; e.g. "MISSING", "LOW", "STALE"
    detail: str | None = None  # e.g. "Today", "450.2 MB", "3 days" — parenthesized if present


# ── Sample data — structured equivalents of the real scenarios run_checks() produces
# today (as plain strings) in scripts/healthcheck.py. See Elimination trail #2 for why this
# scratch script uses structured CheckResult objects rather than re-parsing the current
# list[str] output. ──

SCENARIOS: dict[str, list[CheckResult]] = {
    "single_issue": [
        CheckResult("DB Access", "ok", ""),
        CheckResult("Daily Snapshot", "ok", ""),
        CheckResult("Paper NAV", "ok", ""),
        CheckResult("VIX Data", "warn", "STALE", "3 days"),
        CheckResult("Disk Space", "ok", ""),
    ],
    "multi_issue": [
        CheckResult("DB Access", "ok", ""),
        CheckResult("Daily Snapshot", "critical", "MISSING", "Today"),
        CheckResult("Paper NAV", "warn", "MISSING", "Today"),
        CheckResult("VIX Data", "ok", ""),
        CheckResult("Disk Space", "warn", "LOW", "450.2 MB"),
    ],
    "db_down": [
        CheckResult("DB Access", "critical", "INACCESSIBLE"),
        CheckResult("Daily Snapshot", "critical", "SKIPPED", "DB error"),
        CheckResult("Paper NAV", "warn", "SKIPPED", "DB error"),
        CheckResult("VIX Data", "ok", ""),
        CheckResult("Disk Space", "ok", ""),
    ],
    "exception_text": [
        CheckResult("DB Access", "ok", ""),
        CheckResult("Daily Snapshot", "ok", ""),
        CheckResult("Paper NAV", "ok", ""),
        CheckResult("VIX Data", "warn", "ERROR", "Connection refused: (errno 111)"),
        CheckResult("Disk Space", "warn", "ERROR", "No such file or directory: '/data/portfolio'"),
    ],
}


def build_message(results: list[CheckResult], now: datetime | None = None) -> str:
    """System Healthcheck alert, MarkdownV2-safe — v2 grouped/status-word shape.

    Shape (CONFIRMED 2026-08-10, Animesh's exact counter-proposal — see module docstring):
        ⚠️ NIFTYSHIELD: DEGRADED [<time>]
        <blank line>
        🚨 ACTION REQUIRED:
        <one "{emoji} {label}: {status_word}[ ({detail})]" line per non-ok check, original order>
        <blank line>
        ✅ SYSTEMS NORMAL: {comma-joined labels of ok checks}

    If every check is "ok", `has_issue` upstream is False and `main()` never calls this at all
    (unchanged from today) — this function does not special-case an empty ACTION REQUIRED
    section because that state is unreachable from the real call site.

    If every check is non-ok (SYSTEMS NORMAL would be empty), the trailing "✅ SYSTEMS NORMAL:"
    line is omitted entirely rather than printed with nothing after the colon.
    """
    if now is None:
        now = datetime.now()
    time_str = now.strftime("%H:%M")
    headline = f"⚠️ NIFTYSHIELD: DEGRADED {escape_markdown(f'[{time_str}]')}"

    issues = [r for r in results if r.severity != "ok"]
    normal = [r for r in results if r.severity == "ok"]

    lines = [headline, ""]

    lines.append("🚨 ACTION REQUIRED:")
    for r in issues:
        emoji = _SEVERITY_EMOJI[r.severity]
        tail = f" {escape_markdown(f'({r.detail})')}" if r.detail else ""
        lines.append(f"{emoji} {escape_markdown(r.label)}: {escape_markdown(r.status_word)}{tail}")

    if normal:
        lines.append("")
        normal_labels = escape_markdown(", ".join(r.label for r in normal))
        lines.append(f"✅ SYSTEMS NORMAL: {normal_labels}")

    return "\n".join(lines)


async def send_markdown_v2(bot_token: str, chat_id: str, message: str) -> bool:
    """Send with parse_mode=MarkdownV2 — per epic decision, not legacy Markdown/HTML."""
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "MarkdownV2"}
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, json=payload) as resp:
                # Don't raise_for_status() before reading the body — Telegram puts the
                # actual parse-error reason in the JSON "description" field even on a 400.
                resp_data = await resp.json()
                if not resp_data.get("ok"):
                    print(f"!! Telegram API error ({resp.status}): {resp_data.get('description')}")
                return bool(resp_data.get("ok"))
    except Exception as exc:  # Intentional: isolate all API failures, scratch probe only
        print(f"!! send failed: {exc}")
        return False


async def main() -> None:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "multi_issue"
    if scenario == "--list-scenarios":
        print("\n".join(SCENARIOS.keys()))
        return
    if scenario not in SCENARIOS:
        print(f"!! unknown scenario {scenario!r}; use one of: {', '.join(SCENARIOS)}")
        return

    text = build_message(SCENARIOS[scenario])
    print(f"--- scenario: {scenario} ---")
    print(text)
    print("---")

    if "--send" not in sys.argv:
        print("(print-only; pass --send to actually post to Telegram)")
        return

    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        print(
            "\n!! TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in environment — "
            "cannot send. Aborting without sending anything."
        )
        return

    ok = await send_markdown_v2(settings.telegram_bot_token, settings.telegram_chat_id, text)
    print(f"\nsend_markdown_v2() returned {ok}")
    if not ok:
        print("!! send failed — check logs / credentials before retrying")


if __name__ == "__main__":
    asyncio.run(main())
