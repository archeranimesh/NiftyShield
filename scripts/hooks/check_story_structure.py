"""Check ``docs/plan/`` story/epic folder structure. See ``docs/plan/README.md`` §Conventions.

Shapes enforced:

* **Story folder** — ``prompt.md`` + ``tasks.md`` (or legacy ``*_tasks.md``) + ``stories.md``.
* **Epic folder** — ``prompt.md`` (router) + ``README.md`` at the root, plus at least one
  story sub-folder directly under it. The epic root carries no task file of its own.

Findings carry a level:

* ``error`` — empty / stray folder, a folder that is neither a story nor an epic, a tracked
  non-``.md`` file in a plan folder. Fails every mode.
* ``warn``  — a missing ``stories.md`` / ``README.md`` / ``prompt.md``, a legacy
  ``*_tasks.md`` name, ``CREATE``/``ALTER TABLE`` DDL with no sibling ``schema.md``, an extra
  ``.md`` that holds task checkboxes. Legacy shapes are grandfathered: warnings pass
  ``--all`` but block ``--staged-added`` and path mode.

Modes:
    --all            audit every folder under docs/plan/ (used by the md-organize skill);
                     exits 1 only on ``error`` findings — warnings pass
    --staged-added   check only folders newly added in the current commit (pre-commit);
                     exits 1 on any finding (warnings included)
    <paths...>       check the folders those paths belong to (manual / tests); any finding
                     exits 1
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REQUIRED_PROMPT = "prompt.md"
EXCLUDED = {"_TEMPLATE"}

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_DIR = REPO_ROOT / "docs" / "plan"

DDL_RE = re.compile(r"\b(?:CREATE|ALTER)\s+TABLE\b", re.IGNORECASE)
CHECKBOX_LINE_RE = re.compile(r"^\s*-\s*\[[ xX~]\]\s")

# .md files that legitimately live in a story / epic folder (§Story-folder file set,
# §Epic-folder file set, §Extra files). Anything else is an "extra .md".
KNOWN_MD = {"prompt.md", "tasks.md", "stories.md", "schema.md", "README.md", "plan.md", "spec.md"}


@dataclass(frozen=True)
class Finding:
    """One structural problem with a plan folder."""

    level: str  # "error" | "warn"
    message: str


def _rel(path: Path) -> str:
    """Repo-relative string for display."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _has_task_file(folder: Path) -> bool:
    """True if the folder carries ``tasks.md`` or a legacy ``*_tasks.md``."""
    return (folder / "tasks.md").is_file() or any(folder.glob("*_tasks.md"))


def _has_stories_file(folder: Path) -> bool:
    """True if the folder carries ``stories.md`` or a legacy ``*_stories.md``."""
    return (folder / "stories.md").is_file() or any(folder.glob("*_stories.md"))


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


def _story_subfolders(folder: Path) -> list[Path]:
    """Direct sub-folders of ``folder`` that are themselves story folders."""
    return [d for d in _entries(folder) if d.is_dir() and is_story_folder(d)]


def _text_of(folder: Path, name: str) -> str:
    """Contents of ``folder/name`` if it exists, else empty string."""
    target = folder / name
    return target.read_text(encoding="utf-8") if target.is_file() else ""


def _is_legacy_named(name: str) -> bool:
    """A legacy ``<slug>_tasks.md`` / ``<slug>_stories.md`` name (grandfathered)."""
    return name.endswith("_tasks.md") or name.endswith("_stories.md")


def _extra_file_findings(folder: Path) -> list[Finding]:
    """D6 extra-files rule — no tracked non-``.md`` file, no extra ``.md`` with checkboxes."""
    findings: list[Finding] = []
    for entry in _entries(folder):
        if entry.is_dir():
            continue
        name = entry.name
        if not (name.endswith(".md") or name.endswith(".md.example")):
            findings.append(
                Finding("error", f"{_rel(entry)}: non-.md file in a plan folder — see §Extra files")
            )
            continue
        if name in KNOWN_MD or _is_legacy_named(name):
            continue
        if any(
            CHECKBOX_LINE_RE.match(line) for line in entry.read_text(encoding="utf-8").splitlines()
        ):
            findings.append(
                Finding(
                    "warn",
                    f"{_rel(entry)}: extra .md carries task checkboxes — move them to tasks.md "
                    "(§Extra files)",
                )
            )
    return findings


def _schema_backstop(folder: Path) -> list[Finding]:
    """Warn when a folder's stories.md / prompt.md has DDL and no sibling schema.md."""
    if (folder / "schema.md").is_file():
        return []
    blob = _text_of(folder, "stories.md") + "\n" + _text_of(folder, REQUIRED_PROMPT)
    blob += "\n" + "\n".join(p.read_text(encoding="utf-8") for p in folder.glob("*_stories.md"))
    if DDL_RE.search(blob):
        return [
            Finding(
                "warn",
                f"{_rel(folder)}/: CREATE/ALTER TABLE in stories.md/prompt.md but no schema.md — "
                "see §When a story needs schema.md",
            )
        ]
    return []


def _check_story(folder: Path) -> list[Finding]:
    """Structural checks for a leaf story folder (flat or epic sub-story)."""
    findings: list[Finding] = []
    if not (folder / "tasks.md").is_file() and any(folder.glob("*_tasks.md")):
        findings.append(
            Finding(
                "warn",
                f"{_rel(folder)}/: legacy '*_tasks.md' name — rename to tasks.md when next touched",
            )
        )
    if not _has_stories_file(folder):
        findings.append(
            Finding("warn", f"{_rel(folder)}/: missing stories.md — see §Story-folder file set")
        )
    findings.extend(_schema_backstop(folder))
    findings.extend(_extra_file_findings(folder))
    return findings


def _check_epic(folder: Path) -> list[Finding]:
    """Structural checks for an epic root and each of its story sub-folders."""
    findings: list[Finding] = []
    for name in (REQUIRED_PROMPT, "README.md"):
        if not (folder / name).is_file():
            findings.append(
                Finding(
                    "warn", f"{_rel(folder)}/: epic root missing {name} — see §Epic-folder file set"
                )
            )
    # The epic root is bound by the D6 extra-files rule too (its only shared reference
    # files are checkbox-free); the schema.md backstop applies to sub-stories, not here.
    findings.extend(_extra_file_findings(folder))
    for story in _story_subfolders(folder):
        findings.extend(_check_story(story))
    return findings


def check_folder(folder: Path) -> list[Finding]:
    """Return one :class:`Finding` per problem with ``folder``; empty list if clean."""
    if not folder.is_dir():
        return []
    if not _entries(folder):
        return [
            Finding(
                "error",
                f"{_rel(folder)}/: empty folder — remove it, or add {REQUIRED_PROMPT} + tasks.md + stories.md",
            )
        ]
    if is_epic_folder(folder):
        return _check_epic(folder)
    if is_story_folder(folder):
        return _check_story(folder)
    missing = [] if (folder / REQUIRED_PROMPT).is_file() else [REQUIRED_PROMPT]
    if not _has_task_file(folder):
        missing.append("tasks.md")
    if not _has_stories_file(folder):
        missing.append("stories.md")
    return [
        Finding(
            "error", f"{_rel(folder)}/: not a story or epic folder — missing {', '.join(missing)}"
        )
    ]


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

    findings: list[Finding] = []
    for folder in folders:
        findings.extend(check_folder(folder))
    for finding in findings:
        print(f"{finding.level.upper()}: {finding.message}")
    if not findings:
        return 0

    errors = [f for f in findings if f.level == "error"]
    print(
        f"\n{len(findings)} story-folder issue(s) "
        f"({len(errors)} error, {len(findings) - len(errors)} warn). "
        "See docs/plan/README.md §Conventions."
    )
    # --all grandfathers legacy shapes: warnings pass, only errors fail.
    if audit:
        return 1 if errors else 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
