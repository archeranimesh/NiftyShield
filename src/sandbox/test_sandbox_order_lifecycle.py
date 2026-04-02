"""Sandbox Order Lifecycle Test.

Tests the full order lifecycle against Upstox sandbox:
  Place (LIMIT) → Modify (price change) → Cancel

Uses the Upstox Python SDK with sandbox=True.
No real funds, no static IP required, works 24/7.

Fixture Recording:
    Set UPSTOX_RECORD=1 in .env to save request/response pairs
    as JSON fixtures to tests/fixtures/responses/orders/.

Usage:
    python -m src.sandbox.test_sandbox_order_lifecycle
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
import upstox_client
from upstox_client.rest import ApiException


# ---------------------------------------------------------------------------
# Fixture Recorder
# ---------------------------------------------------------------------------

class FixtureRecorder:
    """Records API request/response pairs as JSON fixture files.

    Activated when UPSTOX_RECORD=1. Saves to tests/fixtures/responses/orders/.
    Each fixture includes: timestamp, environment, request params, and
    the full response payload — enough to reconstruct MockBrokerClient behavior.
    """

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.enabled = os.getenv("UPSTOX_RECORD", "0") == "1"
        if self.enabled:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            print(f"[RECORD] Fixture recording ON → {self.output_dir}")

    def save(self, name: str, request_params: dict, response_obj: object) -> None:
        """Save a request/response pair as a JSON fixture."""
        if not self.enabled:
            return

        fixture = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "environment": "sandbox",
            "request": request_params,
            "response": self._serialize(response_obj),
        }

        filepath = self.output_dir / f"{name}.json"
        filepath.write_text(json.dumps(fixture, indent=2, default=str))
        print(f"[RECORD] Saved → {filepath}")

    def save_error(self, name: str, request_params: dict, error: ApiException) -> None:
        """Save an error response as a JSON fixture."""
        if not self.enabled:
            return

        fixture = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "environment": "sandbox",
            "request": request_params,
            "error": {
                "status": error.status,
                "reason": error.reason,
                "body": self._parse_error_body(error.body),
            },
        }

        filepath = self.output_dir / f"{name}.json"
        filepath.write_text(json.dumps(fixture, indent=2, default=str))
        print(f"[RECORD] Saved error → {filepath}")

    def _serialize(self, obj: object) -> dict:
        """Convert SDK response object to dict."""
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        return {"raw": str(obj)}

    def _parse_error_body(self, body: str | None) -> dict | str:
        """Attempt to parse error body as JSON, fallback to string."""
        if not body:
            return ""
        try:
            return json.loads(body)
        except (json.JSONDecodeError, TypeError):
            return body


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_sandbox_token() -> str:
    """Load sandbox token from .env file."""
    load_dotenv()
    token = os.getenv("UPSTOX_SANDBOX_TOKEN")
    if not token:
        print("ERROR: UPSTOX_SANDBOX_TOKEN not found in .env")
        sys.exit(1)
    return token


def create_sandbox_client(token: str) -> upstox_client.OrderApiV3:
    """Create SDK client configured for sandbox mode."""
    config = upstox_client.Configuration(sandbox=True)
    config.access_token = token
    api_client = upstox_client.ApiClient(config)
    return upstox_client.OrderApiV3(api_client)


# ---------------------------------------------------------------------------
# Order Lifecycle Steps
# ---------------------------------------------------------------------------

def step_place_order(
    client: upstox_client.OrderApiV3,
    recorder: FixtureRecorder,
) -> str:
    """Step 1: Place a LIMIT BUY order (stays open for modify/cancel)."""
    print("\n" + "=" * 60)
    print("STEP 1: Place LIMIT Order")
    print("=" * 60)

    request_params = {
        "quantity": 1,
        "product": "D",
        "validity": "DAY",
        "price": 1.0,
        "tag": "niftyshield-sandbox-test",
        "instrument_token": "NSE_EQ|INE669E01016",
        "order_type": "LIMIT",
        "transaction_type": "BUY",
        "disclosed_quantity": 0,
        "trigger_price": 0.0,
        "is_amo": False,
        "slice": False,
    }

    body = upstox_client.PlaceOrderV3Request(**request_params)

    try:
        response = client.place_order(body)
        print(f"Status : {response.status}")
        print(f"Order IDs: {response.data.order_ids}")
        print(f"Latency : {response.metadata.latency}ms")

        order_id = response.data.order_ids[0]
        print(f"\n>> Order placed successfully. order_id = {order_id}")

        recorder.save("place_order_success", request_params, response)
        return order_id

    except ApiException as e:
        print(f"FAILED: {e.status} — {e.body}")
        recorder.save_error("place_order_failure", request_params, e)
        sys.exit(1)


def step_modify_order(
    client: upstox_client.OrderApiV3,
    order_id: str,
    recorder: FixtureRecorder,
) -> None:
    """Step 2: Modify the order — change price."""
    print("\n" + "=" * 60)
    print("STEP 2: Modify Order (price 1.0 → 1.5)")
    print("=" * 60)

    request_params = {
        "quantity": 1,
        "validity": "DAY",
        "price": 1.5,
        "order_id": order_id,
        "order_type": "LIMIT",
        "disclosed_quantity": 0,
        "trigger_price": 0.0,
    }

    body = upstox_client.ModifyOrderRequest(**request_params)

    try:
        response = client.modify_order(body)
        print(f"Status  : {response.status}")
        print(f"Order ID: {response.data.order_id}")
        print(f"Latency : {response.metadata.latency}ms")
        print(f"\n>> Order modified successfully.")

        recorder.save("modify_order_success", request_params, response)

    except ApiException as e:
        print(f"FAILED: {e.status} — {e.body}")
        recorder.save_error("modify_order_failure", request_params, e)
        sys.exit(1)


def step_cancel_order(
    client: upstox_client.OrderApiV3,
    order_id: str,
    recorder: FixtureRecorder,
) -> None:
    """Step 3: Cancel the order."""
    print("\n" + "=" * 60)
    print("STEP 3: Cancel Order")
    print("=" * 60)

    request_params = {"order_id": order_id}

    try:
        response = client.cancel_order(order_id)
        print(f"Status  : {response.status}")
        print(f"Order ID: {response.data.order_id}")
        print(f"Latency : {response.metadata.latency}ms")
        print(f"\n>> Order cancelled successfully.")

        recorder.save("cancel_order_success", request_params, response)

    except ApiException as e:
        print(f"FAILED: {e.status} — {e.body}")
        recorder.save_error("cancel_order_failure", request_params, e)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run full order lifecycle: Place → Modify → Cancel."""
    print("Upstox Sandbox — Order Lifecycle Test")
    print("Project: NiftyShield")
    print("-" * 40)

    token = load_sandbox_token()
    print(f"Token loaded: ...{token[-8:]}")

    client = create_sandbox_client(token)
    print("Sandbox client created (sandbox=True)")

    # Fixture recorder — writes to tests/fixtures/responses/orders/
    project_root = Path(__file__).resolve().parent.parent.parent
    fixtures_dir = project_root / "tests" / "fixtures" / "responses" / "orders"
    recorder = FixtureRecorder(fixtures_dir)

    # Step 1: Place
    order_id = step_place_order(client, recorder)
    time.sleep(1)

    # Step 2: Modify
    step_modify_order(client, order_id, recorder)
    time.sleep(1)

    # Step 3: Cancel
    step_cancel_order(client, order_id, recorder)

    # Summary
    print("\n" + "=" * 60)
    print("ALL STEPS PASSED")
    print("=" * 60)
    print(f"  Place  → order_id: {order_id}")
    print(f"  Modify → price changed to 1.5")
    print(f"  Cancel → order cancelled")

    if recorder.enabled:
        print(f"\n  Fixtures saved to: {fixtures_dir}/")
        print("  Files:")
        for f in sorted(fixtures_dir.glob("*.json")):
            print(f"    - {f.name}")

    print("\nSandbox order lifecycle verified end-to-end.")


if __name__ == "__main__":
    main()
