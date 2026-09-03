"""Unit tests for scripts/dev/hooks/check_wide_grep.py."""

import json

from scripts.dev.hooks.check_wide_grep import evaluate, main


def _big(tmp_path, name="big.md", lines=1200):
    path = tmp_path / name
    path.write_text("x\n" * lines, encoding="utf-8")
    return str(path)


def _small(tmp_path, name="small.md", lines=40):
    path = tmp_path / name
    path.write_text("x\n" * lines, encoding="utf-8")
    return str(path)


def test_wide_grep_warns_on_unscoped_grep_large_file(tmp_path):
    warning = evaluate(f"grep -E 'pattern' {_big(tmp_path)}")
    assert warning is not None and "wide grep" in warning


def test_wide_grep_silent_with_count_flag(tmp_path):
    assert evaluate(f"grep -c 'pattern' {_big(tmp_path)}") is None


def test_wide_grep_silent_on_small_file(tmp_path):
    assert evaluate(f"grep -E 'pattern' {_small(tmp_path)}") is None


def test_wide_grep_silent_on_pipe_input(tmp_path):
    assert evaluate(f"cat {_big(tmp_path)} | grep 'pattern'") is None


def test_wide_grep_silent_with_sed_range(tmp_path):
    assert evaluate(f"sed -n '1,20p' {_big(tmp_path)}") is None


def test_wide_grep_silent_with_downstream_head(tmp_path):
    assert evaluate(f"grep 'pattern' {_big(tmp_path)} | head -20") is None


def test_wide_grep_warns_on_recursive_grep_without_filter(tmp_path):
    assert evaluate("grep -rn 'CLAUDE.md' .") is not None


def test_wide_grep_silent_on_recursive_grep_with_include(tmp_path):
    assert evaluate("grep -rn --include='*.py' 'pattern' .") is None


def test_wide_grep_warns_on_combined_recursive_flags(tmp_path):
    assert evaluate("grep -ri 'pattern' src/") is not None


def test_wide_grep_warns_with_pipe_inside_pattern(tmp_path):
    """A pipe inside a quoted -E pattern must not hide the large-file match."""
    assert evaluate(f"grep -E 'foo|bar' {_big(tmp_path)}") is not None


def test_wide_grep_warns_on_awk_over_large_file(tmp_path):
    assert evaluate(f"awk '/pattern/' {_big(tmp_path)}") is not None


def test_hook_always_exits_zero(tmp_path, capsys):
    payload = json.dumps({"tool_input": {"command": f"grep 'x' {_big(tmp_path)}"}})
    assert main(payload) == 0
    assert "wide grep" in capsys.readouterr().out
    assert main("not json") == 0
    assert main(json.dumps({"tool_input": {"command": "ls -la"}})) == 0
