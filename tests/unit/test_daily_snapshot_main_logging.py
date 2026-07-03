"""Tests for scripts/portfolio/daily_snapshot.py::main() structured-logging.

BUG-010 / B010.4: main() used to emit bespoke `[timestamp] message` bracket-format
print() lines instead of routing through the shared structlog pipeline. These tests
confirm the three branches now emit structured events instead, per LOGGING.md.

Fully offline: _historical_main and asyncio.run(_async_main(...)) are monkeypatched
out so no DB/network access occurs.
"""

from __future__ import annotations

from datetime import date

import structlog

from scripts.portfolio import daily_snapshot


def test_historical_date_arg_logs_structured_event(monkeypatch, capsys) -> None:
    """Happy-path: --date branch logs daily_snapshot.historical_query, not a print()."""
    monkeypatch.setattr("sys.argv", ["daily_snapshot", "--date", "2026-07-01"])
    monkeypatch.setattr(daily_snapshot, "_historical_main", lambda snap_date, db_path: 0)

    with structlog.testing.capture_logs() as logs:
        result = daily_snapshot.main()

    assert result == 0
    events = [entry["event"] for entry in logs]
    assert "daily_snapshot.historical_query" in events
    entry = next(e for e in logs if e["event"] == "daily_snapshot.historical_query")
    assert entry["snap_date"] == "2026-07-01"
    # No bespoke bracket-timestamp text should be printed to stdout anymore.
    assert "] Historical P&L query" not in capsys.readouterr().out


def test_market_holiday_logs_structured_event_and_skips(monkeypatch, capsys) -> None:
    """Edge-case: holiday branch logs daily_snapshot.market_holiday_skip and returns 0
    without ever reaching the live-snapshot asyncio path."""
    monkeypatch.setattr("sys.argv", ["daily_snapshot"])
    monkeypatch.setattr(daily_snapshot, "is_trading_day", lambda d: False)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("_async_main should not run on a market holiday")

    monkeypatch.setattr(daily_snapshot, "_async_main", _fail_if_called)

    with structlog.testing.capture_logs() as logs:
        result = daily_snapshot.main()

    assert result == 0
    events = [entry["event"] for entry in logs]
    assert "daily_snapshot.market_holiday_skip" in events
    entry = next(e for e in logs if e["event"] == "daily_snapshot.market_holiday_skip")
    assert entry["snap_date"] == date.today().isoformat()
    assert "] Market holiday" not in capsys.readouterr().out
