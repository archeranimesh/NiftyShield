from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.pipeline.capture_far_expiry_chain import main
from src.client.exceptions import DataFetchError


@pytest.fixture
def mock_env(mocker):
    mocker.patch("scripts.pipeline.capture_far_expiry_chain.guard_trading_day", return_value=False)

    mock_lookup = MagicMock()
    mock_lookup.get_expiry_candidates.side_effect = lambda u, t, preference, min_expiry=None: (
        [("yearly", "2026-12-31")] if min_expiry is None else [("yearly", "2027-12-30")]
    )
    mocker.patch(
        "scripts.pipeline.capture_far_expiry_chain.InstrumentLookup.from_file",
        return_value=mock_lookup,
    )

    mock_chain_source = MagicMock()
    mock_chain_source.get_chain = AsyncMock(return_value=MagicMock())
    mocker.patch(
        "scripts.pipeline.capture_far_expiry_chain.CompositeChainSource",
        return_value=mock_chain_source,
    )

    mock_far_store = MagicMock()
    mocker.patch(
        "scripts.pipeline.capture_far_expiry_chain.FarExpiryStore", return_value=mock_far_store
    )

    mock_portfolio_store = MagicMock()
    mocker.patch(
        "scripts.pipeline.capture_far_expiry_chain.PortfolioStore.create",
        new_callable=AsyncMock,
        return_value=mock_portfolio_store,
    )

    mocker.patch(
        "scripts.pipeline.capture_far_expiry_chain.aiohttp.ClientSession", return_value=AsyncMock()
    )

    return {
        "lookup": mock_lookup,
        "chain_source": mock_chain_source,
        "far_store": mock_far_store,
        "portfolio_store": mock_portfolio_store,
    }


@pytest.mark.asyncio
async def test_holiday_exit(mocker):
    mocker.patch("scripts.pipeline.capture_far_expiry_chain.guard_trading_day", return_value=True)
    assert await main() == 0


@pytest.mark.asyncio
async def test_no_bod_file(mocker):
    mocker.patch("scripts.pipeline.capture_far_expiry_chain.guard_trading_day", return_value=False)
    mocker.patch(
        "scripts.pipeline.capture_far_expiry_chain.InstrumentLookup.from_file",
        side_effect=FileNotFoundError,
    )
    assert await main() == 1


@pytest.mark.asyncio
async def test_no_expiries_found(mock_env):
    mock_env["lookup"].get_expiry_candidates.side_effect = (
        lambda u, t, preference, min_expiry=None: []
    )
    assert await main() == 1


@pytest.mark.asyncio
async def test_success_two_expiries_and_spacing(mock_env, mocker):
    mock_sleep = mocker.patch(
        "scripts.pipeline.capture_far_expiry_chain.asyncio.sleep", new_callable=AsyncMock
    )
    assert await main() == 0

    assert mock_env["chain_source"].get_chain.call_count == 2
    assert mock_env["far_store"].record_chain.call_count == 2
    mock_env["portfolio_store"].record_heartbeat.assert_called_once_with(
        "capture_far_expiry", "SUCCESS"
    )
    mock_sleep.assert_called_once_with(4.0)


@pytest.mark.asyncio
async def test_partial_failure(mock_env, mocker):
    mock_sleep = mocker.patch(
        "scripts.pipeline.capture_far_expiry_chain.asyncio.sleep", new_callable=AsyncMock
    )

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
async def test_total_failure(mock_env, mocker):
    mocker.patch("scripts.pipeline.capture_far_expiry_chain.asyncio.sleep", new_callable=AsyncMock)
    mock_env["chain_source"].get_chain.side_effect = DataFetchError("network down")

    assert await main() == 1
    mock_env["portfolio_store"].record_heartbeat.assert_called_once_with(
        "capture_far_expiry", "FAILED", "All fetches failed"
    )
    assert mock_env["far_store"].record_chain.call_count == 0


@pytest.mark.asyncio
async def test_805_response_logged(mock_env, mocker):
    mocker.patch("scripts.pipeline.capture_far_expiry_chain.asyncio.sleep", new_callable=AsyncMock)

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
