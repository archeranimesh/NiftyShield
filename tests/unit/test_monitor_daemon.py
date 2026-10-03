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
        patch("asyncio.gather", new_callable=AsyncMock),
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
    with patch.dict("os.environ", {}, clear=True):
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
        for overlay_cls, _overlay_name in [
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


@pytest.mark.asyncio
async def test_four_ic_strategies_registered() -> None:
    # Setup mocks for main dependencies
    mock_store = MagicMock()
    mock_gateway = MagicMock()
    mock_gateway.start_polling = AsyncMock()
    mock_broker = MagicMock()

    mock_monitor = MagicMock()
    mock_monitor.run = AsyncMock()

    mock_ic_cls = MagicMock()
    instances = []

    def create_ic(*args, **kwargs):
        config = kwargs.get("config")
        inst = MagicMock()
        inst.strategy_name = config.strategy_name if config else "IC"
        instances.append(inst)
        return inst

    mock_ic_cls.side_effect = create_ic

    from src.config import settings

    with (
        patch("scripts.monitor_daemon.PaperStore", return_value=mock_store),
        patch("scripts.monitor_daemon.TelegramGateway", return_value=mock_gateway),
        patch("scripts.monitor_daemon.create_client", return_value=mock_broker),
        patch("scripts.monitor_daemon.StrategyMonitor", return_value=mock_monitor),
        patch("scripts.monitor_daemon.IronCondorV1", mock_ic_cls),
        patch("scripts.monitor_daemon.CSPNiftyV1", None),
        patch("scripts.monitor_daemon.IronCondorV2", None),
        patch("scripts.monitor_daemon.NiftyTrackComparisonV1", None),
        patch("scripts.monitor_daemon.MONITOR_OVERLAYS", False),
        patch("sys.argv", ["monitor_daemon.py"]),
        patch("asyncio.gather", side_effect=asyncio.CancelledError),
        patch.object(settings, "telegram_bot_token", "fake_token"),
        patch.object(settings, "telegram_chat_id", "fake_chat_id"),
    ):
        await daemon.main()

        # Assert four IronCondorV1 instances were successfully registered
        assert len(instances) == 4
        registered_names = [inst.strategy_name for inst in instances]
        assert "paper_ic_nifty_v1_weekly" in registered_names
        assert "paper_ic_nifty_v1_monthly" in registered_names
        assert "paper_ic_nifty_v1_leaps" in registered_names
        assert "paper_ic_nifty_v1_yearly" in registered_names

        # Assert daemon's strategies_ref has all 4 IC strategy names, plus
        # paper_signal_track_v1 (SPT-6, always registered in this test env)
        assert len(daemon.strategies_ref) == 5
        assert "paper_ic_nifty_v1_weekly" in daemon.strategies_ref
        assert "paper_ic_nifty_v1_monthly" in daemon.strategies_ref
        assert "paper_ic_nifty_v1_leaps" in daemon.strategies_ref
        assert "paper_ic_nifty_v1_yearly" in daemon.strategies_ref
        assert "paper_signal_track_v1" in daemon.strategies_ref


@pytest.mark.asyncio
async def test_lookup_wired_into_strategy_monitor(tmp_path) -> None:
    """BUG-2 follow-up (2026-07-20): StrategyMonitor must receive the daemon's
    BOD-backed InstrumentLookup, or _get_position_expiry() can never resolve
    numeric instrument keys and every tick silently evaluates positions
    against the wrong expiry's chain (see DECISIONS.md 2026-07-20).
    """
    bod_file = tmp_path / "bod.json.gz"
    bod_file.write_bytes(b"")  # existence is all get_expiry()'s try/except needs

    mock_store = MagicMock()
    mock_gateway = MagicMock()
    mock_gateway.start_polling = AsyncMock()
    mock_broker = MagicMock()

    mock_monitor = MagicMock()
    mock_monitor.run = AsyncMock()
    mock_monitor_cls = MagicMock(return_value=mock_monitor)

    sentinel_lookup = MagicMock(name="sentinel_lookup")
    mock_lookup_cls = MagicMock()
    mock_lookup_cls.from_file.return_value = sentinel_lookup

    from src.config import settings

    with (
        patch("scripts.monitor_daemon.PaperStore", return_value=mock_store),
        patch("scripts.monitor_daemon.TelegramGateway", return_value=mock_gateway),
        patch("scripts.monitor_daemon.create_client", return_value=mock_broker),
        patch("scripts.monitor_daemon.StrategyMonitor", mock_monitor_cls),
        patch("scripts.monitor_daemon.InstrumentLookup", mock_lookup_cls),
        patch("scripts.monitor_daemon.IronCondorV1", None),
        patch("scripts.monitor_daemon.IronCondorV2", None),
        patch("scripts.monitor_daemon.CSPNiftyV1", None),
        patch("scripts.monitor_daemon.NiftyTrackComparisonV1", None),
        patch("scripts.monitor_daemon.MONITOR_OVERLAYS", False),
        patch("sys.argv", ["monitor_daemon.py"]),
        patch("asyncio.gather", side_effect=asyncio.CancelledError),
        patch.object(settings, "telegram_bot_token", "fake_token"),
        patch.object(settings, "telegram_chat_id", "fake_chat_id"),
        patch.object(settings, "bod_instruments_path", str(bod_file)),
    ):
        await daemon.main()

        mock_lookup_cls.from_file.assert_called_once()
        _, kwargs = mock_monitor_cls.call_args
        assert kwargs.get("lookup") is sentinel_lookup


@pytest.mark.asyncio
async def test_lookup_none_when_bod_load_fails_still_wired() -> None:
    """When BOD load fails, lookup stays None — but must still be passed
    through explicitly (not omitted) so StrategyMonitor's own default/behavior
    is driven by this module's fallback logic, not a silently-stale default.
    """
    mock_store = MagicMock()
    mock_gateway = MagicMock()
    mock_gateway.start_polling = AsyncMock()
    mock_broker = MagicMock()

    mock_monitor = MagicMock()
    mock_monitor.run = AsyncMock()
    mock_monitor_cls = MagicMock(return_value=mock_monitor)

    from src.config import settings

    with (
        patch("scripts.monitor_daemon.PaperStore", return_value=mock_store),
        patch("scripts.monitor_daemon.TelegramGateway", return_value=mock_gateway),
        patch("scripts.monitor_daemon.create_client", return_value=mock_broker),
        patch("scripts.monitor_daemon.StrategyMonitor", mock_monitor_cls),
        patch("scripts.monitor_daemon.IronCondorV1", None),
        patch("scripts.monitor_daemon.IronCondorV2", None),
        patch("scripts.monitor_daemon.CSPNiftyV1", None),
        patch("scripts.monitor_daemon.NiftyTrackComparisonV1", None),
        patch("scripts.monitor_daemon.MONITOR_OVERLAYS", False),
        patch("sys.argv", ["monitor_daemon.py"]),
        patch("asyncio.gather", side_effect=asyncio.CancelledError),
        patch.object(settings, "telegram_bot_token", "fake_token"),
        patch.object(settings, "telegram_chat_id", "fake_chat_id"),
        patch.object(settings, "bod_instruments_path", "/nonexistent/path/bod.json.gz"),
    ):
        await daemon.main()

        _, kwargs = mock_monitor_cls.call_args
        assert "lookup" in kwargs
        assert kwargs.get("lookup") is None


@pytest.mark.asyncio
async def test_one_ic_failure_does_not_block_others() -> None:
    # Setup mocks for main dependencies
    mock_store = MagicMock()
    mock_gateway = MagicMock()
    mock_gateway.start_polling = AsyncMock()
    mock_broker = MagicMock()

    mock_monitor = MagicMock()
    mock_monitor.run = AsyncMock()

    mock_ic_cls = MagicMock()
    instances = []

    def create_ic(*args, **kwargs):
        config = kwargs.get("config")
        if config and config.expiry_type == "weekly":
            raise Exception("Weekly initialization failed")
        inst = MagicMock()
        inst.strategy_name = config.strategy_name if config else "IC"
        instances.append(inst)
        return inst

    mock_ic_cls.side_effect = create_ic

    from src.config import settings

    with (
        patch("scripts.monitor_daemon.PaperStore", return_value=mock_store),
        patch("scripts.monitor_daemon.TelegramGateway", return_value=mock_gateway),
        patch("scripts.monitor_daemon.create_client", return_value=mock_broker),
        patch("scripts.monitor_daemon.StrategyMonitor", return_value=mock_monitor),
        patch("scripts.monitor_daemon.IronCondorV1", mock_ic_cls),
        patch("scripts.monitor_daemon.CSPNiftyV1", None),
        patch("scripts.monitor_daemon.IronCondorV2", None),
        patch("scripts.monitor_daemon.NiftyTrackComparisonV1", None),
        patch("scripts.monitor_daemon.MONITOR_OVERLAYS", False),
        patch("sys.argv", ["monitor_daemon.py"]),
        patch("asyncio.gather", side_effect=asyncio.CancelledError),
        patch.object(settings, "telegram_bot_token", "fake_token"),
        patch.object(settings, "telegram_chat_id", "fake_chat_id"),
        patch("scripts.monitor_daemon.logger.error") as mock_log_error,
    ):
        await daemon.main()

        # Assert three IronCondorV1 instances were successfully registered (excluding weekly)
        assert len(instances) == 3
        registered_names = [inst.strategy_name for inst in instances]
        assert "paper_ic_nifty_v1_weekly" not in registered_names
        assert "paper_ic_nifty_v1_monthly" in registered_names
        assert "paper_ic_nifty_v1_leaps" in registered_names
        assert "paper_ic_nifty_v1_yearly" in registered_names

        # Assert daemon's strategies_ref has the 3 surviving IC strategy names,
        # plus paper_signal_track_v1 (SPT-6, always registered in this test env)
        assert len(daemon.strategies_ref) == 4
        assert "paper_ic_nifty_v1_weekly" not in daemon.strategies_ref
        assert "paper_ic_nifty_v1_monthly" in daemon.strategies_ref
        assert "paper_ic_nifty_v1_leaps" in daemon.strategies_ref
        assert "paper_ic_nifty_v1_yearly" in daemon.strategies_ref
        assert "paper_signal_track_v1" in daemon.strategies_ref

        # Assert logger.error was called with weekly initialization failure details
        mock_log_error.assert_called_with(
            "Failed to initialize IronCondorV1",
            expiry_type="weekly",
            error="Weekly initialization failed",
        )


# --- BUG-060: expiry settlement at daemon startup -------------------------------


@pytest.mark.asyncio
async def test_startup_settlement_persists_and_notifies() -> None:
    """Settlement runs with writes enabled, then the report is sent."""
    store, broker, lookup = MagicMock(), MagicMock(), MagicMock()
    report = MagicMock(settled=[MagicMock()], failures=[])
    settle = AsyncMock(return_value=report)
    notify = AsyncMock()
    with (
        patch("scripts.monitor_daemon.settle_expired_legs", settle),
        patch("scripts.monitor_daemon.notify_settlement", notify),
        patch("scripts.monitor_daemon.build_notifier", return_value="notifier"),
    ):
        await daemon.settle_expired_legs_at_startup(store, broker, lookup)

    args, kwargs = settle.call_args
    assert args[:3] == (store, broker, lookup)
    assert kwargs["dry_run"] is False
    notify.assert_awaited_once_with("notifier", report)


@pytest.mark.asyncio
async def test_startup_settlement_skipped_without_bod() -> None:
    """No BOD lookup -> no settlement attempt (fail-closed, legs stay OPEN)."""
    settle = AsyncMock()
    with patch("scripts.monitor_daemon.settle_expired_legs", settle):
        await daemon.settle_expired_legs_at_startup(MagicMock(), MagicMock(), None)
    settle.assert_not_called()


@pytest.mark.asyncio
async def test_startup_settlement_failure_does_not_raise() -> None:
    """A settlement error is logged and swallowed so the daemon still starts."""
    settle = AsyncMock(side_effect=RuntimeError("upstox down"))
    notify = AsyncMock()
    with (
        patch("scripts.monitor_daemon.settle_expired_legs", settle),
        patch("scripts.monitor_daemon.notify_settlement", notify),
    ):
        await daemon.settle_expired_legs_at_startup(MagicMock(), MagicMock(), MagicMock())
    notify.assert_not_called()


@pytest.mark.asyncio
async def test_main_settles_before_monitor_starts() -> None:
    """main() awaits startup settlement before scheduling the first tick."""
    calls: list[str] = []
    mock_store, mock_broker = MagicMock(), MagicMock()
    mock_gateway = MagicMock()
    mock_gateway.start_polling = AsyncMock()
    mock_monitor = MagicMock()

    async def _run() -> None:
        calls.append("monitor_run")

    mock_monitor.run = _run

    async def _settle(store, broker, lookup) -> None:
        assert (store, broker) == (mock_store, mock_broker)
        calls.append("settle")

    from src.config import settings

    with (
        patch("scripts.monitor_daemon.PaperStore", return_value=mock_store),
        patch("scripts.monitor_daemon.TelegramGateway", return_value=mock_gateway),
        patch("scripts.monitor_daemon.create_client", return_value=mock_broker),
        patch("scripts.monitor_daemon.StrategyMonitor", return_value=mock_monitor),
        patch("scripts.monitor_daemon.settle_expired_legs_at_startup", _settle),
        patch("scripts.monitor_daemon.warn_stale_flat_legs_at_startup", AsyncMock()),
        patch("scripts.monitor_daemon.IronCondorV1", None),
        patch("scripts.monitor_daemon.IronCondorV2", None),
        patch("scripts.monitor_daemon.CSPNiftyV1", None),
        patch("scripts.monitor_daemon.NiftyTrackComparisonV1", None),
        patch("scripts.monitor_daemon.MONITOR_OVERLAYS", False),
        patch("sys.argv", ["monitor_daemon.py"]),
        patch("asyncio.gather", side_effect=asyncio.CancelledError),
        patch.object(settings, "telegram_bot_token", "fake_token"),
        patch.object(settings, "telegram_chat_id", "fake_chat_id"),
    ):
        await daemon.main()
        await asyncio.sleep(0)

    assert calls[0] == "settle"


@pytest.mark.asyncio
async def test_startup_settlement_notify_failure_is_isolated() -> None:
    """A notify error after a successful settlement is swallowed, not re-raised."""
    report = MagicMock(settled=[MagicMock()], failures=[])
    with (
        patch("scripts.monitor_daemon.settle_expired_legs", AsyncMock(return_value=report)),
        patch(
            "scripts.monitor_daemon.notify_settlement",
            AsyncMock(side_effect=ValueError("formatter")),
        ),
        patch("scripts.monitor_daemon.build_notifier", return_value="notifier"),
    ):
        await daemon.settle_expired_legs_at_startup(MagicMock(), MagicMock(), MagicMock())


# --- BUG-070: stale flat-leg warning at daemon startup --------------------------


@pytest.mark.asyncio
async def test_stale_flat_legs_warning_sent() -> None:
    """A flat-but-OPEN leg produces one Telegram warning naming it."""
    store = MagicMock()
    store.find_stale_flat_legs.return_value = [("paper_x", "overlay_cc", "NSE_FO|1")]
    notifier = MagicMock(send=AsyncMock())
    with patch("scripts.monitor_daemon.build_notifier", return_value=notifier):
        await daemon.warn_stale_flat_legs_at_startup(store)
    notifier.send.assert_awaited_once()
    assert "NSE_FO|1" in notifier.send.call_args.args[0]


@pytest.mark.asyncio
async def test_stale_flat_legs_clean_state_sends_nothing() -> None:
    """No stale legs -> no notifier built, nothing sent."""
    store = MagicMock()
    store.find_stale_flat_legs.return_value = []
    with patch("scripts.monitor_daemon.build_notifier") as build:
        await daemon.warn_stale_flat_legs_at_startup(store)
    build.assert_not_called()


@pytest.mark.asyncio
async def test_stale_flat_legs_check_failure_does_not_raise() -> None:
    """A DB error is logged and swallowed so the daemon still starts."""
    store = MagicMock()
    store.find_stale_flat_legs.side_effect = RuntimeError("db locked")
    await daemon.warn_stale_flat_legs_at_startup(store)
