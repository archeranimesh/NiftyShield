"""Unit tests for scripts/dev/reflow_md.py."""

from scripts.dev.reflow_md import MAX_LEN, main, reflow_text


def _words(text: str) -> list[str]:
    """Whitespace-and-blockquote-marker-insensitive token stream of ``text``."""
    return text.replace(">", " ").split()


# --- reflow_text: prose ------------------------------------------------------


def test_prose_fills_to_just_under_cap():
    """Short semantic-linefeed lines are joined and refilled to <= MAX_LEN."""
    src = "\n".join(["one two three", "four five", "six seven eight nine"]) + "\n"

    out = reflow_text(src, width=25)

    assert out == "one two three four five\nsix seven eight nine\n"
    assert all(len(line) <= 25 for line in out.splitlines())
    assert _words(src) == _words(out)


def test_reflow_is_idempotent():
    """Reflowing already-reflowed text changes nothing."""
    src = (
        "A sentence that is quite a bit longer than the wrap width so it has "
        "to break across several lines when reflowed.\n"
    )

    once = reflow_text(src, width=40)
    assert reflow_text(once, width=40) == once


def test_word_longer_than_cap_sits_alone():
    """An unbreakable token over the cap is emitted on its own line, not split."""
    src = "short https://example.com/a/really/long/url/that/exceeds more text\n"

    out = reflow_text(src, width=20)

    assert "https://example.com/a/really/long/url/that/exceeds" in out.splitlines()
    assert _words(src) == _words(out)


# --- reflow_text: structure preservation -----------------------------------


def test_fenced_code_and_tables_are_verbatim():
    """Code fences and table rows pass through untouched even when over-long."""
    src = (
        "Intro prose line that is short.\n\n"
        "```python\n"
        "x = 'a very long code line that must not be touched at all by the reflow pass'\n"
        "```\n\n"
        "| col a | col b that is long enough to matter and would otherwise wrap |\n"
        "| ----- | ---------------------------------------------------------- |\n"
    )

    out = reflow_text(src, width=30)

    assert "x = 'a very long code line that must not be touched at all by the reflow pass'" in out
    assert "| col a | col b that is long enough to matter and would otherwise wrap |" in out


def test_list_item_marker_and_hanging_indent_preserved():
    """A wrapped list item keeps its marker and indents continuation lines."""
    src = "- first item with enough words to force a wrap onto a second line here\n"

    out = reflow_text(src, width=30)
    lines = out.splitlines()

    assert lines[0].startswith("- first")
    assert all(len(line) <= 30 for line in lines)
    assert lines[1].startswith("  ")  # hanging indent, width of "- "
    assert _words(src) == _words(out)


def test_wrapped_line_never_starts_with_bare_marker_token():
    """A '+' used as prose must not land at line-start (spurious nested bullet)."""
    src = (
        "direction word derived from the sign of net_qty and then + quantity "
        "as an absolute value instead of a signed field\n"
    )

    out = reflow_text(src, width=40)

    assert not any(line.lstrip().startswith("+ ") for line in out.splitlines())
    assert _words(src) == _words(out)


def test_blockquote_prefix_kept_on_every_line():
    """Blockquote text refills but each output line keeps the '> ' prefix."""
    src = "> alpha beta gamma\n> delta epsilon zeta eta theta iota kappa\n"

    out = reflow_text(src, width=25)

    assert all(line.startswith("> ") for line in out.splitlines())
    assert all(len(line) <= 25 for line in out.splitlines())


def test_blockquote_depth_change_is_not_flattened():
    """A deeper '>>' line must not be merged into the outer '>' quote."""
    src = "> outer one two three\n>> inner four five six seven eight nine\n"

    out = reflow_text(src, width=30)

    assert any(line.startswith(">> ") for line in out.splitlines())


def test_yaml_front_matter_is_verbatim():
    """A leading '---' fenced YAML block passes through untouched."""
    src = "---\ntitle: a very long front matter value that would otherwise wrap somewhere\n---\n\nbody text here\n"

    out = reflow_text(src, width=20)

    assert out.startswith(
        "---\ntitle: a very long front matter value that would otherwise wrap somewhere\n---\n"
    )


def test_tilde_fence_round_trips():
    """~~~ fences are honored the same as ``` fences."""
    src = "~~~\na long code line inside a tilde fence that must survive the reflow intact\n~~~\n"

    out = reflow_text(src, width=25)

    assert "a long code line inside a tilde fence that must survive the reflow intact" in out


def test_info_string_line_does_not_close_a_fence():
    """A '```lang' line inside an open fence is code, not a closing fence."""
    src = (
        "```python\n"
        "x = 1  # this line is long enough that it would be split if treated as prose text\n"
        "```javascript\n"
        "y = 2  # still inside the original fence, also long enough to be split as prose\n"
        "```\n"
    )

    out = reflow_text(src, width=30)

    assert (
        "x = 1  # this line is long enough that it would be split if treated as prose text" in out
    )
    assert "y = 2  # still inside the original fence, also long enough to be split as prose" in out


def test_numbered_list_marker_preserved():
    """An ordered-list item keeps its 'N.' marker and hanging indent."""
    src = "1. an ordered list item with enough words in it to wrap across two lines here\n"

    out = reflow_text(src, width=30)
    lines = out.splitlines()

    assert lines[0].startswith("1. ")
    assert lines[1].startswith("   ")  # width of "1. "
    assert _words(src) == _words(out)


def test_missing_trailing_newline_is_preserved():
    """Input without a trailing newline stays that way."""
    assert not reflow_text("one two three").endswith("\n")
    assert reflow_text("one two three\n").endswith("\n")


# --- main() ----------------------------------------------------------------


def test_main_check_reports_and_exits_nonzero(tmp_path, capsys):
    """--check on a file that would change returns 1 and names the file."""
    path = tmp_path / "doc.md"
    path.write_text("aaa\nbbb\nccc\n", encoding="utf-8")

    assert main(["--check", str(path)]) == 1
    assert "would reflow" in capsys.readouterr().out
    assert path.read_text(encoding="utf-8") == "aaa\nbbb\nccc\n"  # unwritten


def test_main_rewrites_in_place_and_is_clean_afterwards(tmp_path, capsys):
    """A plain run rewrites the file; a following --check run passes."""
    path = tmp_path / "doc.md"
    path.write_text("one two\nthree four\nfive six\n", encoding="utf-8")

    assert main([str(path)]) == 0
    assert path.read_text(encoding="utf-8") == "one two three four five six\n"
    capsys.readouterr()
    assert main(["--check", str(path)]) == 0


def test_default_width_is_the_200_char_backstop():
    """The module cap matches the md-line-length hook's ceiling."""
    assert MAX_LEN == 200
