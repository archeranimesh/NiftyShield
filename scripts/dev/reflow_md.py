"""Reflow Markdown prose to the fill-to-≤200 line style (RDO-17.7 §A).

Prose paragraphs, list-item bodies and blockquote text are re-wrapped so each
line fills to the last word boundary before the width cap (200 chars). Word
order and word content are never changed — only inter-word whitespace and line
breaks — so a ``git diff --word-diff`` of a reflow shows zero word insert/delete.

Left verbatim: fenced and indented code, table rows, headings, thematic breaks,
HTML-comment lines, YAML front matter, and any list item or blockquote whose
body itself contains a nested list or code fence (too structural to re-wrap
safely). A single word longer than the cap is placed on its own line, matching
the ``<!-- lint-ignore-length -->`` escape hatch of the ``md-line-length`` hook.

This is the reusable engine behind the RDO-17.5→17.7 folder conversions; it is
meant to be re-run on the remaining legacy ``docs/plan/`` folders as they are
converted (see ``docs/plan/README.md`` §"Markdown line style").

Usage::

    python -m scripts.dev.reflow_md docs/plan/<folder>          # rewrite in place
    python -m scripts.dev.reflow_md --check docs/plan/<folder>  # report only, exit 1 if any would change

``print`` here is the CLI output contract, not a log line.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MAX_LEN = 200

_FENCE_RE = re.compile(r"^(?P<indent>\s{0,3})(?P<fence>`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
_HR_RE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_HTML_COMMENT_RE = re.compile(r"^\s*<!--")
_LIST_RE = re.compile(r"^(?P<indent>\s*)(?P<marker>[-*+]|\d+[.)])(?P<gap>\s+)(?P<body>.*)$")
_BLOCKQUOTE_RE = re.compile(r"^(?P<prefix>\s{0,3}(?:>\s?)+)(?P<body>.*)$")
_INDENTED_CODE_RE = re.compile(r"^(?: {4}|\t)")
_MARKER_WORD_RE = re.compile(r"^([-*+]|\d+[.)])$")


def _wrap(text: str, width: int, subsequent_indent: str = "") -> list[str]:
    """Greedily wrap ``text`` at word boundaries; never split a word.

    Args:
        text: The already-joined paragraph text (single-spaced between words).
        width: Cap for each produced line *including* ``subsequent_indent``.
        subsequent_indent: Prefix prepended to every line after the first
            (hanging indent for list items).

    Returns:
        One string per output line. A word longer than the budget sits alone
        on its line rather than being broken. A wrapped line is never left
        starting with a bare list-marker token (``-`` ``*`` ``+`` ``1.``) — that
        would render as a spurious nested bullet — so such a token is always kept
        off line-start (pulled onto the previous line with its preceding word, or
        tucked onto the end of that line if the word there is alone).
    """
    words = text.split()
    if not words:
        return [""]
    rows: list[list[str]] = [[words[0]]]
    cap = width - len(subsequent_indent)
    for word in words[1:]:
        if len(" ".join(rows[-1])) + 1 + len(word) <= cap:
            rows[-1].append(word)
        elif _MARKER_WORD_RE.match(word):
            # Never let a wrapped line start with a bare "-"/"*"/"+"/"1." token —
            # it renders as a spurious nested bullet. Keep the marker off line-start
            # by pulling the preceding word down with it (or, if that word is alone
            # on its line, tucking the marker onto the end of it).
            if len(rows[-1]) > 1:
                rows.append([rows[-1].pop(), word])
            else:
                rows[-1].append(word)
        else:
            rows.append([word])
    lines = [" ".join(row) for row in rows]
    return [lines[0]] + [f"{subsequent_indent}{line}" for line in lines[1:]]


def _closes_fence(fence_match: re.Match[str] | None, open_token: str, line: str) -> bool:
    """True if ``line`` is a valid closing fence for the currently-open one.

    Per CommonMark the closer must use the same fence character, be at least as
    long as the opener, and carry no info string — so ``` ```python ``` inside a
    ``` ``` ``` block does *not* close it.
    """
    if fence_match is None:
        return False
    fence = fence_match["fence"]
    if fence[0] != open_token[0] or len(fence) < len(open_token):
        return False
    return not line[fence_match.end() :].strip()


def _is_structural(line: str) -> bool:
    """True if ``line`` starts a block that must not be merged into prose."""
    stripped = line.strip()
    if not stripped:
        return True
    if _HEADING_RE.match(line) or _HR_RE.match(line) or _HTML_COMMENT_RE.match(line):
        return True
    if stripped.startswith("|"):
        return True
    if _INDENTED_CODE_RE.match(line):
        return True
    return False


def _reflow_list_item(lines: list[str], start: int, width: int) -> tuple[list[str], int]:
    """Reflow one list item (marker line plus lazy/indented continuation).

    Returns the rewritten lines and the index of the first line not consumed.
    """
    match = _LIST_RE.match(lines[start])
    if match is None:  # pragma: no cover - caller guarantees a list line
        raise ValueError("_reflow_list_item called on a non-list line")
    marker_prefix = f"{match['indent']}{match['marker']}{match['gap']}"
    hang = " " * len(marker_prefix)
    body_parts = [match["body"].strip()]
    idx = start + 1
    while idx < len(lines):
        line = lines[idx]
        if not line.strip():
            break
        if _LIST_RE.match(line) or _FENCE_RE.match(line) or _is_structural(line):
            break
        body_parts.append(line.strip())
        idx += 1
    joined = " ".join(part for part in body_parts if part)
    wrapped = _wrap(joined, width, subsequent_indent=hang)
    out = [f"{marker_prefix}{wrapped[0]}"] + wrapped[1:]
    return out, idx


def _reflow_blockquote(lines: list[str], start: int, width: int) -> tuple[list[str], int]:
    """Reflow a run of same-prefix blockquote lines; bail to verbatim on nesting."""
    match = _BLOCKQUOTE_RE.match(lines[start])
    if match is None:  # pragma: no cover - caller guarantees a blockquote line
        raise ValueError("_reflow_blockquote called on a non-blockquote line")
    prefix = match["prefix"].rstrip() + " "  # keep the '>' run as authored; one trailing space
    depth = prefix.count(">")
    end = start
    bodies: list[str] = []
    nested = False
    while end < len(lines):
        bq = _BLOCKQUOTE_RE.match(lines[end])
        if bq is None or not lines[end].strip():
            break
        if bq["prefix"].count(">") != depth:
            break  # nesting-depth change — end this run, don't flatten ">>" into ">"
        body = bq["body"]
        if _LIST_RE.match(body) or body.strip().startswith("```") or _HEADING_RE.match(body):
            nested = True
        bodies.append(body.strip())
        end += 1
    if nested:
        return lines[start:end], end
    wrapped = _wrap(" ".join(part for part in bodies if part), width - len(prefix))
    return [f"{prefix}{line}" for line in wrapped], end


def reflow_text(text: str, width: int = MAX_LEN) -> str:
    """Reflow a full Markdown document to the fill-to-≤``width`` style.

    Single-pass line-oriented state machine: ``in_front_matter`` and
    ``in_fence`` (+ ``fence_token``) are the only carried state; every other
    block kind is decided from the current line alone. Prose paragraphs and
    list/quote bodies are gathered then handed to ``_wrap``; everything else is
    emitted verbatim.
    """
    lines = text.split("\n")
    trailing_newline = text.endswith("\n")
    if trailing_newline:
        lines = lines[:-1]
    out: list[str] = []
    idx = 0
    in_fence = False
    fence_token = ""
    in_front_matter = False
    while idx < len(lines):
        line = lines[idx]
        if idx == 0 and line.strip() == "---":
            in_front_matter = True
            out.append(line)
            idx += 1
            continue
        if in_front_matter:
            out.append(line)
            if line.strip() == "---":
                in_front_matter = False
            idx += 1
            continue
        fence_match = _FENCE_RE.match(line)
        if in_fence:
            out.append(line)
            if _closes_fence(fence_match, fence_token, line):
                in_fence = False
            idx += 1
            continue
        if fence_match:
            in_fence = True
            fence_token = fence_match["fence"]
            out.append(line)
            idx += 1
            continue
        if not line.strip() or _is_structural(line):
            out.append(line)
            idx += 1
            continue
        if _LIST_RE.match(line):
            rewritten, idx = _reflow_list_item(lines, idx, width)
            out.extend(rewritten)
            continue
        if _BLOCKQUOTE_RE.match(line) and line.lstrip().startswith(">"):
            rewritten, idx = _reflow_blockquote(lines, idx, width)
            out.extend(rewritten)
            continue
        para: list[str] = []
        while idx < len(lines):
            nxt = lines[idx]
            if (
                not nxt.strip()
                or _is_structural(nxt)
                or _LIST_RE.match(nxt)
                or _FENCE_RE.match(nxt)
                or (_BLOCKQUOTE_RE.match(nxt) and nxt.lstrip().startswith(">"))
            ):
                break
            para.append(nxt.strip())
            idx += 1
        out.extend(_wrap(" ".join(para), width))
    result = "\n".join(out)
    return f"{result}\n" if trailing_newline else result


def _iter_md_files(paths: list[str]) -> list[Path]:
    """Expand file/dir args into a sorted list of ``.md`` files."""
    found: set[Path] = set()
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            found.update(p.rglob("*.md"))
        elif p.suffix == ".md":
            found.add(p)
    return sorted(found)


def main(argv: list[str]) -> int:
    """Reflow (or, with ``--check``, report) every ``.md`` under the given paths."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", help="Markdown files or directories")
    parser.add_argument(
        "--check", action="store_true", help="report only; exit 1 if any file would change"
    )
    parser.add_argument("--width", type=int, default=MAX_LEN, help=f"line cap (default {MAX_LEN})")
    args = parser.parse_args(argv)

    changed: list[Path] = []
    for path in _iter_md_files(args.paths):
        original = path.read_text(encoding="utf-8")
        reflowed = reflow_text(original, args.width)
        if reflowed == original:
            continue
        changed.append(path)
        if not args.check:
            path.write_text(reflowed, encoding="utf-8")

    verb = "would reflow" if args.check else "reflowed"
    for path in changed:
        print(f"{verb} {path}")
    if args.check and changed:
        print(f"\n{len(changed)} file(s) not in fill-to-≤{args.width} style.")
        return 1
    if not changed:
        print(f"all files already in fill-to-≤{args.width} style.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
