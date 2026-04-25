"""Tests for scripts/validate_strategy_spec.py.

All tests are fully offline — no network calls, no live docs/strategies/.
Spec files are constructed in-memory using pytest's ``tmp_path`` fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validate_strategy_spec import (
    REQUIRED_SECTIONS,
    SpecResult,
    check_file,
    validate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_sections() -> str:
    """Return a minimal but complete strategy spec markdown string."""
    metadata = (
        "# My Strategy v1\n\n"
        "| Field   | Value     |\n"
        "|---------|----------|\n"
        "| Name    | My Strat  |\n"
        "| Version | v1        |\n"
        "| Status  | Active    |\n\n"
    )
    sections = "\n".join(
        f"## {label.split('/')[0].strip()}\n\nContent here.\n"
        for _, label in REQUIRED_SECTIONS
    )
    return metadata + sections


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# check_file — happy path
# ---------------------------------------------------------------------------

class TestCheckFileHappyPath:
    def test_valid_spec_passes(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "strategy_v1.md", _all_sections())
        result = check_file(path)
        assert result.passed
        assert result.is_spec
        assert not result.deprecated
        assert result.missing == []

    def test_section_headers_are_case_insensitive(self, tmp_path: Path) -> None:
        """Uppercase section headings should still pass."""
        content = _all_sections().replace("## Entry Rule", "## ENTRY RULE")
        path = _write(tmp_path, "upper.md", content)
        result = check_file(path)
        assert result.passed

    def test_plural_headings_accepted(self, tmp_path: Path) -> None:
        """'Exit Rules' (plural) still matches the 'exit' pattern."""
        content = _all_sections().replace("## Exit Rule", "## Exit Rules")
        path = _write(tmp_path, "plural.md", content)
        result = check_file(path)
        assert result.passed

    def test_verbose_heading_accepted(self, tmp_path: Path) -> None:
        """'Variance Threshold for Live Deployment' matches 'variance threshold'."""
        content = _all_sections().replace(
            "## Variance Threshold",
            "## Variance Threshold for Live Deployment",
        )
        path = _write(tmp_path, "verbose.md", content)
        result = check_file(path)
        assert result.passed


# ---------------------------------------------------------------------------
# check_file — not a spec
# ---------------------------------------------------------------------------

class TestCheckFileNotSpec:
    def test_file_without_name_table_row_is_skipped(self, tmp_path: Path) -> None:
        content = "# Revision Prompt\n\nSome notes about strategy revision.\n"
        path = _write(tmp_path, "revision_prompt.md", content)
        result = check_file(path)
        assert not result.is_spec
        assert not result.deprecated
        assert result.missing == []

    def test_is_spec_false_means_not_passed(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "random.md", "# Just notes\n\nNo table here.\n")
        result = check_file(path)
        assert not result.passed


# ---------------------------------------------------------------------------
# check_file — deprecated
# ---------------------------------------------------------------------------

class TestCheckFileDeprecated:
    def test_blockquote_deprecated_marker_skips(self, tmp_path: Path) -> None:
        content = (
            "# Old Strategy v1\n\n"
            "> **DEPRECATED 2026-04-25.** Superseded by csp_nifty_v1.\n\n"
            "| Name | Old Strat |\n"
        )
        path = _write(tmp_path, "old.md", content)
        result = check_file(path)
        assert result.is_spec
        assert result.deprecated
        assert not result.passed

    def test_status_table_deprecated_skips(self, tmp_path: Path) -> None:
        content = (
            "# Another Strategy\n\n"
            "| Field   | Value      |\n"
            "|---------|------------|\n"
            "| Name    | Strat      |\n"
            "| Status  | DEPRECATED |\n\n"
        )
        path = _write(tmp_path, "status_depr.md", content)
        result = check_file(path)
        assert result.is_spec
        assert result.deprecated

    def test_deprecated_flag_case_insensitive(self, tmp_path: Path) -> None:
        content = (
            "| Name   | X |\n"
            "> **deprecated** — old spec.\n"
        )
        path = _write(tmp_path, "lower_depr.md", content)
        result = check_file(path)
        assert result.deprecated


# ---------------------------------------------------------------------------
# check_file — missing sections (one per required section)
# ---------------------------------------------------------------------------

class TestCheckFileMissingSections:
    @pytest.mark.parametrize("pattern,label", REQUIRED_SECTIONS)
    def test_missing_section_reported(
        self, tmp_path: Path, pattern: str, label: str
    ) -> None:
        """Removing the heading that matches *pattern* surfaces *label* in missing."""
        # Build a spec with all sections, then strip the one we want to test.
        lines = _all_sections().splitlines(keepends=True)
        # Drop any line whose lower-cased content contains the pattern.
        filtered = [
            line
            for line in lines
            if not (line.startswith("##") and pattern in line.lower())
        ]
        content = "".join(filtered)
        path = _write(tmp_path, f"missing_{pattern.replace(' ', '_')}.md", content)
        result = check_file(path)
        assert not result.passed
        assert label in result.missing

    def test_multiple_missing_sections_all_reported(self, tmp_path: Path) -> None:
        """A spec missing both Entry and Exit surfaces both labels."""
        lines = _all_sections().splitlines(keepends=True)
        filtered = [
            line
            for line in lines
            if not (line.startswith("##") and ("entry" in line.lower() or "exit" in line.lower()))
        ]
        path = _write(tmp_path, "two_missing.md", "".join(filtered))
        result = check_file(path)
        labels = result.missing
        assert any("Entry" in l for l in labels)
        assert any("Exit" in l for l in labels)


# ---------------------------------------------------------------------------
# validate — directory scan
# ---------------------------------------------------------------------------

class TestValidateDirectoryScan:
    def test_all_pass_returns_zero(self, tmp_path: Path) -> None:
        _write(tmp_path, "spec_a.md", _all_sections())
        _write(tmp_path, "spec_b.md", _all_sections())
        assert validate([tmp_path]) == 0

    def test_one_failure_returns_one(self, tmp_path: Path) -> None:
        _write(tmp_path, "good.md", _all_sections())
        bad = _all_sections().replace("## Kill Criteria\n", "")
        _write(tmp_path, "bad.md", bad)
        assert validate([tmp_path]) == 1

    def test_deprecated_files_do_not_count_as_failures(self, tmp_path: Path) -> None:
        deprecated = (
            "| Name | X |\n"
            "> **DEPRECATED**\n\n"
        )
        _write(tmp_path, "old.md", deprecated)
        _write(tmp_path, "good.md", _all_sections())
        assert validate([tmp_path]) == 0

    def test_non_spec_files_do_not_count_as_failures(self, tmp_path: Path) -> None:
        _write(tmp_path, "revision_prompt.md", "# Prompt\n\nJust notes.\n")
        _write(tmp_path, "spec.md", _all_sections())
        assert validate([tmp_path]) == 0

    def test_empty_directory_returns_one(self, tmp_path: Path) -> None:
        assert validate([tmp_path]) == 1

    def test_directory_of_only_deprecated_returns_zero(self, tmp_path: Path) -> None:
        """All specs deprecated → no active specs → all-pass (nothing to fail)."""
        deprecated = (
            "| Name | Old Strat |\n"
            "> **DEPRECATED**\n\n"
        )
        _write(tmp_path, "old.md", deprecated)
        assert validate([tmp_path]) == 0

    def test_explicit_file_path_works(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "spec.md", _all_sections())
        assert validate([path]) == 0

    def test_explicit_failing_file_path_returns_one(self, tmp_path: Path) -> None:
        bad = _all_sections().replace("## Kill Criteria\n", "")
        path = _write(tmp_path, "bad.md", bad)
        assert validate([path]) == 1


# ---------------------------------------------------------------------------
# validate — live docs/strategies/ smoke test (read-only, no writes)
# ---------------------------------------------------------------------------

class TestLiveStrategiesDirectory:
    """Smoke-test against the actual docs/strategies/ folder.

    This test will fail if a new active spec is added without all required
    sections — which is exactly the enforcement goal of task 0.7.
    """

    def test_csp_nifty_v1_passes(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent.parent
        spec = repo_root / "docs" / "strategies" / "csp_nifty_v1.md"
        if not spec.exists():
            pytest.skip("csp_nifty_v1.md not found — skipping live smoke test")
        result = check_file(spec)
        assert result.passed, f"Missing sections: {result.missing}"

    def test_csp_niftybees_v1_is_deprecated(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent.parent
        spec = repo_root / "docs" / "strategies" / "csp_niftybees_v1.md"
        if not spec.exists():
            pytest.skip("csp_niftybees_v1.md not found")
        result = check_file(spec)
        assert result.deprecated, "Expected this spec to be detected as DEPRECATED"
