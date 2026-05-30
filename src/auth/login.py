"""OAuth login flow for Upstox API. Opens browser, captures auth code, exchanges for token."""

import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import upstox_client
from dotenv import load_dotenv

from src.config import settings

load_dotenv()

API_KEY = settings.upstox_api_key
API_SECRET = settings.upstox_api_secret
REDIRECT_URI = settings.upstox_redirect_uri

AUTH_URL = (
    f"https://api.upstox.com/v2/login/authorization/dialog"
    f"?client_id={API_KEY}"
    f"&redirect_uri={REDIRECT_URI}"
    f"&response_type=code"
)


def capture_auth_code() -> str | None:
    """Open browser for Upstox login, listen for redirect with auth code."""
    auth_code = None

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal auth_code
            query = parse_qs(urlparse(self.path).query)
            auth_code = query.get("code", [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Login successful. You can close this tab.")

        def log_message(self, *args):
            pass

    server = HTTPServer(("localhost", 8000), CallbackHandler)
    print("Opening browser for Upstox login...")
    webbrowser.open(AUTH_URL)
    server.handle_request()
    server.server_close()
    return auth_code


def exchange_code_for_token(auth_code: str) -> str:
    """Exchange authorization code for access token using Upstox SDK."""
    api = upstox_client.LoginApi()
    response = api.token(
        api_version="2.0",
        code=auth_code,
        client_id=API_KEY,
        client_secret=API_SECRET,
        redirect_uri=REDIRECT_URI,
        grant_type="authorization_code",
    )
    return response.access_token


def save_token(token: str):
    """Append access token to .env file."""
    with open(".env") as f:
        content = f.read()

    # Ensure file ends with newline
    if content and not content.endswith("\n"):
        content += "\n"

    # Remove existing token line if present
    lines = content.splitlines(keepends=True)
    lines = [line for line in lines if not line.startswith("UPSTOX_ACCESS_TOKEN=")]

    lines.append(f"UPSTOX_ACCESS_TOKEN={token}\n")

    with open(".env", "w") as f:
        f.writelines(lines)


def main():
    auth_code = capture_auth_code()
    if not auth_code:
        print("ERROR: No authorization code received.")
        return

    print(f"Auth code received: {auth_code[:10]}...")

    token = exchange_code_for_token(auth_code)
    print(f"Access token: {token[:20]}...")

    save_token(token)
    print("Token saved to .env. Login complete.")


if __name__ == "__main__":
    main()
