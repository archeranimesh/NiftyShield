import pytest
import structlog

# Vars that can leak into os.environ across tests: several scripts/ modules
# (e.g. scripts/morning_signal.py, scripts/healthcheck.py,
# scripts/strategies/three_track/paper_3track_roll.py) call dotenv's
# load_dotenv() unconditionally at import time, which writes the real .env
# values straight into os.environ. monkeypatch cannot undo that mutation
# later (it only reverts changes it made itself), so once one test's import
# triggers load_dotenv(), a real TELEGRAM_BOT_TOKEN/CHAT_ID can leak into
# whichever test runs next in the same pytest-xdist worker and cause
# build_notifier() (src/notifications/telegram.py) to build a live notifier
# instead of the None a test expects in isolation — sending a real Telegram
# message. Placed here (not per-file, e.g. tests/unit/test_notifications.py
# previously) so every test in every worker is covered regardless of which
# script happened to be imported first.
_TELEGRAM_ENV_VARS = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_MESSAGE_BUDGET"]


def reset_structlog_test_config() -> None:
    """Restore the baseline structlog config tests are expected to run under.

    Exposed as a standalone function (not just the session fixture below) so
    any test that intentionally mutates global structlog/logging state via a
    real ``setup_logging()`` call (e.g. tests/unit/utils/test_logging.py) can
    restore this baseline in its own teardown, instead of leaking its config
    into whichever test runs next in the same worker process.
    """
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.render_to_log_kwargs,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )


@pytest.fixture(scope="session", autouse=True)
def configure_structlog():
    reset_structlog_test_config()


@pytest.fixture(autouse=True)
def clean_telegram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent Telegram env var leakage between tests — dotenv writes to os.environ globally."""
    for var in _TELEGRAM_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def _clear_structlog_contextvars():
    """Clear structlog contextvars before and after every test.

    ``bind_trace_id`` (src/utils/logging.py) binds to structlog's global
    contextvars store, which is process-wide and outlives any single test.
    Production code paths that call it (e.g. src/strategy/monitor.py,
    src/strategy/executor.py) have no reason to clear it themselves — that's
    a test-isolation concern, not a runtime one. Without this fixture, a
    trace_id bound by one test's exercised code leaks into whichever test
    runs next in the same worker process and shows up unexpectedly in that
    test's captured log output (e.g. tests/unit/utils/test_logging.py's
    pipeline-shape assertion).
    """
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()
