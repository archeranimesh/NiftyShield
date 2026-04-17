"""Nuvama API connectivity check.

Loads the persisted APIConnect session from the settings file and calls
Holdings() to confirm the session is active and readable.

Usage:
    python -m src.auth.nuvama_verify
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# APIConnect.py has a module-level logging.basicConfig(filename='apiconnect.log')
# that fires at import time and creates a stray file in CWD (project root).
# basicConfig is a no-op when handlers already exist, so adding NullHandler first
# suppresses the stray file. init_logger() inside APIConnect.__init__ removes all
# handlers and re-configures using settings.ini — so actual log routing is unaffected.
logging.root.addHandler(logging.NullHandler())

try:
    from APIConnect.APIConnect import APIConnect  # type: ignore[import]
except ImportError:
    APIConnect = None  # type: ignore[assignment,misc]

DEFAULT_SETTINGS_FILE = "data/nuvama/settings.json"
# INI conf file for SDK logger — must stay separate from the JSON session file.
# See nuvama_login.py:NUVAMA_CONF_FILE for the canonical explanation.
NUVAMA_CONF_FILE = "data/nuvama/settings.ini"


def load_api_connect(env_path: Path = Path(".env")) -> Any:
    """Initialize APIConnect from persisted settings file (no request_id needed).

    Args:
        env_path: Path to .env file containing NUVAMA_API_KEY, NUVAMA_API_SECRET,
                  and NUVAMA_SETTINGS_FILE.

    Returns:
        Initialized APIConnect instance ready for API calls.

    Raises:
        ValueError: If API credentials are missing from env.
        FileNotFoundError: If settings file does not exist (login not yet run).
    """
    load_dotenv(env_path)

    api_key = os.getenv("NUVAMA_API_KEY", "").strip()
    api_secret = os.getenv("NUVAMA_API_SECRET", "").strip()
    settings_file = os.getenv("NUVAMA_SETTINGS_FILE", DEFAULT_SETTINGS_FILE)

    if not api_key or not api_secret:
        raise ValueError(
            "NUVAMA_API_KEY and NUVAMA_API_SECRET must be set in .env. "
            "Run 'python -m src.auth.nuvama_login' first."
        )

    if not Path(settings_file).exists():
        raise FileNotFoundError(
            f"Nuvama settings file not found: {settings_file}\n"
            "Run 'python -m src.auth.nuvama_login' to create a session first."
        )

    if APIConnect is None:
        raise ImportError(
            "APIConnect package is not installed in this environment.\n"
            "Fix: .venv/bin/pip install APIConnect"
        )

    # The SDK hardcodes data_{api_key}.txt relative to CWD for session reads/writes.
    # Temporarily change CWD to the session file's directory so the SDK finds it there
    # without any copying — and without leaving a stray file in the project root.
    # Resolve both paths to absolute BEFORE the chdir.
    session_dir = Path(settings_file).resolve().parent
    conf_path = Path(NUVAMA_CONF_FILE).resolve()
    conf_arg: str | None = str(conf_path) if conf_path.exists() else None

    original_cwd = Path.cwd()
    os.chdir(session_dir)
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # download_contract=False: never download instruments.zip during a connectivity
        # check — that is a separate, deliberate operation.
        api = APIConnect(api_key, api_secret, "", False, conf_arg)
    finally:
        os.chdir(original_cwd)
    return api


def parse_holdings(raw_response: str) -> list[dict]:
    """Parse the Holdings() JSON response into a flat list of holding records.

    Args:
        raw_response: JSON string returned by api.Holdings().

    Returns:
        List of dicts with keys: company_name, total_qty, ltp.
    """
    data = json.loads(raw_response)

    # Updated path based on your raw response
    try:
        raw_holdings = data["resp"]["data"]["rmsHdg"]
    except KeyError:
        # Fallback for different API versions or empty responses
        print("Structure 'resp.data.rmsHdg' not found. Checking fallback...")
        raw_holdings = data.get("eq", {}).get("data", {}).get("rmsHdg", [])

    return [
        {
            "company_name": h["cpName"].strip(),
            "total_qty": h["totalQty"],
            "ltp": h["ltp"],
        }
        for h in raw_holdings
    ]


def verify(env_path: Path = Path(".env")) -> bool:
    """Verify Nuvama session is active by fetching holdings.

    Args:
        env_path: Path to .env file.

    Returns:
        True if session is active and holdings are readable, False otherwise.
    """
    raw: str | None = None
    try:
        api = load_api_connect(env_path)
        raw = api.Holdings()

        holdings = parse_holdings(raw)
        print(f"✓ Nuvama session active — {len(holdings)} holding(s) found.")
        for h in holdings:
            print(f"  {h['company_name']:40s}  qty={h['total_qty']:>8}  ltp={h['ltp']}")
        return True
    except (ValueError, FileNotFoundError) as e:
        print(f"✗ Configuration error: {e}")
        return False
    except json.JSONDecodeError as e:
        print(f"✗ Unexpected response format (JSON decode failed): {e}")
        if raw is not None:
            print(f"  Raw response (first 500 chars): {raw[:500]}")
        return False
    except KeyError as e:
        print(f"✗ Unexpected holdings response schema — missing key: {e}")
        if raw is not None:
            _dump_response_shape(raw)
        return False
    except Exception as e:  # Broad catch: Nuvama SDK may raise non-standard exceptions (e.g. network error, internal SDK error); connectivity check must not crash
        print(f"✗ Nuvama connectivity check failed: {e}")
        return False


def _dump_response_shape(raw: str) -> None:
    """Print the top-level keys (and one level deeper) of a JSON response.

    Used to diagnose schema mismatches without exposing full payload in logs.
    """
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            print(f"  Response top-level keys: {list(data.keys())}")
            for k, v in data.items():
                if isinstance(v, dict):
                    print(f"  '{k}' keys: {list(v.keys())}")
                elif isinstance(v, list):
                    print(f"  '{k}': list of {len(v)} item(s)")
        else:
            print(
                f"  Response is not a dict — type: {type(data).__name__}, value: {str(data)[:200]}"
            )
    except Exception:  # Diagnostic helper — silently swallow json.loads failures; never let shape-dumping crash the caller
        print(f"  Raw response (first 500 chars): {raw[:500]}")


if __name__ == "__main__":
    ok = verify()
    # os._exit bypasses atexit and threading cleanup — necessary to kill the SDK's
    # background Feed thread, which is non-daemon and would otherwise keep the
    # process alive indefinitely. Same pattern as nuvama_login.py.
    os._exit(0 if ok else 1)
