import logging
import secrets
import sys

import structlog

from src.config import settings


def uppercase_level(logger, method_name, event_dict):
    """Uppercase the log level string for readability (INFO vs info)."""
    if "level" in event_dict:
        event_dict["level"] = event_dict["level"].upper()
    return event_dict


def prepend_logger_name(logger, method_name, event_dict):
    """Prepend [pkg] [sub] [module] to the event string.

    Pops the 'logger' key (set by structlog.stdlib.add_logger_name) so it
    doesn't also appear as a trailing key=value pair.
    """
    name = event_dict.pop("logger", None)
    if name:
        bracketed = " ".join(f"[{part}]" for part in name.split("."))
        event_dict["event"] = f"{bracketed} {event_dict.get('event', '')}"
    return event_dict


def plain_renderer(logger, method_name, event_dict):
    """Format a log line as: TIMESTAMP [LEVEL] event key=value ...

    Replaces ConsoleRenderer to avoid fixed-width level padding and give full
    control over the output format regardless of TTY state.
    """
    timestamp = event_dict.pop("timestamp", "")
    level = event_dict.pop("level", "")
    event = event_dict.pop("event", "")
    extras = " ".join(f"{k}={v}" for k, v in event_dict.items() if not k.startswith("_"))
    line = f"{timestamp} [{level}] {event}"
    if extras:
        line += f" {extras}"
    return line


def plain_renderer_color(logger, method_name, event_dict):
    """Coloured variant of plain_renderer for interactive TTY sessions."""
    timestamp = event_dict.pop("timestamp", "")
    level = event_dict.pop("level", "")
    event = event_dict.pop("event", "")
    extras = " ".join(f"{k}={v}" for k, v in event_dict.items() if not k.startswith("_"))

    _level_colors = {
        "DEBUG": "\033[36m",  # cyan
        "INFO": "\033[32m",  # green
        "WARNING": "\033[33m",  # yellow
        "ERROR": "\033[31m",  # red
        "CRITICAL": "\033[35m",  # magenta
    }
    reset = "\033[0m"
    color = _level_colors.get(level, "")
    line = f"\033[2m{timestamp}{reset} [{color}{level}{reset}] {event}"
    if extras:
        line += f" \033[2m{extras}{reset}"
    return line


def setup_logging(*, json: bool | None = None, level: str | None = None) -> None:
    """Configure structlog for the application.

    Uses structlog.stdlib.LoggerFactory so that logger.name is available to
    the prepend_logger_name processor (PrintLogger has no .name attribute).

    Args:
        json: If True, emit JSON. If False, plain text. If None, auto-detects
              from UPSTOX_LOG_JSON=1 (defaults to False — plain text always,
              regardless of UPSTOX_ENV).
        level: Log level string. If None, auto-detects from UPSTOX_DEBUG == "1" (DEBUG)
               else defaults to "INFO".
    """
    if json is None:
        json = settings.upstox_log_json

    if level is None:
        level = "DEBUG" if settings.upstox_debug else "INFO"

    # Route stdlib logging through structlog so third-party libraries (requests,
    # aiohttp, etc.) appear in the same format. Only WARNING+ from stdlib to avoid
    # noise from verbose third-party DEBUG output.
    # Set stdlib root logger to the same level as structlog so INFO messages
    # are not silently dropped when stdlib.LoggerFactory routes through stdlib.
    # Third-party library noise (urllib3, aiohttp, etc.) is suppressed separately.
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, level.upper(), logging.INFO),
        stream=sys.stdout,
        force=True,
    )
    for noisy_lib in ("urllib3", "aiohttp", "asyncio", "httpx"):
        logging.getLogger(noisy_lib).setLevel(logging.WARNING)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,  # requires stdlib.LoggerFactory — sets event_dict["logger"]
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        # Renders exc_info=True into a real traceback string under the "exception"
        # key. Must run in BOTH modes — previously only appended inside the `if
        # json:` branch, so any log.warning/error(..., exc_info=True) call in
        # plain/console mode (the default; see monitor_daemon.log) silently
        # dropped the traceback, printing the literal token `exc_info=True`
        # instead. Root cause of a 2026-08-10 incident where a
        # counterfactual_log_failed warning left no diagnosable exception.
        structlog.processors.format_exc_info,
    ]
    if json:
        # JSON mode: level stays lowercase (machine-readable); logger kept as separate key.
        shared_processors.append(structlog.processors.JSONRenderer())
    else:
        # Console mode: uppercase level and prepend [module] to event for human readability.
        shared_processors.append(uppercase_level)
        shared_processors.append(prepend_logger_name)
        # Color only when explicitly opted in via UPSTOX_LOG_COLOR=1.
        # sys.stdout.isatty() is unreliable under launchd/cron (pseudo-TTY
        # stays open), causing ANSI escape codes to bleed into log files.
        import os

        if os.environ.get("UPSTOX_LOG_COLOR") == "1":
            shared_processors.append(plain_renderer_color)
        else:
            shared_processors.append(plain_renderer)

    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),  # gives logger.name to processors
    )


def generate_trace_id() -> str:
    """Return a fresh 8-character hex correlation ID.

    Uses ``secrets.token_hex`` so each call is cryptographically random.

    Returns:
        8-character lowercase hex string, e.g. ``"a3f1c8b0"``.
    """
    return secrets.token_hex(4)


def bind_trace_id(trace_id: str) -> None:
    """Bind *trace_id* to the current structlog contextvars context.

    All subsequent log calls in the same async task or call stack will
    include ``trace_id=<value>`` automatically.

    Args:
        trace_id: The correlation ID to bind (typically from
            ``generate_trace_id()``).
    """
    structlog.contextvars.bind_contextvars(trace_id=trace_id)
