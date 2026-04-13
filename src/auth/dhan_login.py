"""Dhan API manual token login flow.

Opens browser to web.dhan.co for the user to generate an access token.
User pastes the token — this module validates it and saves it to .env.

Token lifetime: 24 hours. Regenerate daily via web.dhan.co or re-run this script.

Prerequisites:
    1. Create a Dhan account at dhan.co
    2. Login to web.dhan.co → Profile → "Access DhanHQ APIs"
    3. Add DHAN_CLIENT_ID to .env (your numeric client ID)
    4. Generate an access token (Application Name: NiftyShield, Token validity: 24h)

Usage:
    python -m src.auth.dhan_login
"""

import os
import webbrowser
from pathlib import Path

from dotenv import load_dotenv, set_key

DHAN_WEB_URL = "https://web.dhan.co"


def build_login_url() -> str:
    """Return the Dhan web URL where users generate their access token."""
    return DHAN_WEB_URL


def validate_token(token: str) -> str:
    """Validate and clean the access token input.

    Args:
        token: Raw user input (may contain whitespace).

    Returns:
        Cleaned token string.

    Raises:
        ValueError: If token is empty or whitespace-only.
    """
    cleaned = token.strip()
    if not cleaned:
        raise ValueError("Access token cannot be empty.")
    return cleaned


def save_token(env_path: Path, token: str) -> None:
    """Upsert DHAN_ACCESS_TOKEN into the .env file.

    Uses dotenv set_key so it upserts without clobbering other variables.

    Args:
        env_path: Path to the .env file.
        token: Validated access token string.
    """
    set_key(str(env_path), "DHAN_ACCESS_TOKEN", token)


def login(env_path: Path = Path(".env")) -> None:
    """Full interactive login flow for Dhan manual token.

    Reads DHAN_CLIENT_ID from env_path, opens browser to web.dhan.co,
    prompts user to paste the generated access token, saves it to .env.

    Args:
        env_path: Path to the .env file to read credentials from and update.

    Raises:
        ValueError: If DHAN_CLIENT_ID is not set or user provides empty input.
    """
    load_dotenv(env_path)

    client_id = os.getenv("DHAN_CLIENT_ID", "").strip()
    if not client_id:
        raise ValueError(
            "DHAN_CLIENT_ID must be set in .env before running login.\n"
            "Steps:\n"
            "  1. Login to web.dhan.co\n"
            "  2. Click your profile icon (top-right)\n"
            "  3. Your Client ID is displayed there (numeric, e.g. 1000000001)\n"
            "  4. Add to .env: DHAN_CLIENT_ID=<your-client-id>"
        )

    url = build_login_url()
    print(f"\nOpening Dhan web portal...\n{url}\n")
    webbrowser.open(url)

    print("Steps to generate your access token:")
    print("  1. Login to web.dhan.co")
    print("  2. Click Profile → 'Access DhanHQ APIs'")
    print("  3. Click 'Generate Access Token'")
    print("  4. Fill in: App Name (e.g. NiftyShield), Token validity: 24h")
    print("  5. Copy the generated token\n")

    raw_token = input("Paste your access token: ").strip()
    token = validate_token(raw_token)

    save_token(env_path, token)
    print(f"\n✓ DHAN_ACCESS_TOKEN saved to {env_path}")
    print(f"  Client ID: {client_id}")
    print(f"  Token: {token[:20]}...")
    print("\nRun 'python -m src.auth.dhan_verify' to confirm connectivity.")


if __name__ == "__main__":
    login()
