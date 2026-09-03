"""PreToolUse warn — an unscoped ``grep``/``sed``/``awk`` over a large file.

Registered via ``.claude/hooks/wide_grep.sh`` on ``Bash``. Warn-only: prints
guidance to stdout and always exits 0.

Fires when the first pipeline segment is a ``grep``/``sed``/``awk`` (not fed by
an upstream pipe) that:

* reads a file argument over ``LARGE_FILE_LINES`` lines with no result-narrowing
  flag (``-c`` / ``-l`` / ``-o`` / ``--max-count``) and no downstream
  ``head``/``tail``/``cut`` or ``N,Mp`` range, or
* is a recursive ``grep`` (``-r``/``-R``) with no ``--include`` / ``--exclude``
  / ``--exclude-dir`` and no narrowing flag.

Closes ``suggestions.md`` ``wide-grep-dump-then-page``.

Run directly; ``print`` is the hook output contract, not a log line.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys

LARGE_FILE_LINES = 800

_GREP_TOOLS = ("grep", "egrep", "fgrep", "rg")
_STREAM_TOOLS = ("sed", "awk", "gawk")

_NARROW_RE = re.compile(
    r"(?:^|\s)(?:-c|--count|-l|-L|--files-with-matches|-o|--only-matching|"
    r"--max-count|-m\s*\d+)(?:\s|=|$)"
    r"|--include[= ]|--exclude(?:-dir)?[= ]"
)
_RANGE_RE = re.compile(r"\d+,\d*\s*[a-zA-Z]?p|(?:^|\s)\d+p(?:\s|$|['\"])")
_DOWNSTREAM_RE = re.compile(r"(?:^|\s)(?:head|tail|cut|wc)(?:\s|$)")

_FILE_HINT = (".md", ".py", ".txt", ".json", ".sql", ".yaml", ".yml", ".toml", ".sh", ".cfg")

MESSAGE = (
    "⚠ wide {tool} over {target} — this can write a large tool-result file that "
    "then costs a capped Read to page.\nScope it: `-c` for counts, `sed -n 'N,Mp'` "
    "for a range, `--include`/`--exclude-dir` for a recursive grep, or use "
    "`search_code(pattern)`."
)


def _line_count(path: str) -> int | None:
    """Return the line count of ``path``, or None if it is not a readable file."""
    try:
        with open(path, "rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return None


def _file_args(tokens: list[str]) -> list[str]:
    """Pull likely file-path arguments out of a token list."""
    out: list[str] = []
    for tok in tokens:
        if tok.startswith("-"):
            continue
        if os.sep in tok or tok.endswith(_FILE_HINT):
            out.append(tok)
    return out


def evaluate(command: str) -> str | None:
    """Return a warning string for an unscoped wide read, else None."""
    if not command:
        return None
    try:
        all_tokens = shlex.split(command)
    except ValueError:
        return None
    if "|" not in all_tokens:
        first_tokens = all_tokens
        downstream = ""
    else:
        cut = all_tokens.index("|")
        first_tokens = all_tokens[:cut]
        downstream = " ".join(all_tokens[cut + 1 :])
    if not first_tokens:
        return None
    tool = os.path.basename(first_tokens[0])
    if tool not in _GREP_TOOLS + _STREAM_TOOLS:
        return None
    first = " ".join(first_tokens)
    if _NARROW_RE.search(first):
        return None
    if _RANGE_RE.search(first) or _DOWNSTREAM_RE.search(downstream):
        return None

    for arg in _file_args(first_tokens[1:]):
        count = _line_count(arg)
        if count is not None and count > LARGE_FILE_LINES:
            return MESSAGE.format(tool=tool, target=f"{arg} ({count} lines)")

    recursive = any(re.match(r"-[a-zA-Z]*[rR]", t) or t == "--recursive" for t in first_tokens)
    if tool in _GREP_TOOLS and recursive:
        return MESSAGE.format(tool=tool, target="a recursive tree")
    return None


def main(stdin_text: str) -> int:
    """Parse the PreToolUse payload on stdin; print a warning if warranted."""
    try:
        data = json.loads(stdin_text)
    except (ValueError, TypeError):
        return 0
    command = data.get("tool_input", {}).get("command", "") or ""
    warning = evaluate(command)
    if warning:
        print(warning)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.stdin.read()))
