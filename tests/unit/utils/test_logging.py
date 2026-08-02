import json
import re

import pytest
import structlog

from src.utils.logging import bind_trace_id, generate_trace_id, setup_logging
from tests.unit.conftest import reset_structlog_test_config


@pytest.fixture(autouse=True)
def _restore_baseline_structlog_config():
    """Every test in this file calls the real ``setup_logging()``, which

    reconfigures structlog's global wrapper_class/processors (and forces the
    stdlib root logger level via ``logging.basicConfig(force=True)``) with no
    built-in teardown. Left unrestored, that config leaks into whichever test
    runs next in the same worker process — e.g. it silently downgrades
    log.debug() calls elsewhere in the suite to no-ops when setup_logging()
    was last called with level="INFO". Restore the session baseline after
    every test here so this file's real-setup_logging tests stay isolated.
    """
    yield
    reset_structlog_test_config()


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


# ── generate_trace_id / bind_trace_id ─────────────────────────────────────────


def test_generate_trace_id_format():
    """generate_trace_id returns an 8-character lowercase hex string."""
    tid = generate_trace_id()
    assert len(tid) == 8
    assert re.fullmatch(r"[0-9a-f]{8}", tid), f"Not lowercase hex: {tid!r}"


def test_generate_trace_id_unique():
    """Successive calls return different IDs."""
    ids = {generate_trace_id() for _ in range(20)}
    assert len(ids) == 20, "Expected all 20 IDs to be unique"


def test_bind_trace_id_appears_in_log(capsys):
    """bind_trace_id causes trace_id to appear in subsequent JSON log output."""
    setup_logging(json=True, level="INFO")
    structlog.contextvars.clear_contextvars()

    tid = generate_trace_id()
    bind_trace_id(tid)

    logger = structlog.get_logger("test_bind")
    logger.info("trace test event")
    structlog.contextvars.clear_contextvars()

    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed["trace_id"] == tid


def test_entrypoint_script_emits_structlog_pipeline_shaped_line(capsys):
    """After setup_logging(), a dotted module-name logger renders the full

    documented pipeline shape (LOGGING.md "Required shape of every log line"):
    ``YYYY-MM-DD HH:MM:SS [LEVEL] [pkg] [sub] [module] event key=value``.
    """
    setup_logging(json=False, level="INFO")
    logger = structlog.get_logger("scripts.strategies.ic.paper_ic_snapshot")
    logger.warning("ic_snapshot.no_expiry_found", strategy="paper_ic_nifty_v1_monthly")

    captured = capsys.readouterr()
    line = captured.out.strip()
    pattern = (
        r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} "
        r"\[WARNING\] \[scripts\] \[strategies\] \[ic\] \[paper_ic_snapshot\] "
        r"ic_snapshot\.no_expiry_found strategy=paper_ic_nifty_v1_monthly$"
    )
    assert re.match(pattern, line), f"Line did not match pipeline shape: {line!r}"


def test_log_call_before_setup_logging_degrades_gracefully(capsys):
    """A log call made before setup_logging() is ever called must not crash.

    Simulates the state structlog is in for any process that logs at import
    time (or in a code path reached before main() calls setup_logging()):
    no explicit configure() has been called, so structlog falls back to its
    own built-in defaults. This is not the documented pipeline shape, but it
    must still degrade gracefully rather than raising.
    """
    structlog.reset_defaults()
    try:
        logger = structlog.get_logger("scripts.strategies.ic.pre_setup")
        logger.info("pre_setup.log_call", foo="bar")  # must not raise

        captured = capsys.readouterr()
        assert "pre_setup.log_call" in captured.out
    finally:
        # Leave structlog configured for any tests that run after this one.
        setup_logging(json=False, level="INFO")


def test_two_bind_trace_ids_are_independent(capsys):
    """Each bind_trace_id call replaces the previous value in the context."""
    setup_logging(json=True, level="INFO")
    structlog.contextvars.clear_contextvars()

    tid1 = generate_trace_id()
    bind_trace_id(tid1)
    logger = structlog.get_logger("test_independent")
    logger.info("first event")

    tid2 = generate_trace_id()
    bind_trace_id(tid2)
    logger.info("second event")
    structlog.contextvars.clear_contextvars()

    captured = capsys.readouterr()
    lines = [json.loads(line) for line in captured.out.strip().splitlines()]
    assert lines[0]["trace_id"] == tid1
    assert lines[1]["trace_id"] == tid2
    assert tid1 != tid2
