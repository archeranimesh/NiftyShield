"""Does Dhan's expired-options data reach far-dated (yearly) 2025 contracts? Read-only. Implied expiry is solved from stored close, spot, strike, IV (inference)."""

import math
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, "scratch/_lib")
from dhan_data_api import RATE, auth_headers, call, rolling_body

H = auth_headers()


def bs_call(s, k, t, vol):
    d1 = (math.log(s / k) + (RATE + vol * vol / 2) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)

    def n(x):
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    return s * n(d1) - k * math.exp(-RATE * t) * n(d2)


def implied_expiry(ts, s, k, close, iv):
    lo, hi = 1e-4, 3.0
    if not bs_call(s, k, lo, iv / 100) <= close <= bs_call(s, k, hi, iv / 100):
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if bs_call(s, k, mid, iv / 100) < close else (lo, mid)
    t = (lo + hi) / 2
    return ts.date() + timedelta(days=round(t * 365))


for start in [
    date(2025, 1, 6),
    date(2025, 6, 2),
    date(2025, 9, 1),
    date(2025, 10, 6),
    date(2025, 12, 1),
]:
    for flag in ("MONTH", "WEEK"):
        for code in (1, 2, 3):
            body = rolling_body("ATM", "CALL", flag, code, "60", start, start + timedelta(days=4))
            data, err = call("POST", "/charts/rollingoption", H, body, 3.5)
            blk = ((data or {}).get("data") or {}).get("ce") or {}
            ts = blk.get("timestamp") or []
            if not ts:
                print(start, flag, code, "rows 0", err)
                continue
            out = []
            for i in (0, len(ts) - 1):
                if (blk["iv"][i] or 0) > 0 and (blk["close"][i] or 0) > 0:
                    t0 = datetime.fromtimestamp(ts[i], tz=timezone.utc)
                    out.append(
                        str(
                            implied_expiry(
                                t0, blk["spot"][i], blk["strike"][i], blk["close"][i], blk["iv"][i]
                            )
                        )
                    )
            print(start, flag, code, "rows", len(ts), "implied expiry first/last row:", out)

print("--- roll test: code 3 monthly daily, 2025-09-15 to 2025-10-14 ---")
for code in (1, 3):
    body = rolling_body("ATM", "CALL", "MONTH", code, "60", date(2025, 9, 15), date(2025, 10, 14))
    data, err = call("POST", "/charts/rollingoption", H, body, 3.5)
    blk = ((data or {}).get("data") or {}).get("ce") or {}
    seen = {}
    for i, t in enumerate(blk.get("timestamp") or []):
        t0 = datetime.fromtimestamp(t, tz=timezone.utc)
        if t0.date() in seen or not ((blk["iv"][i] or 0) > 0 and (blk["close"][i] or 0) > 0):
            continue
        e = implied_expiry(t0, blk["spot"][i], blk["strike"][i], blk["close"][i], blk["iv"][i])
        seen[t0.date()] = (e, (e - t0.date()).days if e else None, round(blk["strike"][i]))
    print("code", code, err)
    for d, v in seen.items():
        print(" ", d, "implied expiry", v[0], "implied DTE", v[1], "ATM strike", v[2])
