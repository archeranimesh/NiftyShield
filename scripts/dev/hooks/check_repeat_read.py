"""PreToolUse warn — a second ``Read`` of a path already read this session.

Registered via ``.claude/hooks/repeat_read.sh`` on ``Read`` / ``Edit`` /
``Write``. Warn-only: prints guidance to stdout and always exits 0.

Seen paths are tracked in a session-scoped file passed as ``argv[0]`` (the shim
derives it from the Claude Code PID). An ``Edit`` or ``Write`` to a path clears
it, so a re-``Read`` after a real modification is not flagged.

Closes ``suggestions.md`` ``reread-file-already-in-context``. The
Edit/Write-precondition re-Read (the harness requires a prior ``Read`` before
``Edit``) is a harness constraint, not caught here — that residual is accepted
in the SWEEP-1 cluster map.

Run directly; ``print`` is the hook output contract, not a log line.
"""

from __future__ import annotations

import json
import sys

MESSAGE = (
    "⚠ already Read this session: {path}\n"
    "Edit against the copy already in context, or use `get_code_snippet` / "
    "`sed -n 'N,Mp'` for a specific block instead of a second Read."
)


def _load(seen_path: str) -> set[str]:
    """Return the set of paths recorded in ``seen_path`` (empty if absent)."""
    try:
        with open(seen_path, encoding="utf-8") as fh:
            return {line.strip() for line in fh if line.strip()}
    except OSError:
        return set()


def _save(seen_path: str, paths: set[str]) -> None:
    """Overwrite ``seen_path`` with ``paths``, one per line."""
    body = "\n".join(sorted(paths))
    with open(seen_path, "w", encoding="utf-8") as fh:
        fh.write(body + "\n" if body else "")


def evaluate(tool_name: str, file_path: str, seen_path: str) -> str | None:
    """Update the seen-set for one tool call; return a warning string or None.

    Args:
        tool_name: The intercepted tool (``Read``, ``Edit``, ``Write``).
        file_path: The ``file_path`` from the tool input; ``""`` if none.
        seen_path: Path to the session-scoped seen-paths file.

    Returns:
        A warning to print when a path is being re-read with no intervening
        edit, else None.
    """
    if not file_path:
        return None
    seen = _load(seen_path)
    if tool_name in ("Edit", "Write"):
        if file_path in seen:
            seen.discard(file_path)
            _save(seen_path, seen)
        return None
    if tool_name == "Read":
        warning = MESSAGE.format(path=file_path) if file_path in seen else None
        if file_path not in seen:
            seen.add(file_path)
            _save(seen_path, seen)
        return warning
    return None


def main(argv: list[str], stdin_text: str) -> int:
    """Parse the PreToolUse payload on stdin; print a warning if warranted."""
    seen_path = argv[0] if argv else "/tmp/niftyshield-seen-reads"
    try:
        data = json.loads(stdin_text)
    except (ValueError, TypeError):
        return 0
    tool_name = data.get("tool_name", "")
    file_path = data.get("tool_input", {}).get("file_path", "") or ""
    try:
        warning = evaluate(tool_name, file_path, seen_path)
    except OSError:
        return 0
    if warning:
        print(warning)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], sys.stdin.read()))
