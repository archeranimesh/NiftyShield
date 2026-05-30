import logging

import structlog

from src.config import settings


def add_logger_name(logger, method_name, event_dict):
    """Safely add logger name if available, without failing on PrintLogger."""
    try:
        event_dict["logger"] = logger.name
    except AttributeError:
        pass
    return event_dict


def setup_logging(*, json: bool | None = None, level: str | None = None) -> None:
    """Configure structlog for the application.

    Args:
        json: If True, emit JSON (production). If False, emit coloured console (dev).
              If None, auto-detects from UPSTOX_ENV == "prod".
        level: Log level string. If None, auto-detects from UPSTOX_DEBUG == "1" (DEBUG)
               else defaults to "INFO".
    """
    if json is None:
        json = settings.upstox_env == "prod"

    if level is None:
        level = "DEBUG" if settings.upstox_debug else "INFO"

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    if json:
        shared_processors.append(structlog.processors.format_exc_info)
        shared_processors.append(structlog.processors.JSONRenderer())
    else:
        shared_processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),  # Resolves sys.stdout dynamically at log-time
    )
