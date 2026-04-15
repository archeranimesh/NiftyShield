"""Probe the full field schema of Nuvama Holdings() rmsHdg records.

Prints every key/value in every holding record so we know what fields
are available for building the Nuvama bond module.

Usage:
    python -m scripts.probe_nuvama_schema
"""

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Suppress APIConnect's module-level basicConfig
logging.root.addHandler(logging.NullHandler())

try:
    from APIConnect.APIConnect import APIConnect  # type: ignore[import]
except ImportError:
    print("✗ APIConnect not installed. Run: .venv/bin/pip install APIConnect")
    raise SystemExit(1)

NUVAMA_CONF_FILE = "data/nuvama/settings.ini"


def main() -> None:
    load_dotenv()
    api_key = os.getenv("NUVAMA_API_KEY", "").strip()
    api_secret = os.getenv("NUVAMA_API_SECRET", "").strip()
    settings = os.getenv("NUVAMA_SETTINGS_FILE", "data/nuvama/settings.json")

    if not api_key or not api_secret:
        print("✗ NUVAMA_API_KEY / NUVAMA_API_SECRET missing from .env")
        raise SystemExit(1)

    session_dir = Path(settings).resolve().parent
    conf_path = Path(NUVAMA_CONF_FILE).resolve()
    conf_arg: str | None = str(conf_path) if conf_path.exists() else None

    original = Path.cwd()
    os.chdir(session_dir)
    try:
        api = APIConnect(api_key, api_secret, "", False, conf_arg)
    finally:
        os.chdir(original)

    raw = api.Holdings()
    data = json.loads(raw)

    # Try both known response paths
    try:
        records = data["resp"]["data"]["rmsHdg"]
    except KeyError:
        records = data.get("eq", {}).get("data", {}).get("rmsHdg", [])

    print(f"\nTotal holdings: {len(records)}")
    print("=" * 60)

    for i, r in enumerate(records):
        print(f"\n[{i}] {r.get('cpName', '?')}")
        for k, v in sorted(r.items()):
            print(f"     {k!r:30s} = {v!r}")

    # Also dump top-level response keys for diagnostics
    print("\n\n=== Raw response top-level keys ===")
    print(f"  {sorted(data.keys())}")
    try:
        print(f"  resp.keys = {sorted(data['resp'].keys())}")
        print(f"  resp.data.keys = {sorted(data['resp']['data'].keys())}")
    except (KeyError, AttributeError):
        pass

    os._exit(0)


if __name__ == "__main__":
    main()
