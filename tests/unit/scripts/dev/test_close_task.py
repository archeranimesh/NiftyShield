"""Tests for scripts.dev.close_task."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.dev.close_task import (
    CloseTaskError,
    add_session_log,
    advance_open,
    close_task,
    main,
    next_unchecked,
    rewrite_pointers,
    tick_task,
)

_TASKS = """# Story — tasks

**Open: PC-2.**

- [x] **PC-1** — scaffold | Owner: Claude | SHA: aaa1111
- [ ] **PC-2** — core | Owner: Antigravity |
  Model: n/a | Review: code-reviewer | SHA: —
- [ ] **PC-3** — series | Owner: Claude | SHA: —
"""


def test_tick_task_handles_wrapped_item() -> None:
    out = tick_task(_TASKS, "PC-2", "bbb2222")
    assert "- [x] **PC-2**" in out
    assert "SHA: bbb2222" in out
    assert "- [ ] **PC-3**" in out
    assert out.count("SHA: —") == 1


@pytest.mark.parametrize("task", ["PC-1", "PC-9"])
def test_tick_task_rejects_done_or_missing(task: str) -> None:
    with pytest.raises(CloseTaskError):
        tick_task(_TASKS, task, "x")


def test_tick_task_requires_sha_placeholder() -> None:
    text = "- [ ] **PC-2** — core | SHA: abc\n"
    with pytest.raises(CloseTaskError):
        tick_task(text, "PC-2", "x")


def test_advance_open_single_id_moves_to_next_unchecked() -> None:
    ticked = tick_task(_TASKS, "PC-2", "bbb2222")
    assert next_unchecked(ticked) == "PC-3"
    assert "**Open: PC-3.**" in advance_open(ticked, "PC-2")


def test_advance_open_list_drops_closed_id() -> None:
    text = "**Open: GS-1, GS-2, GS-3.**\n- [ ] **GS-2** — x | SHA: —\n"
    assert "**Open: GS-2, GS-3.**" in advance_open(text, "GS-1")


def test_advance_open_last_task_says_complete() -> None:
    text = "**Open: PC-3.**\n- [x] **PC-3** — x | SHA: abc\n"
    assert "**Open: none — complete.**" in advance_open(text, "PC-3")


def test_rewrite_pointers_standard_forms_and_miss() -> None:
    text = "start: PC-3 done, next **PC-4** here (PC-3 done) and next **PC-4** (file.py)"
    out, n = rewrite_pointers(text, "PC", "PC-4", "PC-5", todos=True)
    assert out.count("PC-5") == 2 and n == 3
    _, none = rewrite_pointers("free prose only", "PC", "PC-4", "PC-5", todos=True)
    assert none == 0


def test_add_session_log_inserts_under_heading() -> None:
    out = add_session_log("# T\n\n## Session Log\n- old\n", "- new")
    assert out.split("\n")[3] == "- new"
    with pytest.raises(CloseTaskError):
        add_session_log("# no heading", "- new")


def _make_repo(tmp_path: Path) -> Path:
    story = tmp_path / "docs/plan/epic/story"
    story.mkdir(parents=True)
    (story / "tasks.md").write_text(_TASKS)
    (story.parent / "README.md").write_text("| story | 🟡 In progress (PC-1 done) |\n")
    (tmp_path / "docs/plan/README.md").write_text("epic PC-1 done, next **PC-2**\n")
    (tmp_path / "TODOS.md").write_text("6. item — next **PC-2** (f.py)\n\n## Session Log\n- old\n")
    return story / "tasks.md"


def test_close_task_end_to_end(tmp_path: Path) -> None:
    tasks = _make_repo(tmp_path)
    report = close_task(tasks, "PC-2", "bbb2222", "did it", tmp_path, "2026-10-04")
    assert "next unchecked: PC-3" in report[0]
    assert "SHA: bbb2222" in tasks.read_text()
    assert "(PC-2 done)" in (tasks.parent.parent / "README.md").read_text()
    assert "PC-2 done, next **PC-3**" in (tmp_path / "docs/plan/README.md").read_text()
    todos = (tmp_path / "TODOS.md").read_text()
    assert "next **PC-3**" in todos
    assert "- [2026-10-04] story PC-2 closed (`bbb2222`): did it" in todos


def test_close_task_writes_nothing_on_failure(tmp_path: Path) -> None:
    tasks = _make_repo(tmp_path)
    before = tasks.read_text()
    (tmp_path / "TODOS.md").write_text("no log heading\n")
    with pytest.raises(CloseTaskError):
        close_task(tasks, "PC-2", "bbb2222", "x", tmp_path, "2026-10-04")
    assert tasks.read_text() == before


def test_main_returns_1_on_bad_task(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tasks = _make_repo(tmp_path)
    rc = main(
        [str(tasks), "--task", "PC-9", "--sha", "x", "--summary", "s", "--root", str(tmp_path)]
    )
    assert rc == 1
    assert "not found" in capsys.readouterr().err


def test_advance_open_tolerates_trailing_whitespace() -> None:
    text = "**Open: PC-2.**  \n- [ ] **PC-3** — x | SHA: —\n"
    assert "**Open: PC-3.**" in advance_open(text, "PC-2")


def test_close_task_last_task_skips_pointer_rewrites(tmp_path: Path) -> None:
    tasks = _make_repo(tmp_path)
    tasks.write_text("**Open: PC-2.**\n\n- [ ] **PC-2** — core | SHA: —\n")
    plan_readme = tmp_path / "docs/plan/README.md"
    before = plan_readme.read_text()
    report = close_task(tasks, "PC-2", "bbb2222", "done", tmp_path, "2026-10-04")
    assert any("story complete" in line for line in report)
    assert "**Open: none — complete.**" in tasks.read_text()
    assert plan_readme.read_text() == before


def test_main_happy_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tasks = _make_repo(tmp_path)
    argv = [str(tasks), "--task", "PC-2", "--sha", "bbb2222", "--summary", "s"]
    rc = main([*argv, "--root", str(tmp_path), "--date", "2026-10-04"])
    assert rc == 0
    assert "ticked PC-2" in capsys.readouterr().out
