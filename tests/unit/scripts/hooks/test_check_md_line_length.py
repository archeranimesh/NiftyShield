"""Unit tests for scripts/hooks/check_md_line_length.py."""

from scripts.hooks.check_md_line_length import IGNORE_MARKER, MAX_LEN, main


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
