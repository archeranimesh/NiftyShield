"""Fetch current OpenRouter model slugs for the signals providers (BUG-041).

Read-only. Hits the public models endpoint (no API key needed) and prints the
live `x-ai/*`, `google/gemini*flash*`, and `openai/gpt*` slugs with context
window + per-1M pricing, so the stale-slug failure in BUG-041 can be corrected
by setting SIGNAL_MODEL_{GROK,GPT4O,GEMINI}.

Usage:
    python scratch/2026-09-08_openrouter_model_slugs.py
    python scratch/2026-09-08_openrouter_model_slugs.py grok      # one family
    python scratch/2026-09-08_openrouter_model_slugs.py --all     # no filter

"latest" aliases (~author/family-latest) resolve at request time — the concrete
model comes back in the response `model` field, not from this list.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date, datetime, timezone

_MODELS_URL = "https://openrouter.ai/api/v1/models"

# family key -> substrings that identify it in a model id
_FAMILIES: dict[str, tuple[str, ...]] = {
    "grok": ("x-ai/",),
    "gemini": ("google/gemini",),
    "gpt4o": ("openai/gpt", "openai/o"),
}


def _fetch() -> list[dict]:
    req = urllib.request.Request(_MODELS_URL, headers={"User-Agent": "niftyshield-scratch"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - fixed https URL
        return json.loads(resp.read())["data"]


def _price_per_million(pricing: dict, key: str) -> str:
    raw = pricing.get(key)
    if raw in (None, ""):
        return "-"
    try:
        return f"${float(raw) * 1_000_000:.2f}"
    except (TypeError, ValueError):
        return str(raw)


def _released(model: dict) -> str:
    ts = model.get("created")
    if not ts:
        return "?"
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return "?"


def _matches(model_id: str, substrings: tuple[str, ...]) -> bool:
    lid = model_id.lower()
    return any(s in lid for s in substrings)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("-")]
    show_all = "--all" in argv
    wanted = args[0].lower() if args else None

    if wanted and wanted not in _FAMILIES:
        print(f"unknown family {wanted!r}; pick from {', '.join(_FAMILIES)} or --all")
        return 2

    try:
        models = _fetch()
    except Exception as exc:  # scratch: surface any network/parse failure plainly
        print(f"fetch failed: {exc}")
        return 1

    if show_all:
        selected = [(m["id"], m) for m in models]
    else:
        families = {wanted: _FAMILIES[wanted]} if wanted else _FAMILIES
        selected = [
            (m["id"], m)
            for m in models
            if any(_matches(m["id"], subs) for subs in families.values())
        ]

    selected.sort(key=lambda pair: pair[0])
    print(f"# openrouter.ai/api/v1/models — {len(selected)} slugs — fetched {date.today()}\n")
    print(f"{'slug':<44} {'released':<12} {'context':>10} {'in/1M':>10} {'out/1M':>10}")
    print("-" * 90)
    for model_id, m in selected:
        pricing = m.get("pricing", {})
        ctx = m.get("context_length") or "-"
        print(
            f"{model_id:<44} {_released(m):<12} {str(ctx):>10} "
            f"{_price_per_million(pricing, 'prompt'):>10} "
            f"{_price_per_million(pricing, 'completion'):>10}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
