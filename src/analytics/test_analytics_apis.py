"""Analytics Token — API Verification & Fixture Recording.

Tests read-only APIs available via the Analytics Token:
  1. LTP Quote      — NiftyBees current price
  2. Option Contracts — Available Nifty expiry dates
  3. Option Chain    — Nearest expiry with Greeks, IV, OI
  4. Historical Candles V3 — NiftyBees daily OHLCV

Uses raw requests (not SDK) for clean JSON fixture capture.
Analytics Token: 1-year validity, no OAuth flow, read-only.

Fixture Recording:
    Set UPSTOX_RECORD=1 in .env to save responses as JSON
    fixtures to tests/fixtures/responses/<category>/.

Usage:
    python -m src.analytics.test_analytics_apis
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Constants — Instruments relevant to NiftyShield
# ---------------------------------------------------------------------------

NIFTYBEES = "NSE_EQ|INF204KB14I2"
NIFTY_INDEX = "NSE_INDEX|Nifty 50"
BASE_URL = "https://api.upstox.com"


# ---------------------------------------------------------------------------
# Fixture Recorder (shared with sandbox script)
# ---------------------------------------------------------------------------


class FixtureRecorder:
    """Records API responses as JSON fixture files.

    Activated when UPSTOX_RECORD=1. Each fixture includes timestamp,
    environment, endpoint, request params, and full response payload.
    """

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.enabled = os.getenv("UPSTOX_RECORD", "0") == "1"
        if self.enabled:
            print(f"[RECORD] Fixture recording ON → {self.base_dir}")

    def save(
        self,
        category: str,
        name: str,
        endpoint: str,
        params: dict,
        response_json: dict,
    ) -> None:
        """Save an API response as a JSON fixture."""
        if not self.enabled:
            return

        output_dir = self.base_dir / category
        output_dir.mkdir(parents=True, exist_ok=True)

        fixture = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "environment": "analytics",
            "endpoint": endpoint,
            "request_params": params,
            "response": response_json,
        }

        filepath = output_dir / f"{name}.json"
        filepath.write_text(json.dumps(fixture, indent=2, default=str))
        print(f"[RECORD] Saved → {filepath}")


# ---------------------------------------------------------------------------
# API Caller
# ---------------------------------------------------------------------------


class AnalyticsClient:
    """Thin wrapper for Upstox REST API calls with Analytics Token."""

    def __init__(self, token: str):
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }

    def get(self, endpoint: str, params: dict | None = None) -> dict:
        """Make a GET request and return parsed JSON."""
        url = f"{BASE_URL}{endpoint}"
        resp = requests.get(url, headers=self.headers, params=params)

        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}: {resp.text}")
            return {
                "status": "error",
                "http_status": resp.status_code,
                "body": resp.text,
            }

        return resp.json()


# ---------------------------------------------------------------------------
# Test Steps
# ---------------------------------------------------------------------------


def step_ltp_quote(client: AnalyticsClient, recorder: FixtureRecorder) -> None:
    """Step 1: Fetch LTP for NiftyBees."""
    print("\n" + "=" * 60)
    print("STEP 1: LTP Quote — NiftyBees")
    print("=" * 60)

    endpoint = "/v3/market-quote/ltp"
    params = {"instrument_key": NIFTYBEES}

    data = client.get(endpoint, params)
    print(f"Status: {data.get('status')}")

    if data.get("status") == "success":
        for key, quote in data.get("data", {}).items():
            print(f"  Instrument : {key}")
            print(f"  LTP        : ₹{quote.get('last_price')}")
            print(f"  Volume     : {quote.get('volume')}")
            print(f"  Prev Close : ₹{quote.get('cp')}")
        recorder.save("market_quote", "niftybees_ltp", endpoint, params, data)
    else:
        print("  FAILED — see response above")
        recorder.save("market_quote", "niftybees_ltp_error", endpoint, params, data)


def step_option_contracts(
    client: AnalyticsClient,
    recorder: FixtureRecorder,
) -> str | None:
    """Step 2: Fetch available Nifty option expiry dates."""
    print("\n" + "=" * 60)
    print("STEP 2: Option Contracts — Nifty 50 Expiries")
    print("=" * 60)

    endpoint = "/v2/option/contract"
    params = {"instrument_key": NIFTY_INDEX}

    data = client.get(endpoint, params)
    print(f"Status: {data.get('status')}")

    if data.get("status") == "success":
        # Extract unique expiry dates
        contracts = data.get("data", [])
        expiries = sorted({c.get("expiry") for c in contracts if c.get("expiry")})
        print(f"  Total contracts: {len(contracts)}")
        print(f"  Available expiries: {len(expiries)}")
        for exp in expiries[:5]:
            print(f"    - {exp}")
        if len(expiries) > 5:
            print(f"    ... and {len(expiries) - 5} more")

        nearest_expiry = expiries[0] if expiries else None
        print(f"\n>> Nearest expiry: {nearest_expiry}")

        recorder.save("option_chain", "nifty_option_contracts", endpoint, params, data)
        return nearest_expiry
    else:
        print("  FAILED — see response above")
        recorder.save(
            "option_chain", "nifty_option_contracts_error", endpoint, params, data
        )
        return None


def step_option_chain(
    client: AnalyticsClient,
    expiry_date: str,
    recorder: FixtureRecorder,
) -> None:
    """Step 3: Fetch Nifty option chain for nearest expiry."""
    print("\n" + "=" * 60)
    print(f"STEP 3: Option Chain — Nifty 50 ({expiry_date})")
    print("=" * 60)

    endpoint = "/v2/option/chain"
    params = {"instrument_key": NIFTY_INDEX, "expiry_date": expiry_date}

    data = client.get(endpoint, params)
    print(f"Status: {data.get('status')}")

    if data.get("status") == "success":
        strikes = data.get("data", [])
        print(f"  Strikes returned: {len(strikes)}")

        if strikes:
            spot = strikes[0].get("underlying_spot_price")
            print(f"  Nifty Spot: {spot}")

            # Find ATM strike
            atm = min(strikes, key=lambda s: abs(s["strike_price"] - spot))
            sp = atm["strike_price"]
            call = atm.get("call_options", {})
            put = atm.get("put_options", {})
            call_greeks = call.get("option_greeks", {})
            put_greeks = put.get("option_greeks", {})
            call_mkt = call.get("market_data", {})
            put_mkt = put.get("market_data", {})

            print(f"\n  ATM Strike: {sp}")
            print(
                f"  CE  LTP: {call_mkt.get('ltp'):>8}  IV: {call_greeks.get('iv'):>7}  "
                f"Delta: {call_greeks.get('delta'):>7}  OI: {call_mkt.get('oi')}"
            )
            print(
                f"  PE  LTP: {put_mkt.get('ltp'):>8}  IV: {put_greeks.get('iv'):>7}  "
                f"Delta: {put_greeks.get('delta'):>7}  OI: {put_mkt.get('oi')}"
            )

        fixture_name = f"nifty_chain_{expiry_date}"
        recorder.save("option_chain", fixture_name, endpoint, params, data)
    else:
        print("  FAILED — see response above")
        recorder.save("option_chain", "nifty_chain_error", endpoint, params, data)


def step_historical_candles(
    client: AnalyticsClient,
    recorder: FixtureRecorder,
) -> None:
    """Step 4: Fetch NiftyBees daily candles (last 30 days)."""
    print("\n" + "=" * 60)
    print("STEP 4: Historical Candles — NiftyBees Daily")
    print("=" * 60)

    today = datetime.now().strftime("%Y-%m-%d")
    # V3 path: /v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}
    instrument_encoded = NIFTYBEES.replace("|", "%7C")
    endpoint = f"/v3/historical-candle/{instrument_encoded}/days/1/{today}/2026-03-01"

    data = client.get(endpoint)
    print(f"Status: {data.get('status')}")

    if data.get("status") == "success":
        candles = data.get("data", {}).get("candles", [])
        print(f"  Candles returned: {len(candles)}")

        if candles:
            print(f"\n  Format: [timestamp, open, high, low, close, volume, oi]")
            print(f"  Latest 3:")
            for candle in candles[:3]:
                ts = candle[0][:10] if candle[0] else "?"
                o, h, l, c, v = candle[1], candle[2], candle[3], candle[4], candle[5]
                print(f"    {ts}  O:{o}  H:{h}  L:{l}  C:{c}  Vol:{v}")

        params = {
            "instrument_key": NIFTYBEES,
            "unit": "days",
            "interval": 1,
            "to_date": today,
            "from_date": "2026-03-01",
        }
        recorder.save(
            "historical_candles", "niftybees_daily_30d", endpoint, params, data
        )
    else:
        print("  FAILED — see response above")
        recorder.save("historical_candles", "niftybees_daily_error", endpoint, {}, data)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run all analytics API tests with fixture recording."""
    print("Upstox Analytics Token — API Verification")
    print("Project: NiftyShield")
    print("-" * 40)

    load_dotenv()
    token = os.getenv("UPSTOX_ANALYTICS_TOKEN")
    if not token:
        print("ERROR: UPSTOX_ANALYTICS_TOKEN not found in .env")
        sys.exit(1)

    print(f"Token loaded: ...{token[-8:]}")

    client = AnalyticsClient(token)

    # Fixture recorder
    project_root = Path(__file__).resolve().parent.parent.parent
    fixtures_dir = project_root / "tests" / "fixtures" / "responses"
    recorder = FixtureRecorder(fixtures_dir)

    # Step 1: LTP
    step_ltp_quote(client, recorder)

    # Step 2: Option Contracts (get expiries)
    nearest_expiry = step_option_contracts(client, recorder)

    # Step 3: Option Chain (if we have a valid expiry)
    if nearest_expiry:
        step_option_chain(client, nearest_expiry, recorder)
    else:
        print("\n  SKIPPED Step 3 — no valid expiry found")

    # Step 4: Historical Candles
    step_historical_candles(client, recorder)

    # Summary
    print("\n" + "=" * 60)
    print("ALL STEPS COMPLETED")
    print("=" * 60)

    if recorder.enabled:
        print(f"\nFixtures saved under: {fixtures_dir}/")
        for category_dir in sorted(fixtures_dir.iterdir()):
            if category_dir.is_dir():
                for f in sorted(category_dir.glob("*.json")):
                    print(f"  {category_dir.name}/{f.name}")

    print("\nAnalytics API verification complete.")


if __name__ == "__main__":
    main()
