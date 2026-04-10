"""Unit tests for src/auth/nuvama_login.py.

All tests are fully offline — APIConnect is patched at module level.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.auth.nuvama_login import (
    build_login_url,
    extract_request_id,
    initialize_session,
    save_settings_path,
    login,
    LOGIN_URL,
    NUVAMA_CONF_FILE,
)

# Env vars that can leak across tests if dotenv loads into os.environ
_NUVAMA_ENV_VARS = ["NUVAMA_API_KEY", "NUVAMA_API_SECRET", "NUVAMA_SETTINGS_FILE"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Prevent env var leakage between tests — dotenv writes to os.environ globally."""
    for var in _NUVAMA_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# build_login_url
# ---------------------------------------------------------------------------

def test_build_login_url_embeds_api_key():
    url = build_login_url("TEST_KEY_123")
    assert "api_key=TEST_KEY_123" in url
    assert "nuvamawealth.com" in url


def test_build_login_url_format():
    url = build_login_url("abc")
    assert url == LOGIN_URL.format(api_key="abc")


# ---------------------------------------------------------------------------
# extract_request_id
# ---------------------------------------------------------------------------

def test_extract_request_id_from_full_url():
    redirect = "https://127.0.0.1/?request_id=REQ_TOKEN_XYZ&status=ok"
    assert extract_request_id(redirect) == "REQ_TOKEN_XYZ"


def test_extract_request_id_from_url_first_param():
    redirect = "https://127.0.0.1/?request_id=TOKEN_FIRST"
    assert extract_request_id(redirect) == "TOKEN_FIRST"


def test_extract_request_id_bare_token():
    assert extract_request_id("REQ_TOKEN_BARE") == "REQ_TOKEN_BARE"


def test_extract_request_id_strips_whitespace():
    assert extract_request_id("  REQ_WITH_SPACES  ") == "REQ_WITH_SPACES"


def test_extract_request_id_bare_token_with_whitespace():
    redirect = "  https://127.0.0.1/?request_id=TOKEN_WS  "
    assert extract_request_id(redirect) == "TOKEN_WS"


# ---------------------------------------------------------------------------
# initialize_session — patched at module level
# ---------------------------------------------------------------------------

def test_initialize_session_calls_apiconnect_with_conf_not_session(tmp_path):
    # SDK's conf arg must be the INI conf file, not the JSON session destination.
    # download_contract defaults to False — instruments.zip must not be downloaded on auth.
    settings_file = str(tmp_path / "session.json")
    conf_file = str(tmp_path / "settings.ini")
    mock_instance = MagicMock()
    mock_cls = MagicMock(return_value=mock_instance)

    with patch("src.auth.nuvama_login.APIConnect", mock_cls):
        result = initialize_session("KEY", "SECRET", "REQ123", settings_file, _conf_file=conf_file)

    # 4th arg is download_contract — must default to False.
    # 5th arg is the absolute conf path — must NOT be the JSON session file.
    call_args = mock_cls.call_args[0]
    assert call_args[:3] == ("KEY", "SECRET", "REQ123")
    assert call_args[3] is False, "download_contract must default to False"
    assert call_args[4].endswith("settings.ini"), "conf must be the INI file"
    assert call_args[4] != settings_file
    assert result is mock_instance


def test_initialize_session_creates_conf_parent_dir(tmp_path):
    settings_file = str(tmp_path / "session.json")
    conf_file = str(tmp_path / "nested" / "deep" / "settings.ini")
    mock_cls = MagicMock(return_value=MagicMock())

    with patch("src.auth.nuvama_login.APIConnect", mock_cls):
        initialize_session("KEY", "SECRET", "REQ", settings_file, _conf_file=conf_file)

    assert Path(conf_file).parent.exists()


def test_initialize_session_creates_global_stub_conf_file(tmp_path):
    # SDK reads the conf with configparser and accesses conf['GLOBAL'] during logger init.
    # An absent or empty file causes KeyError: 'GLOBAL'. initialize_session pre-seeds
    # the INI conf file (NOT the JSON session file) with a [GLOBAL] stub.
    settings_file = str(tmp_path / "session.json")
    conf_file = str(tmp_path / "settings.ini")
    mock_cls = MagicMock(return_value=MagicMock())

    assert not Path(conf_file).exists()
    with patch("src.auth.nuvama_login.APIConnect", mock_cls):
        initialize_session("KEY", "SECRET", "REQ", settings_file, _conf_file=conf_file)

    content = Path(conf_file).read_text()
    assert "[GLOBAL]" in content
    assert "[STREAM]" in content
    assert "[PROXY]" in content
    assert "LOG_FILE = logs/apiconnect.log" in content


def test_initialize_session_does_not_overwrite_existing_conf(tmp_path):
    # If the INI conf already exists from a prior login, don't clobber it.
    settings_file = str(tmp_path / "session.json")
    conf_file = tmp_path / "settings.ini"
    conf_file.write_text("[GLOBAL]\nLOG_LEVEL = INFO\n")
    mock_cls = MagicMock(return_value=MagicMock())

    with patch("src.auth.nuvama_login.APIConnect", mock_cls):
        initialize_session("KEY", "SECRET", "REQ", str(settings_file), _conf_file=str(conf_file))

    assert conf_file.read_text() == "[GLOBAL]\nLOG_LEVEL = INFO\n"


def test_initialize_session_creates_logs_dir_before_apiconnect(tmp_path):
    # Regression: APIConnect resolves LOG_FILE = logs/apiconnect.log relative to CWD
    # (which _in_dir sets to session_dir). If session_dir/logs/ does not exist the SDK
    # raises FileNotFoundError before returning. initialize_session must pre-create it.
    settings_file = str(tmp_path / "session.json")
    conf_file = str(tmp_path / "settings.ini")
    logs_dir = tmp_path / "logs"

    captured = {}

    def capturing_apiconnect(*args, **kwargs):
        # At call time, CWD is session_dir (tmp_path). Check logs/ exists there.
        captured["logs_exists"] = (Path.cwd() / "logs").exists()
        return MagicMock()

    with patch("src.auth.nuvama_login.APIConnect", side_effect=capturing_apiconnect):
        initialize_session("KEY", "SECRET", "REQ", settings_file, _conf_file=conf_file)

    assert captured.get("logs_exists"), "logs/ must exist inside session_dir before APIConnect init"


def test_initialize_session_passes_download_contract_true(tmp_path):
    # Caller can opt in to instrument download when explicitly needed.
    settings_file = str(tmp_path / "session.json")
    conf_file = str(tmp_path / "settings.ini")
    mock_cls = MagicMock(return_value=MagicMock())

    with patch("src.auth.nuvama_login.APIConnect", mock_cls):
        initialize_session("KEY", "SECRET", "REQ", settings_file, download_contract=True, _conf_file=conf_file)

    assert mock_cls.call_args[0][3] is True


def test_initialize_session_does_not_pass_json_session_as_conf(tmp_path):
    # Regression: NUVAMA_SETTINGS_FILE pointing to existing JSON session (from a prior
    # login) must NOT be forwarded to APIConnect as conf — configparser raises
    # MissingSectionHeaderError on JSON content.
    session_file = tmp_path / "data_KEY.txt"
    session_file.write_text('{"vt": "token", "auth": "hash"}')  # JSON, not INI
    conf_file = str(tmp_path / "settings.ini")
    mock_cls = MagicMock(return_value=MagicMock())

    with patch("src.auth.nuvama_login.APIConnect", mock_cls):
        initialize_session("KEY", "SECRET", "REQ", str(session_file), _conf_file=conf_file)

    call_conf_arg = mock_cls.call_args[0][4]
    assert call_conf_arg.endswith("settings.ini"), "SDK must receive INI conf path, not JSON session file"
    assert call_conf_arg != str(session_file)
    # download_contract must still be False
    assert mock_cls.call_args[0][3] is False


# ---------------------------------------------------------------------------
# save_settings_path
# ---------------------------------------------------------------------------

def test_save_settings_path_writes_key(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("NUVAMA_API_KEY=abc\n")

    save_settings_path(env_path, "/some/path/settings.json")

    content = env_path.read_text()
    assert "NUVAMA_SETTINGS_FILE" in content
    assert "/some/path/settings.json" in content


def test_save_settings_path_upserts_existing_key(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text('NUVAMA_SETTINGS_FILE="old/path.json"\n')

    save_settings_path(env_path, "new/path.json")

    content = env_path.read_text()
    assert "new/path.json" in content
    assert content.count("NUVAMA_SETTINGS_FILE") == 1


# ---------------------------------------------------------------------------
# login (full flow)
# ---------------------------------------------------------------------------

def test_login_raises_if_api_key_missing(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("NUVAMA_API_SECRET=secret\n")

    with pytest.raises(ValueError, match="NUVAMA_API_KEY"):
        login(env_path)


def test_login_raises_if_api_secret_missing(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("NUVAMA_API_KEY=key\n")

    with pytest.raises(ValueError, match="NUVAMA_API_SECRET"):
        login(env_path)


def test_login_raises_if_empty_input(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("NUVAMA_API_KEY=key\nNUVAMA_API_SECRET=secret\n")

    monkeypatch.setattr("builtins.input", lambda _: "")

    with patch("webbrowser.open"):
        with pytest.raises(ValueError, match="login aborted"):
            login(env_path)


def test_login_full_flow(tmp_path, monkeypatch):
    settings_file = str(tmp_path / "nuvama" / "settings.json")
    env_path = tmp_path / ".env"
    env_path.write_text(
        f"NUVAMA_API_KEY=MYKEY\nNUVAMA_API_SECRET=MYSECRET\n"
        f"NUVAMA_SETTINGS_FILE={settings_file}\n"
    )

    redirect_url = "https://127.0.0.1/?request_id=REQ_FULL_FLOW"
    monkeypatch.setattr("builtins.input", lambda _: redirect_url)

    mock_init = MagicMock()
    mock_save = MagicMock()

    # os._exit(0) at the end of login() would terminate the pytest process outright.
    # Patch it to raise SystemExit so it stays within the test boundary.
    with patch("os._exit", side_effect=SystemExit(0)):
        with patch("webbrowser.open") as mock_browser:
            with patch("src.auth.nuvama_login.initialize_session", mock_init):
                with patch("src.auth.nuvama_login.save_settings_path", mock_save):
                    with pytest.raises(SystemExit):
                        login(env_path)

    mock_browser.assert_called_once()
    mock_init.assert_called_once_with("MYKEY", "MYSECRET", "REQ_FULL_FLOW", settings_file)
    mock_save.assert_called_once_with(env_path, settings_file)
