"""Scaffold a new ``docs/plan/`` story or epic folder from ``docs/plan/_TEMPLATE/``.

Copies the story or epic template, strips the ``<!-- ... -->`` guidance comments, and
substitutes the ``<slug>`` / ``<Story title>`` / ``<Epic title>`` placeholders so the
output passes ``check_story_structure.py --all`` with zero further edits. See
``docs/plan/README.md`` §Conventions "Folder shapes".

Usage::

    python -m scripts.dev.new_plan_folder --story risk-gamma-phase-a
    python -m scripts.dev.new_plan_folder --epic telegram-markdown-migration --title "Telegram Markdown Migration"
    python -m scripts.dev.new_plan_folder --story greeks-fix --into telegram-markdown-migration

``print`` here is the CLI output contract, not a log line.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Literal

_SCRIPT_NAME = "scripts.dev.new_plan_folder"

REPO_ROOT = Path(__file__).resolve().parents[2]  # scripts/dev/ -> repo root
PLAN_DIR = REPO_ROOT / "docs" / "plan"
TEMPLATE_DIR = PLAN_DIR / "_TEMPLATE"

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?-")
_HTML_COMMENT_RE = re.compile(r"[ \t]*<!--.*?-->\n?", re.DOTALL)


def _title_case(slug: str) -> str:
    """``risk-gamma-phase-a`` -> ``Risk Gamma Phase A``."""
    return " ".join(word.capitalize() for word in slug.split("-"))


def validate_slug(slug: str) -> None:
    """Raise ``ValueError`` if ``slug`` is not bare kebab-case with no date prefix."""
    if not _SLUG_RE.match(slug):
        raise ValueError(f"slug {slug!r} must be kebab-case (lowercase letters, digits, hyphens)")
    if _DATE_PREFIX_RE.match(slug):
        raise ValueError(f"slug {slug!r} must not carry a date prefix")


def _strip_comments(text: str) -> str:
    """Remove every ``<!-- ... -->`` guidance block, collapsing the blank line it leaves."""
    text = _HTML_COMMENT_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text)


def _substitute(text: str, *, slug: str, title: str) -> str:
    """Replace the template placeholder tokens with the real slug / title."""
    text = text.replace("<Story title>", title).replace("<Epic title>", title)
    text = text.replace("<epic-slug>/<story-slug>", slug).replace("<slug>", slug)
    return text.replace("<epic-slug>", slug)


def _write_file(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _scaffold_story(dest: Path, *, slug: str, title: str) -> None:
    src = TEMPLATE_DIR / "story"
    for item in src.iterdir():
        if not item.is_file():
            continue
        if item.name == "schema.md.example":
            continue  # only kept when the story touches DB schema; author adds it by hand
        text = _substitute(
            _strip_comments(item.read_text(encoding="utf-8")), slug=slug, title=title
        )
        _write_file(dest / item.name, text)


def _scaffold_epic(dest: Path, *, slug: str, title: str) -> None:
    src = TEMPLATE_DIR / "epic"
    for item in src.iterdir():
        if not item.is_file():
            continue
        text = _substitute(
            _strip_comments(item.read_text(encoding="utf-8")), slug=slug, title=title
        )
        _write_file(dest / item.name, text)


def scaffold(
    *, kind: Literal["story", "epic"], slug: str, title: str | None = None, into: str | None = None
) -> Path:
    """Create the story or epic folder; return its path. Raises on invalid input."""
    validate_slug(slug)
    if into:
        validate_slug(into)
        epic_dir = PLAN_DIR / into
        if not epic_dir.is_dir():
            raise FileNotFoundError(f"epic {into!r} not found at {epic_dir}")
        dest = epic_dir / slug
    else:
        dest = PLAN_DIR / slug
    if dest.exists():
        raise FileExistsError(f"{dest} already exists")
    resolved_title = title or _title_case(slug)
    dest.mkdir(parents=True)
    try:
        if kind == "story":
            _scaffold_story(dest, slug=slug, title=resolved_title)
        elif kind == "epic":
            _scaffold_epic(dest, slug=slug, title=resolved_title)
        else:
            raise ValueError(f"unknown kind {kind!r}")
    except Exception:  # Intentional: clean up partial scaffold before re-raising
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return dest


def main(argv: list[str]) -> int:
    """CLI entrypoint. Returns 0 on success, 1 on a validation / target-exists error."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--story", metavar="SLUG", help="scaffold a single-story folder")
    group.add_argument("--epic", metavar="SLUG", help="scaffold an epic root folder")
    parser.add_argument("--title", help="story/epic title (default: Title Case of the slug)")
    parser.add_argument(
        "--into", metavar="EPIC_SLUG", help="scaffold as a sub-story of an existing epic"
    )
    args = parser.parse_args(argv)

    if args.into and args.epic:
        print(f"[{_SCRIPT_NAME}] --into is only valid with --story", file=sys.stderr)
        return 1

    kind: Literal["story", "epic"] = "story" if args.story else "epic"
    slug = args.story or args.epic
    try:
        dest = scaffold(kind=kind, slug=slug, title=args.title, into=args.into)
    except (ValueError, FileExistsError, FileNotFoundError) as exc:
        print(f"[{_SCRIPT_NAME}] {exc}", file=sys.stderr)
        return 1

    rel = dest.relative_to(REPO_ROOT)
    print(f"[{_SCRIPT_NAME}] created {rel}/")
    for item in sorted(dest.iterdir()):
        print(f"  {item.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
