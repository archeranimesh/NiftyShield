"""Fail if any Markdown line exceeds the 200-char backstop.

Enforced by the ``md-line-length`` pre-commit hook over root ``.md`` files plus
everything under ``docs/plan/`` and ``docs/bugs/``. 200 is a hard ceiling for
every line kind — prose, table rows, fenced code. Prose is *filled* to just
under this cap (fill-to-≤200 style; see ``docs/plan/README.md`` §"Markdown line
style" and ``scripts/dev/reflow_md.py``), not hand-wrapped narrower.

Put ``<!-- lint-ignore-length -->`` on the line immediately before a line that
legitimately must run long (a base64 blob, an unbreakable URL) to suppress it.

Run directly; ``print`` is the pre-commit output contract, not a log line.
"""

from __future__ import annotations

import sys

MAX_LEN = 200
IGNORE_MARKER = "<!-- lint-ignore-length -->"


def check_file(path: str) -> list[str]:
    """Scan one Markdown file for over-length lines.

    Args:
        path: Path to the Markdown file to scan.

    Returns:
        One ``path:line: N chars`` message per offending line; empty if clean.
    """
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    violations: list[str] = []
    for idx, line in enumerate(lines):
        if len(line) <= MAX_LEN:
            continue
        prev = lines[idx - 1] if idx > 0 else ""
        if IGNORE_MARKER in prev:
            continue
        violations.append(f"{path}:{idx + 1}: {len(line)} chars")
    return violations


def main(argv: list[str]) -> int:
    """Scan every path in ``argv``; return 1 if any line is over the cap."""
    violations: list[str] = []
    for path in argv:
        violations.extend(check_file(path))
    for message in violations:
        print(message)
    if violations:
        print(
            f"\n{len(violations)} line(s) over {MAX_LEN} chars. "
            f"Wrap them, or put '{IGNORE_MARKER}' on the "
            f"preceding line for an unbreakable token."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
