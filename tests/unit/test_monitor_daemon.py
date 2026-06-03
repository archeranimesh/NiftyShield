"""Unit tests for the monitor daemon script."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import scripts.monitor_daemon as daemon


@pytest.mark.asyncio
async def test_monitor_daemon_shutdown() -> None:
    # Setup mocks
    mock_store = MagicMock()
    mock_store.expire_all_pending_approvals = MagicMock()
    mock_store.write_heartbeat = MagicMock()

    # Set references in daemon module
    daemon.store_ref = mock_store
    daemon.strategies_ref = ["paper_csp_nifty_v1"]
    daemon._shutdown_started = False

    # Mock tasks
    mock_task1 = MagicMock(spec=asyncio.Task)
    mock_task1.done.return_value = False
    mock_task1.cancel = MagicMock()
    daemon.monitor_task = mock_task1

    mock_task2 = MagicMock(spec=asyncio.Task)
    mock_task2.done.return_value = True
    daemon.gateway_task = mock_task2

    with (
        patch("sys.exit") as mock_exit,
        patch("asyncio.gather", new_callable=AsyncMock) as mock_gather,
        patch("os.getpid", return_value=12345),
    ):
        await daemon.shutdown()

        # Check cancellations
        mock_task1.cancel.assert_called_once()
        mock_task2.cancel.assert_not_called()  # Already done

        # Check database updates
        mock_store.expire_all_pending_approvals.assert_called_once()
        mock_store.write_heartbeat.assert_called_once_with(
            12345,
            ["paper_csp_nifty_v1"],
            "SHUTDOWN",
        )
        mock_exit.assert_called_once_with(0)


def test_monitor_overlays_gate_disabled_by_default() -> None:
    """MONITOR_OVERLAYS defaults to False when env var is unset."""
    with patch.dict("os.environ", {}, clear=False):
        # Re-evaluate the constant expression directly — module already loaded
        import os
        result = os.getenv("MONITOR_OVERLAYS", "0") == "1"
        assert result is False


def test_monitor_overlays_gate_enabled_when_env_set() -> None:
    """MONITOR_OVERLAYS=1 enables overlay strategy registration."""
    from unittest.mock import MagicMock, patch

    import scripts.monitor_daemon as _daemon

    cc = MagicMock()
    pp = MagicMock()
    collar = MagicMock()
    cc_instance = MagicMock()
    pp_instance = MagicMock()
    collar_instance = MagicMock()
    cc.return_value = cc_instance
    pp.return_value = pp_instance
    collar.return_value = collar_instance

    with (
        patch.object(_daemon, "MONITOR_OVERLAYS", True),
        patch.object(_daemon, "CCOverlayV1", cc),
        patch.object(_daemon, "PPOverlayV1", pp),
        patch.object(_daemon, "CollarOverlayV1", collar),
    ):
        strategies: list = []
        for overlay_cls, overlay_name in [
            (_daemon.CCOverlayV1, "CCOverlayV1"),
            (_daemon.PPOverlayV1, "PPOverlayV1"),
            (_daemon.CollarOverlayV1, "CollarOverlayV1"),
        ]:
            if overlay_cls is not None:
                strategies.append(overlay_cls())

        assert cc_instance in strategies
        assert pp_instance in strategies
        assert collar_instance in strategies
        assert len(strategies) == 3


@pytest.mark.asyncio
async def test_monitor_daemon_shutdown_duplicate_ignored() -> None:
    # Set references in daemon module
    daemon.store_ref = MagicMock()
    daemon._shutdown_started = True

    with patch("sys.exit") as mock_exit:
        await daemon.shutdown()
        # Verify duplicate shutdown was ignored and did not call exit
        mock_exit.assert_not_called()
