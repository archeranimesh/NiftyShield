"""No-network tests for the S5.5d signal_report Telegram digest."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts import signal_report

_FMT = signal_report._format_report_message


def test_format_report_message_wraps_in_fenced_block() -> None:
    msg = _FMT("Signal Pipeline Performance Report\nOVERALL: 5 trades")
    assert msg.startswith("```\n")
    assert msg.endswith("\n```")
    assert "OVERALL: 5 trades" in msg


def test_format_report_message_escapes_fence_reserved_chars() -> None:
    msg = _FMT("path C:\\x and `code`")
    assert "\\\\x" in msg
    assert "\\`code\\`" in msg


def test_notify_no_notifier_configured_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(signal_report, "build_notifier", lambda: None)
    # Must not raise when no notifier is configured.
    signal_report._notify("some report body")


def test_notify_send_failure_is_non_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Boom:
        async def send(self, _msg: str) -> None:
            raise RuntimeError("telegram down")

    monkeypatch.setattr(signal_report, "build_notifier", lambda: _Boom())
    # Logged and swallowed — no exception past the caller.
    signal_report._notify("some report body")
