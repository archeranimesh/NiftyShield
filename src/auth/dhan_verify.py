"""Dhan API connectivity check.

Loads DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN from .env, calls the
User Profile and Holdings endpoints to confirm the token is valid.

Usage:
    python -m src.auth.dhan_verify
"""

import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

DHAN_API_BASE = "https://api.dhan.co/v2"


def load_dhan_credentials(env_path: Path = Path(".env")) -> tuple[str, str]:
    """Load Dhan client ID and access token from .env.

    Args:
        env_path: Path to the .env file.

    Returns:
        Tuple of (client_id, access_token).

    Raises:
        ValueError: If either credential is missing or empty.
    """
    load_dotenv(env_path)

    client_id = os.getenv("DHAN_CLIENT_ID", "").strip()
    access_token = os.getenv("DHAN_ACCESS_TOKEN", "").strip()

    if not client_id:
        raise ValueError(
            "DHAN_CLIENT_ID must be set in .env. "
            "Run 'python -m src.auth.dhan_login' first."
        )
    if not access_token:
        raise ValueError(
            "DHAN_ACCESS_TOKEN must be set in .env. "
            "Run 'python -m src.auth.dhan_login' to generate and save a token."
        )

    return client_id, access_token


def _build_headers(access_token: str) -> dict[str, str]:
    """Build the HTTP headers required for Dhan API calls.

    Args:
        access_token: JWT access token.

    Returns:
        Headers dict with access-token and Content-Type.
    """
    return {
        "access-token": access_token,
        "Content-Type": "application/json",
    }


def fetch_profile(client_id: str, access_token: str) -> dict[str, Any]:
    """Fetch user profile from Dhan API.

    Args:
        client_id: Dhan client ID.
        access_token: JWT access token.

    Returns:
        Profile data dict.

    Raises:
        requests.HTTPError: On non-2xx response.
    """
    url = f"{DHAN_API_BASE}/profile"
    headers = _build_headers(access_token)
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_holdings(client_id: str, access_token: str) -> list[dict[str, Any]]:
    """Fetch holdings from Dhan API.

    Args:
        client_id: Dhan client ID.
        access_token: JWT access token.

    Returns:
        List of holding dicts.

    Raises:
        requests.HTTPError: On non-2xx response.
    """
    url = f"{DHAN_API_BASE}/holdings"
    headers = _build_headers(access_token)
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    # Dhan returns a list directly for holdings
    if isinstance(data, list):
        return data
    # Some responses may wrap in a dict
    return data.get("data", data.get("holdings", []))


def parse_holdings(raw_holdings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract display-relevant fields from raw holdings response.

    Args:
        raw_holdings: List of holding dicts from the API.

    Returns:
        List of dicts with keys: trading_symbol, total_qty, avg_cost_price.
    """
    result = []
    for h in raw_holdings:
        try:
            result.append({
                "trading_symbol": h.get("tradingSymbol", "UNKNOWN").strip(),
                "total_qty": h.get("totalQty", 0),
                "avg_cost_price": h.get("avgCostPrice", 0.0),
            })
        except (AttributeError, TypeError):
            # Skip malformed entries
            continue
    return result


def verify(env_path: Path = Path(".env")) -> bool:
    """Verify Dhan session is active by fetching profile and holdings.

    Args:
        env_path: Path to .env file.

    Returns:
        True if session is active, False otherwise.
    """
    try:
        client_id, access_token = load_dhan_credentials(env_path)
    except ValueError as e:
        print(f"✗ Configuration error: {e}")
        return False

    # Verify profile
    try:
        profile = fetch_profile(client_id, access_token)
        name = profile.get("dhanClientName", profile.get("clientName", "N/A"))
        dhan_id = profile.get("dhanClientId", client_id)
        print(f"✓ Dhan session active — profile: {name} ({dhan_id})")
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        if status == 401:
            print(
                "✗ Token expired or invalid. "
                "Generate a new one from web.dhan.co → Profile → Access DhanHQ APIs."
            )
        else:
            print(f"✗ Dhan profile fetch failed (HTTP {status}): {e}")
        return False
    except Exception as e:
        print(f"✗ Dhan connectivity check failed: {e}")
        return False

    # Fetch holdings
    try:
        raw = fetch_holdings(client_id, access_token)
        holdings = parse_holdings(raw)
        print(f"✓ {len(holdings)} holding(s) found.")
        for h in holdings:
            print(
                f"  {h['trading_symbol']:40s}  "
                f"qty={h['total_qty']:>8}  "
                f"avg={h['avg_cost_price']:.2f}"
            )
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        print(f"✗ Holdings fetch failed (HTTP {status}): {e}")
        return False
    except Exception as e:
        print(f"✗ Holdings fetch failed: {e}")
        return False

    return True


if __name__ == "__main__":
    ok = verify()
    raise SystemExit(0 if ok else 1)
