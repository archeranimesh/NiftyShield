"""Nuvama API Connect login flow.

Opens browser to Nuvama login URL. User logs in, browser redirects to the
callback URL (default: https://127.0.0.1/) with request_id in the address bar.
User pastes the redirect URL (or bare request_id) — this module extracts the
request_id, initializes an APIConnect session, and persists the settings file
path to .env.

Session lifetime: APIConnect persists the session token in a settings file.
Subsequent calls (e.g. nuvama_verify.py) load from settings_file directly —
no request_id needed after initial login.

Usage:
    python -m src.auth.nuvama_login
"""

import contextlib
import os
import webbrowser
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from dotenv import load_dotenv, set_key

try:
    from APIConnect.APIConnect import APIConnect  # type: ignore[import]
except ImportError:
    # In unit tests APIConnect is patched at the module level before this runs.
    # In production, a missing package should fail loudly — not silently produce None.
    APIConnect = None  # type: ignore[assignment,misc]

LOGIN_URL = "https://www.nuvamawealth.com/api-connect/login?api_key={api_key}"
DEFAULT_SETTINGS_FILE = "data/nuvama/settings.json"
# Separate INI config file for the SDK logger — never the same file as the JSON session.
# The SDK's 5th constructor arg (conf) must be INI format; the session file it writes
# is always data_{api_key}.txt and is JSON. Conflating the two causes MissingSectionHeaderError
# on any re-login after the first successful login.
NUVAMA_CONF_FILE = "data/nuvama/settings.ini"


@contextlib.contextmanager
def _in_dir(directory: Path):
    """Temporarily change CWD to directory, then restore on exit.

    The Nuvama SDK hardcodes data_{api_key}.txt relative to CWD for both reads
    and writes. Changing CWD to the desired session directory ensures the SDK
    places (and finds) its file there, with no manual move needed.

    All paths passed to code inside this context must be absolute.
    """
    original = Path.cwd()
    directory.mkdir(parents=True, exist_ok=True)
    os.chdir(directory)
    try:
        yield
    finally:
        os.chdir(original)


def build_login_url(api_key: str) -> str:
    """Build the Nuvama login URL with the API key embedded."""
    return LOGIN_URL.format(api_key=api_key)


def extract_request_id(redirect_input: str) -> str:
    """Extract request_id from a redirect URL or return the bare token as-is.

    Handles both:
    - Full redirect: "https://127.0.0.1/?request_id=abc123&..."
    - Bare token:    "abc123"
    """
    stripped = redirect_input.strip()
    parsed = urlparse(stripped)
    params = parse_qs(parsed.query)
    if "request_id" in params:
        return params["request_id"][0]
    return stripped


def initialize_session(
    api_key: str,
    api_secret: str,
    request_id: str,
    settings_file: str = DEFAULT_SETTINGS_FILE,
    download_contract: bool = False,
    _conf_file: str | None = None,
):
    """Initialize an APIConnect session and persist it to settings_file.

    The SDK constructor (APIConnect.__init__) has two logically separate concerns:
    - conf (5th arg): optional INI file for logger configuration, read by configparser.
    - session file: hardcoded as data_{api_key}.txt relative to CWD. The SDK reads and
      writes this file to restore the session token across restarts.

    We use `_in_dir` to temporarily change CWD to the directory that contains
    settings_file. This causes the SDK to read/write its session file there directly —
    no manual move needed, and no stray file left in the project root.

    The `download_contract` flag (SDK's 4th arg) controls whether the SDK downloads
    the full instrument/contract master file (instruments.zip → instruments.csv) on
    init. For auth and connectivity checks this is almost always False — downloading
    contracts is a separate, deliberate operation.

    Args:
        api_key: Nuvama API key.
        api_secret: Nuvama API secret.
        request_id: Token from the login redirect URL (only needed on first login).
        settings_file: Path for the session token file (JSON) created by the SDK.
        download_contract: Whether the SDK should download the full instrument master
            on init. Default False — instrument download is a separate concern.
        _conf_file: Override the INI conf path (defaults to NUVAMA_CONF_FILE). Intended
            for tests only — production callers should leave this as None.

    Returns:
        Initialized APIConnect instance.
    """
    if APIConnect is None:
        raise ImportError(
            "APIConnect package is not installed in this environment.\n"
            "Fix: .venv/bin/pip install APIConnect"
        )

    # Prepare the INI conf file (logger config). Keep it separate from the session file.
    conf_path = Path(_conf_file if _conf_file is not None else NUVAMA_CONF_FILE)
    conf_path.parent.mkdir(parents=True, exist_ok=True)
    if not conf_path.exists():
        config_template = (
            "[GLOBAL]\n"
            "LOG_LEVEL = DEBUG\n"
            "LOG_FILE = logs/apiconnect.log\n\n"
            "[PROXY]\n"
            "SSL_VERIFY = True\n\n"
            "[STREAM]\n"
            "HOST = ncst.nuvamawealth.com\n"
            "PORT = 9443\n"
        )
        conf_path.write_text(config_template)

    # Resolve to absolute BEFORE chdir — relative paths break after CWD changes.
    conf_abs = conf_path.resolve()
    session_dir = Path(settings_file).resolve().parent

    # Run SDK init inside the target session directory so it reads/writes
    # data_{api_key}.txt there, not in the project root.
    with _in_dir(session_dir):
        # SDK resolves LOG_FILE relative to CWD — create the logs dir before init.
        Path("logs").mkdir(exist_ok=True)
        api = APIConnect(api_key, api_secret, request_id, download_contract, str(conf_abs))

    return api


def save_settings_path(env_path: Path, settings_file: str) -> None:
    """Write NUVAMA_SETTINGS_FILE into the .env file.

    Uses dotenv set_key so it upserts without clobbering other variables.
    """
    target = env_path.resolve()
    print(f"DEBUG: Actual .env path being updated: {target}")
    set_key(str(env_path), "NUVAMA_SETTINGS_FILE", settings_file)


def login(env_path: Path = Path(".env")) -> None:
    """Full interactive login flow. Reads credentials from env_path, opens browser,
    prompts for request_id, initializes session, saves settings path.

    Args:
        env_path: Path to the .env file to read credentials from and update.

    Raises:
        ValueError: If NUVAMA_API_KEY or NUVAMA_API_SECRET are not set.
    """
    load_dotenv(env_path)

    api_key = os.getenv("NUVAMA_API_KEY", "").strip()
    api_secret = os.getenv("NUVAMA_API_SECRET", "").strip()

    if not api_key or not api_secret:
        raise ValueError(
            "NUVAMA_API_KEY and NUVAMA_API_SECRET must be set in .env before running login."
        )

    settings_file = os.getenv("NUVAMA_SETTINGS_FILE", DEFAULT_SETTINGS_FILE)

    login_url = build_login_url(api_key)
    print(f"\nOpening Nuvama login page...\n{login_url}\n")
    webbrowser.open(login_url)

    print(
        "After login you'll be redirected to your callback URL (e.g. https://127.0.0.1/)."
    )
    print(
        "Copy the full redirect URL (or just the request_id value from the address bar).\n"
    )
    redirect_input = input("Paste redirect URL or request_id: ").strip()

    if not redirect_input:
        raise ValueError("No input provided — login aborted.")

    request_id = extract_request_id(redirect_input)
    print(f"\nExtracted request_id: {request_id[:10]}...")

    initialize_session(api_key, api_secret, request_id, settings_file)

    save_settings_path(env_path, settings_file)
    print(f"\n✓ Session initialized. Settings persisted at: {settings_file}")
    print(f"✓ NUVAMA_SETTINGS_FILE written to {env_path}")
    print("\nRun 'python -m src.auth.nuvama_verify' to confirm connectivity.")
    # Force exit to kill the background Feed thread
    os._exit(0)


if __name__ == "__main__":
    login()
