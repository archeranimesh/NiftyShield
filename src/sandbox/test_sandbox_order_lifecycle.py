"""Sandbox Order Lifecycle Test.

Tests the full order lifecycle against Upstox sandbox:
  Place (LIMIT) → Modify (price change) → Cancel

Uses the Upstox Python SDK with sandbox=True.
No real funds, no static IP required, works 24/7.

Usage:
    python test_sandbox_order_lifecycle.py
"""

import os
import sys
import time

from dotenv import load_dotenv
import upstox_client
from upstox_client.rest import ApiException


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


def step_place_order(client: upstox_client.OrderApiV3) -> str:
    """Step 1: Place a LIMIT BUY order (stays open for modify/cancel)."""
    print("\n" + "=" * 60)
    print("STEP 1: Place LIMIT Order")
    print("=" * 60)

    body = upstox_client.PlaceOrderV3Request(
        quantity=1,
        product="D",
        validity="DAY",
        price=1.0,  # Low price so it won't execute
        tag="niftyshield-sandbox-test",
        instrument_token="NSE_EQ|INE669E01016",  # NHPC — used in Upstox sandbox examples
        order_type="LIMIT",
        transaction_type="BUY",
        disclosed_quantity=0,
        trigger_price=0.0,
        is_amo=False,
        slice=False,
    )

    try:
        response = client.place_order(body)
        print(f"Status : {response.status}")
        print(f"Order IDs: {response.data.order_ids}")
        print(f"Latency : {response.metadata.latency}ms")
        order_id = response.data.order_ids[0]
        print(f"\n>> Order placed successfully. order_id = {order_id}")
        return order_id
    except ApiException as e:
        print(f"FAILED: {e.status} — {e.body}")
        sys.exit(1)


def step_modify_order(client: upstox_client.OrderApiV3, order_id: str) -> None:
    """Step 2: Modify the order — change price."""
    print("\n" + "=" * 60)
    print("STEP 2: Modify Order (price 1.0 → 1.5)")
    print("=" * 60)

    body = upstox_client.ModifyOrderRequest(
        quantity=1,
        validity="DAY",
        price=1.5,
        order_id=order_id,
        order_type="LIMIT",
        disclosed_quantity=0,
        trigger_price=0.0,
    )

    try:
        response = client.modify_order(body)
        print(f"Status  : {response.status}")
        print(f"Order ID: {response.data.order_id}")
        print(f"Latency : {response.metadata.latency}ms")
        print(f"\n>> Order modified successfully.")
    except ApiException as e:
        print(f"FAILED: {e.status} — {e.body}")
        sys.exit(1)


def step_cancel_order(client: upstox_client.OrderApiV3, order_id: str) -> None:
    """Step 3: Cancel the order."""
    print("\n" + "=" * 60)
    print("STEP 3: Cancel Order")
    print("=" * 60)

    try:
        response = client.cancel_order(order_id)
        print(f"Status  : {response.status}")
        print(f"Order ID: {response.data.order_id}")
        print(f"Latency : {response.metadata.latency}ms")
        print(f"\n>> Order cancelled successfully.")
    except ApiException as e:
        print(f"FAILED: {e.status} — {e.body}")
        sys.exit(1)


def main() -> None:
    """Run full order lifecycle: Place → Modify → Cancel."""
    print("Upstox Sandbox — Order Lifecycle Test")
    print("Project: NiftyShield")
    print("-" * 40)

    token = load_sandbox_token()
    print(f"Token loaded: ...{token[-8:]}")

    client = create_sandbox_client(token)
    print("Sandbox client created (sandbox=True)")

    # Step 1: Place
    order_id = step_place_order(client)

    # Brief pause between API calls
    time.sleep(1)

    # Step 2: Modify
    step_modify_order(client, order_id)

    time.sleep(1)

    # Step 3: Cancel
    step_cancel_order(client, order_id)

    # Summary
    print("\n" + "=" * 60)
    print("ALL STEPS PASSED")
    print("=" * 60)
    print(f"  Place  → order_id: {order_id}")
    print(f"  Modify → price changed to 1.5")
    print(f"  Cancel → order cancelled")
    print("\nSandbox order lifecycle verified end-to-end.")


if __name__ == "__main__":
    main()
