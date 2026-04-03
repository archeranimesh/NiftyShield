"""AMFI NAV fetcher.

Downloads and parses the AMFI NAVAll.txt flat file, returning a mapping
of amfi_code → NAV for a requested set of scheme codes.

The AMFI file is semicolon-delimited with six fields per data line::

    Scheme Code;ISIN Growth;ISIN Div Reinvest;Scheme Name;NAV;Date

Section/category header lines (no semicolons) and the column header line
are silently skipped.  Lines whose NAV field is "N.A." or otherwise
non-numeric are skipped and logged at DEBUG.

Network access is isolated to ``_load_source``.  ``_parse`` is pure and
takes a raw string, making the entire module testable with a fixture file.
"""

from __future__ import annotations

import logging
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path

logger = logging.getLogger(__name__)

AMFI_URL = "https://www.amfiindia.com/spages/NAVAll.txt"

_CODE_IDX = 0
_NAV_IDX = 4
_MIN_FIELDS = 6


def fetch_navs(
    amfi_codes: set[str],
    source: str | Path | None = None,
) -> dict[str, Decimal]:
    """Return NAV for each requested scheme code.

    Args:
        amfi_codes: Set of AMFI scheme codes to look up (e.g. ``{"119551", "120503"}``).
        source: URL string or local ``Path`` to read from.  Defaults to the
            official AMFI flat file URL.  Pass a ``Path`` in tests to avoid
            any network dependency.

    Returns:
        Dict mapping amfi_code → NAV as ``Decimal``.  Codes not found in the
        source are absent from the result — no ``KeyError``, no exception.
        The caller is responsible for deciding whether a missing code is fatal.
    """
    raw = _load_source(source or AMFI_URL)
    result = _parse(raw, amfi_codes)

    missing = amfi_codes - result.keys()
    if missing:
        logger.warning("NAV not found for scheme codes: %s", sorted(missing))

    return result


def _load_source(source: str | Path) -> str:
    """Read raw text from a local path or an HTTP URL.

    Args:
        source: Local ``Path`` / path string, or an ``https://`` URL.

    Returns:
        Decoded UTF-8 text content.

    Raises:
        FileNotFoundError: If a local path does not exist.
        urllib.error.URLError: If the HTTP request fails.
    """
    if isinstance(source, Path) or (
        isinstance(source, str) and not source.startswith("http")
    ):
        return Path(source).read_text(encoding="utf-8")

    with urllib.request.urlopen(str(source)) as resp:
        return resp.read().decode("utf-8")


def _parse(raw: str, amfi_codes: set[str]) -> dict[str, Decimal]:
    """Parse raw AMFI flat-file text and extract NAVs for requested codes.

    Args:
        raw: Full text content of the AMFI flat file.
        amfi_codes: Scheme codes to extract.

    Returns:
        Dict of amfi_code → ``Decimal`` NAV for all codes found in the file.
    """
    result: dict[str, Decimal] = {}

    for line in raw.splitlines():
        parts = line.strip().split(";")

        # Skip headers, blank lines, section labels — all lack a digit-only code
        if len(parts) < _MIN_FIELDS or not parts[_CODE_IDX].strip().isdigit():
            continue

        code = parts[_CODE_IDX].strip()
        if code not in amfi_codes:
            continue

        nav_str = parts[_NAV_IDX].strip()
        try:
            result[code] = Decimal(nav_str)
        except InvalidOperation:
            logger.debug("Skipping non-numeric NAV for code %s: %r", code, nav_str)

    return result
