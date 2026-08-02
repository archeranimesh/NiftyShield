import pytest
import structlog


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
