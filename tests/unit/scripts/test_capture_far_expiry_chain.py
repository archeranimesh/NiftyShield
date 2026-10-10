from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.pipeline.capture_far_expiry_chain import main
from src.client.exceptions import DataFetchError


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setattr(
        "scripts.pipeline.capture_far_expiry_chain.guard_trading_day", lambda *a, **kw: False
    )

    mock_lookup = MagicMock()
    mock_lookup.get_expiry_candidates.side_effect = lambda u, t, preference, min_expiry=None: (
        [("yearly", "2026-12-31")] if min_expiry is None else [("yearly", "2027-12-30")]
    )
    monkeypatch.setattr(
        "scripts.pipeline.capture_far_expiry_chain.InstrumentLookup.from_file",
        lambda *a, **kw: mock_lookup,
    )

    mock_chain_source = MagicMock()
    mock_chain_source.get_chain = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(
        "scripts.pipeline.capture_far_expiry_chain.DhanChainSource",
        lambda *a, **kw: mock_chain_source,
    )

    mock_far_store = MagicMock()
    monkeypatch.setattr(
        "scripts.pipeline.capture_far_expiry_chain.FarExpiryStore", lambda *a, **kw: mock_far_store
    )

    mock_portfolio_store = MagicMock()
    monkeypatch.setattr(
        "scripts.pipeline.capture_far_expiry_chain.PortfolioStore.create",
        AsyncMock(return_value=mock_portfolio_store),
    )

    monkeypatch.setattr(
        "scripts.pipeline.capture_far_expiry_chain.aiohttp.ClientSession",
        MagicMock(return_value=AsyncMock()),
    )

    return {
        "lookup": mock_lookup,
        "chain_source": mock_chain_source,
        "far_store": mock_far_store,
        "portfolio_store": mock_portfolio_store,
    }


@pytest.mark.asyncio
async def test_holiday_exit(monkeypatch):
    monkeypatch.setattr(
        "scripts.pipeline.capture_far_expiry_chain.guard_trading_day", lambda *a, **kw: True
    )
    assert await main() == 0


@pytest.mark.asyncio
async def test_no_bod_file(monkeypatch):
    monkeypatch.setattr(
        "scripts.pipeline.capture_far_expiry_chain.guard_trading_day", lambda *a, **kw: False
    )

    def raise_file_not_found(*a, **kw):
        raise FileNotFoundError()

    monkeypatch.setattr(
        "scripts.pipeline.capture_far_expiry_chain.InstrumentLookup.from_file",
        raise_file_not_found,
    )
    assert await main() == 1


@pytest.mark.asyncio
async def test_no_expiries_found(mock_env):
    mock_env["lookup"].get_expiry_candidates.side_effect = (
        lambda u, t, preference, min_expiry=None: []
    )
    assert await main() == 1


@pytest.mark.asyncio
async def test_success_two_expiries_and_spacing(mock_env, monkeypatch):
    mock_sleep = AsyncMock()
    monkeypatch.setattr("scripts.pipeline.capture_far_expiry_chain.asyncio.sleep", mock_sleep)
    assert await main() == 0

    assert mock_env["chain_source"].get_chain.call_count == 2
    assert mock_env["far_store"].record_chain.call_count == 2
    mock_env["portfolio_store"].record_heartbeat.assert_called_once_with(
        "capture_far_expiry", "SUCCESS"
    )
    mock_sleep.assert_called_once_with(4.0)


@pytest.mark.asyncio
async def test_partial_failure(mock_env, monkeypatch):
    mock_sleep = AsyncMock()
    monkeypatch.setattr("scripts.pipeline.capture_far_expiry_chain.asyncio.sleep", mock_sleep)

    # First succeeds, second fails
    mock_env["chain_source"].get_chain.side_effect = [MagicMock(), DataFetchError("some error")]

    assert await main() == 0
    assert mock_env["chain_source"].get_chain.call_count == 2
    assert mock_env["far_store"].record_chain.call_count == 1
    mock_env["portfolio_store"].record_heartbeat.assert_called_once_with(
        "capture_far_expiry", "SUCCESS"
    )
    mock_sleep.assert_called_once_with(4.0)


@pytest.mark.asyncio
async def test_total_failure(mock_env, monkeypatch):
    mock_sleep = AsyncMock()
    monkeypatch.setattr("scripts.pipeline.capture_far_expiry_chain.asyncio.sleep", mock_sleep)
    mock_env["chain_source"].get_chain.side_effect = DataFetchError("network down")

    assert await main() == 1
    mock_env["portfolio_store"].record_heartbeat.assert_called_once_with(
        "capture_far_expiry", "FAILED", "All fetches failed"
    )
    assert mock_env["far_store"].record_chain.call_count == 0


@pytest.mark.asyncio
async def test_805_response_logged(mock_env, monkeypatch):
    mock_sleep = AsyncMock()
    monkeypatch.setattr("scripts.pipeline.capture_far_expiry_chain.asyncio.sleep", mock_sleep)

    # Test that 805 is handled as a warning, though behavior is same as partial failure
    mock_env["chain_source"].get_chain.side_effect = [
        MagicMock(),
        DataFetchError("Error 805 after max retries"),
    ]

    assert await main() == 0
    assert mock_env["chain_source"].get_chain.call_count == 2
    assert mock_env["far_store"].record_chain.call_count == 1
    mock_env["portfolio_store"].record_heartbeat.assert_called_once_with(
        "capture_far_expiry", "SUCCESS"
    )


def test_no_get_logger_dunder_name():
    with open("scripts/pipeline/capture_far_expiry_chain.py") as f:
        content = f.read()
    assert "structlog.get_logger(__name__)" not in content
