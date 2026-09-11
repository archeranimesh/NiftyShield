"""Unit tests for scripts/dev/hooks/check_repeat_read.py."""

import json

from scripts.dev.hooks.check_repeat_read import evaluate, main


def _seen(tmp_path):
    return str(tmp_path / "seen-reads")


def test_repeat_read_silent_first_read(tmp_path, capsys):
    """The first Read of a path records it and prints nothing."""
    assert evaluate("Read", "/repo/CLAUDE.md", _seen(tmp_path)) is None


def test_repeat_read_warns_on_second_read(tmp_path):
    """A second Read with no intervening edit returns a warning."""
    seen = _seen(tmp_path)
    evaluate("Read", "/repo/a.py", seen)
    warning = evaluate("Read", "/repo/a.py", seen)
    assert warning is not None
    assert "already Read this session" in warning


def test_repeat_read_silent_after_edit(tmp_path):
    """An Edit to the path clears it; the next Read is not flagged."""
    seen = _seen(tmp_path)
    evaluate("Read", "/repo/a.py", seen)
    evaluate("Edit", "/repo/a.py", seen)
    assert evaluate("Read", "/repo/a.py", seen) is None


def test_repeat_read_silent_after_write(tmp_path):
    """A Write to the path clears it; the next Read is not flagged."""
    seen = _seen(tmp_path)
    evaluate("Read", "/repo/a.py", seen)
    evaluate("Write", "/repo/a.py", seen)
    assert evaluate("Read", "/repo/a.py", seen) is None


def test_main_exits_zero_when_seen_dir_missing(capsys):
    """An unwritable/absent seen-path parent dir must not break exit 0."""
    payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/repo/a.py"}})
    assert main(["/nonexistent/dir/seen"], payload) == 0


def test_repeat_read_distinct_paths_independent(tmp_path):
    """Reading a different path does not trigger a warning."""
    seen = _seen(tmp_path)
    evaluate("Read", "/repo/a.py", seen)
    assert evaluate("Read", "/repo/b.py", seen) is None


def test_hook_blocks_on_repeat_read(tmp_path, capsys):
    """main() returns 0 on a first read and malformed input, 2 on a re-read."""
    seen = _seen(tmp_path)
    payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/repo/a.py"}})
    assert main([seen], payload) == 0
    assert main([seen], payload) == 2  # second read — blocks
    assert "already Read" in capsys.readouterr().err
    assert main([seen], "not json") == 0


def test_main_exits_zero_on_null_tool_input(tmp_path):
    """A payload with tool_input: null must not crash the hook."""
    seen = _seen(tmp_path)
    payload = json.dumps({"tool_name": "Read", "tool_input": None})
    assert main([seen], payload) == 0


def test_main_exits_zero_on_non_dict_payload(tmp_path):
    """A well-formed but non-dict JSON payload must not crash the hook."""
    seen = _seen(tmp_path)
    assert main([seen], json.dumps(["not", "a", "dict"])) == 0
