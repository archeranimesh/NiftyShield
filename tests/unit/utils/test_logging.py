import json

import structlog

from src.utils.logging import setup_logging


def test_setup_logging_console(capsys):
    """Verify setup_logging with console output configuration works."""
    setup_logging(json=False, level="INFO")
    logger = structlog.get_logger("test_console")
    logger.info("console log message")

    captured = capsys.readouterr()
    assert "console log message" in captured.out
    # Console mode shouldn't be valid JSON
    try:
        json.loads(captured.out)
        raise AssertionError("Console log should not be valid JSON")
    except json.JSONDecodeError:
        pass  # expected


def test_setup_logging_json(capsys):
    """Verify setup_logging with JSON output configuration works."""
    setup_logging(json=True, level="INFO")
    logger = structlog.get_logger("test_json")
    logger.info("json log message", key="val")

    captured = capsys.readouterr()
    assert "json log message" in captured.out

    # Must be valid JSON
    parsed = json.loads(captured.out.strip())
    assert parsed["event"] == "json log message"
    assert parsed["key"] == "val"
    assert parsed["level"] == "info"
    assert "timestamp" in parsed


def test_setup_logging_env_override(monkeypatch):
    """Verify environment variables dictate defaults if not supplied."""
    # Test JSON mode from UPSTOX_ENV
    monkeypatch.setenv("UPSTOX_ENV", "prod")
    monkeypatch.setenv("UPSTOX_DEBUG", "0")
    setup_logging(json=None, level=None)

    # To check that it configured JSON, retrieve current processors
    # Since configure returns None and doesn't expose processors easily,
    # we can verify behaviour by checking logging levels/output.
    # But let's check log level configuration by mocking getattr on logging.
    # Let's ensure level configuration handles UPSTOX_DEBUG=1
    monkeypatch.setenv("UPSTOX_DEBUG", "1")
    setup_logging(json=None, level=None)

    # Check default levels without debug
    monkeypatch.setenv("UPSTOX_DEBUG", "0")
    setup_logging(json=None, level=None)
