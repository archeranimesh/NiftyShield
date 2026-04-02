"""Test Upstox Market Quote LTP API — V2 vs V3.

Hits both endpoints with the EBBETF0431 instrument key to check
which versions work with the Analytics Token.

Usage:
    python scripts/test_api_version.py
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("UPSTOX_ANALYTICS_TOKEN")
if not TOKEN:
    print("Error: UPSTOX_ANALYTICS_TOKEN not set in .env")
    sys.exit(1)

TEST_KEY = "NSE_EQ|INF754K01LE1"  # EBBETF0431
HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Bearer {TOKEN}",
}

ENDPOINTS = {
    "V2 LTP": f"https://api.upstox.com/v2/market-quote/ltp?instrument_key={TEST_KEY}",
    "V3 LTP": f"https://api.upstox.com/v3/market-quote/ltp?instrument_key={TEST_KEY}",
}

for label, url in ENDPOINTS.items():
    print(f"\n{'='*50}")
    print(f"Testing {label}")
    print(f"  URL: {url}")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        print(f"  Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"  Response: {data}")
        else:
            print(f"  Error: {resp.text[:300]}")
    except Exception as e:
        print(f"  Exception: {e}")

print(f"\n{'='*50}")
print("Done. Use whichever version returns status 200.")
