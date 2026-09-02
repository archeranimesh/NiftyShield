"""Tests for scripts.dev.token_audit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.dev.token_audit import (
    Record,
    attribute,
    parse_records,
    render_json,
    render_table,
    resolve_transcript,
)

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "transcripts" / "sample_session.jsonl"


@pytest.fixture
def fake_repo_root(tmp_path: Path) -> Path:
    (tmp_path / "CLAUDE.md").write_text("x" * 40, encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("y" * 20, encoding="utf-8")
    return tmp_path


def test_attribute_sums_to_total() -> None:
    records = [
        Record(0, "assistant_text", "assistant", 40, False),
        Record(1, "tool_result", "Bash", 100, True),
        Record(2, "assistant_text", "assistant", 15, False),
        Record(3, "subagent_reports", "subagent", 12, True),
        Record(4, "subagent_internal", "subagent", 2000, False),
        Record(5, "project_docs", "docs", 300, True),
        Record(6, "system_prompt", "first_turn_prefix", 12000, False),
    ]

    buckets = attribute(records)

    assert sum(buckets.values()) == sum(r.tokens for r in records)
    assert buckets["tool_results:Bash"] == 100
    assert buckets["assistant_text"] == 55
    assert buckets["system_prompt"] == 12000


def test_subagent_internal_counted_separately(fake_repo_root: Path) -> None:
    records = parse_records(FIXTURE, repo_root=fake_repo_root)

    buckets = attribute(records)

    assert buckets["subagent_internal"] == 2000
    assert buckets.get("tool_results:subagent", 0) == 0
    assert buckets["subagent_reports"] != buckets["subagent_internal"]
    assert buckets["subagent_reports"] > 0


def test_parse_records_full_fixture_buckets(fake_repo_root: Path) -> None:
    buckets = attribute(parse_records(FIXTURE, repo_root=fake_repo_root))

    assert buckets["system_prompt"] == 12000
    assert buckets["assistant_text"] == 55
    assert buckets["tool_results:Bash"] == 24
    assert buckets["subagent_reports"] == 28
    assert buckets["subagent_internal"] == 2000
    assert buckets["project_docs"] == 15


def test_resolve_transcript_bad_arg_raises() -> None:
    with pytest.raises(FileNotFoundError, match="does-not-exist-xyz"):
        resolve_transcript("this-session-id-does-not-exist-xyz")


def test_resolve_transcript_explicit_path() -> None:
    assert resolve_transcript(str(FIXTURE)) == FIXTURE


def test_render_table_orders_by_tokens_desc() -> None:
    buckets = {"small": 5, "big": 500, "medium": 50}

    table = render_table(buckets)

    assert table.index("big") < table.index("medium") < table.index("small")


def test_json_mode_round_trips() -> None:
    buckets = {"assistant_text": 55, "tool_results:Bash": 24}

    parsed = json.loads(render_json(buckets))

    assert parsed["buckets"] == buckets
    assert parsed["total"] == sum(buckets.values())
