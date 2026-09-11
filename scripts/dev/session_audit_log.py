#!/usr/bin/env python3
"""Append/read per-session feature-usage rows for the weekly-audit skill.

`session-close` computes protocol-compliance and token-efficiency counts for
every session it closes. This module gives it a durable place to record one
row per session (``session_audit.jsonl`` at the repo root, committed) so the
on-demand `weekly-audit` skill can aggregate a week of small JSON rows
instead of re-parsing every session's raw transcript.

Usage::

    python -m scripts.dev.session_audit_log read --since 2026-09-04
    python -m scripts.dev.session_audit_log append --session-id sess-1 \\
        --date 2026-09-04 --project NiftyShield --graph-calls 3 \\
        --raw-read-violations 0 --bash-output-violations 0 --subagent-spawns 1
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import structlog

from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.dev.session_audit_log"
logger = structlog.get_logger(_SCRIPT_NAME)

_DEFAULT_LOG_PATH = Path(__file__).resolve().parents[2] / "session_audit.jsonl"


@dataclass(frozen=True)
class SessionAuditRow:
    """One session's feature-usage summary, as logged by `session-close`.

    Args:
        session_id: Claude Code session id (transcript filename stem).
        date: Session close date, ``YYYY-MM-DD``.
        project: Repo-slug or project name the session ran in.
        graph_calls: Count of `codebase-memory-mcp` graph tool calls.
        raw_read_violations: Rule 0 violations (Step 3a).
        bash_output_violations: Rule 1 violations (Step 3b).
        subagent_spawns: Count of subagents/forks spawned.
        skills_invoked: Names of skills invoked this session.
        autotrigger_fires: Agent name -> whether it fired (Step 3c).
        suggestions_count: Number of Step 4 suggestions produced.
    """

    session_id: str
    date: str
    project: str
    graph_calls: int
    raw_read_violations: int
    bash_output_violations: int
    subagent_spawns: int
    skills_invoked: list[str] = field(default_factory=list)
    autotrigger_fires: dict[str, bool] = field(default_factory=dict)
    suggestions_count: int = 0


def append_row(row: SessionAuditRow, *, path: Path = _DEFAULT_LOG_PATH) -> None:
    """Append ``row`` as one JSON line to the audit log at ``path``.

    Args:
        row: The row to record.
        path: Log file path. Created if it does not yet exist.
    """
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(row), sort_keys=True))
        f.write("\n")
    logger.info("session_audit_row_appended", session_id=row.session_id, date=row.date)


def read_range(since_date: str, *, path: Path = _DEFAULT_LOG_PATH) -> list[SessionAuditRow]:
    """Read rows on or after ``since_date`` from the audit log.

    Args:
        since_date: Inclusive lower bound, ``YYYY-MM-DD``. Compared as a
            plain string, which sorts correctly for this format.
        path: Log file path. A missing file yields an empty list.

    Returns:
        Matching rows in file order.
    """
    if not path.is_file():
        return []

    rows: list[SessionAuditRow] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if data.get("date", "") >= since_date:
                rows.append(SessionAuditRow(**data))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Append/read per-session feature-usage rows in session_audit.jsonl."
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    read_parser = subparsers.add_parser("read", help="Read rows since a date")
    read_parser.add_argument("--since", required=True, help="Inclusive lower bound, YYYY-MM-DD")

    append_parser = subparsers.add_parser("append", help="Append one session's row")
    append_parser.add_argument("--session-id", required=True)
    append_parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    append_parser.add_argument("--project", required=True)
    append_parser.add_argument("--graph-calls", type=int, required=True)
    append_parser.add_argument("--raw-read-violations", type=int, required=True)
    append_parser.add_argument("--bash-output-violations", type=int, required=True)
    append_parser.add_argument("--subagent-spawns", type=int, required=True)
    append_parser.add_argument("--skills-invoked", default="[]", help="JSON list of skill names")
    append_parser.add_argument(
        "--autotrigger-fires", default="{}", help="JSON object of agent name -> bool"
    )
    append_parser.add_argument("--suggestions-count", type=int, default=0)

    args = parser.parse_args()

    if args.action == "read":
        rows = read_range(args.since)
        print(json.dumps([asdict(r) for r in rows], indent=2, sort_keys=True))
        logger.info("session_audit_log_read", since=args.since, row_count=len(rows))
        return

    row = SessionAuditRow(
        session_id=args.session_id,
        date=args.date,
        project=args.project,
        graph_calls=args.graph_calls,
        raw_read_violations=args.raw_read_violations,
        bash_output_violations=args.bash_output_violations,
        subagent_spawns=args.subagent_spawns,
        skills_invoked=json.loads(args.skills_invoked),
        autotrigger_fires=json.loads(args.autotrigger_fires),
        suggestions_count=args.suggestions_count,
    )
    append_row(row)
    logger.info("session_audit_log_append", session_id=row.session_id, date=row.date)


if __name__ == "__main__":
    setup_logging()
    main()
