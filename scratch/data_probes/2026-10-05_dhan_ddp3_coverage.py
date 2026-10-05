"""DDP-3 coverage inventory for the Dhan Data API POC (docs/plan/dhan-data-poc).

Scratch, read-only, no orders. Raw responses are saved under --out; stdout carries only aggregates.

Usage:
    PYTHONPATH=. python scratch/data_probes/2026-10-05_dhan_ddp3_coverage.py --out DIR [--phase matrix,intervals,chain]

Phases:
    matrix     rolling expired options: expiryCode 1/2/3 (0 is rejected) x WEEK/MONTH x CALL/PUT x ATM, ATM+-10, ATM+-11
    intervals  candle sizes 1/5/15/25/60 on one case
    chain      live option chain for every listed expiry (4 s spacing): strikes, delta, two-sided quotes

Model delta in the matrix table is an INFERENCE: Black-Scholes from the stored IV, spot and strike, with
the expiry derived from the Tuesday rule (REFERENCES.md) and r=6.5%. Dhan returns no delta for expired data.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from scratch._lib.dhan_data_api import NIFTY_ID, auth_headers, call, rolling_body

RATE = 0.065
RATE_GAP_S = 1.0
CHAIN_GAP_S = 4.0
STRIKE_CASES = ["ATM", "ATM+10", "ATM+11", "ATM-10", "ATM-11"]


def _last_tuesday(year: int, month: int) -> date:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    d = nxt - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - 1) % 7)


def expiry_for(d: date, flag: str, code: int) -> date:
    """Expiry that code 1/2/3 (near/next/far, inferred) would point at on date d (inference: Tuesday expiries)."""
    if flag == "WEEK":
        first = d + timedelta(days=(1 - d.weekday()) % 7)
        return first + timedelta(weeks=code - 1)
    y, m = d.year, d.month
    exp = _last_tuesday(y, m)
    if exp < d:
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    for _ in range(code - 1):
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return _last_tuesday(y, m)


def bs_delta(
    spot: float, strike: float, t_years: float, iv_pct: float, is_call: bool
) -> float | None:
    if t_years <= 0 or iv_pct <= 0:
        return None
    s = iv_pct / 100.0
    d1 = (math.log(spot / strike) + (RATE + s * s / 2) * t_years) / (s * math.sqrt(t_years))
    nd1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
    return nd1 if is_call else nd1 - 1


def _day(ts: float) -> date:
    secs = ts / 1000 if ts > 1e11 else ts
    return (
        datetime.fromtimestamp(secs, tz=timezone.utc)
        .astimezone(timezone(timedelta(hours=5, minutes=30)))
        .date()
    )


def summarise(block: dict[str, Any], flag: str, code: int, is_call: bool) -> dict[str, Any]:
    """Aggregate one rolling response block into a compact row."""
    n = max((len(v) for v in block.values() if isinstance(v, list)), default=0)
    if not n:
        return {"rows": 0}
    ts, strike, spot, iv = (block.get(k) or [] for k in ("timestamp", "strike", "spot", "iv"))
    out: dict[str, Any] = {"rows": n, "first": str(_day(ts[0])), "last": str(_day(ts[-1]))}
    for f in ("iv", "oi", "volume"):
        col = block.get(f) or []
        out[f"{f}_nz"] = f"{sum(1 for x in col if x):d}/{len(col)}"
    pct, deltas = [], []
    for i in range(min(len(strike), len(spot), len(iv), len(ts))):
        if not spot[i]:
            continue
        pct.append(abs(strike[i] - spot[i]) / spot[i] * 100)
        d = _day(ts[i])
        t = (expiry_for(d, flag, code) - d).days / 365
        dl = bs_delta(spot[i], strike[i], t, iv[i] or 0, is_call)
        if dl is not None:
            deltas.append(abs(dl))
    if pct:
        out["otm_pct"] = f"{min(pct):.1f}-{max(pct):.1f}"
    if deltas:
        out["model_delta"] = f"{min(deltas):.2f}-{max(deltas):.2f}"
    return out


def run_matrix(h: dict[str, str], out: Path, start: date, end: date) -> None:
    print("\nMATRIX (window", start, "..", end, ", 60-min candles)")
    print(
        "code flag  opt  strike  | rows first..last | iv_nz oi_nz vol_nz | otm_pct | model_delta(inferred)"
    )
    for code in (1, 2, 3):
        for flag in ("WEEK", "MONTH"):
            for opt in ("CALL", "PUT"):
                for strike in STRIKE_CASES:
                    body = rolling_body(strike, opt, flag, code, "60", start, end)
                    data, err = call("POST", "/charts/rollingoption", h, body, RATE_GAP_S)
                    tag = f"{code} {flag:5} {opt:4} {strike:7}"
                    if err:
                        print(f"{tag} | ERR {err}")
                        if "805" in err:
                            print("rate limit hit; stopping matrix")
                            return
                        continue
                    (out / f"matrix_{code}_{flag}_{opt}_{strike}.json").write_text(json.dumps(data))
                    block = (data.get("data") or {}).get("ce" if opt == "CALL" else "pe") or {}
                    s = summarise(block, flag, code, opt == "CALL")
                    if not s["rows"]:
                        print(f"{tag} | rows=0")
                        continue
                    print(
                        f"{tag} | {s['rows']} {s['first']}..{s['last']} | {s['iv_nz']} {s['oi_nz']} "
                        f"{s['volume_nz']} | {s.get('otm_pct', '-')} | {s.get('model_delta', '-')}"
                    )


def run_intervals(h: dict[str, str], out: Path, end: date) -> None:
    print("\nINTERVALS (ATM CALL MONTH code 1, 7-day window)")
    for interval in ("1", "5", "15", "25", "60"):
        body = rolling_body("ATM", "CALL", "MONTH", 1, interval, end - timedelta(days=6), end)
        data, err = call("POST", "/charts/rollingoption", h, body, RATE_GAP_S)
        if err:
            print(f"interval {interval:>2}: ERR {err}")
            continue
        block = (data.get("data") or {}).get("ce") or {}
        n = max((len(v) for v in block.values() if isinstance(v, list)), default=0)
        print(f"interval {interval:>2}: rows={n}")


def run_chain(h: dict[str, str], out: Path) -> None:
    print("\nCHAIN (live, every listed expiry)")
    base = {"UnderlyingScrip": NIFTY_ID, "UnderlyingSeg": "IDX_I"}
    data, err = call("POST", "/optionchain/expirylist", h, base, CHAIN_GAP_S)
    expiries = (data or {}).get("data") or []
    print(f"expiries: {len(expiries)} {err}")
    print("expiry      strikes  ce_delta pe_delta  two_sided_quotes")
    for exp in expiries:
        chain, err = call("POST", "/optionchain", h, {**base, "Expiry": exp}, CHAIN_GAP_S)
        if err:
            print(f"{exp}  ERR {err}")
            continue
        (out / f"chain_{exp}.json").write_text(json.dumps(chain))
        oc = (chain.get("data") or {}).get("oc") or {}
        legs = [(side, r.get(side) or {}) for r in oc.values() for side in ("ce", "pe")]
        nz = {
            s: sum(1 for sd, x in legs if sd == s and (x.get("greeks") or {}).get("delta"))
            for s in ("ce", "pe")
        }
        two = sum(
            1
            for _, x in legs
            if (x.get("top_bid_price") or 0) > 0 and (x.get("top_ask_price") or 0) > 0
        )
        print(f"{exp}  {len(oc):7} {nz['ce']:8} {nz['pe']:8} {two:10}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, help="directory for raw JSON (use the scratchpad)")
    ap.add_argument("--phase", default="matrix,intervals,chain")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    phases = {p.strip() for p in args.phase.split(",")}
    h = auth_headers()
    end = date.today()
    if "matrix" in phases:
        run_matrix(h, out, end - timedelta(days=9), end)
    if "intervals" in phases:
        run_intervals(h, out, end)
    if "chain" in phases:
        run_chain(h, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
