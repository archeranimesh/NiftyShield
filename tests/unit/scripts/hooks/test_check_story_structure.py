"""Unit tests for scripts/hooks/check_story_structure.py."""

import pytest

from scripts.hooks import check_story_structure as css


def _story(folder, *, prompt=True, tasks="tasks.md", extra=None):
    """Build a story folder under ``folder`` and return it."""
    folder.mkdir(parents=True, exist_ok=True)
    if prompt:
        (folder / "prompt.md").write_text("# prompt\n", encoding="utf-8")
    if tasks:
        (folder / tasks).write_text("# tasks\n", encoding="utf-8")
    for name in extra or []:
        (folder / name).write_text("x\n", encoding="utf-8")
    return folder


@pytest.fixture
def plan_dir(tmp_path, monkeypatch):
    """Point the module's REPO_ROOT / PLAN_DIR at a temp docs/plan tree."""
    root = tmp_path
    plan = root / "docs" / "plan"
    plan.mkdir(parents=True)
    monkeypatch.setattr(css, "REPO_ROOT", root)
    monkeypatch.setattr(css, "PLAN_DIR", plan)
    return plan


def test_story_folder_is_clean(tmp_path):
    """A folder with prompt.md + tasks.md produces no findings."""
    folder = _story(tmp_path / "good-story")

    assert css.is_story_folder(folder) is True
    assert css.check_folder(folder) == []


def test_empty_folder_is_flagged(tmp_path):
    """An empty folder is reported as stray."""
    folder = tmp_path / "stray"
    folder.mkdir()

    messages = css.check_folder(folder)
    assert len(messages) == 1
    assert "empty folder" in messages[0]


def test_non_story_non_empty_folder_reports_missing_files(tmp_path):
    """A populated folder that is neither story nor epic names what it lacks."""
    folder = tmp_path / "half"
    folder.mkdir()
    (folder / "notes.md").write_text("stray\n", encoding="utf-8")

    messages = css.check_folder(folder)
    assert len(messages) == 1
    assert "missing prompt.md, tasks.md" in messages[0]


def test_epic_folder_with_story_subdir_is_clean(tmp_path):
    """A container folder is valid when a sub-folder is a story."""
    epic = tmp_path / "epic"
    epic.mkdir()
    (epic / "README.md").write_text("# epic\n", encoding="utf-8")
    _story(epic / "sub-story")

    assert css.is_epic_folder(epic) is True
    assert css.check_folder(epic) == []


def test_legacy_tasks_name_warns_but_stays_a_story(tmp_path):
    """prompt.md + `<name>_tasks.md` is a valid story with a rename warning."""
    folder = _story(tmp_path / "legacy", tasks="legacy_tasks.md")

    assert css.is_story_folder(folder) is True
    messages = css.check_folder(folder)
    assert len(messages) == 1
    assert "legacy '*_tasks.md'" in messages[0]


def test_main_all_fails_on_empty_folder(plan_dir):
    """Audit mode exits 1 when a stray empty folder exists."""
    _story(plan_dir / "ok")
    (plan_dir / "stray").mkdir()

    assert css.main(["--all"]) == 1


def test_main_all_passes_on_legacy_warning_only(plan_dir, capsys):
    """Audit mode exits 0 when the only findings are legacy-name warnings."""
    _story(plan_dir / "ok")
    _story(plan_dir / "legacy", tasks="legacy_tasks.md")

    assert css.main(["--all"]) == 0
    assert "legacy '*_tasks.md'" in capsys.readouterr().out


def test_main_path_mode_flags_the_owning_folder(plan_dir):
    """Passing a file path checks the docs/plan/<slug>/ folder it lives in."""
    bad = plan_dir / "broken"
    bad.mkdir()
    (bad / "stories.md").write_text("orphan\n", encoding="utf-8")

    assert css.main([str(bad / "stories.md")]) == 1


def test_main_excludes_template_folder(plan_dir):
    """_TEMPLATE is skipped by the audit even if it looks irregular."""
    (plan_dir / "_TEMPLATE").mkdir()
    (plan_dir / "_TEMPLATE" / "prompt.md").write_text("# t\n", encoding="utf-8")
    _story(plan_dir / "ok")

    assert css.main(["--all"]) == 0


def test_nested_epic_is_valid(tmp_path):
    """An epic containing a sub-epic that contains a story still validates."""
    epic = tmp_path / "epic"
    _story(epic / "sub-epic" / "leaf-story")

    assert css.is_epic_folder(epic) is True
    assert css.check_folder(epic) == []


def test_staged_added_folders_parses_git_output(plan_dir, monkeypatch):
    """`--staged-added` maps newly-added git paths to their story folders."""
    # folder exists with a stray file but no prompt.md / tasks.md
    _story(plan_dir / "new-story", prompt=False, tasks=None, extra=["stories.md"])

    class _Result:
        stdout = "docs/plan/new-story/stories.md\nREADME.md\n"

    monkeypatch.setattr(css.subprocess, "run", lambda *a, **k: _Result())

    assert css._staged_added_folders() == [plan_dir / "new-story"]
    assert css.main(["--staged-added"]) == 1
