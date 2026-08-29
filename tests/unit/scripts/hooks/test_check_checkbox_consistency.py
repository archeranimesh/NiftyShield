"""Unit tests for scripts/hooks/check_checkbox_consistency.py."""

from pathlib import Path

import pytest

from scripts.hooks import check_checkbox_consistency as ccc

CLEAN_TASKS = """\
# Demo — tasks

- [x] **D-1** — first thing done.
- [ ] **D-2** — second thing open.

## Epic done when

- **D-1** — first criterion.
- **D-2** — second criterion.
"""

SUMMARY_CHECKBOX_TASKS = """\
# Demo — tasks

- [x] **D-1** — first thing done.
- [ ] **D-2** — second thing open.

## Epic done when

- [x] **D-1** — first criterion.
- [ ] **D-2** — second criterion.
"""

DRIFT_TASKS = """\
# Demo — tasks

- [x] **D-1** — done here.
- [ ] **D-2** — open.

## Notes

- [ ] **D-1** — but open here.
"""


def _write(tmp_path: Path, name: str, body: str) -> Path:
    folder = tmp_path / "docs" / "plan" / name
    folder.mkdir(parents=True)
    task_file = folder / "tasks.md"
    task_file.write_text(body, encoding="utf-8")
    return task_file


@pytest.fixture
def plan_tree(tmp_path, monkeypatch):
    """Point the module's repo paths at a temp docs/plan tree."""
    plan = tmp_path / "docs" / "plan"
    plan.mkdir(parents=True)
    monkeypatch.setattr(ccc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(ccc, "PLAN_DIR", plan)
    monkeypatch.setattr(ccc, "PLAN_README", plan / "README.md")
    monkeypatch.setattr(ccc, "BUGS_TASK", tmp_path / "docs" / "bugs" / "task.md")
    return plan


def test_clean_file_has_no_findings(tmp_path):
    """A prose-only Epic-done block with single-checkbox ids is clean."""
    task_file = _write(tmp_path, "clean", CLEAN_TASKS)

    assert ccc.check_file(task_file) == []


def test_checkbox_in_summary_block_is_flagged(tmp_path):
    """A `- [ ]` id line inside `## Epic done when` is a convention-a violation."""
    task_file = _write(tmp_path, "summary-boxes", SUMMARY_CHECKBOX_TASKS)

    findings = ccc.check_file(task_file)
    assert len(findings) == 2
    assert all("inside a summary block" in f for f in findings)


def test_disagreeing_state_for_same_id_is_flagged(tmp_path):
    """The same id with two different checkbox states in one file is drift."""
    task_file = _write(tmp_path, "drift", DRIFT_TASKS)

    findings = ccc.check_file(task_file)
    assert len(findings) == 1
    assert "disagreeing checkbox state" in findings[0]
    assert "D-1" in findings[0]


def test_readme_pointer_at_done_id_is_flagged(plan_tree):
    """A README `next:` marker pointing at an already-[x] id is flagged."""
    _write(plan_tree.parent.parent, "story-a", "# a\n\n- [x] **A-1** — done.\n")
    (plan_tree / "README.md").write_text(
        "**`story-a/`** · \U0001f504 In progress · next: **A-1**\n",
        encoding="utf-8",
    )

    findings = ccc.check_readme_pointers()
    assert len(findings) == 1
    assert "already [x]" in findings[0]


def test_readme_pointer_at_open_id_is_clean(plan_tree):
    """A README `next:` marker pointing at an open id produces nothing."""
    _write(plan_tree.parent.parent, "story-b", "# b\n\n- [ ] **B-1** — open.\n")
    (plan_tree / "README.md").write_text("**`story-b/`** · next: **B-1**\n", encoding="utf-8")

    assert ccc.check_readme_pointers() == []


def test_main_all_exits_1_on_finding(plan_tree, capsys):
    """Audit mode returns 1 and prints the offending line when drift exists."""
    _write(plan_tree.parent.parent, "bad", SUMMARY_CHECKBOX_TASKS)

    assert ccc.main(["--all"]) == 1
    assert "summary block" in capsys.readouterr().out


def test_main_all_exits_0_when_clean(plan_tree):
    """Audit mode returns 0 when every task file follows the convention."""
    _write(plan_tree.parent.parent, "ok", CLEAN_TASKS)

    assert ccc.main(["--all"]) == 0


def test_main_path_mode_checks_owning_task_file(plan_tree):
    """Passing a folder path checks that folder's tasks.md."""
    _write(plan_tree.parent.parent, "scoped", DRIFT_TASKS)

    assert ccc.main([str(plan_tree / "scoped")]) == 1


def test_template_folder_is_excluded(plan_tree):
    """_TEMPLATE is skipped by the audit even if it carries checkboxes in a summary."""
    _write(plan_tree.parent.parent, "_TEMPLATE", SUMMARY_CHECKBOX_TASKS)
    _write(plan_tree.parent.parent, "ok", CLEAN_TASKS)

    assert ccc.main(["--all"]) == 0


SUBHEADER_IN_SUMMARY = """\
# Demo — tasks

- [x] **D-1** — done.

## Epic done when

### Sub-criteria

- [x] **D-1** — still inside the summary block via an h3 sub-header.
"""


def test_subheader_does_not_exit_summary_block(tmp_path):
    """A deeper header under `## Epic done when` stays inside the summary block."""
    task_file = _write(tmp_path, "subhdr", SUBHEADER_IN_SUMMARY)

    findings = ccc.check_file(task_file)
    assert len(findings) == 1
    assert "inside a summary block" in findings[0]


def test_bugs_task_file_checked_via_directory_path(plan_tree, tmp_path):
    """Passing `docs/bugs/` as a directory resolves the singular task.md."""
    bugs = tmp_path / "docs" / "bugs"
    bugs.mkdir(parents=True)
    (bugs / "task.md").write_text(DRIFT_TASKS, encoding="utf-8")

    assert ccc.main([str(bugs)]) == 1


STORY_DONE_WHEN_CHECKBOX = """\
# Demo — tasks

- [ ] **D-1** — open.

## Story done when

- [ ] **D-1** — criterion mistakenly kept as a checkbox.
"""


def test_story_done_when_block_flags_checkboxes(tmp_path):
    """`## Story done when` is a summary block — a `- [ ]` id line in it is a violation."""
    task_file = _write(tmp_path, "story-done", STORY_DONE_WHEN_CHECKBOX)

    findings = ccc.check_file(task_file)
    assert len(findings) == 1
    assert "inside a summary block" in findings[0]


CANONICAL_TAIL_CLEAN = """\
# Demo — tasks

- [x] **D-1** — done. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 7b6d05f
- [ ] **D-2** — open. | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>
"""


def test_canonical_tail_clean_file_has_no_findings(tmp_path):
    """A ticked line with a real SHA and an open line with the placeholder both pass."""
    task_file = _write(tmp_path, "tail-clean", CANONICAL_TAIL_CLEAN)

    assert ccc.check_file(task_file) == []


def test_ticked_task_with_placeholder_sha_is_flagged(tmp_path):
    """`- [x]` with `SHA: <—>` on a canonical tail is a state/SHA disagreement."""
    body = (
        "# t\n\n- [x] **D-1** — done. "
        "| Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>\n"
    )
    task_file = _write(tmp_path, "ticked-placeholder", body)

    findings = ccc.check_file(task_file)
    assert len(findings) == 1
    assert "ticked but SHA" in findings[0]


def test_open_task_with_real_sha_is_flagged(tmp_path):
    """`- [ ]` with a real hex SHA on a canonical tail is a state/SHA disagreement."""
    body = (
        "# t\n\n- [ ] **D-1** — open. "
        "| Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 7b6d05f\n"
    )
    task_file = _write(tmp_path, "open-realsha", body)

    findings = ccc.check_file(task_file)
    assert len(findings) == 1
    assert "unchecked but SHA" in findings[0]


def test_unknown_review_value_is_flagged(tmp_path):
    """A canonical tail whose Review field is not a known gate name is flagged."""
    body = (
        "# t\n\n- [ ] **D-1** — open. "
        "| Owner: Claude | Model: claude-sonnet-5 | Review: maybe | SHA: <—>\n"
    )
    task_file = _write(tmp_path, "bad-review", body)

    findings = ccc.check_file(task_file)
    assert len(findings) == 1
    assert "Review: 'maybe'" in findings[0]


def test_canonical_tail_on_continuation_line_is_validated(tmp_path):
    """The tail is picked up even when it wraps onto an indented continuation line."""
    body = (
        "# t\n\n"
        "- [x] **D-1** — a long description that wraps across\n"
        "  two lines. | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>\n"
    )
    task_file = _write(tmp_path, "wrapped-tail", body)

    findings = ccc.check_file(task_file)
    assert len(findings) == 1
    assert "ticked but SHA" in findings[0]


def test_in_progress_task_with_real_sha_is_flagged(tmp_path):
    """`- [~]` (in progress) is treated as open — a real SHA on its canonical tail is flagged."""
    body = (
        "# t\n\n- [~] **D-1** — in progress. "
        "| Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 7b6d05f\n"
    )
    task_file = _write(tmp_path, "wip-realsha", body)

    findings = ccc.check_file(task_file)
    assert len(findings) == 1
    assert "unchecked but SHA" in findings[0]


LEGACY_TAILS_SKIPPED = """\
# Demo — tasks

- [x] **L-1** — legacy three-field tail.
  | Owner: Claude | Model: claude-sonnet-5 | SHA: abc1234
- [x] **L-2** — prose-laden review note, no trailing SHA field.
  | Owner: Claude | Model: Sonnet | Review: code-reviewer (not financial-logic tier) — judgment call
- [x] **L-3** — bare closing SHA only. | SHA: def5678
"""


def test_legacy_tails_are_grandfathered(tmp_path):
    """Legacy `| Owner | Model | SHA` and prose `| Review:` tails are skipped, not flagged."""
    task_file = _write(tmp_path, "legacy-tails", LEGACY_TAILS_SKIPPED)

    assert ccc.check_file(task_file) == []
