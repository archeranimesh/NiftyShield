"""Instrument key lookup from Upstox BOD JSON files or Search API.

Two modes:
1. Offline: Load a downloaded BOD JSON file (NSE.json.gz) and search locally.
2. API: Use the Upstox Instrument Search API with an analytics/access token.

Usage examples:
    # Offline — search the downloaded BOD file
    lookup = InstrumentLookup.from_file("data/instruments/NSE.json.gz")
    results = lookup.search("EBBETF0431")
    results = lookup.search_options("NIFTY", strike=23000, option_type="PE", expiry="2026-12-31")

    # API — search via Upstox Search API
    results = await search_api("NIFTY 23000 PE", token="your_token", expiry="2026-12-31")
"""

from __future__ import annotations

import gzip
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# Optional fast fuzzy; difflib is stdlib fallback — no hard dependency on rapidfuzz.
try:
    from rapidfuzz import fuzz as _fuzz  # type: ignore

    def _fuzzy_ratio(a: str, b: str) -> float:
        """Token-set ratio normalised to 0.0–1.0."""
        return _fuzz.token_set_ratio(a, b) / 100.0

except ImportError:  # pragma: no cover
    from difflib import SequenceMatcher as _SM  # type: ignore

    def _fuzzy_ratio(a: str, b: str) -> float:  # type: ignore[misc]
        return _SM(None, a, b).ratio()


def _score_query(query: str, candidate: str) -> tuple[float, str]:
    """Return (score, reason) for a query against a single candidate string.

    Ranking tier:
        exact  → 1.00  (case-insensitive equality)
        prefix → 0.92  (candidate starts with query)
        fuzzy  → rapidfuzz token_set_ratio (or difflib fallback)

    Args:
        query: The search term (already stripped/lowercased by caller).
        candidate: A single field value (trading_symbol, name, etc.).

    Returns:
        Tuple of (score 0.0–1.0, reason string).
    """
    c = candidate.strip().lower()
    if not c:
        return 0.0, "none"
    if query == c:
        return 1.0, "exact"
    if c.startswith(query):
        return 0.92, "prefix"
    return _fuzzy_ratio(query, c), "fuzzy"


def _best_score(query: str, instrument: dict[str, Any]) -> tuple[float, str]:
    """Return the highest (score, reason) across all searchable fields of an instrument.

    Args:
        query: Lowercased, stripped search term.
        instrument: Raw instrument dict from the BOD JSON.

    Returns:
        Best (score, reason) tuple across trading_symbol, name, underlying_symbol, short_name.
    """
    fields = [
        instrument.get("trading_symbol", ""),
        instrument.get("name", ""),
        instrument.get("underlying_symbol", ""),
        instrument.get("short_name", ""),
    ]
    best = (0.0, "none")
    for field in fields:
        s, r = _score_query(query, field)
        if s > best[0]:
            best = (s, r)
    return best


def _parse_expiry(expiry_val: Any) -> str | None:
    """Convert Upstox expiry (epoch ms) to YYYY-MM-DD string."""
    if expiry_val is None:
        return None
    if isinstance(expiry_val, str):
        return expiry_val
    try:
        dt = datetime.fromtimestamp(expiry_val / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return None


# ── Offline lookup from BOD JSON ─────────────────────────────────


class InstrumentLookup:
    """Search instruments from a locally downloaded Upstox BOD JSON file.

    Download the file from:
        https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz
    """

    def __init__(self, instruments: list[dict[str, Any]]) -> None:
        self._instruments = instruments

    @classmethod
    def from_file(cls, path: str | Path) -> InstrumentLookup:
        """Load instruments from a gzipped or plain JSON file.

        Args:
            path: Path to NSE.json.gz or NSE.json.
        """
        path = Path(path)
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8") as f:
                data = json.load(f)
        else:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        return cls(data)

    def search(
        self,
        query: str,
        segment: str | None = None,
        instrument_type: str | None = None,
        max_results: int = 10,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Ranked free-text search across trading_symbol, name, and underlying_symbol.

        Results are scored and sorted: exact matches first (1.0), prefix matches
        second (0.92), fuzzy matches last (rapidfuzz token_set_ratio or difflib
        fallback). The old substring behaviour is preserved at min_score=0.0 (any
        positive fuzzy score is included).

        Args:
            query: Text to match (case-insensitive).
            segment: Filter by segment (e.g. 'NSE_EQ', 'NSE_FO').
            instrument_type: Filter by type (e.g. 'EQ', 'CE', 'PE', 'FUT').
            max_results: Maximum results to return.
            min_score: Discard results below this score (0.0–1.0). Use ~0.65 to
                suppress low-confidence fuzzy matches.

        Returns:
            List of instrument dicts sorted by descending score, capped at max_results.
        """
        if not query or not query.strip():
            return []

        query_lower = query.strip().lower()
        scored: list[tuple[float, str, dict[str, Any]]] = []

        for inst in self._instruments:
            if segment and inst.get("segment") != segment:
                continue
            if instrument_type and inst.get("instrument_type") != instrument_type:
                continue

            score, reason = _best_score(query_lower, inst)
            if score > 0.0 and score >= min_score:
                scored.append((score, reason, inst))

        scored.sort(key=lambda t: t[0], reverse=True)
        return [inst for _, _, inst in scored[:max_results]]

    def search_equity(self, symbol: str) -> list[dict[str, Any]]:
        """Search for an equity instrument by trading symbol.

        Args:
            symbol: Trading symbol (e.g. 'EBBETF0431', 'RELIANCE').
        """
        return self.search(symbol, segment="NSE_EQ", instrument_type="EQ")

    def search_options(
        self,
        underlying: str,
        strike: float | None = None,
        option_type: str | None = None,
        expiry: str | date | None = None,
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """Search for option contracts with specific filters.

        Args:
            underlying: Underlying symbol (e.g. 'NIFTY', 'BANKNIFTY').
            strike: Strike price to match exactly.
            option_type: 'CE' or 'PE'.
            expiry: Expiry date as 'YYYY-MM-DD' string or date object.
            max_results: Maximum results to return.
        """
        if isinstance(expiry, date):
            expiry = expiry.isoformat()

        results = []
        for inst in self._instruments:
            if inst.get("segment") != "NSE_FO":
                continue
            if option_type and inst.get("instrument_type") != option_type:
                continue
            if inst.get("instrument_type") not in ("CE", "PE"):
                continue

            underlying_sym = inst.get("underlying_symbol", "")
            if underlying.upper() not in underlying_sym.upper():
                continue

            if strike is not None and inst.get("strike_price") != strike:
                continue

            if expiry is not None:
                inst_expiry = _parse_expiry(inst.get("expiry"))
                if inst_expiry != expiry:
                    continue

            results.append(inst)
            if len(results) >= max_results:
                break

        return results

    def search_futures(
        self,
        underlying: str,
        expiry: str | date | None = None,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for futures contracts.

        Args:
            underlying: Underlying symbol (e.g. 'NIFTY').
            expiry: Expiry date as 'YYYY-MM-DD' string or date object.
            max_results: Maximum results to return.
        """
        if isinstance(expiry, date):
            expiry = expiry.isoformat()

        results = []
        for inst in self._instruments:
            if inst.get("segment") != "NSE_FO":
                continue
            if inst.get("instrument_type") != "FUT":
                continue
            if underlying.upper() not in inst.get("underlying_symbol", "").upper():
                continue
            if expiry is not None:
                inst_expiry = _parse_expiry(inst.get("expiry"))
                if inst_expiry != expiry:
                    continue

            results.append(inst)
            if len(results) >= max_results:
                break

        return results

    def get_by_key(self, instrument_key: str) -> dict[str, Any] | None:
        """Look up a single instrument by its exact instrument_key."""
        for inst in self._instruments:
            if inst.get("instrument_key") == instrument_key:
                return inst
        return None

    # ── Expiry parsing (module-level: _parse_expiry) ──

    @property
    def count(self) -> int:
        """Total number of instruments loaded."""
        return len(self._instruments)


# ── API-based search ─────────────────────────────────────────────


SEARCH_API_URL = "https://api.upstox.com/v1/instruments/search"


async def search_api(
    query: str,
    token: str,
    exchanges: str | None = "NSE",
    segments: str | None = None,
    instrument_types: str | None = None,
    expiry: str | None = None,
    strike_price: float | None = None,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Search instruments via the Upstox Instrument Search API.

    Requires an Analytics Token or Access Token.

    Args:
        query: Free text search (e.g. 'NIFTY 23000 PE', 'EBBETF0431').
        token: Upstox access/analytics token.
        exchanges: Comma-separated exchanges (e.g. 'NSE', 'NSE,BSE').
        segments: Comma-separated segments (e.g. 'EQ', 'FO').
        instrument_types: Comma-separated types (e.g. 'CE', 'PE', 'FUT').
        expiry: Expiry date as 'YYYY-MM-DD' or relative ('next_week', 'next_month').
        strike_price: Exact strike price to filter.
        max_results: Number of results per page.
    """
    import aiohttp

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    params: dict[str, Any] = {
        "query": query,
        "records": max_results,
    }
    if exchanges:
        params["exchanges"] = exchanges
    if segments:
        params["segments"] = segments
    if instrument_types:
        params["instrument_types"] = instrument_types
    if expiry:
        params["expiry"] = expiry
    if strike_price is not None:
        params["strike_price"] = strike_price

    async with aiohttp.ClientSession() as session:
        async with session.get(SEARCH_API_URL, headers=headers, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data.get("data", [])


# ── Display helper ───────────────────────────────────────────────


def format_results(results: list[dict[str, Any]], fields: list[str] | None = None) -> str:
    """Format search results as a readable table.

    Args:
        results: List of instrument dicts from search.
        fields: Fields to display. Defaults to the most useful subset.
    """
    if not results:
        return "No results found."

    if fields is None:
        fields = [
            "instrument_key", "trading_symbol", "instrument_type",
            "strike_price", "expiry", "lot_size", "segment",
        ]

    # Filter to fields that exist in results
    available = [f for f in fields if any(f in r for r in results)]

    # Header
    lines = ["  ".join(f"{f:<25}" for f in available)]
    lines.append("-" * len(lines[0]))

    for r in results:
        row = []
        for f in available:
            val = r.get(f, "")
            if f == "expiry" and isinstance(val, (int, float)):
                val = _parse_expiry(val) or val
            row.append(f"{str(val):<25}")
        lines.append("  ".join(row))

    return "\n".join(lines)
