"""Check ``docs/plan/`` story-folder structure. See ``docs/plan/README.md`` §Conventions.

A *story folder* has ``prompt.md`` plus ``tasks.md`` (or a legacy ``*_tasks.md``).
An *epic folder* has no task file of its own but contains at least one story sub-folder.
Anything else under ``docs/plan/`` — an empty folder, or a non-empty folder that is
neither a story nor an epic — is a problem.

Modes:
    --all            audit every folder under docs/plan/ (used by the md-organize skill);
                     exits 1 only on empty/stray folders, warnings alone exit 0
    --staged-added   check only folders newly added in the current commit (pre-commit);
                     exits 1 on any problem
    <paths...>       check the folders those paths belong to (manual / tests)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REQUIRED_PROMPT = "prompt.md"
EXCLUDED = {"_TEMPLATE"}

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_DIR = REPO_ROOT / "docs" / "plan"


def _rel(path: Path) -> str:
    """Repo-relative string for display."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _has_task_file(folder: Path) -> bool:
    """True if the folder carries ``tasks.md`` or a legacy ``*_tasks.md``."""
    return (folder / "tasks.md").is_file() or any(folder.glob("*_tasks.md"))


def _entries(folder: Path) -> list[Path]:
    """Non-hidden direct children of the folder."""
    return [p for p in folder.iterdir() if not p.name.startswith(".")]


def is_story_folder(folder: Path) -> bool:
    """A leaf story folder — has a prompt and a task file."""
    return (folder / REQUIRED_PROMPT).is_file() and _has_task_file(folder)


def is_epic_folder(folder: Path, _depth: int = 0) -> bool:
    """A container folder whose sub-folders are stories (or nested epics)."""
    if _depth >= 3:  # docs/plan/ is at most epic → story deep; guard symlink cycles
        return False
    subdirs = [p for p in _entries(folder) if p.is_dir()]
    return any(is_story_folder(d) or is_epic_folder(d, _depth + 1) for d in subdirs)


def check_folder(folder: Path) -> list[str]:
    """Return one message per problem with ``folder``; empty list if clean."""
    if not folder.is_dir():
        return []
    if not _entries(folder):
        return [f"{_rel(folder)}/: empty folder — remove it, or add {REQUIRED_PROMPT} + tasks.md"]
    if is_story_folder(folder) or is_epic_folder(folder):
        problems = []
        if not (folder / "tasks.md").is_file() and any(folder.glob("*_tasks.md")):
            problems.append(
                f"{_rel(folder)}/: legacy '*_tasks.md' name — rename to tasks.md when next touched"
            )
        return problems
    missing = [] if (folder / REQUIRED_PROMPT).is_file() else [REQUIRED_PROMPT]
    if not _has_task_file(folder):
        missing.append("tasks.md")
    return [f"{_rel(folder)}/: not a story or epic folder — missing {', '.join(missing)}"]


def _folders_for_paths(paths: list[str]) -> list[Path]:
    """Map file/dir paths to the distinct docs/plan/<slug>/ folders they live in."""
    out: dict[str, Path] = {}
    for raw in paths:
        p = Path(raw)
        p = (REPO_ROOT / p).resolve() if not p.is_absolute() else p.resolve()
        try:
            rel = p.relative_to(PLAN_DIR)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] not in EXCLUDED:
            out[rel.parts[0]] = PLAN_DIR / rel.parts[0]
    return list(out.values())


def _all_folders() -> list[Path]:
    return sorted(
        p
        for p in PLAN_DIR.iterdir()
        if p.is_dir() and p.name not in EXCLUDED and not p.name.startswith(".")
    )


def _staged_added_folders() -> list[Path]:
    """docs/plan/ folders that have a newly-added file staged in this commit."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--diff-filter=A", "--name-only"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=True,
    )
    return _folders_for_paths(result.stdout.splitlines())


def main(argv: list[str]) -> int:
    """Run the structure check; return 1 on failure (see module docstring for modes)."""
    audit = "--all" in argv
    if audit:
        folders = _all_folders()
    elif "--staged-added" in argv:
        folders = _staged_added_folders()
    else:
        folders = _folders_for_paths(argv)

    problems: list[str] = []
    for folder in folders:
        problems.extend(check_folder(folder))
    for message in problems:
        print(message)
    if not problems:
        return 0
    print(f"\n{len(problems)} story-folder issue(s). See docs/plan/README.md §Conventions.")
    # In audit mode only an empty/stray folder is a hard failure; naming warnings pass.
    if audit and all("legacy '*_tasks.md'" in m for m in problems):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
