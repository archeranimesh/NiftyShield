"""Pre-commit sanity checks the ``commit`` skill runs before it stages a phase.

Not a git hook — a CLI the skill invokes in Step 1 so a recurring re-stage /
swap-only-commit cycle is caught before the commit, not after a ``pre-commit``
abort. Closes the ``suggestions.md`` "Commit flow & pre-commit" cluster
(SWEEP-4).

Checks, against the current staged set (``git diff --cached``):

1. **staged-index sanity** — every staged path is inside the phase's expected
   set (passed as one or more ``--expect`` prefixes). Warn only.
2. **``ruff format --check``** on staged ``.py`` — flags a file the format hook
   would reformat, and authored lines over the 100-char cap, before the hook
   aborts the commit. Blocker.
3. **md-line-length** on staged hook-covered ``.md`` — reuses
   ``check_md_line_length.check_file`` (200-char backstop). Blocker.
4. **next-marker** — if the staged diff ticks a ``- [ ] **ID**`` box, no staged
   ``tasks.md`` / ``README.md`` / ``TODOS.md`` may still name that id as the
   *next* task (``next: **ID**``, ``next is **ID**``, ``ID (next)``,
   ``Open: ID (next)``). Matches the prose forms the ``README_ENTRY_RE`` guard
   in ``check_checkbox_consistency.py`` misses. Warn only.
5. **SHA-placeholder policy** — a staged ``tasks.md`` line whose box is ``[x]``
   but whose ``SHA:`` is still the unchecked placeholder (``<—>`` / ``—`` / …).
   The accepted interim is ``SHA: <pending>``, backfilled in the next real
   commit — never a dedicated swap-only commit. Warn only.

Exit code: 1 if any **blocker** finding, else 0. Warnings never fail the run —
the decision stays with the session, matching the ``.claude/hooks/`` contract.

Usage::

    python -m scripts.dev.commit_preflight --expect scripts/dev/ --expect tests/

Run directly; ``print`` is the output contract, not a log line.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from scripts.dev.hooks.check_md_line_length import check_file as _md_check_file

REPO_ROOT = Path(__file__).resolve().parents[2]  # scripts/dev/ → repo root

MD_HOOK_SCOPE_RE = re.compile(r"^([^/]+\.md|docs/(plan|bugs)/.*\.md)$")
TICKED_BOX_RE = re.compile(r"^\+\s*-\s*\[[xX]\]\s*\*\*([^*]+?)\*\*")
UNTICKED_BOX_RE = re.compile(r"^-\s*-\s*\[ \]\s*\*\*([^*]+?)\*\*")
CHECKED_TASK_LINE_RE = re.compile(r"^\s*-\s*\[[xX]\]\s*\*\*([^*]+?)\*\*")
SHA_FIELD_RE = re.compile(r"\|\s*SHA:\s*(?P<sha>\S+)")
PLACEHOLDER_SHA = {"<—>", "—", "–", "-", "<->", "<-->", "tbd", "TBD", "n/a"}

_NEXT_MARKER_TEMPLATES = (
    r"next:\s*\*{{0,2}}{id}\*{{0,2}}",
    r"next\s+is\s*\*{{0,2}}{id}\*{{0,2}}",
    r"\*{{0,2}}{id}\*{{0,2}}\s*\(next\)",
    r"Open:\s*\*{{0,2}}{id}\b",
)


def _run_git(args: list[str]) -> str:
    """Return stdout of ``git <args>`` run at the repo root ('' on failure)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout


def staged_names() -> list[str]:
    """Repo-relative paths in the current staged set."""
    return [p for p in _run_git(["diff", "--cached", "--name-only"]).splitlines() if p]


def staged_diff() -> str:
    """Unified diff of the current staged set."""
    return _run_git(["diff", "--cached", "--unified=0"])


def check_staged_index(staged: list[str], expected: list[str]) -> list[str]:
    """Flag staged paths outside every ``expected`` prefix. Empty ``expected`` → no-op."""
    if not expected:
        return []
    norm = [e.rstrip("/") for e in expected]
    stray = [p for p in staged if not any(p == e or p.startswith(e + "/") for e in norm)]
    return [
        f"staged-index: {p} is outside the phase's expected paths ({', '.join(norm)})"
        for p in stray
    ]


def ruff_format_check(py_paths: list[str], runner=subprocess.run) -> list[str]:
    """Blocker finding if ``ruff format --check`` would reformat any staged ``.py``."""
    if not py_paths:
        return []
    try:
        result = runner(
            ["ruff", "format", "--check", "--quiet", *py_paths],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(REPO_ROOT),
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode == 0:
        return []
    changed = [ln for ln in (result.stdout or "").splitlines() if ln.strip()]
    detail = "; ".join(changed) if changed else "see `ruff format --check`"
    return [f"ruff-format: staged .py would be reformatted by the format hook — {detail}"]


def check_md_line_length(md_paths: list[str]) -> list[str]:
    """Blocker findings for staged hook-covered ``.md`` lines over the 200-char cap."""
    findings: list[str] = []
    for rel in md_paths:
        if not MD_HOOK_SCOPE_RE.match(rel):
            continue
        abs_path = REPO_ROOT / rel
        if abs_path.is_file():
            findings.extend(f"md-line-length: {v}" for v in _md_check_file(str(abs_path)))
    return findings


def ticked_ids(diff_text: str) -> set[str]:
    """Task ids whose checkbox flips from ``[ ]`` to ``[x]`` in the staged diff."""
    added = {m.group(1).strip() for m in map(TICKED_BOX_RE.match, diff_text.splitlines()) if m}
    removed = {m.group(1).strip() for m in map(UNTICKED_BOX_RE.match, diff_text.splitlines()) if m}
    return added & removed


def check_next_marker(ticked: set[str], texts: dict[str, str]) -> list[str]:
    """Warn when a staged marker file still names a just-ticked id as the next task."""
    findings: list[str] = []
    for task_id in sorted(ticked):
        patterns = [
            re.compile(tmpl.format(id=re.escape(task_id)), re.I) for tmpl in _NEXT_MARKER_TEMPLATES
        ]
        for rel, text in texts.items():
            for lineno, line in enumerate(text.splitlines(), 1):
                if any(p.search(line) for p in patterns):
                    findings.append(
                        f"next-marker: {rel}:{lineno} still points at '{task_id}' "
                        "which this commit ticks — advance it to the next unchecked id"
                    )
    return findings


def check_sha_placeholder(tasks_texts: dict[str, str]) -> list[str]:
    """Warn when a ticked task line still carries the unchecked SHA placeholder."""
    findings: list[str] = []
    for rel, text in tasks_texts.items():
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            if not CHECKED_TASK_LINE_RE.match(line):
                continue
            joined = line
            if not SHA_FIELD_RE.search(joined) and idx + 1 < len(lines):
                joined = f"{line} {lines[idx + 1]}"
            sha_match = SHA_FIELD_RE.search(joined)
            if sha_match and sha_match.group("sha") in PLACEHOLDER_SHA:
                task = CHECKED_TASK_LINE_RE.match(line).group(1).strip()
                findings.append(
                    f"sha-placeholder: {rel}:{idx + 1} '{task}' is [x] but SHA is "
                    f"'{sha_match.group('sha')}' — set 'SHA: <pending>' now and backfill "
                    "the real SHA in the next commit (no swap-only commit)"
                )
    return findings


def _read_worktree_texts(staged: list[str], suffixes: tuple[str, ...]) -> dict[str, str]:
    """Working-tree text of staged files whose basename ends with any ``suffixes``."""
    out: dict[str, str] = {}
    for rel in staged:
        if not rel.endswith(suffixes):
            continue
        abs_path = REPO_ROOT / rel
        if abs_path.is_file():
            out[rel] = abs_path.read_text(encoding="utf-8")
    return out


def run_preflight(expected: list[str]) -> tuple[list[str], list[str]]:
    """Run every check against the staged set; return ``(blockers, warnings)``."""
    staged = staged_names()
    diff = staged_diff()
    py_paths = [p for p in staged if p.endswith(".py")]
    md_paths = [p for p in staged if p.endswith(".md")]
    marker_texts = _read_worktree_texts(staged, ("tasks.md", "README.md", "TODOS.md"))
    tasks_texts = _read_worktree_texts(staged, ("tasks.md",))

    blockers: list[str] = []
    blockers += ruff_format_check(py_paths)
    blockers += check_md_line_length(md_paths)

    warnings: list[str] = []
    warnings += check_staged_index(staged, expected)
    warnings += check_next_marker(ticked_ids(diff), marker_texts)
    warnings += check_sha_placeholder(tasks_texts)
    return blockers, warnings


def _parse_expected(argv: list[str]) -> list[str]:
    """Collect every ``--expect <path>`` value from ``argv``."""
    expected: list[str] = []
    it = iter(argv)
    for tok in it:
        if tok == "--expect":
            expected.append(next(it, ""))
        elif tok.startswith("--expect="):
            expected.append(tok.split("=", 1)[1])
    return [e for e in expected if e]


def main(argv: list[str]) -> int:
    """Print the findings list; return 1 if any blocker fired."""
    blockers, warnings = run_preflight(_parse_expected(argv))
    for line in blockers:
        print(f"✗ {line}")
    for line in warnings:
        print(f"⚠ {line}")
    if not blockers and not warnings:
        print("commit-preflight: clean")
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
