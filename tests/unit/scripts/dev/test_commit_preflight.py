"""Unit tests for scripts/dev/commit_preflight.py."""

from __future__ import annotations

import subprocess

from scripts.dev import commit_preflight as cp


class _FakeRun:
    """Minimal ``subprocess.run`` stand-in with a canned returncode/stdout."""

    def __init__(self, returncode: int, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout

    def __call__(self, *args, **kwargs) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args, self.returncode, self.stdout, "")


# --- staged-index sanity -----------------------------------------------------


def test_staged_index_silent_when_all_inside_expected():
    staged = ["scripts/dev/commit_preflight.py", "tests/unit/scripts/dev/test_x.py"]
    assert cp.check_staged_index(staged, ["scripts/dev/", "tests/"]) == []


def test_staged_index_flags_stray_path():
    staged = ["scripts/dev/commit_preflight.py", "src/portfolio/store.py"]
    findings = cp.check_staged_index(staged, ["scripts/dev/"])
    assert len(findings) == 1 and "src/portfolio/store.py" in findings[0]


def test_staged_index_noop_without_expected():
    assert cp.check_staged_index(["anything/at/all.py"], []) == []


# --- ruff format check -----------------------------------------------------


def test_ruff_format_silent_on_clean():
    assert cp.ruff_format_check(["a.py"], runner=_FakeRun(0)) == []


def test_ruff_format_flags_reformat():
    findings = cp.ruff_format_check(["a.py"], runner=_FakeRun(1, "Would reformat: a.py\n"))
    assert len(findings) == 1 and "a.py" in findings[0]


def test_ruff_format_noop_without_py():
    assert cp.ruff_format_check([], runner=_FakeRun(1)) == []


# --- md line length --------------------------------------------------------


def test_md_line_length_flags_over_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "REPO_ROOT", tmp_path)
    long = tmp_path / "NOTES.md"
    long.write_text("x" * 250 + "\n", encoding="utf-8")
    findings = cp.check_md_line_length(["NOTES.md"])
    assert len(findings) == 1 and "250 chars" in findings[0]


def test_md_line_length_silent_on_short_and_out_of_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "REPO_ROOT", tmp_path)
    (tmp_path / "NOTES.md").write_text("short line\n", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "big.md").write_text("y" * 300 + "\n", encoding="utf-8")
    assert cp.check_md_line_length(["NOTES.md", "src/big.md"]) == []


# --- next-marker ----------------------------------------------------------


def test_ticked_ids_detects_box_flip():
    diff = "\n".join(
        [
            "@@ -3 +3 @@",
            "-- [ ] **SWEEP-4** — commit flow",
            "+- [x] **SWEEP-4** — commit flow",
        ]
    )
    assert cp.ticked_ids(diff) == {"SWEEP-4"}


def test_ticked_ids_ignores_unpaired_add():
    diff = "+- [x] **SWEEP-9** — brand new already checked"
    assert cp.ticked_ids(diff) == set()


def test_next_marker_flags_prose_pointer():
    texts = {"suggestions-sweep/tasks.md": "**Open: SWEEP-4 (next), SWEEP-5.**"}
    findings = cp.check_next_marker({"SWEEP-4"}, texts)
    assert len(findings) == 1 and "SWEEP-4" in findings[0]


def test_next_marker_flags_readme_form():
    texts = {"docs/plan/README.md": "- **`token-efficiency/`** … next: **SWEEP-4**"}
    assert cp.check_next_marker({"SWEEP-4"}, texts) != []


def test_next_marker_silent_when_pointer_advanced():
    texts = {"tasks.md": "**Open: SWEEP-5 (next), SWEEP-6.**"}
    assert cp.check_next_marker({"SWEEP-4"}, texts) == []


# --- sha placeholder ----------------------------------------------------


def test_sha_placeholder_flags_ticked_with_placeholder():
    text = "- [x] **SWEEP-4** — commit flow |\n      Owner: Claude | Review: none | SHA: <—>"
    findings = cp.check_sha_placeholder({"tasks.md": text})
    assert len(findings) == 1 and "SWEEP-4" in findings[0]


def test_sha_placeholder_silent_on_real_sha():
    text = "- [x] **SWEEP-3** — test routing | Review: none | SHA: e325e86"
    assert cp.check_sha_placeholder({"tasks.md": text}) == []


def test_sha_placeholder_silent_on_pending():
    text = "- [x] **SWEEP-4** — commit flow | Review: none | SHA: <pending>"
    assert cp.check_sha_placeholder({"tasks.md": text}) == []


def test_sha_placeholder_silent_on_unchecked():
    text = "- [ ] **SWEEP-5** — mcp params | Review: none | SHA: <—>"
    assert cp.check_sha_placeholder({"tasks.md": text}) == []


# --- main / integration -------------------------------------------------


def test_preflight_clean_repo_reports_nothing(monkeypatch, capsys):
    monkeypatch.setattr(cp, "staged_names", lambda: [])
    monkeypatch.setattr(cp, "staged_diff", lambda: "")
    assert cp.main([]) == 0
    assert "clean" in capsys.readouterr().out


def test_main_returns_one_on_blocker(monkeypatch):
    monkeypatch.setattr(cp, "staged_names", lambda: ["a.py"])
    monkeypatch.setattr(cp, "staged_diff", lambda: "")
    monkeypatch.setattr(cp, "ruff_format_check", lambda paths: ["ruff-format: bad"])
    assert cp.main([]) == 1


def test_main_warnings_do_not_fail(monkeypatch, capsys):
    monkeypatch.setattr(cp, "staged_names", lambda: ["src/x.py"])
    monkeypatch.setattr(cp, "staged_diff", lambda: "")
    monkeypatch.setattr(cp, "ruff_format_check", lambda paths: [])
    assert cp.main(["--expect", "scripts/dev/"]) == 0
    assert "⚠" in capsys.readouterr().out
