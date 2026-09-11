"""PreToolUse block — a bare full-suite ``pytest`` run from the main session.

Registered via ``.claude/hooks/inline_full_suite.sh`` on ``Bash``. Blocking:
prints guidance to stderr and exits 2 on a bare full-suite run (exit 0
otherwise) — DEBT-9 escalated this from warn-only after the
``pytest-inlined-not-test-runner`` slug recurred 17x post-remediation with no
change in behavior.

Fires when the command invokes ``pytest`` (directly, or via ``python -m pytest``)
against the whole unit tree — ``tests/unit`` / ``tests/`` / no path at all — with
no narrowing: no ``-k`` expression, no ``-m`` marker, no specific test file or
``::`` node id, no ``--last-failed`` / ``--lf`` / ``--failed-first`` / ``--ff``.

Such a run belongs in the ``@test-runner`` subagent (Haiku, isolated context),
not the main session where its output is carried for every later turn. Closes
``suggestions.md`` ``pytest-inlined-not-test-runner`` and
``full-suite-run-for-docs-only-change``.

Run directly; ``print`` is the hook output contract, not a log line.
"""

from __future__ import annotations

import json
import os
import shlex
import sys

_NARROW_FLAGS = ("-k", "-m", "--last-failed", "--lf", "--failed-first", "--ff")

MESSAGE = (
    "⚠ full-suite pytest in the main session — spawn `@test-runner` instead so the "
    "run stays in an isolated context (the AutoTrigger fires it once before "
    "`@code-reviewer` / the commit).\nFor a docs/tooling-only change, gate on the "
    "targeted dir instead, e.g. `pytest tests/unit/scripts/dev/hooks/`."
)


def _pytest_args(tokens: list[str]) -> list[str] | None:
    """Return the args after the pytest invocation, or None if not a pytest run."""
    if not tokens:
        return None
    if os.path.basename(tokens[0]) == "pytest":
        return tokens[1:]
    if os.path.basename(tokens[0]).startswith("python"):
        if tokens[1:3] == ["-m", "pytest"]:
            return tokens[3:]
    return None


def _is_narrowed(args: list[str]) -> bool:
    """True if any argument narrows the run below the whole unit tree."""
    for tok in args:
        if tok in _NARROW_FLAGS or tok.startswith("-k=") or tok.startswith("-m="):
            return True
        if tok.startswith("-"):
            continue
        norm = tok.lstrip("./").rstrip("/")
        if norm in ("tests", "tests/unit"):
            continue
        # a positional that is not the whole tree: a file, dir, or node id
        if "::" in tok or tok.endswith(".py") or norm.startswith("tests/"):
            return True
    return False


def evaluate(command: str) -> str | None:
    """Return a warning for a bare full-suite pytest run, else None."""
    if not command:
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    # only look at the first pipeline segment
    if "|" in tokens:
        tokens = tokens[: tokens.index("|")]
    args = _pytest_args(tokens)
    if args is None:
        return None
    if _is_narrowed(args):
        return None
    return MESSAGE


def main(stdin_text: str) -> int:
    """Parse the PreToolUse payload on stdin; block (exit 2) on a bare full-suite run."""
    try:
        data = json.loads(stdin_text)
    except (ValueError, TypeError):
        return 0
    if not isinstance(data, dict):
        return 0
    command = (data.get("tool_input") or {}).get("command", "") or ""
    warning = evaluate(command)
    if warning:
        print(warning, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.stdin.read()))
