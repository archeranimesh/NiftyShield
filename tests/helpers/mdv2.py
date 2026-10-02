"""Offline MarkdownV2 safety check for Telegram message text (BUG-042).

Approximates what Telegram's parser rejects with a 400 "can't parse entities":
any reserved character left bare outside a fenced block or inline code span.
Paired ``*bold*`` markers are the one intended markup this codebase emits, so
balanced ``*`` are allowed; everything else reserved must be backslash-escaped.
"""

from __future__ import annotations

import re

_RESERVED = "_*[]()~`>#+-=|{}.!"


def unescaped_reserved(text: str) -> list[str]:
    """Return reserved characters a MarkdownV2 parse would trip on.

    Args:
        text: Message text exactly as it would be passed to ``send()``.

    Returns:
        The bare reserved characters found (an unpaired ``*`` counts once);
        empty when the text is MarkdownV2-safe.
    """
    text = re.sub(r"```.*?```", "", text, flags=re.S)  # fence content is literal
    text = re.sub(r"\\.", "", text, flags=re.S)  # escaped pairs are inert
    text = re.sub(r"`[^`]*`", "", text)  # inline code spans are literal
    bare = [ch for ch in text if ch in _RESERVED and ch != "*"]
    if text.count("*") % 2:
        bare.append("*")
    return bare
