"""CM-0 probe: four-leg Greeks/bid-ask availability and winged-calendar margin. Read-only (margin calc places no order)."""

import asyncio
import os
import sys

import requests
from dotenv import load_dotenv

from src.client.upstox_live import UpstoxLiveClient

load_dotenv()
NEAR, FAR = sys.argv[1], sys.argv[2]
WING = int(sys.argv[3]) if len(sys.argv) > 3 else 600
QTY = int(os.environ.get("LOT", "65"))
H = {
    "Accept": "application/json",
    "Authorization": f"Bearer {os.environ['UPSTOX_ANALYTICS_TOKEN']}",
}


def chain(exp):
    r = requests.get(
        "https://api.upstox.com/v2/option/chain",
        headers=H,
        timeout=30,
        params={"instrument_key": "NSE_INDEX|Nifty 50", "expiry_date": exp},
    )
    r.raise_for_status()
    return {int(s["strike_price"]): s for s in r.json()["data"]}


def leg(rows, strike, side):
    o = rows[strike][side]
    g, m = o["option_greeks"], o["market_data"]
    return o["instrument_key"], dict(
        k=strike,
        ltp=m["ltp"],
        bid=m["bid_price"],
        ask=m["ask_price"],
        delta=g.get("delta"),
        vega=g.get("vega"),
        iv=g.get("iv"),
    )


async def main():
    near, far = chain(NEAR), chain(FAR)
    spot = next(iter(near.values()))["underlying_spot_price"]
    atm = min(near, key=lambda k: abs(k - spot))
    legs = [
        ("near CE", *leg(near, atm, "call_options"), "SELL"),
        ("near PE", *leg(near, atm, "put_options"), "SELL"),
        ("far CE", *leg(far, atm + WING, "call_options"), "BUY"),
        ("far PE", *leg(far, atm - WING, "put_options"), "BUY"),
    ]
    print("spot", spot, "atm", atm, "wing", WING, "qty", QTY)
    for name, key, d, act in legs:
        print(name, act, key, d)
    print("far-month strikes (step 100) with two-sided quotes, +-1500 of ATM:")
    print(
        [
            k
            for k in sorted(far)
            if k % 100 == 0
            and abs(k - atm) <= 1500
            and (far[k]["call_options"]["market_data"]["bid_price"] or 0) > 0
            and (far[k]["call_options"]["market_data"]["ask_price"] or 0) > 0
        ]
    )
    c = UpstoxLiveClient(token=os.environ["UPSTOX_ACCESS_TOKEN"])

    def basket(ls):
        return [
            {"instrument_key": k, "quantity": QTY, "transaction_type": a, "product": "D"}
            for _, k, _, a in ls
        ]

    for label, ls in [("straddle only", legs[:2]), ("winged 4-leg", legs)]:
        print(label, await c.get_order_margin(basket(ls)))


asyncio.run(main())
