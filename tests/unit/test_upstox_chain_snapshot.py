"""Tests for scripts/upstox_chain_snapshot.py — EOD chain snapshot cron.

All tests are fully offline. No network, no file I/O, no .env required.
Mocks: is_trading_day, InstrumentLookup, UpstoxMarketClient,
       parse_upstox_option_chain, ChainWriter.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.upstox_chain_snapshot import main
from src.client.exceptions import DataFetchError

# ── Shared fixtures ───────────────────────────────────────────────────────────

THREE_EXPIRIES = [
    ("monthly", "2026-06-26"),
    ("quarterly", "2026-09-24"),
    ("yearly", "2026-12-31"),
]

_SCRIPT_MODULE = "scripts.upstox_chain_snapshot"


def _make_mock_chain(n_strikes: int = 3) -> MagicMock:
    """Return a mock OptionChain with n_strikes strikes."""
    chain = MagicMock()
    chain.strikes = {f"strike_{i}": MagicMock() for i in range(n_strikes)}
    return chain


def _make_mock_lookup(expiries: list) -> MagicMock:
    """Return a mock InstrumentLookup whose get_expiry_candidates returns expiries."""
    lookup = MagicMock()
    lookup.get_expiry_candidates.return_value = expiries
    return lookup


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_holiday_guard_exits_clean() -> None:
    """Non-trading day: main() == 0 and no chain fetch is called."""
    with (
        patch(f"{_SCRIPT_MODULE}.is_trading_day", return_value=False) as mock_is_td,
        patch(f"{_SCRIPT_MODULE}.InstrumentLookup") as mock_lu,
        patch(f"{_SCRIPT_MODULE}.UpstoxMarketClient") as mock_client_cls,
        patch(f"{_SCRIPT_MODULE}.ChainWriter"),
    ):
        result = main()

    assert result == 0
    mock_is_td.assert_called_once()
    mock_lu.from_file.assert_not_called()
    mock_client_cls.return_value.get_option_chain_sync.assert_not_called()


def test_happy_path_three_expiries() -> None:
    """Trading day with 3 expiries: write_eod_snapshot called 3×, returns 0."""
    mock_chain = _make_mock_chain(n_strikes=5)
    mock_lookup = _make_mock_lookup(THREE_EXPIRIES)
    written_path = Path("/tmp/some/upstox_2026-06-26.parquet")

    with (
        patch(f"{_SCRIPT_MODULE}.is_trading_day", return_value=True),
        patch(f"{_SCRIPT_MODULE}.InstrumentLookup") as mock_lu_cls,
        patch(f"{_SCRIPT_MODULE}.UpstoxMarketClient") as mock_client_cls,
        patch(f"{_SCRIPT_MODULE}.parse_upstox_option_chain", return_value=mock_chain),
        patch(f"{_SCRIPT_MODULE}.ChainWriter") as mock_writer_cls,
    ):
        mock_lu_cls.from_file.return_value = mock_lookup
        mock_writer_cls.return_value.write_eod_snapshot.return_value = written_path

        result = main()

    assert result == 0
    assert mock_writer_cls.return_value.write_eod_snapshot.call_count == 3
    mock_client_cls.return_value.get_option_chain_sync.assert_called()
    assert mock_client_cls.return_value.get_option_chain_sync.call_count == 3


def test_single_expiry_failure_continues() -> None:
    """First expiry raises DataFetchError; remaining 2 succeed; returns 0."""
    mock_chain = _make_mock_chain()
    mock_lookup = _make_mock_lookup(THREE_EXPIRIES)

    client_side_effects = [
        DataFetchError("timeout"),
        {"data": "ok"},
        {"data": "ok"},
    ]

    with (
        patch(f"{_SCRIPT_MODULE}.is_trading_day", return_value=True),
        patch(f"{_SCRIPT_MODULE}.InstrumentLookup") as mock_lu_cls,
        patch(f"{_SCRIPT_MODULE}.UpstoxMarketClient") as mock_client_cls,
        patch(f"{_SCRIPT_MODULE}.parse_upstox_option_chain", return_value=mock_chain),
        patch(f"{_SCRIPT_MODULE}.ChainWriter") as mock_writer_cls,
    ):
        mock_lu_cls.from_file.return_value = mock_lookup
        mock_client_cls.return_value.get_option_chain_sync.side_effect = client_side_effects
        mock_writer_cls.return_value.write_eod_snapshot.return_value = Path("/tmp/x.parquet")

        result = main()

    assert result == 0
    # Only 2 successful writes (first expiry failed before write)
    assert mock_writer_cls.return_value.write_eod_snapshot.call_count == 2


def test_all_expiries_fail_returns_one() -> None:
    """All three fetches raise; main() returns 1."""
    mock_lookup = _make_mock_lookup(THREE_EXPIRIES)

    with (
        patch(f"{_SCRIPT_MODULE}.is_trading_day", return_value=True),
        patch(f"{_SCRIPT_MODULE}.InstrumentLookup") as mock_lu_cls,
        patch(f"{_SCRIPT_MODULE}.UpstoxMarketClient") as mock_client_cls,
        patch(f"{_SCRIPT_MODULE}.parse_upstox_option_chain"),
        patch(f"{_SCRIPT_MODULE}.ChainWriter") as mock_writer_cls,
    ):
        mock_lu_cls.from_file.return_value = mock_lookup
        mock_client_cls.return_value.get_option_chain_sync.side_effect = DataFetchError("all down")

        result = main()

    assert result == 1
    mock_writer_cls.return_value.write_eod_snapshot.assert_not_called()


def test_fewer_than_three_expiries_ok() -> None:
    """get_expiry_candidates returns 2; write called 2×; returns 0."""
    two_expiries = [
        ("monthly", "2026-06-26"),
        ("quarterly", "2026-09-24"),
    ]
    mock_chain = _make_mock_chain()
    mock_lookup = _make_mock_lookup(two_expiries)

    with (
        patch(f"{_SCRIPT_MODULE}.is_trading_day", return_value=True),
        patch(f"{_SCRIPT_MODULE}.InstrumentLookup") as mock_lu_cls,
        patch(f"{_SCRIPT_MODULE}.UpstoxMarketClient"),
        patch(f"{_SCRIPT_MODULE}.parse_upstox_option_chain", return_value=mock_chain),
        patch(f"{_SCRIPT_MODULE}.ChainWriter") as mock_writer_cls,
    ):
        mock_lu_cls.from_file.return_value = mock_lookup
        mock_writer_cls.return_value.write_eod_snapshot.return_value = Path("/tmp/x.parquet")

        result = main()

    assert result == 0
    assert mock_writer_cls.return_value.write_eod_snapshot.call_count == 2


def test_snapshot_ts_is_utc_aware() -> None:
    """snapshot_ts passed to write_eod_snapshot is timezone-aware UTC."""
    mock_chain = _make_mock_chain(n_strikes=2)
    mock_lookup = _make_mock_lookup(THREE_EXPIRIES[:1])  # one expiry is enough

    with (
        patch(f"{_SCRIPT_MODULE}.is_trading_day", return_value=True),
        patch(f"{_SCRIPT_MODULE}.InstrumentLookup") as mock_lu_cls,
        patch(f"{_SCRIPT_MODULE}.UpstoxMarketClient"),
        patch(f"{_SCRIPT_MODULE}.parse_upstox_option_chain", return_value=mock_chain),
        patch(f"{_SCRIPT_MODULE}.ChainWriter") as mock_writer_cls,
    ):
        mock_lu_cls.from_file.return_value = mock_lookup
        mock_writer_cls.return_value.write_eod_snapshot.return_value = Path("/tmp/x.parquet")

        main()

    call_args = mock_writer_cls.return_value.write_eod_snapshot.call_args
    snapshot_ts: datetime = call_args[0][1]  # positional arg index 1

    assert snapshot_ts.tzinfo is not None
    assert snapshot_ts.utcoffset().total_seconds() == 0.0


def test_base_dir_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """CHAIN_SNAPSHOT_DIR env var is passed to ChainWriter constructor."""
    custom_dir = "/tmp/test_chain_snapshots"
    monkeypatch.setenv("CHAIN_SNAPSHOT_DIR", custom_dir)

    mock_chain = _make_mock_chain()
    mock_lookup = _make_mock_lookup(THREE_EXPIRIES[:1])

    with (
        patch(f"{_SCRIPT_MODULE}.is_trading_day", return_value=True),
        patch(f"{_SCRIPT_MODULE}.InstrumentLookup") as mock_lu_cls,
        patch(f"{_SCRIPT_MODULE}.UpstoxMarketClient"),
        patch(f"{_SCRIPT_MODULE}.parse_upstox_option_chain", return_value=mock_chain),
        patch(f"{_SCRIPT_MODULE}.ChainWriter") as mock_writer_cls,
    ):
        mock_lu_cls.from_file.return_value = mock_lookup
        mock_writer_cls.return_value.write_eod_snapshot.return_value = Path("/tmp/x.parquet")

        main()

    mock_writer_cls.assert_called_once_with(custom_dir)


def test_log_output_includes_expiry_and_rows(
    capsys,
) -> None:
    """INFO log entry per expiry includes expiry date and row count."""
    mock_chain = _make_mock_chain(n_strikes=4)
    mock_lookup = _make_mock_lookup(THREE_EXPIRIES)

    with (
        patch(f"{_SCRIPT_MODULE}.is_trading_day", return_value=True),
        patch(f"{_SCRIPT_MODULE}.InstrumentLookup") as mock_lu_cls,
        patch(f"{_SCRIPT_MODULE}.UpstoxMarketClient"),
        patch(
            f"{_SCRIPT_MODULE}.parse_upstox_option_chain",
            return_value=mock_chain,
        ),
        patch(f"{_SCRIPT_MODULE}.ChainWriter") as mock_writer_cls,
    ):
        mock_lu_cls.from_file.return_value = mock_lookup
        mock_writer_cls.return_value.write_eod_snapshot.return_value = Path(
            "/tmp/upstox_2026-06-26.parquet"
        )
        result = main()

    assert result == 0
    # At least one log record per expiry mentioning expiry date and rows
    captured = capsys.readouterr()
    log_text = captured.out
    for _, expiry_str in THREE_EXPIRIES:
        assert expiry_str in log_text, f"Expected expiry {expiry_str} in log"
    assert "rows=" in log_text
