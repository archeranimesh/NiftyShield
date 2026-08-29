"""Unit tests for scripts/dev/hooks/check_story_structure.py."""

import pytest

from scripts.dev.hooks import check_story_structure as css


def _story(folder, *, prompt=True, tasks="tasks.md", stories="stories.md", extra=None):
    """Build a (by default fully-conforming) story folder under ``folder`` and return it."""
    folder.mkdir(parents=True, exist_ok=True)
    if prompt:
        (folder / "prompt.md").write_text("# prompt\n", encoding="utf-8")
    if tasks:
        (folder / tasks).write_text("# tasks\n", encoding="utf-8")
    if stories:
        (folder / stories).write_text("# stories\n", encoding="utf-8")
    for name in extra or []:
        (folder / name).write_text("x\n", encoding="utf-8")
    return folder


def _epic(folder, *, prompt=True, readme=True):
    """Build an epic root with one conforming sub-story and return the root."""
    folder.mkdir(parents=True, exist_ok=True)
    if prompt:
        (folder / "prompt.md").write_text("# router\n", encoding="utf-8")
    if readme:
        (folder / "README.md").write_text("# epic\n", encoding="utf-8")
    _story(folder / "sub-story")
    return folder


def _levels(findings):
    return {f.level for f in findings}


def _messages(findings):
    return " ".join(f.message for f in findings)


@pytest.fixture
def plan_dir(tmp_path, monkeypatch):
    """Point the module's REPO_ROOT / PLAN_DIR at a temp docs/plan tree."""
    root = tmp_path
    plan = root / "docs" / "plan"
    plan.mkdir(parents=True)
    monkeypatch.setattr(css, "REPO_ROOT", root)
    monkeypatch.setattr(css, "PLAN_DIR", plan)
    return plan


def test_conforming_story_folder_is_clean(tmp_path):
    """prompt.md + tasks.md + stories.md produces no findings."""
    folder = _story(tmp_path / "good-story")

    assert css.is_story_folder(folder) is True
    assert css.check_folder(folder) == []


def test_conforming_epic_folder_is_clean(tmp_path):
    """prompt.md + README.md + a conforming sub-story produces no findings."""
    epic = _epic(tmp_path / "epic")

    assert css.is_epic_folder(epic) is True
    assert css.check_folder(epic) == []


def test_missing_stories_md_warns(tmp_path):
    """A flat story folder with no stories.md is a grandfathered warning."""
    folder = _story(tmp_path / "legacy-flat", stories=None)

    findings = css.check_folder(folder)
    assert len(findings) == 1
    assert findings[0].level == "warn"
    assert "missing stories.md" in findings[0].message


def test_legacy_stories_name_satisfies_the_requirement(tmp_path):
    """A legacy ``<slug>_stories.md`` counts as the stories file."""
    folder = _story(tmp_path / "legacy", stories="legacy_stories.md")

    assert css.check_folder(folder) == []


def test_epic_missing_readme_warns(tmp_path):
    """An epic root without README.md warns but stays an epic."""
    epic = _epic(tmp_path / "epic", readme=False)

    findings = css.check_folder(epic)
    assert _levels(findings) == {"warn"}
    assert "epic root missing README.md" in _messages(findings)


def test_epic_root_non_md_file_is_an_error(tmp_path):
    """The D6 extra-files rule reaches the epic root, not just its sub-stories."""
    epic = _epic(tmp_path / "epic")
    (epic / "diagram.png").write_bytes(b"x")

    findings = css.check_folder(epic)
    assert [f.level for f in findings] == ["error"]
    assert "non-.md file" in findings[0].message


def test_empty_folder_is_an_error(tmp_path):
    """An empty folder is reported as a hard error."""
    folder = tmp_path / "stray"
    folder.mkdir()

    findings = css.check_folder(folder)
    assert len(findings) == 1
    assert findings[0].level == "error"
    assert "empty folder" in findings[0].message


def test_non_story_non_empty_folder_errors_with_missing_files(tmp_path):
    """A populated folder that is neither story nor epic names what it lacks."""
    folder = tmp_path / "half"
    folder.mkdir()
    (folder / "notes.md").write_text("stray\n", encoding="utf-8")

    findings = css.check_folder(folder)
    assert len(findings) == 1
    assert findings[0].level == "error"
    assert "missing prompt.md, tasks.md, stories.md" in findings[0].message


def test_legacy_tasks_name_warns_but_stays_a_story(tmp_path):
    """prompt.md + `<name>_tasks.md` + stories.md is a valid story with a rename warning."""
    folder = _story(tmp_path / "legacy", tasks="legacy_tasks.md")

    findings = css.check_folder(folder)
    assert len(findings) == 1
    assert findings[0].level == "warn"
    assert "legacy '*_tasks.md'" in findings[0].message


def test_schema_backstop_warns_on_ddl_without_schema_md(tmp_path):
    """CREATE TABLE in stories.md with no sibling schema.md is a warning."""
    folder = _story(tmp_path / "db-story")
    (folder / "stories.md").write_text("Use `CREATE TABLE foo (...)`.\n", encoding="utf-8")

    findings = css.check_folder(folder)
    assert len(findings) == 1
    assert findings[0].level == "warn"
    assert "no schema.md" in findings[0].message


def test_schema_backstop_silent_when_schema_md_present(tmp_path):
    """DDL plus a schema.md sibling produces nothing."""
    folder = _story(tmp_path / "db-story")
    (folder / "stories.md").write_text("Use `CREATE TABLE foo (...)`.\n", encoding="utf-8")
    (folder / "schema.md").write_text("DDL here\n", encoding="utf-8")

    assert css.check_folder(folder) == []


def test_non_md_file_is_an_error(tmp_path):
    """A tracked non-.md file in a plan folder is a hard error."""
    folder = _story(tmp_path / "with-junk", extra=["diagram.png"])

    findings = css.check_folder(folder)
    assert [f.level for f in findings] == ["error"]
    assert "non-.md file" in findings[0].message


def test_extra_md_with_checkboxes_warns(tmp_path):
    """An extra .md (not tasks.md) carrying task checkboxes is a grandfathered warning."""
    folder = _story(tmp_path / "with-extra")
    (folder / "backlog.md").write_text("- [ ] **X-1** — stray task\n", encoding="utf-8")

    findings = css.check_folder(folder)
    assert len(findings) == 1
    assert findings[0].level == "warn"
    assert "task checkboxes" in findings[0].message


def test_plan_md_without_checkboxes_is_allowed(tmp_path):
    """A checkbox-free plan.md is permitted extra reference material (§Extra files)."""
    folder = _story(tmp_path / "with-plan")
    (folder / "plan.md").write_text("# file-by-file plan\n\nno checkboxes here\n", encoding="utf-8")

    assert css.check_folder(folder) == []


def test_main_all_passes_on_warnings_only(plan_dir, capsys):
    """Audit mode exits 0 when every finding is a grandfathered warning."""
    _story(plan_dir / "ok")
    _story(plan_dir / "legacy", tasks="legacy_tasks.md", stories=None)

    assert css.main(["--all"]) == 0
    out = capsys.readouterr().out
    assert "WARN:" in out
    assert "ERROR:" not in out


def test_main_all_fails_on_an_error(plan_dir):
    """Audit mode exits 1 when a hard error (stray empty folder) exists."""
    _story(plan_dir / "ok")
    (plan_dir / "stray").mkdir()

    assert css.main(["--all"]) == 1


def test_main_path_mode_fails_on_a_warning(plan_dir):
    """Path mode blocks on any finding, warnings included."""
    folder = _story(plan_dir / "legacy-flat", stories=None)

    assert css.main([str(folder / "tasks.md")]) == 1


def test_main_excludes_template_folder(plan_dir):
    """_TEMPLATE is skipped by the audit even if it looks irregular."""
    (plan_dir / "_TEMPLATE").mkdir()
    (plan_dir / "_TEMPLATE" / "prompt.md").write_text("# t\n", encoding="utf-8")
    _story(plan_dir / "ok")

    assert css.main(["--all"]) == 0


def test_nested_epic_is_recognised_and_grandfathered(tmp_path):
    """An epic containing a sub-epic that contains a story validates as an epic (warn-only)."""
    epic = tmp_path / "epic"
    _story(epic / "sub-epic" / "leaf-story")

    assert css.is_epic_folder(epic) is True
    assert _levels(css.check_folder(epic)) <= {"warn"}


def test_staged_added_folders_parses_git_output(plan_dir, monkeypatch):
    """`--staged-added` maps newly-added git paths to their story folders and blocks."""
    _story(plan_dir / "new-story", prompt=False, tasks=None, stories="stories.md")

    class _Result:
        stdout = "docs/plan/new-story/stories.md\nREADME.md\n"

    monkeypatch.setattr(css.subprocess, "run", lambda *a, **k: _Result())

    assert css._staged_added_folders() == [plan_dir / "new-story"]
    assert css.main(["--staged-added"]) == 1
