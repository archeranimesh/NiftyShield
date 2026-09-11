from pathlib import Path

from scripts.dev.session_audit_log import SessionAuditRow, append_row, read_range


def _row(session_id: str, date: str) -> SessionAuditRow:
    return SessionAuditRow(
        session_id=session_id,
        date=date,
        project="NiftyShield",
        graph_calls=3,
        raw_read_violations=0,
        bash_output_violations=0,
        subagent_spawns=1,
        skills_invoked=["commit"],
        autotrigger_fires={"test-runner": True, "code-reviewer": True},
        suggestions_count=0,
    )


def test_append_then_read_range_returns_row(tmp_path: Path) -> None:
    log_path = tmp_path / "session_audit.jsonl"
    row = _row("sess-1", "2026-09-10")

    append_row(row, path=log_path)
    rows = read_range("2026-09-01", path=log_path)

    assert rows == [row]


def test_read_range_excludes_rows_before_since_date(tmp_path: Path) -> None:
    log_path = tmp_path / "session_audit.jsonl"
    append_row(_row("sess-old", "2026-09-01"), path=log_path)
    append_row(_row("sess-new", "2026-09-10"), path=log_path)

    rows = read_range("2026-09-05", path=log_path)

    assert [r.session_id for r in rows] == ["sess-new"]


def test_read_range_missing_file_returns_empty(tmp_path: Path) -> None:
    rows = read_range("2026-09-01", path=tmp_path / "does_not_exist.jsonl")

    assert rows == []
