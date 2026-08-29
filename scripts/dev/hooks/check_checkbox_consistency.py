"""Check ``tasks.md`` checkbox-state consistency. See ``docs/plan/README.md`` §Conventions.

Convention (RDO-15): every task id carries exactly **one** checkbox — the one in the
working list. A trailing ``## Epic done when`` block (if present) is a prose criteria
list with no ``- [ ]`` / ``- [x]`` checkboxes, so nothing mirrors task state and nothing
can drift.

Checks, over every non-archived ``docs/plan/**/tasks.md`` (plus legacy ``*_tasks.md``)
and ``docs/bugs/task.md``:

1. no ``- [ ] **ID**`` / ``- [x] **ID**`` line inside a summary block (``## Epic done when``
   / ``## Story done when`` / ``## Definition of done`` / ``## Done when`` / ``## Acceptance``);
2. defensive — the same ``**ID**`` never appears with disagreeing checkbox state
   anywhere in one file (catches a re-introduced mirror);
3. cross-file — ``docs/plan/README.md`` ``next: **<id>**`` must not name an id that is
   already ``- [x]`` in that story's ``tasks.md``;
4. task-line tail — a working-list line that carries the ``| Review:`` field (i.e. is on
   the post-RDO-17.1 format) must have a well-formed ``| Owner: … | Model: … | Review: … |
   SHA: …`` tail with ``Review`` one of ``code-reviewer`` / ``greeks-analyst`` /
   ``roll-validator`` / ``none``, and ``SHA`` a placeholder (``—`` / ``<—>``) iff the box is
   unchecked, a real 7–40 hex SHA iff it is ticked. Legacy ``| Owner | Model | SHA`` and
   bare ``| SHA`` lines are grandfathered and skipped.

Modes:
    --all         audit everything (used by the md-organize skill); exits 1 on any finding
    <paths...>    check the task files those paths belong to (manual / tests)

Run directly; ``print`` is the output contract, not a log line.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]  # scripts/dev/hooks/ → repo root
PLAN_DIR = REPO_ROOT / "docs" / "plan"
BUGS_TASK = REPO_ROOT / "docs" / "bugs" / "task.md"
PLAN_README = PLAN_DIR / "README.md"
EXCLUDED = {"_TEMPLATE"}

HEADER_RE = re.compile(r"^(#+)\s+\S")
SUMMARY_RE = re.compile(
    r"^(#+)\s+(epic done when|story done when|definition of done|done when|acceptance)", re.I
)
CHECKBOX_RE = re.compile(r"^\s*-\s*\[([ xX~])\]\s*\*\*([^*]+?)\*\*")
README_ENTRY_RE = re.compile(r"\*\*`([a-z0-9_-]+)/`\*\*.*?next:\s*\*\*([A-Za-z0-9._-]+)\*\*", re.I)

# The canonical post-RDO-17.1 tail: `| Owner: X | Model: Y | Review: <token> | SHA: <w>`
# ending the line, with Review a bare token immediately before `| SHA:`. Legacy tails
# (`| Owner | Model | SHA` with no Review, or a prose-laden `| Review: <sentence>`) do not
# match and are grandfathered — skipped, not flagged.
TAIL_RE = re.compile(
    r"\|\s*Owner:\s*[^|]+?\s*"
    r"\|\s*Model:\s*[^|]+?\s*"
    r"\|\s*Review:\s*(?P<review>[A-Za-z][\w-]*)\s*"
    r"\|\s*SHA:\s*(?P<sha>\S+?)\s*$"
)
REVIEW_VALUES = {"code-reviewer", "greeks-analyst", "roll-validator", "none"}
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
PLACEHOLDER_SHA = {"—", "<—>", "–", "-", "tbd", "TBD"}


def _rel(path: Path) -> str:
    """Repo-relative string for display."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _norm_state(raw: str) -> str:
    """Map a raw checkbox char to ``x`` (done), ``~`` (in progress) or ``' '`` (open)."""
    low = raw.lower()
    return "x" if low == "x" else ("~" if low == "~" else " ")


def _check_task_tail(path: Path, lineno: int, task_id: str, state: str, joined: str) -> list[str]:
    """Validate the canonical ``| Owner | Model | Review | SHA`` tail of one working-list line.

    Only lines whose tail matches :data:`TAIL_RE` exactly are on the post-RDO-17.1 format;
    legacy tails (``| Owner | Model | SHA`` with no ``Review``, prose-laden ``| Review:``)
    are grandfathered and skipped.
    """
    match = TAIL_RE.search(joined)
    if match is None:
        return []
    findings: list[str] = []
    review = match.group("review").strip()
    if review not in REVIEW_VALUES:
        findings.append(
            f"{_rel(path)}:{lineno}: '{task_id}' Review: '{review}' is not one of "
            f"{sorted(REVIEW_VALUES)} (§Task-line format)"
        )
    sha = match.group("sha").strip().strip("`")
    if state == "x" and not SHA_RE.match(sha):
        findings.append(
            f"{_rel(path)}:{lineno}: '{task_id}' is ticked but SHA is '{sha}' — set the real "
            "commit SHA when ticking the box (§Task-line format)"
        )
    if state != "x" and sha not in PLACEHOLDER_SHA:
        findings.append(
            f"{_rel(path)}:{lineno}: '{task_id}' is unchecked but SHA is '{sha}' — an open "
            "task's SHA must be the placeholder '—' (§Task-line format)"
        )
    return findings


def _task_entries(lines: list[str]) -> list[tuple[int, str, str, str, bool]]:
    """Split ``lines`` into working-list entries.

    Each entry is ``(lineno, task_id, state, joined_text, in_summary)`` where ``state`` is
    ``x`` / ``~`` / ``' '`` and ``joined_text`` folds the checkbox line and its indented
    continuation lines (up to the next blank line or checkbox) into one string.
    """
    entries: list[tuple[int, str, str, str, bool]] = []
    in_summary = False
    summary_level = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        header = HEADER_RE.match(line)
        if header:
            if SUMMARY_RE.match(line):
                in_summary, summary_level = True, len(header.group(1))
            elif in_summary and len(header.group(1)) <= summary_level:
                in_summary = False

        box = CHECKBOX_RE.match(line)
        if not box:
            i += 1
            continue

        buf = [line]
        j = i + 1
        while (
            j < len(lines)
            and lines[j].strip()
            and not CHECKBOX_RE.match(lines[j])
            and lines[j][:1] in (" ", "\t")
        ):
            buf.append(lines[j])
            j += 1
        entries.append(
            (
                i + 1,
                box.group(2).strip(),
                _norm_state(box.group(1)),
                " ".join(s.strip() for s in buf),
                in_summary,
            )
        )
        i = j
    return entries


def check_file(path: Path) -> list[str]:
    """Return one message per checkbox-consistency problem in ``path``; empty if clean."""
    lines = path.read_text(encoding="utf-8").splitlines()
    findings: list[str] = []
    id_states: dict[str, set[str]] = {}
    id_line: dict[str, int] = {}

    for lineno, task_id, state, joined, in_summary in _task_entries(lines):
        if in_summary:
            findings.append(
                f"{_rel(path)}:{lineno}: '{task_id}' checkbox inside a summary block — "
                "'## Story done when' / '## Epic done when' must be prose criteria, no `- [ ]` (RDO-15)"
            )
            continue
        id_states.setdefault(task_id, set()).add(state)
        id_line.setdefault(task_id, lineno)
        findings.extend(_check_task_tail(path, lineno, task_id, state, joined))

    for task_id, states in id_states.items():
        if len(states) > 1:
            findings.append(
                f"{_rel(path)}:{id_line[task_id]}: '{task_id}' has disagreeing checkbox "
                f"state across the file ({sorted(states)}) — one checkbox per id (RDO-15)"
            )
    return findings


def check_readme_pointers() -> list[str]:
    """Warn when ``docs/plan/README.md`` points a story's ``next:`` marker at a done id."""
    if not PLAN_README.is_file():
        return []
    findings: list[str] = []
    for idx, line in enumerate(PLAN_README.read_text(encoding="utf-8").splitlines(), 1):
        match = README_ENTRY_RE.search(line)
        if not match:
            continue
        slug, task_id = match.group(1), match.group(2)
        task_file = PLAN_DIR / slug / "tasks.md"
        if not task_file.is_file():
            continue
        for raw in task_file.read_text(encoding="utf-8").splitlines():
            box = CHECKBOX_RE.match(raw)
            if box and box.group(2).strip() == task_id and _norm_state(box.group(1)) == "x":
                findings.append(
                    f"docs/plan/README.md:{idx}: '{slug}/' next-marker points at '{task_id}' "
                    f"which is already [x] in {slug}/tasks.md"
                )
                break
    return findings


def _task_files() -> list[Path]:
    """Every non-archived task file the audit covers."""
    files = sorted(PLAN_DIR.glob("**/tasks.md")) + sorted(PLAN_DIR.glob("**/*_tasks.md"))
    files = [f for f in files if not set(f.relative_to(PLAN_DIR).parts) & EXCLUDED]
    if BUGS_TASK.is_file():
        files.append(BUGS_TASK)
    return files


def _resolve_task_files(paths: list[str]) -> list[Path]:
    """Map file/dir paths to the distinct task files they belong to."""
    out: dict[str, Path] = {}
    for raw in paths:
        p = Path(raw)
        p = (REPO_ROOT / p).resolve() if not p.is_absolute() else p.resolve()
        if p.name == "tasks.md" or p.name.endswith("_tasks.md") or p.name == "task.md":
            if p.is_file():
                out[str(p)] = p
        elif p.is_dir():
            globbed = (
                sorted(p.glob("tasks.md"))
                + sorted(p.glob("*_tasks.md"))
                + sorted(p.glob("task.md"))
            )
            for task_file in globbed:
                out[str(task_file)] = task_file
    return list(out.values())


def main(argv: list[str]) -> int:
    """Run the checkbox-consistency check; return 1 on any finding."""
    audit = "--all" in argv
    files = (
        _task_files() if audit else _resolve_task_files([a for a in argv if not a.startswith("--")])
    )

    findings: list[str] = []
    for task_file in files:
        findings.extend(check_file(task_file))
    if audit:
        findings.extend(check_readme_pointers())

    for message in findings:
        print(message)
    if findings:
        print(
            f"\n{len(findings)} checkbox-consistency issue(s). "
            "See docs/plan/README.md §Conventions."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
