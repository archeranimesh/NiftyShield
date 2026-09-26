"""Probe candidate OpenRouter models for the signals pipeline (BUG-041).

Sends the real signal prompt (``src.signals.prompt.build_prompt``) to a spread
of candidate slugs per family and reports, for each: HTTP status, latency,
whether ``message.content`` came back non-null, whether the body parses as the
required signal JSON (with a markdown-fence-strip fallback), and the parsed
direction/confidence. Ends with a recommended slug per family — the cheapest
one that returned clean, parseable JSON within the timeout.

Needs OPENROUTER_API_KEY (read from env or .env). Costs a handful of cheap
calls. Read-only w.r.t. the repo — makes live API calls only.

    python scratch/2026-09-08_signal_model_probe.py
    python scratch/2026-09-08_signal_model_probe.py --max-tokens 512
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiohttp
from dotenv import dotenv_values

from src.signals.models import (
    FIIData,
    MarketSnapshot,
    OILevel,
    OptionChainSummary,
)
from src.signals.prompt import build_prompt

_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

# (family, slug, rough $/1M output — for the recommendation tie-break)
_CANDIDATES: list[tuple[str, str, float]] = [
    ("grok", "~x-ai/grok-latest", 6.00),
    ("grok", "x-ai/grok-4.6", 6.00),
    ("grok", "x-ai/grok-4.3", 2.50),
    ("gpt4o", "~openai/gpt-latest", 10.00),
    ("gpt4o", "~openai/gpt-mini-latest", 4.50),
    ("gpt4o", "openai/gpt-4.1", 8.00),
    ("gpt4o", "openai/gpt-4o", 10.00),
    ("gemini", "~google/gemini-flash-latest", 3.75),
    ("gemini", "~google/gemini-pro-latest", 12.00),
    ("gemini", "google/gemini-2.5-flash", 2.50),
    ("gemini", "google/gemini-3.7-flash", 3.75),
]

_REQUIRED_KEYS = {
    "direction",
    "confidence",
    "recommended_strike",
    "entry_premium_low",
    "entry_premium_high",
    "key_reason",
    "key_risk",
}


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        trade_date=date(2026, 9, 8),
        nifty_spot=Decimal("23635.10"),
        prev_close=Decimal("23779.15"),
        prev_high=Decimal("23890.00"),
        prev_low=Decimal("23737.90"),
        gift_nifty=Decimal("23713.50"),
        india_vix=Decimal("11.23"),
        vix_5d_trend="flat",
        usd_inr=Decimal("94.85"),
        monthly_expiry=date(2026, 9, 29),
        option_chain=OptionChainSummary(
            atm_strike=23650,
            atm_iv=Decimal("10.23"),
            iv_skew=Decimal("0.29"),
            pcr_total=Decimal("1.04"),
            pcr_atm=Decimal("0.95"),
            top_call_oi=[OILevel(strike=23700, oi=120000, oi_change=8000)],
            top_put_oi=[OILevel(strike=23600, oi=140000, oi_change=-3000)],
        ),
        fii=FIIData(
            fii_cash_net_cr=Decimal("280.13"),
            dii_cash_net_cr=Decimal("566.76"),
        ),
    )


def _strip_fence(text: str) -> str:
    """Drop a leading/trailing markdown code fence if present."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _classify(status: int, body: dict | str, latency: float) -> dict:
    """Turn a raw response into a compact verdict row."""
    row = {
        "status": status,
        "latency_s": round(latency, 1),
        "content": "-",
        "parse": "-",
        "note": "",
    }
    if status != 200:
        snippet = json.dumps(body)[:160] if isinstance(body, (dict, list)) else str(body)[:160]
        row["note"] = f"HTTP {status}: {snippet}"
        return row

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        row["note"] = f"no choices/content in envelope: {json.dumps(body)[:160]}"
        return row

    if content is None:
        finish = body["choices"][0].get("finish_reason")
        row["content"] = "null"
        row["note"] = f"content=null finish_reason={finish!r} (reasoning model ate the budget?)"
        return row
    row["content"] = f"{len(content)}ch"

    raw_ok = False
    try:
        parsed = json.loads(content)
        raw_ok = True
    except json.JSONDecodeError:
        try:
            parsed = json.loads(_strip_fence(content))
        except json.JSONDecodeError as e:
            row["parse"] = "FAIL"
            row["note"] = f"{e}; head={content[:80]!r}"
            return row

    missing = _REQUIRED_KEYS - set(parsed)
    if missing:
        row["parse"] = "keys?"
        row["note"] = f"missing {sorted(missing)}"
        return row

    row["parse"] = "ok" if raw_ok else "ok(after fence-strip)"
    row["note"] = (
        f"{parsed['direction']} conf={parsed['confidence']} strike={parsed['recommended_strike']}"
    )
    return row


async def _probe(
    session: aiohttp.ClientSession, key: str, slug: str, messages: list[dict], max_tokens: int
) -> dict:
    payload = {
        "model": slug,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {key}"}
    t0 = time.monotonic()
    try:
        async with session.post(_BASE_URL, json=payload, headers=headers) as resp:
            try:
                body = await resp.json()
            except aiohttp.ContentTypeError:
                body = await resp.text()
            return _classify(resp.status, body, time.monotonic() - t0)
    except asyncio.TimeoutError:
        return {
            "status": 0,
            "latency_s": round(time.monotonic() - t0, 1),
            "content": "-",
            "parse": "-",
            "note": "TIMEOUT",
        }
    except aiohttp.ClientError as e:
        return {
            "status": 0,
            "latency_s": round(time.monotonic() - t0, 1),
            "content": "-",
            "parse": "-",
            "note": f"client error: {e}",
        }


async def _run(max_tokens: int, timeout_s: float) -> None:
    key = (dotenv_values(".env").get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        import os

        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise SystemExit("OPENROUTER_API_KEY not found in .env or environment")

    messages = build_prompt(_snapshot(), "gpt4o")
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    results: list[tuple[str, str, dict]] = []
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [_probe(session, key, slug, messages, max_tokens) for _fam, slug, _p in _CANDIDATES]
        rows = await asyncio.gather(*tasks)
    for (fam, slug, price), row in zip(_CANDIDATES, rows, strict=True):
        results.append((fam, slug, {**row, "_price": price}))

    print(f"# signal model probe — max_tokens={max_tokens} timeout={timeout_s}s — {date.today()}\n")
    print(f"{'family':<8} {'slug':<30} {'HTTP':>5} {'lat':>6} {'content':>8} {'parse':>20}  note")
    print("-" * 120)
    for fam, slug, row in results:
        print(
            f"{fam:<8} {slug:<30} {row['status']:>5} {row['latency_s']:>5}s "
            f"{row['content']:>8} {row['parse']:>20}  {row['note'][:60]}"
        )

    print("\n## Recommended (cheapest clean parse per family):")
    for fam in ("grok", "gpt4o", "gemini"):
        ok = [
            (slug, row["_price"])
            for f, slug, row in results
            if f == fam and row["parse"].startswith("ok")
        ]
        if ok:
            best = min(ok, key=lambda pair: pair[1])
            print(f"  SIGNAL_MODEL_{fam.upper():<7} {best[0]}")
        else:
            print(
                f"  SIGNAL_MODEL_{fam.upper():<7} — no candidate returned clean JSON; see rows above"
            )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--timeout", type=float, default=90.0)
    args = ap.parse_args()
    asyncio.run(_run(args.max_tokens, args.timeout))


if __name__ == "__main__":
    main()
