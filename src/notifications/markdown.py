"""MarkdownV2 escaping helpers for Telegram notifications.

Telegram's MarkdownV2 parse mode reserves 18 characters outside a code
span: ``_*[]()~`>#+-=|{}.!``. Any of these appearing unescaped in plain
text either opens an unintended formatting entity or causes the send to
be rejected with a 400 ("can't parse entities"). ``TelegramNotifier.send()``
no longer auto-escapes (see ``src/notifications/CLAUDE.md``) — every
caller that interpolates a dynamic value, or writes static template
prose containing reserved punctuation, is responsible for using these
helpers.
"""

from __future__ import annotations

MARKDOWNV2_RESERVED = "_*[]()~`>#+-=|{}.!"


def escape_markdown(text: str) -> str:
    """Backslash-escape MarkdownV2 reserved characters in free text.

    Args:
        text: Arbitrary text that may contain any of MARKDOWNV2_RESERVED and
              should render as literal characters, not open/be part of a
              formatting entity. Covers both dynamic interpolated values AND
              static template prose (MarkdownV2's reserved set includes '.',
              '(', ')', '-' — ordinary punctuation, not just markup characters).

    Returns:
        text with every character in MARKDOWNV2_RESERVED preceded by a
        backslash. Safe to interpolate into or use as a larger
        MarkdownV2-formatted message without risk of unescaped entities
        from this substring specifically.
    """
    return "".join(f"\\{ch}" if ch in MARKDOWNV2_RESERVED else ch for ch in text)


def mdcode(value: str) -> str:
    """Wrap a dynamic value as an inline code span for safe interpolation.

    Args:
        value: A dynamic identifier/label (strategy_id, signal code, instrument
               key, error message) being interpolated into a larger MarkdownV2
               message.

    Returns:
        `` `value` `` — backtick-wrapped. Telegram does not parse entities
        inside a code span, so any MARKDOWNV2_RESERVED character inside value
        is inert regardless of count or balance. Preferred over
        escape_markdown() for anything that's conceptually an identifier
        (renders as monospace, which reads naturally for strategy IDs / signal
        codes) — use escape_markdown() only for free-form prose that must stay
        visually plain, not code-styled. If value itself contains a literal
        backtick or backslash, falls back to escape_markdown(value) instead of
        producing a broken/nested code span — Telegram's code-span escaping
        rule for backtick/backslash is a narrower special case than the
        general reserved-character rule, and reusing escape_markdown() here
        keeps this module's escaping behavior to a single source of truth
        rather than adding a second, subtly different rule.
    """
    if "`" in value or "\\" in value:
        return escape_markdown(value)
    return f"`{value}`"
