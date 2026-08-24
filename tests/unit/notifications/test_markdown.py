"""Unit tests for src/notifications/markdown.py."""

from src.notifications.markdown import MARKDOWNV2_RESERVED, escape_markdown, mdcode


def test_escape_markdown_escapes_all_reserved_chars() -> None:
    text = MARKDOWNV2_RESERVED
    expected = "".join(f"\\{ch}" for ch in MARKDOWNV2_RESERVED)
    assert escape_markdown(text) == expected


def test_escape_markdown_noop_on_plain_text() -> None:
    text = "Delta neutral adjustment complete"
    assert escape_markdown(text) == text


def test_escape_markdown_handles_prose_punctuation() -> None:
    text = "Captured: 4% (up from 2%)."
    assert escape_markdown(text) == "Captured: 4% \\(up from 2%\\)\\."


def test_escape_markdown_escapes_realistic_assignment_fragment() -> None:
    # Regression: '=' is in MARKDOWNV2_RESERVED but was never exercised
    # end-to-end by an exhaustive-alphabet-only test (ROLL-13 workshop, 2026-08-11).
    text = "qty=480"
    assert escape_markdown(text) == "qty\\=480"


def test_escape_markdown_does_not_escape_non_reserved_unicode() -> None:
    # Regression (ROLL-13 workshop, 2026-08-11): a non-ASCII symbol like an
    # em dash must pass through untouched — it is not in MARKDOWNV2_RESERVED,
    # and a stray backslash in front of it renders as a literal '\' on
    # Telegram without failing the send, so this needs its own assertion
    # rather than relying on "did it send" to catch the bug.
    text = "Rolled — new strike selected"
    result = escape_markdown(text)
    assert result == text
    assert "\\—" not in result


def test_mdcode_wraps_in_backticks() -> None:
    assert mdcode("DELTA_WARN") == "`DELTA_WARN`"


def test_mdcode_falls_back_when_value_contains_backtick() -> None:
    value = "weird`value"
    result = mdcode(value)
    # Falls back to escape_markdown() — never produces an unescaped/nested
    # backtick pair around a value that itself contains a backtick.
    assert result == escape_markdown(value)
    assert not result.startswith("`") or not result.endswith("`")


def test_mdcode_falls_back_when_value_contains_backslash() -> None:
    value = "path\\to\\thing"
    result = mdcode(value)
    assert result == escape_markdown(value)


def test_mdcode_empty_string() -> None:
    assert mdcode("") == "``"
