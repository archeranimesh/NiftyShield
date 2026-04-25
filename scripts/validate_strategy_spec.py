"""Strategy specification validator.

Reads every ``*.md`` file under ``docs/strategies/`` (or any paths given on
the command line) and verifies that each **active** (non-deprecated) spec
contains all eight required section headers.

A file is treated as a strategy spec when it contains a metadata-table row
beginning with ``| Name``.  Files without that marker (e.g. revision-prompt
drafts) are silently skipped.

A spec is treated as deprecated — and therefore excluded from validation — when
its first 2 000 characters contain a ``**DEPRECATED`` blockquote marker, or
when the ``Status`` table row contains the word "DEPRECATED".

Exit codes
----------
0 — all active specs passed.
1 — at least one active spec is missing a required section, or no ``.md``
    files were found.

Usage::

    python -m scripts.validate_strategy_spec               # default: docs/strategies/
    python -m scripts.validate_strategy_spec docs/strategies/csp_nifty_v1.md
    python -m scripts.validate_strategy_spec docs/strategies/
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Required sections
# ---------------------------------------------------------------------------
# Each entry is (pattern, label):
#   pattern — lower-case substring that must appear in at least one ``##``
#             heading inside the spec.
#   label   — human-readable description used in error output.
# ---------------------------------------------------------------------------
REQUIRED_SECTIONS: list[tuple[str, str]] = [
    ("entry",              "Entry Rule / Entry Rules"),
    ("exit",               "Exit Rule / Exit Rules"),
    ("adjustment",         "Adjustment Rule"),
    ("position sizing",    "Position Sizing"),
    ("p&l distribution",   "Expected P&L Distribution Prior"),
    ("regimes",            "Regimes (work in / fail in)"),
    ("kill criteria",      "Kill Criteria"),
    ("variance threshold", "Variance Threshold for Live Deployment"),
]

# ---------------------------------------------------------------------------
# Detection regexes
# ---------------------------------------------------------------------------

# Presence of ``| Name`` anywhere in the file → it is a strategy spec.
_SPEC_MARKER_RE = re.compile(r"^\|\s*Name\s*\|", re.MULTILINE)

# ``**DEPRECATED`` in a blockquote, OR a Status table row containing the word.
_DEPRECATED_RE = re.compile(
    r"\*\*DEPRECATED"                       # blockquote marker (csp_niftybees_v1 style)
    r"|"
    r"^\|\s*Status\s*\|[^|]*DEPRECATED",   # Status field in metadata table
    re.MULTILINE | re.IGNORECASE,
)

# All level-2 headings (``## Some Heading``).
_H2_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)

# How many characters to inspect for the deprecated marker — keeps the scan
# cheap for large spec files where the marker always appears at the top.
_DEPRECATED_SCAN_CHARS = 2_000


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class SpecResult(NamedTuple):
    """Validation outcome for a single file."""

    path: Path
    deprecated: bool       # True → file is deprecated; skip
    is_spec: bool          # False → file is not a strategy spec; skip
    missing: list[str]     # human-readable labels of missing required sections

    @property
    def passed(self) -> bool:
        """True iff the spec is active and has all required sections."""
        return self.is_spec and not self.deprecated and not self.missing


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def check_file(path: Path) -> SpecResult:
    """Validate a single ``.md`` file.

    Args:
        path: Absolute or relative path to the markdown file.

    Returns:
        A :class:`SpecResult` describing whether the file is a spec, whether
        it is deprecated, and which required sections (if any) are absent.
    """
    text = path.read_text(encoding="utf-8")

    if not _SPEC_MARKER_RE.search(text):
        return SpecResult(path=path, deprecated=False, is_spec=False, missing=[])

    if _DEPRECATED_RE.search(text[:_DEPRECATED_SCAN_CHARS]):
        return SpecResult(path=path, deprecated=True, is_spec=True, missing=[])

    headings_lower = [h.lower() for h in _H2_RE.findall(text)]
    missing: list[str] = [
        label
        for pattern, label in REQUIRED_SECTIONS
        if not any(pattern in h for h in headings_lower)
    ]
    return SpecResult(path=path, deprecated=False, is_spec=True, missing=missing)


def validate(paths: list[Path]) -> int:
    """Validate strategy specs under the given paths.

    Args:
        paths: List of files or directories.  Directories are scanned for
            ``*.md`` files (non-recursive).

    Returns:
        0 if all active specs passed; 1 if any spec failed or no files found.
    """
    md_files: list[Path] = []
    for p in paths:
        if p.is_dir():
            md_files.extend(sorted(p.glob("*.md")))
        elif p.suffix == ".md":
            md_files.append(p)
        else:
            print(f"SKIP  {p}  (not a .md file)", file=sys.stderr)

    if not md_files:
        print("No markdown files found.", file=sys.stderr)
        return 1

    failures = 0
    for md in md_files:
        result = check_file(md)

        if not result.is_spec:
            print(f"SKIP  {md.name}  (no metadata table — not a strategy spec)")
            continue

        if result.deprecated:
            print(f"SKIP  {md.name}  (DEPRECATED)")
            continue

        if result.missing:
            failures += 1
            print(f"FAIL  {md.name}")
            for label in result.missing:
                print(f"        missing section: {label}")
        else:
            print(f"PASS  {md.name}")

    if failures:
        print(f"\n{failures} spec(s) failed validation.", file=sys.stderr)
        return 1

    print("\nAll active specs passed.")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point."""
    args = sys.argv[1:]
    if args:
        paths = [Path(a) for a in args]
    else:
        # Default: docs/strategies/ relative to the repository root.
        root = Path(__file__).resolve().parent.parent
        paths = [root / "docs" / "strategies"]

    sys.exit(validate(paths))


if __name__ == "__main__":
    main()
