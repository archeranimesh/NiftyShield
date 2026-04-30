"""Tests for scripts/ask_council.py — pure helper functions only.

All tests are fully offline.  No network, no server, no Upstox token.
Network-dependent functions (council_is_running, run_council) are excluded
and exercised only in integration tests (not yet wired).

Functions covered:
  - read_context_file: normal read / truncation / missing file
  - load_template:     existing template / missing template
  - build_prompt:      section ordering, extra files, template inclusion
  - make_output_path:  date + slug naming
  - make_pending_path: date + slug naming with _prompt suffix
  - format_decision:   full result dict / empty result dict
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from scripts.ask_council import (
    _slugify,
    build_prompt,
    format_decision,
    load_template,
    make_output_path,
    make_pending_path,
    read_context_file,
)


# ---------------------------------------------------------------------------
# read_context_file
# ---------------------------------------------------------------------------


class TestReadContextFile:
    def test_reads_file_normally(self, tmp_path: Path) -> None:
        f = tmp_path / "CONTEXT.md"
        f.write_text("line one\nline two\n")
        result = read_context_file(f, max_lines=200)
        assert result == "line one\nline two\n"

    def test_truncates_at_max_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "CONTEXT.md"
        lines = [f"line {i}" for i in range(10)]
        f.write_text("\n".join(lines))
        result = read_context_file(f, max_lines=5)
        # First 5 lines present
        assert "line 0" in result
        assert "line 4" in result
        # Line 5+ absent from body (truncation note instead)
        assert "line 5" not in result.split("[")[0]
        assert "truncated at 5 lines" in result

    def test_returns_placeholder_for_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "no_such_file.md"
        result = read_context_file(missing)
        assert "[File not found: no_such_file.md]" == result

    def test_no_truncation_when_exactly_at_limit(self, tmp_path: Path) -> None:
        f = tmp_path / "exact.md"
        lines = [f"L{i}" for i in range(5)]
        f.write_text("\n".join(lines))
        result = read_context_file(f, max_lines=5)
        assert "truncated" not in result


# ---------------------------------------------------------------------------
# load_template
# ---------------------------------------------------------------------------


class TestLoadTemplate:
    def test_loads_existing_template(self, tmp_path: Path) -> None:
        (tmp_path / "backtest_methodology.md").write_text("# Backtest\nsome content\n")
        result = load_template(tmp_path, "backtest_methodology")
        assert result == "# Backtest\nsome content"  # .strip() applied

    def test_returns_empty_string_for_missing_template(self, tmp_path: Path) -> None:
        result = load_template(tmp_path, "nonexistent_template")
        assert result == ""

    def test_strips_whitespace_from_template(self, tmp_path: Path) -> None:
        (tmp_path / "t.md").write_text("   \ncontent\n   ")
        result = load_template(tmp_path, "t")
        assert result == "content"


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def _make_context(self, tmp_path: Path, name: str = "CONTEXT.md") -> Path:
        p = tmp_path / name
        p.write_text("project state here")
        return p

    def test_always_includes_project_state_section(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path)
        prompt = build_prompt(
            question="What is X?",
            context_md=ctx,
            templates_dir=tmp_path,
        )
        assert "=== NIFTYSHIELD PROJECT STATE ===" in prompt
        assert "project state here" in prompt

    def test_always_includes_question_section(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path)
        prompt = build_prompt(
            question="Why is the sky blue?",
            context_md=ctx,
            templates_dir=tmp_path,
        )
        assert "=== QUESTION FOR THE COUNCIL ===" in prompt
        assert "Why is the sky blue?" in prompt

    def test_section_ordering_project_state_before_question(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path)
        prompt = build_prompt(
            question="Q?",
            context_md=ctx,
            templates_dir=tmp_path,
        )
        idx_state = prompt.index("=== NIFTYSHIELD PROJECT STATE ===")
        idx_question = prompt.index("=== QUESTION FOR THE COUNCIL ===")
        assert idx_state < idx_question

    def test_includes_template_section_when_provided(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path)
        (tmp_path / "strategy_parameters.md").write_text("delta must be 0.25")
        prompt = build_prompt(
            question="Q?",
            context_md=ctx,
            templates_dir=tmp_path,
            template_name="strategy_parameters",
        )
        assert "=== DECISION DOMAIN CONSTRAINTS ===" in prompt
        assert "delta must be 0.25" in prompt

    def test_template_section_absent_when_not_provided(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path)
        prompt = build_prompt(
            question="Q?",
            context_md=ctx,
            templates_dir=tmp_path,
            template_name=None,
        )
        assert "=== DECISION DOMAIN CONSTRAINTS ===" not in prompt

    def test_template_section_absent_when_file_missing(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path)
        # Template name given but file absent
        prompt = build_prompt(
            question="Q?",
            context_md=ctx,
            templates_dir=tmp_path,
            template_name="nonexistent",
        )
        assert "=== DECISION DOMAIN CONSTRAINTS ===" not in prompt

    def test_extra_files_included_in_order(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path)
        f1 = tmp_path / "strat.md"
        f2 = tmp_path / "decisions.md"
        f1.write_text("strategy content")
        f2.write_text("decisions content")
        prompt = build_prompt(
            question="Q?",
            context_md=ctx,
            templates_dir=tmp_path,
            extra_files=[f1, f2],
        )
        assert "=== ADDITIONAL CONTEXT: strat.md ===" in prompt
        assert "strategy content" in prompt
        assert "=== ADDITIONAL CONTEXT: decisions.md ===" in prompt
        assert "decisions content" in prompt
        # f1 must appear before f2
        assert prompt.index("strat.md") < prompt.index("decisions.md")

    def test_extra_files_appear_after_project_state(self, tmp_path: Path) -> None:
        ctx = self._make_context(tmp_path)
        extra = tmp_path / "extra.md"
        extra.write_text("extra content")
        prompt = build_prompt(
            question="Q?",
            context_md=ctx,
            templates_dir=tmp_path,
            extra_files=[extra],
        )
        idx_state = prompt.index("=== NIFTYSHIELD PROJECT STATE ===")
        idx_extra = prompt.index("=== ADDITIONAL CONTEXT: extra.md ===")
        assert idx_state < idx_extra

    def test_template_appears_after_extra_files_and_before_question(
        self, tmp_path: Path
    ) -> None:
        ctx = self._make_context(tmp_path)
        extra = tmp_path / "extra.md"
        extra.write_text("extra")
        (tmp_path / "tmpl.md").write_text("tmpl content")
        prompt = build_prompt(
            question="Q?",
            context_md=ctx,
            templates_dir=tmp_path,
            template_name="tmpl",
            extra_files=[extra],
        )
        idx_extra = prompt.index("=== ADDITIONAL CONTEXT: extra.md ===")
        idx_tmpl = prompt.index("=== DECISION DOMAIN CONSTRAINTS ===")
        idx_q = prompt.index("=== QUESTION FOR THE COUNCIL ===")
        assert idx_extra < idx_tmpl < idx_q


# ---------------------------------------------------------------------------
# make_output_path / make_pending_path
# ---------------------------------------------------------------------------


class TestOutputPaths:
    def test_output_path_uses_today_and_slug(self, tmp_path: Path) -> None:
        today = datetime.date.today().isoformat()
        path = make_output_path("Slippage Model", tmp_path)
        assert path.parent == tmp_path
        assert path.name == f"{today}_slippage-model.md"

    def test_output_path_slugifies_spaces(self, tmp_path: Path) -> None:
        path = make_output_path("iv rank entry", tmp_path)
        assert "iv-rank-entry" in path.name

    def test_output_path_lowercases_topic(self, tmp_path: Path) -> None:
        path = make_output_path("CSP-Delta", tmp_path)
        assert "csp-delta" in path.name

    def test_pending_path_has_prompt_suffix(self, tmp_path: Path) -> None:
        today = datetime.date.today().isoformat()
        path = make_pending_path("slippage-model", tmp_path)
        assert path.name == f"{today}_slippage-model_prompt.md"

    def test_pending_path_slugifies_topic(self, tmp_path: Path) -> None:
        path = make_pending_path("IV Rank", tmp_path)
        assert "iv-rank" in path.name
        assert path.name.endswith("_prompt.md")


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_lowercases(self) -> None:
        assert _slugify("SlippageModel") == "slippagemodel"

    def test_replaces_spaces_with_dashes(self) -> None:
        assert _slugify("iv rank entry") == "iv-rank-entry"

    def test_already_slug(self) -> None:
        assert _slugify("slippage-model") == "slippage-model"


# ---------------------------------------------------------------------------
# format_decision
# ---------------------------------------------------------------------------


class TestFormatDecision:
    def _make_result(self) -> dict:
        return {
            "stage3": {
                "model": "claude-opus-4-6",
                "response": "Use absolute INR slippage.",
            },
            "stage1": [
                {"model": "gpt-4o", "response": "Percentage-based is risky."},
                {"model": "gemini-pro", "response": "Agree with absolute model."},
            ],
            "metadata": {
                "aggregate_rankings": [
                    {"model": "gpt-4o", "average_rank": 1.5, "rankings_count": 2},
                    {"model": "gemini-pro", "average_rank": 2.0, "rankings_count": 2},
                ]
            },
        }

    def test_contains_topic_heading(self) -> None:
        doc = format_decision("slippage-model", "prompt text", self._make_result())
        assert "# Council Decision: slippage-model" in doc

    def test_contains_today_date(self) -> None:
        today = datetime.date.today().isoformat()
        doc = format_decision("slippage-model", "prompt text", self._make_result())
        assert today in doc

    def test_contains_chairman_synthesis(self) -> None:
        doc = format_decision("slippage-model", "prompt text", self._make_result())
        assert "Use absolute INR slippage." in doc
        assert "claude-opus-4-6" in doc

    def test_contains_stage1_responses(self) -> None:
        doc = format_decision("slippage-model", "prompt text", self._make_result())
        assert "gpt-4o" in doc
        assert "Percentage-based is risky." in doc
        assert "gemini-pro" in doc

    def test_contains_aggregate_rankings(self) -> None:
        doc = format_decision("slippage-model", "prompt text", self._make_result())
        assert "avg rank 1.5" in doc
        assert "avg rank 2.0" in doc

    def test_contains_prompt_preview(self) -> None:
        doc = format_decision("slippage-model", "the prompt content", self._make_result())
        assert "the prompt content" in doc

    def test_truncates_long_prompt_to_3000_chars(self) -> None:
        long_prompt = "x" * 5000
        doc = format_decision("topic", long_prompt, self._make_result())
        # The preview section should have "..." indicating truncation
        assert "..." in doc
        # But not 5000 x's in a row
        assert "x" * 4000 not in doc

    def test_handles_empty_result(self) -> None:
        doc = format_decision("topic", "prompt", {})
        # Should not raise; fallback text present
        assert "# Council Decision: topic" in doc
        assert "*(no synthesis returned)*" in doc

    def test_rankings_section_absent_when_no_rankings(self) -> None:
        result = self._make_result()
        result["metadata"] = {}
        doc = format_decision("topic", "prompt", result)
        assert "Aggregate Rankings" not in doc
