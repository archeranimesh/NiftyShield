"""Unit tests for scripts/dev/hooks/check_md_line_length.py."""

import re
from pathlib import Path

import yaml

from scripts.dev.hooks.check_md_line_length import IGNORE_MARKER, MAX_LEN, main

_REPO_ROOT = Path(__file__).resolve().parents[5]


def _hook_pattern(hook_id: str) -> tuple[str, str | None]:
    """Return the ``files``/``exclude`` regex pair for a local pre-commit hook."""
    config = yaml.safe_load((_REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    for repo in config["repos"]:
        for hook in repo["hooks"]:
            if hook["id"] == hook_id:
                return hook["files"], hook.get("exclude")
    raise AssertionError(f"hook {hook_id!r} not found in .pre-commit-config.yaml")


def _matches(hook_id: str, path: str) -> bool:
    files, exclude = _hook_pattern(hook_id)
    if not re.search(files, path):
        return False
    if exclude and re.search(exclude, path):
        return False
    return True


def test_md_line_length_scope_skips_archive_template_and_council():
    """The repo-wide scope excludes docs/archive/, docs/plan/_TEMPLATE/, docs/council/."""
    assert not _matches("md-line-length", "docs/archive/BUGS_LEGACY.md")
    assert not _matches("md-line-length", "docs/plan/_TEMPLATE/story/prompt.md")
    assert not _matches("md-line-length", "docs/council/2026-01-01_decision.md")


def test_md_line_length_scope_covers_whole_tree():
    """The repo-wide scope now covers .md files outside docs/plan + docs/bugs too."""
    assert _matches("md-line-length", ".claude/skills/work/SKILL.md")
    assert _matches("md-line-length", "src/paper/CLAUDE.md")
    assert _matches("md-line-length", "README.md")


def test_md_reflow_scope_matches_md_line_length():
    """md-reflow shares the same widened files/exclude pair as md-line-length."""
    assert _hook_pattern("md-reflow") == _hook_pattern("md-line-length")


def _write(tmp_path, name, lines):
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def test_main_happy_path(tmp_path, capsys):
    """A file with every line within the cap returns 0 and prints nothing."""
    lines = ["# Title", "x" * MAX_LEN, "short line"]
    clean = _write(tmp_path, "clean.md", lines)

    assert main([clean]) == 0
    assert capsys.readouterr().out == ""


def test_main_flags_over_length_line(tmp_path, capsys):
    """A line one char over the cap returns 1 and reports its length."""
    bad = _write(tmp_path, "bad.md", ["ok", "y" * (MAX_LEN + 1)])

    assert main([bad]) == 1
    out = capsys.readouterr().out
    assert f"{bad}:2: {MAX_LEN + 1} chars" in out


def test_ignore_marker_on_preceding_line_suppresses(tmp_path, capsys):
    """An over-length line is allowed when the prior line has the marker."""
    lines = [IGNORE_MARKER, "z" * (MAX_LEN + 50)]
    excused = _write(tmp_path, "excused.md", lines)

    assert main([excused]) == 0
    assert capsys.readouterr().out == ""
