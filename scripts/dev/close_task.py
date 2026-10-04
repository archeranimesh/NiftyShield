"""Close one task of a ``docs/plan`` story: tick it, set its SHA, advance the pointers.

Deterministic part of the "docs close" commit that follows every task commit.
For one task id + commit SHA it:

1. ticks the box and replaces the first ``SHA: —`` in that task's ``tasks.md`` item;
2. advances the ``**Open: ...**`` marker (a single id becomes the next unchecked id; a list
   drops the closed id; none left becomes ``none — complete``);
3. adds a line under ``## Session Log`` in ``TODOS.md``;
4. rewrites prose pointers that already use the standard forms ``<ID> done, next **<ID>**`` and
   ``(<ID> done)`` in the epic ``README.md`` / ``docs/plan/README.md``, and ``next **<ID>**``
   in ``TODOS.md``. Pointers in any other wording are reported, never guessed;
5. reflows the edited Markdown to the fill-to-≤200 style.

Usage::

    python -m scripts.dev.close_task docs/plan/<epic>/<story>/tasks.md --task PC-5 --sha abc1234 \\
        --summary "renderer; test-runner green (4040), code-reviewer clean"

Nothing is written unless every edit computes successfully. Staging and committing stay with the caller.
``print`` here is the CLI output contract, not a log line.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from scripts.dev.reflow_md import reflow_text

_TASK_ID_RE = re.compile(r"^(?P<prefix>[A-Za-z]+)-(?P<num>\d+)$")
_ID_RE = re.compile(r"[A-Za-z]+-\d+")
_OPEN_RE = re.compile(r"^\*\*Open: (?P<body>.*)\.\*\*\s*$", re.MULTILINE)
_SESSION_LOG = "## Session Log"


class CloseTaskError(ValueError):
    """Raised when a task cannot be closed (missing, already done, malformed)."""


def _item_range(lines: list[str], start: int) -> int:
    """Return the end index (exclusive) of the list item that begins at ``start``."""
    end = start + 1
    while end < len(lines) and lines[end].strip() and not lines[end].startswith(("- ", "#")):
        end += 1
    return end


def tick_task(text: str, task_id: str, sha: str) -> str:
    """Tick ``task_id`` and replace its first ``SHA: —`` placeholder with ``sha``.

    Args:
        text: Contents of a ``tasks.md``.
        task_id: Task id such as ``PC-5``.
        sha: Commit SHA to record.

    Returns:
        The updated text.

    Raises:
        CloseTaskError: If the task is absent, already ticked, or has no SHA placeholder.
    """
    lines = text.split("\n")
    open_re = re.compile(rf"^- \[ \] \*\*{re.escape(task_id)}\*\*")
    done_re = re.compile(rf"^- \[x\] \*\*{re.escape(task_id)}\*\*")
    for i, line in enumerate(lines):
        if done_re.match(line):
            raise CloseTaskError(f"{task_id} is already ticked")
        if not open_re.match(line):
            continue
        end = _item_range(lines, i)
        item = "\n".join(lines[i:end]).replace("- [ ]", "- [x]", 1)
        if "SHA: —" not in item:
            raise CloseTaskError(f"{task_id} has no 'SHA: —' placeholder")
        lines[i:end] = item.replace("SHA: —", f"SHA: {sha}", 1).split("\n")
        return "\n".join(lines)
    raise CloseTaskError(f"{task_id} not found as an unchecked task")


def next_unchecked(text: str) -> str | None:
    """Return the id of the first unchecked task in ``text``, or ``None``."""
    match = re.search(r"^- \[ \] \*\*([A-Za-z]+-\d+)\*\*", text, re.MULTILINE)
    return match.group(1) if match else None


def advance_open(text: str, task_id: str) -> str:
    """Update the ``**Open: ...**`` marker after ``task_id`` was ticked.

    Args:
        text: ``tasks.md`` text with ``task_id`` already ticked.
        task_id: The task just closed.

    Returns:
        The updated text; unchanged if there is no marker or it already says ``none``.
    """
    nxt = next_unchecked(text)

    def repl(m: re.Match[str]) -> str:
        body = m.group("body")
        if body.startswith("none"):
            return m.group(0)
        ids = _ID_RE.findall(body)
        if len(ids) > 1:
            kept = [i for i in ids if i != task_id]
            return f"**Open: {', '.join(kept)}.**" if kept else "**Open: none — complete.**"
        return f"**Open: {nxt}.**" if nxt else "**Open: none — complete.**"

    return _OPEN_RE.sub(repl, text, count=1)


def rewrite_pointers(text: str, prefix: str, closed: str, nxt: str, todos: bool) -> tuple[str, int]:
    """Rewrite standard-form progress pointers; return the new text and the match count.

    Args:
        text: README or TODOS text.
        prefix: Task id prefix, e.g. ``PC``.
        closed: The task just closed.
        nxt: The next task id.
        todos: Also rewrite the bare ``next **<ID>**`` form (used in ``TODOS.md``).

    Returns:
        ``(new_text, match_count)``.
    """
    p = re.escape(prefix)
    text, n1 = re.subn(
        rf"{p}-\d+ done, next \*\*{p}-\d+\*\*", f"{closed} done, next **{nxt}**", text
    )
    text, n2 = re.subn(rf"\({p}-\d+ done\)", f"({closed} done)", text)
    n3 = 0
    if todos:
        text, n3 = re.subn(rf"next \*\*{p}-\d+\*\*", f"next **{nxt}**", text)
        n3 = max(n3 - n1, 0)  # P1 matches already rewrote one "next **ID**" each
    return text, n1 + n2 + n3


def add_session_log(text: str, line: str) -> str:
    """Insert ``line`` directly under the ``## Session Log`` heading.

    Raises:
        CloseTaskError: If the heading is missing.
    """
    lines = text.split("\n")
    for i, existing in enumerate(lines):
        if existing.strip() == _SESSION_LOG:
            lines.insert(i + 1, line)
            return "\n".join(lines)
    raise CloseTaskError(f"'{_SESSION_LOG}' heading not found")


def close_task(
    tasks_md: Path, task_id: str, sha: str, summary: str, root: Path, today: str
) -> list[str]:
    """Apply every edit for one closed task and return a human-readable report.

    Args:
        tasks_md: Path to the story's ``tasks.md``.
        task_id: Task id such as ``PC-5``.
        sha: Commit SHA of the task's code commit.
        summary: One-line summary for the ``TODOS.md`` session log.
        root: Repo root holding ``TODOS.md`` and ``docs/plan/README.md``.
        today: ISO date for the session-log line.

    Returns:
        Report lines (what changed, what needs a manual pointer edit).

    Raises:
        CloseTaskError: On any malformed input; nothing is written in that case.
    """
    id_match = _TASK_ID_RE.match(task_id)
    if not id_match:
        raise CloseTaskError(f"bad task id {task_id!r} (expected e.g. PC-5)")
    prefix = id_match.group("prefix")
    tasks_text = advance_open(
        tick_task(tasks_md.read_text(encoding="utf-8"), task_id, sha), task_id
    )
    nxt = next_unchecked(tasks_text)
    story = tasks_md.parent.name
    todos_path = root / "TODOS.md"
    log = f"- [{today}] {story} {task_id} closed (`{sha}`): {summary}"
    todos_text = add_session_log(todos_path.read_text(encoding="utf-8"), log)
    edits: dict[Path, str] = {tasks_md: tasks_text}
    report = [f"ticked {task_id} (SHA {sha}); next unchecked: {nxt or 'none — story complete'}"]
    pointer_files = [tasks_md.parent.parent / "README.md", root / "docs/plan/README.md"]
    if nxt is None:
        report.append("story complete: update epic/plan README status and archive by hand")
    else:
        for path in pointer_files:
            new, n = rewrite_pointers(
                path.read_text(encoding="utf-8"), prefix, task_id, nxt, todos=False
            )
            edits[path] = new
            report.append(
                f"{path.relative_to(root)}: {n} pointer(s) rewritten"
                + ("" if n else " — CHECK BY HAND")
            )
        todos_text, n = rewrite_pointers(todos_text, prefix, task_id, nxt, todos=True)
        report.append(
            f"TODOS.md: {n} pointer(s) rewritten; verify any file hint next to 'next **{nxt}**'"
        )
    edits[todos_path] = todos_text
    for path, new in edits.items():
        path.write_text(reflow_text(new), encoding="utf-8")
    return report


def main(argv: list[str]) -> int:
    """CLI entry point; returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tasks_md", type=Path, help="path to the story's tasks.md")
    parser.add_argument("--task", required=True, help="task id, e.g. PC-5")
    parser.add_argument("--sha", required=True, help="commit SHA of the task's code commit")
    parser.add_argument("--summary", required=True, help="one-line TODOS.md session-log summary")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repo root (default: cwd)")
    parser.add_argument(
        "--date", default=date.today().isoformat(), help="log date (default: today)"
    )
    args = parser.parse_args(argv)
    try:
        report = close_task(
            args.tasks_md.resolve(),
            args.task,
            args.sha,
            args.summary,
            args.root.resolve(),
            args.date,
        )
    except (CloseTaskError, OSError) as exc:
        print(f"close_task: {exc}", file=sys.stderr)
        return 1
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
