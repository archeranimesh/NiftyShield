"""Unit tests for scripts/dev/new_plan_folder.py."""

from pathlib import Path

import pytest

from scripts.dev import new_plan_folder as npf
from scripts.dev.hooks import check_story_structure as css


@pytest.fixture
def plan_dir(tmp_path, monkeypatch):
    """Point the module's REPO_ROOT / PLAN_DIR (in both modules) at a temp tree."""
    root = tmp_path
    plan = root / "docs" / "plan"
    template = plan / "_TEMPLATE"
    shutil_copy_template(template)
    monkeypatch.setattr(npf, "REPO_ROOT", root)
    monkeypatch.setattr(npf, "PLAN_DIR", plan)
    monkeypatch.setattr(npf, "TEMPLATE_DIR", template)
    monkeypatch.setattr(css, "REPO_ROOT", root)
    monkeypatch.setattr(css, "PLAN_DIR", plan)
    return plan


def shutil_copy_template(dest_template_dir: Path) -> None:
    """Copy the repo's real _TEMPLATE/ tree into the fixture's temp docs/plan/."""
    import shutil

    real_template = npf.TEMPLATE_DIR
    shutil.copytree(real_template, dest_template_dir)


def test_scaffold_story_passes_structure_check(plan_dir):
    dest = npf.scaffold(kind="story", slug="risk-gamma-phase-a")
    assert dest == plan_dir / "risk-gamma-phase-a"
    assert (dest / "prompt.md").is_file()
    assert (dest / "tasks.md").is_file()
    assert (dest / "stories.md").is_file()
    assert not (dest / "schema.md.example").exists()
    for item in dest.iterdir():
        assert "<!--" not in item.read_text(encoding="utf-8")
    findings = css.check_folder(dest)
    assert [f for f in findings if f.level == "error"] == []
    assert findings == []


def test_scaffold_epic_with_substory_passes_structure_check(plan_dir):
    epic = npf.scaffold(
        kind="epic", slug="telegram-markdown-migration", title="Telegram Markdown Migration"
    )
    npf.scaffold(kind="story", slug="phase-a", into="telegram-markdown-migration")
    assert (epic / "prompt.md").is_file()
    assert (epic / "README.md").is_file()
    assert (epic / "phase-a" / "tasks.md").is_file()
    findings = css.check_folder(epic)
    assert [f for f in findings if f.level == "error"] == []
    assert findings == []


def test_scaffold_refuses_existing_target(plan_dir):
    npf.scaffold(kind="story", slug="dup-slug")
    with pytest.raises(FileExistsError):
        npf.scaffold(kind="story", slug="dup-slug")


def test_scaffold_into_nonexistent_epic_raises(plan_dir):
    with pytest.raises(FileNotFoundError):
        npf.scaffold(kind="story", slug="orphan-story", into="no-such-epic")
    assert not (plan_dir / "no-such-epic").exists()


@pytest.mark.parametrize(
    "slug",
    ["2026-09-22-risk-gamma", "Risk_Gamma", "risk gamma", "RiskGamma", "risk_gamma"],
)
def test_scaffold_rejects_invalid_slug(plan_dir, slug):
    with pytest.raises(ValueError):
        npf.scaffold(kind="story", slug=slug)


def test_title_defaults_to_title_case_of_slug(plan_dir):
    dest = npf.scaffold(kind="story", slug="risk-gamma-phase-a")
    text = (dest / "prompt.md").read_text(encoding="utf-8")
    assert "Risk Gamma Phase A" in text


def test_main_cli_creates_story(plan_dir, capsys):
    rc = npf.main(["--story", "cli-story"])
    assert rc == 0
    assert (plan_dir / "cli-story" / "tasks.md").is_file()
    out = capsys.readouterr().out
    assert "cli-story" in out


def test_main_cli_rejects_into_with_epic(plan_dir, capsys):
    rc = npf.main(["--epic", "some-epic", "--into", "other-epic"])
    assert rc == 1
