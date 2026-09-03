"""Unit tests for scripts/dev/hooks/check_inline_full_suite.py."""

import json

from scripts.dev.hooks.check_inline_full_suite import evaluate, main


def test_warns_on_bare_full_suite():
    assert evaluate("python -m pytest tests/unit/ --tb=no -q") is not None


def test_warns_on_pytest_no_path():
    assert evaluate("pytest -q") is not None


def test_warns_on_tests_root():
    assert evaluate("pytest tests/") is not None


def test_silent_with_k_filter():
    assert evaluate("python -m pytest tests/unit/ -k repeat_read") is None


def test_silent_with_marker_filter():
    assert evaluate("pytest tests/unit/ -m 'not slow'") is None


def test_silent_with_path_narrowing():
    assert evaluate("pytest tests/unit/scripts/dev/hooks/") is None


def test_silent_with_dot_prefix_narrowing():
    assert evaluate("pytest ./tests/unit/scripts/dev/hooks/") is None


def test_warns_with_dot_prefix_whole_tree():
    assert evaluate("pytest ./tests/unit/") is not None


def test_silent_with_node_id():
    assert evaluate("pytest tests/unit/test_foo.py::test_bar") is None


def test_silent_with_last_failed():
    assert evaluate("python -m pytest tests/unit/ --lf") is None


def test_silent_on_non_pytest():
    assert evaluate("ruff check src/") is None
    assert evaluate("python -m build") is None


def test_silent_on_pipe_from_other_command():
    assert evaluate("echo hi | pytest tests/unit/") is None


def test_warns_when_piped_to_tail():
    assert evaluate("python -m pytest tests/unit/ --tb=no -q | tail -1") is not None


def test_exits_zero():
    payload = json.dumps({"tool_input": {"command": "pytest tests/unit/ -q"}})
    assert main(payload) == 0
    assert main("not json") == 0
    assert main(json.dumps({"tool_input": {"command": "ls -la"}})) == 0
