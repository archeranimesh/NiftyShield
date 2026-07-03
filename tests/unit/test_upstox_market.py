"""Tests for src/client/upstox_market.py logging migration (BUG-010 B010.2).

Covers: logger is a structlog logger (not bare stdlib), and the
non-numeric-Greek warning path still fires safely with the new
keyword-argument event shape. No network access.
"""

from __future__ import annotations

import logging

import structlog

from src.client import upstox_market
from src.client.upstox_market import _safe_decimal_greek


def test_module_logger_is_structlog_not_stdlib() -> None:
    """Happy path: module logger must be a structlog logger, per LOGGING.md.

    Regression guard for BUG-010 B010.2 — a bare stdlib
    `logging.getLogger(__name__)` renders with no timestamp/level/module
    tag once `setup_logging()` sets the stdlib root formatter to
    `"%(message)s"`. `structlog.stdlib.get_logger` must be used instead.
    """
    assert not isinstance(upstox_market.logger, logging.Logger)
    # BoundLoggerLazyProxy / BoundLogger — either is a valid structlog handle.
    assert "structlog" in type(upstox_market.logger).__module__


def test_safe_decimal_greek_non_numeric_logs_warning_event() -> None:
    """Edge case: non-numeric Greek value still warns and returns None safely.

    Also confirms the migrated call site uses a dot-namespaced event name
    with keyword args (`greek.non_numeric_value value=...`) instead of the
    old `%r`-style stdlib message, per LOGGING.md event-naming convention.
    Uses `structlog.testing.capture_logs()` (self-contained, no global
    `structlog.configure()` mutation) to avoid leaking config into other
    test modules run in the same process.
    """
    with structlog.testing.capture_logs() as captured:
        result = _safe_decimal_greek("not-a-number")

    assert result is None
    events = [e for e in captured if e.get("event") == "greek.non_numeric_value"]
    assert events, f"expected a 'greek.non_numeric_value' warning, got {captured}"
    assert events[0]["log_level"] == "warning"
    assert events[0]["value"] == repr("not-a-number")
