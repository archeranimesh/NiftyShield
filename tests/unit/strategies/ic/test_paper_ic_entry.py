# tests/unit/strategies/ic/test_paper_ic_entry.py
"""Unit tests for scripts/strategies/ic/paper_ic_entry.py."""

# fmt: off
from __future__ import annotations

import subprocess
import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.strategies.ic.paper_ic_entry import run
from src.paper.constants import STRATEGY_CSP
from src.paper.models import PaperPosition


@pytest.fixture(autouse=True)
def mock_path_exists():
    """Mock Path.exists to always return True for dummy paths in tests."""
    with patch("scripts.strategies.ic.paper_ic_entry.Path.exists") as mock_exists:
        mock_exists.return_value = True
        yield mock_exists


@pytest.fixture(autouse=True)
def mock_post_expiry_gate():
    """Stub _post_expiry_gate so monthly tests are not blocked by calendar date."""
    with patch("scripts.strategies.ic.paper_ic_entry._post_expiry_gate") as m:
        yield m


@pytest.fixture
def mock_vix_data():
    """Mock VIX loading/computing functions."""
    with (
        patch("scripts.strategies.ic.paper_ic_entry.load_vix_series") as mock_load,
        patch("scripts.strategies.ic.paper_ic_entry.IntradayMarketStore") as mock_store_cls,
        patch("scripts.strategies.ic.paper_ic_entry.fetch_vix_latest") as mock_fetch,
        patch("scripts.strategies.ic.paper_ic_entry.compute_ivr") as mock_ivr,
    ):
        mock_load.return_value = []
        mock_store = MagicMock()
        mock_store.get_latest_vix_today.return_value = 15.0
        mock_store_cls.return_value = mock_store
        mock_fetch.return_value = 15.0
        mock_ivr.return_value = 0.30  # default IVR = 30% (above gate)
        yield {
            "load": mock_load,
            "store": mock_store,
            "fetch": mock_fetch,
            "ivr": mock_ivr,
        }


@pytest.fixture
def mock_store():
    """Mock PaperStore to return no open positions by default.

    ``get_position`` defaults to a confirmed (non-zero net_qty) position for
    any (strategy_name, leg_role) so the post-execution DB-verification step
    (added 2026-07-03 after discovering every prior IC entry silently no-op'd)
    passes by default in tests that aren't specifically exercising that check.
    """
    with patch("scripts.strategies.ic.paper_ic_entry.PaperStore") as mock_cls:
        store_inst = MagicMock()
        store_inst.get_positions.return_value = []
        store_inst.get_strategy_names.return_value = []
        store_inst.get_position.return_value = PaperPosition(
            strategy_name="paper_ic_nifty_v1_monthly",
            leg_role="mock_leg",
            net_qty=-65,
            avg_cost=Decimal("0"),
            avg_sell_price=Decimal("20.0"),
            instrument_key="NSE_FO|MOCK",
        )
        mock_cls.return_value = store_inst
        yield store_inst


@pytest.fixture
def mock_lookup():
    """Mock InstrumentLookup and get_expiry_candidates."""
    with patch("scripts.strategies.ic.paper_ic_entry.InstrumentLookup") as mock_cls:
        inst = MagicMock()
        # Default returns weekly candidate
        inst.get_expiry_candidates.return_value = [("weekly", "2026-07-02")]
        inst.search_options.return_value = [{"instrument_key": "NSE_FO|MOCK_LONG_LEG"}]
        mock_cls.from_file.return_value = inst
        yield inst


@pytest.fixture
def mock_chain():
    """Helper to generate a mock option chain."""

    def _chain():
        # Create strikes around 24000
        strikes = [
            23000,
            23100,
            23200,
            23300,
            23400,
            23500,
            23600,
            23700,
            23800,
            23900,
            24000,
            24100,
            24200,
            24300,
            24400,
            24500,
            24600,
            24700,
            24800,
            24900,
            25000,
            25100,
            25200,
        ]
        # PE deltas (negative), CE deltas (positive)
        pe_deltas = {
            23000: -0.01,
            23100: -0.02,
            23200: -0.02,
            23300: -0.03,
            23400: -0.03,
            23500: -0.04,
            23600: -0.05,
            23700: -0.08,
            23800: -0.10,
            23900: -0.15,
            24000: -0.20,
            24100: -0.30,
            24200: -0.45,
            24300: -0.60,
            24400: -0.80,
            24500: -0.85,
            24600: -0.89,
            24700: -0.91,
            24800: -0.95,
            24900: -0.96,
            25000: -0.97,
            25100: -0.98,
            25200: -0.99,
        }
        ce_deltas = {
            23000: 0.99,
            23100: 0.98,
            23200: 0.97,
            23300: 0.96,
            23400: 0.95,
            23500: 0.94,
            23600: 0.95,
            23700: 0.91,
            23800: 0.89,
            23900: 0.85,
            24000: 0.80,
            24100: 0.70,
            24200: 0.55,
            24300: 0.40,
            24400: 0.20,
            24500: 0.15,
            24600: 0.10,
            24700: 0.08,
            24800: 0.05,
            24900: 0.04,
            25000: 0.03,
            25100: 0.02,
            25200: 0.01,
        }

        chain_data = []
        for s in strikes:
            chain_data.append(
                {
                    "strike_price": float(s),
                    "call_options": {
                        "instrument_key": f"NSE_FO|C{s}",
                        "option_greeks": {"delta": ce_deltas[s], "iv": 15.0},
                        "market_data": {
                            "ltp": 50.0,
                            "bid_price": 49.5,
                            "ask_price": 50.5,
                            "oi": 5000,
                        },
                    },
                    "put_options": {
                        "instrument_key": f"NSE_FO|P{s}",
                        "option_greeks": {"delta": pe_deltas[s], "iv": 16.0},
                        "market_data": {
                            "ltp": 60.0,
                            "bid_price": 59.5,
                            "ask_price": 60.5,
                            "oi": 6000,
                        },
                    },
                }
            )
        return chain_data

    return _chain


@pytest.fixture
def mock_market_client(mock_chain):
    """Mock UpstoxMarketClient to return mock chain and LTP."""
    with patch("scripts.strategies.ic.paper_ic_entry.UpstoxMarketClient") as mock_cls:
        client = MagicMock()
        client.get_option_chain_sync.return_value = mock_chain()
        client.get_ltp_sync.return_value = {"NSE_INDEX|Nifty 50": Decimal("24000")}
        mock_cls.return_value = client
        yield client


@pytest.fixture
def mock_subprocess():
    """Mock subprocess.run."""
    with patch("scripts.strategies.ic.paper_ic_entry.subprocess.run") as mock_run:
        yield mock_run


@pytest.fixture(autouse=True)
def mock_upstox_live_client():
    """Mock UpstoxLiveClient (Step 12b margin capture) — no network in tests.

    Applies to every test in this module: the --no-dry-run execute path
    unconditionally constructs UpstoxLiveClient() and calls get_order_margin
    after legs are persisted. Without this fixture that would be a real
    network call to the live Upstox margin-calculator endpoint.
    """
    with patch("scripts.strategies.ic.paper_ic_entry.UpstoxLiveClient") as mock_cls:
        client = MagicMock()
        client.get_order_margin = AsyncMock(
            return_value={"required_margin": 100000.0, "final_margin": 40000.0}
        )
        mock_cls.return_value = client
        yield client


@pytest.fixture
def mock_telegram():
    """Mock TelegramGateway."""
    with patch("scripts.strategies.ic.paper_ic_entry.TelegramGateway") as mock_cls:
        inst = MagicMock()
        inst.send_notification = AsyncMock()
        mock_cls.return_value = inst
        yield inst


@pytest.mark.asyncio
async def test_weekly_standalone(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
):
    """Test weekly expiry entry in standalone mode."""
    # Target: PUT 0.10, CALL 0.08, wing 200
    # Expected: 23800 PE (delta -0.10), 24700 CE (delta 0.08)
    # Long PE: 23800 - 200 = 23600 PE
    # Long CE: 24700 + 200 = 24900 CE
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with patch.object(sys, "argv", test_args):
        await run()

    assert mock_subprocess.call_count == 4
    called_cmds = [call.args[0] for call in mock_subprocess.call_args_list]

    # Verify short put. argv[0] is sys.executable (not a hardcoded "python"
    # literal — see bbacf77), so compare everything after it.
    assert called_cmds[0][1:] == [
        "-m",
        "scripts.record.record_paper_trade",
        "--strategy",
        "paper_ic_nifty_v1_weekly",
        "--leg",
        "short_put",
        "--key",
        "NSE_FO|P23800",
        "--action",
        "SELL",
        "--qty",
        "65",
        "--price",
        "60.0",
        "--ivr-gate",
        "0.15",
        "--no-dry-run",
    ]
    # Verify long put
    assert called_cmds[1][6] == "long_put_hedge"
    assert called_cmds[1][10] == "BUY"

    # Verify Telegram notification was sent
    assert mock_telegram.send_notification.call_count == 1


@pytest.mark.asyncio
async def test_monthly_standalone(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
):
    """Test monthly expiry entry in standalone mode."""
    # Target: PUT 0.15, CALL 0.10, wing 500
    # Expected: 23900 PE (delta -0.15), 24600 CE (delta 0.10)
    mock_lookup.get_expiry_candidates.return_value = [("monthly", "2026-07-30")]
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "monthly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with patch.object(sys, "argv", test_args):
        await run()

    assert mock_subprocess.call_count == 4
    called_cmds = [call.args[0] for call in mock_subprocess.call_args_list]

    # Short Put: 24000 PE
    assert called_cmds[0][8] == "NSE_FO|P24000"
    # Short Call: 24500 CE
    assert called_cmds[2][8] == "NSE_FO|C24500"


def test_weekly_and_monthly_forward_distinct_ivr_gate(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
):
    """Regression for 2026-07-08: record_paper_trade.py's own R3 gate was
    hardcoded to 0.25 regardless of strategy, silently diverging from
    weekly's looser configured gate (0.15) and hard-blocking entries that
    weekly's own config had already approved. Every leg command must now
    carry --ivr-gate matching the strategy's ic_expiry_config.py value.
    """
    import asyncio

    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with patch.object(sys, "argv", test_args):
        asyncio.run(run())
    weekly_cmds = [call.args[0] for call in mock_subprocess.call_args_list]
    assert weekly_cmds, "expected at least one leg command for weekly"
    for cmd in weekly_cmds:
        assert "--ivr-gate" in cmd
        assert cmd[cmd.index("--ivr-gate") + 1] == "0.15"

    mock_subprocess.reset_mock()
    mock_lookup.get_expiry_candidates.return_value = [("monthly", "2026-07-30")]
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "monthly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with patch.object(sys, "argv", test_args):
        asyncio.run(run())
    monthly_cmds = [call.args[0] for call in mock_subprocess.call_args_list]
    assert monthly_cmds, "expected at least one leg command for monthly"
    for cmd in monthly_cmds:
        assert "--ivr-gate" in cmd
        assert cmd[cmd.index("--ivr-gate") + 1] == "0.25"


@pytest.mark.asyncio
async def test_monthly_concurrent(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
):
    """Test monthly expiry entry in concurrent mode (shifted delta targets)."""
    # Open CSP positions: target shift short put by -0.06 (0.15 - 0.06 = 0.09)
    # Short call target shifted by +0.03 (0.10 + 0.03 = 0.13)
    # Closest PE to 0.09 is 23700 PE (delta -0.08) or 23800 PE (delta -0.10)
    # Closest CE to 0.13 is 24500 CE (delta 0.15) or 24600 CE (delta 0.10)
    mock_store.get_positions.side_effect = lambda name: (
        [
            PaperPosition(
                strategy_name="paper_csp_nifty_v1",
                leg_role="short_put",
                net_qty=-65,
                avg_cost=Decimal("0"),
                avg_sell_price=Decimal("100"),
                instrument_key="dummy",
            )
        ]
        if name == STRATEGY_CSP
        else []
    )
    mock_lookup.get_expiry_candidates.return_value = [("monthly", "2026-07-30")]

    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "monthly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with patch.object(sys, "argv", test_args):
        await run()

    assert mock_subprocess.call_count == 4
    called_cmds = [call.args[0] for call in mock_subprocess.call_args_list]

    # Target put delta = 0.09. Filter puts in [0.09 - 0.06, 0.09 + 0.06] = [0.03, 0.15].
    # In mock chain, 23700 has delta -0.08, 23800 has delta -0.10, 23900 has delta -0.15.
    # Closest to 0.09 is 23700 or 23800 (both ±0.01). Our rank/sort picks closest.
    # Target call delta = 0.13. Filter calls in [0.13 - 0.06, 0.13 + 0.06] = [0.07, 0.19].
    # In mock chain, 24500 has delta 0.15, 24600 has delta 0.10. Closest is 24500 (diff 0.02) vs 24600 (diff 0.03).
    # So short call should be 24500 CE.
    assert called_cmds[2][8] == "NSE_FO|C24500"


@pytest.mark.asyncio
async def test_dry_run_mode(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
    capsys,
):
    """Test that dry run prints commands instead of executing them."""
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with patch.object(sys, "argv", test_args):
        await run()

    assert mock_subprocess.call_count == 0
    captured = capsys.readouterr()
    assert "[DRY-RUN] Commands to execute:" in captured.out
    assert "scripts.record.record_paper_trade" in captured.out


@pytest.mark.asyncio
async def test_ivr_passes(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
):
    """Test happy path when IVR is above gate."""
    mock_vix_data["ivr"].return_value = 0.28  # Gate is 0.15 for weekly
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with patch.object(sys, "argv", test_args):
        await run()

    assert mock_subprocess.call_count == 4


@pytest.mark.asyncio
async def test_telegram_failure_non_fatal(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
):
    """Test that Telegram failures are logged and do not crash the script."""
    mock_telegram.send_notification.side_effect = Exception(
        "Telegram Gateway error"
    )
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with patch.object(sys, "argv", test_args):
        await run()  # should not raise


@pytest.mark.asyncio
async def test_margin_captured_and_persisted_on_successful_entry(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
    mock_upstox_live_client,
):
    """Step 12b: after all 4 legs are confirmed persisted, margin is fetched
    for the basket and the snapshot is written to the store."""
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with patch.object(sys, "argv", test_args):
        await run()

    mock_upstox_live_client.get_order_margin.assert_awaited_once()
    instruments = mock_upstox_live_client.get_order_margin.call_args.args[0]
    assert len(instruments) == 4
    assert {i["transaction_type"] for i in instruments} == {"BUY", "SELL"}
    mock_store.record_margin_snapshot.assert_called_once()


@pytest.mark.asyncio
async def test_margin_capture_failure_does_not_block_success_notification(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
    mock_upstox_live_client,
):
    """get_order_margin failing must not prevent the success Telegram notification
    or otherwise crash the script — legs are already persisted at that point."""
    mock_upstox_live_client.get_order_margin.side_effect = RuntimeError("network down")
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with patch.object(sys, "argv", test_args):
        await run()  # should not raise

    assert mock_telegram.send_notification.call_count == 1
    mock_store.record_margin_snapshot.assert_not_called()

    assert mock_subprocess.call_count == 4


@pytest.mark.asyncio
async def test_original_entry_credit_persisted_on_successful_entry(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
    mock_upstox_live_client,
):
    """BUG-021: after all 4 legs are confirmed persisted, the basket's net
    credit is written via ``PaperStore.set_original_entry_credit`` so the
    profit-target/loss-stop branch can reference the original 4-leg
    economics instead of recomputing from whatever legs are still open
    after a partial close (mirrors BUG-020 Phase 2 for IronCondorV2)."""
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with patch.object(sys, "argv", test_args):
        await run()

    mock_store.set_original_entry_credit.assert_called_once()
    call_args = mock_store.set_original_entry_credit.call_args.args
    assert call_args[0] == "paper_ic_nifty_v1_weekly"
    # short/long mids come from the mock chain fixture: short leg mid=50 (CE)
    # or 60 (PE), long leg same — net credit = (60+50)-(60+50) = 0 with this
    # fixture's flat pricing; assert the type/shape, not a hand-derived value.
    assert isinstance(call_args[1], Decimal)


@pytest.mark.asyncio
async def test_original_entry_credit_persist_failure_does_not_block_success_notification(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
    mock_upstox_live_client,
):
    """set_original_entry_credit failing must not prevent the success Telegram
    notification or otherwise crash the script — legs are already persisted
    at that point (same non-fatal contract as margin capture)."""
    mock_store.set_original_entry_credit.side_effect = RuntimeError("db locked")
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with patch.object(sys, "argv", test_args):
        await run()  # should not raise

    assert mock_telegram.send_notification.call_count == 1


@pytest.mark.asyncio
async def test_open_position_prevention(
    mock_vix_data, mock_store, mock_lookup, mock_market_client, mock_subprocess
):
    """Test that open position prevents new entry."""
    mock_store.get_positions.return_value = [
        PaperPosition(
            strategy_name="paper_ic_nifty_v1_weekly",
            leg_role="short_put",
            net_qty=-65,
            avg_cost=Decimal("0"),
            avg_sell_price=Decimal("100"),
            instrument_key="dummy",
        )
    ]
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with (
        patch.object(sys, "argv", test_args),
        pytest.raises(SystemExit) as excinfo,
    ):
        await run()

    assert excinfo.value.code == 1
    assert mock_subprocess.call_count == 0


@pytest.mark.asyncio
async def test_duplicate_guard_blocks_even_with_log_only_gates_on(
    mock_vix_data, mock_store, mock_lookup, mock_market_client, mock_subprocess
):
    """STRUCTURAL gate edge case: duplicate position always hard-blocks.

    check_duplicate is a structural/data-integrity gate — it must abort
    entry even when --log-only-gates is explicitly on (the default), never
    downgraded to a logged GateViolation.
    """
    mock_store.get_positions.return_value = [
        PaperPosition(
            strategy_name="paper_ic_nifty_v1_weekly",
            leg_role="short_put",
            net_qty=-65,
            avg_cost=Decimal("0"),
            avg_sell_price=Decimal("100"),
            instrument_key="dummy",
        )
    ]
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--log-only-gates",
        "--bod-path",
        "dummy.json",
    ]
    with (
        patch.object(sys, "argv", test_args),
        pytest.raises(SystemExit) as excinfo,
    ):
        await run()

    assert excinfo.value.code == 1
    assert mock_subprocess.call_count == 0
    assert mock_store.record_gate_violation.call_count == 0


@pytest.mark.asyncio
async def test_ivr_below_gate_error(
    mock_vix_data, mock_store, mock_lookup, mock_market_client, mock_subprocess
):
    """Test that low IVR blocks entry when --no-log-only-gates is passed."""
    mock_vix_data["ivr"].return_value = 0.10  # weekly gate is 0.15
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--no-log-only-gates",
        "--bod-path",
        "dummy.json",
    ]
    with (
        patch.object(sys, "argv", test_args),
        pytest.raises(SystemExit) as excinfo,
    ):
        await run()

    assert excinfo.value.code == 1
    assert mock_subprocess.call_count == 0


@pytest.mark.asyncio
async def test_ivr_below_gate_logs_violation_and_proceeds_by_default(
    mock_vix_data, mock_store, mock_lookup, mock_market_client, mock_subprocess, mock_telegram
):
    """Default --log-only-gates=True: low IVR records a GateViolation, entry proceeds.

    Happy-path test for THRESHOLD-gate log-only mode: trade opens (4 legs
    executed) and the violation is persisted, queryable via
    get_gate_violation_counts (GROUP BY strategy_name, gate_name).
    """
    mock_vix_data["ivr"].return_value = 0.10  # weekly gate is 0.15
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with patch.object(sys, "argv", test_args):
        await run()

    assert mock_subprocess.call_count == 4
    assert mock_store.record_gate_violation.call_count >= 1
    violation_args = [c.args[0] for c in mock_store.record_gate_violation.call_args_list]
    assert any(v.gate_name == "ivr" for v in violation_args)

    # record_paper_trade.py has no --ivr flag and enforces its own
    # independent SELL-only R3 gate — this script must forward --force-entry
    # on the SELL legs (short_put, short_call) so that gate doesn't re-block
    # what was already logged-and-allowed here, while leaving the BUY hedge
    # legs alone (record_paper_trade's R3 gate never applies to BUY anyway,
    # but its portfolio-delta check should still run on those legs).
    called_cmds = [call.args[0] for call in mock_subprocess.call_args_list]
    for cmd in called_cmds:
        assert "--ivr" not in cmd
    short_put_cmd, long_put_cmd, short_call_cmd, long_call_cmd = called_cmds
    assert short_put_cmd[10] == "SELL"
    assert "--force-entry" in short_put_cmd
    assert short_call_cmd[10] == "SELL"
    assert "--force-entry" in short_call_cmd
    assert long_put_cmd[10] == "BUY"
    assert "--force-entry" not in long_put_cmd
    assert long_call_cmd[10] == "BUY"
    assert "--force-entry" not in long_call_cmd


@pytest.mark.asyncio
async def test_ivr_below_gate_forced(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
):
    """Test that low IVR is bypassed with --force-entry."""
    mock_vix_data["ivr"].return_value = 0.10  # weekly gate is 0.15
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--force-entry",
        "--bod-path",
        "dummy.json",
    ]
    with patch.object(sys, "argv", test_args):
        await run()

    assert mock_subprocess.call_count == 4

    # --force-entry (top-level bypass) does not populate gate_violations, so
    # this exercises the other branch of ivr_below_gate: it must still be
    # forwarded to record_paper_trade.py on SELL legs only.
    called_cmds = [call.args[0] for call in mock_subprocess.call_args_list]
    short_put_cmd, long_put_cmd, short_call_cmd, long_call_cmd = called_cmds
    assert "--force-entry" in short_put_cmd
    assert "--force-entry" in short_call_cmd
    assert "--force-entry" not in long_put_cmd
    assert "--force-entry" not in long_call_cmd


@pytest.mark.asyncio
async def test_no_expiry_candidate_error(
    mock_vix_data, mock_store, mock_lookup, mock_market_client, mock_subprocess
):
    """Test that missing expiry candidate causes exit 1."""
    mock_lookup.get_expiry_candidates.return_value = []
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with (
        patch.object(sys, "argv", test_args),
        pytest.raises(SystemExit) as excinfo,
    ):
        await run()

    assert excinfo.value.code == 1
    assert mock_subprocess.call_count == 0


@pytest.mark.asyncio
async def test_bod_lookup_failed_error(
    mock_vix_data, mock_store, mock_lookup, mock_market_client, mock_subprocess
):
    """Test that long put BOD lookup failure exits 1."""
    mock_lookup.search_options.return_value = []  # fail long leg search
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with (
        patch.object(sys, "argv", test_args),
        pytest.raises(SystemExit) as excinfo,
    ):
        await run()

    assert excinfo.value.code == 1
    assert mock_subprocess.call_count == 0


@pytest.mark.asyncio
async def test_ic_entry_ignores_other_open_positions(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
):
    """IC entries are judged on their own two short legs only (2026-07-03).

    Regression test for the removal of cross-strategy/cross-IC-variant
    portfolio-delta gating and self-adjustment. Previously, an open position
    in another strategy (or another IC expiry variant) with a large delta
    could push this script to silently shift the short_put/short_call strike
    one notch OTM ("Portfolio delta gate adjusted ..."). Per explicit product
    decision, this script must no longer query PaperStore.get_strategy_names()
    or PaperStore.get_positions() for any strategy other than its own
    duplicate-entry guard, and must not import/construct PortfolioDeltaTracker
    at all. Strikes are chosen purely by delta-target proximity on the live
    chain, regardless of what else is open.
    """
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with patch.object(sys, "argv", test_args):
        await run()

    assert mock_subprocess.call_count == 4
    called_cmds = [call.args[0] for call in mock_subprocess.call_args_list]

    # Strikes land at the plain delta-target selection (23800 PE / 24600 CE
    # per mock_chain's delta table) — no adjustment mechanism exists anymore.
    assert called_cmds[0][8] == "NSE_FO|P23800"
    assert called_cmds[2][8] == "NSE_FO|C24600"

    # get_strategy_names() was only ever called by the removed cross-strategy
    # aggregation step — its absence here is direct evidence the mechanism is
    # gone, not just dormant. get_positions() is still legitimately called
    # once for this strategy's own duplicate-entry guard.
    mock_store.get_strategy_names.assert_not_called()


@pytest.mark.asyncio
async def test_leg_not_persisted_blocks_success_notification(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
):
    """DB-verification gate: subprocess exit 0 alone must not be trusted.

    Regression test for the 2026-07-03 defect where record_paper_trade.py's
    own --dry-run default (True) meant every IC entry ever "executed" by this
    script silently no-op'd at the DB layer while still exiting 0 and
    triggering a false-positive "✅ IC Entry" Telegram message. Simulates
    that exact failure mode: subprocess.run succeeds for all 4 legs, but
    store.get_position reports net_qty=0 for one of them (e.g. --no-dry-run
    wiring regresses again, or record_paper_trade.py silently rejects a leg).
    The script must exit 1, send only a ⚠️ warning notification, and never
    send the ✅ success message.
    """
    mock_store.get_position.return_value = PaperPosition(
        strategy_name="paper_ic_nifty_v1_weekly",
        leg_role="mock_leg",
        net_qty=0,  # not persisted
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("0"),
        instrument_key="NSE_FO|MOCK",
    )
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with (
        patch.object(sys, "argv", test_args),
        pytest.raises(SystemExit) as excinfo,
    ):
        await run()

    assert excinfo.value.code == 1
    assert mock_subprocess.call_count == 4  # all 4 legs were still attempted
    assert mock_telegram.send_notification.call_count == 1
    sent_msg = mock_telegram.send_notification.call_args[0][0]
    assert "⚠️" in sent_msg
    assert "✅" not in sent_msg
    # PG-2e: the post-entry verification loop must pass instrument_key
    # explicitly rather than relying on get_position()'s most-recent-entry_date
    # fallback (PG-2a) — each of the 4 leg calls carries its own key.
    assert mock_store.get_position.call_count == 4
    for call in mock_store.get_position.call_args_list:
        assert "instrument_key" in call.kwargs
        assert call.kwargs["instrument_key"]


@pytest.mark.asyncio
async def test_db_verification_query_failure_blocks_success_notification(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
):
    """DB-verification gate must itself fail safe.

    If store.get_position() raises (e.g. transient SQLite lock) AFTER the 4
    subprocess calls already ran, the script must not crash silently with no
    notification at all — it must catch the error, send a ⚠️ warning
    explaining verification itself failed, and exit 1. Without this handling,
    an exception here would reintroduce the exact blind spot the DB
    verification step exists to close, just one line later.
    """
    mock_store.get_position.side_effect = RuntimeError("database is locked")
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with (
        patch.object(sys, "argv", test_args),
        pytest.raises(SystemExit) as excinfo,
    ):
        await run()

    assert excinfo.value.code == 1
    assert mock_subprocess.call_count == 4  # all 4 legs were still attempted
    assert mock_telegram.send_notification.call_count == 1
    sent_msg = mock_telegram.send_notification.call_args[0][0]
    assert "⚠️" in sent_msg
    assert "✅" not in sent_msg
    assert "database is locked" in sent_msg


# ---------------------------------------------------------------------------
# RH-1 — mid-sequence subprocess failure triggers compensating closes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mid_sequence_failure_compensates_persisted_legs(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
):
    """RH-1 happy path: leg 3 crashes, legs 1-2 (already persisted) get closed.

    Simulates `record_paper_trade.py` raising on the 3rd subprocess call
    (short_call) after the first two (short_put, long_put_hedge) succeeded.
    The 4th leg (long_call_hedge) is never attempted — the loop must stop at
    first failure, not compound a partial basket. Verification then finds
    short_put/long_put_hedge persisted and short_call/long_call_hedge missing;
    compensating BUY/SELL-reversed closes must be issued for the two
    persisted legs so no naked exposure survives the script exiting 1.
    """
    mock_subprocess.side_effect = [
        MagicMock(),  # short_put — succeeds
        MagicMock(),  # long_put_hedge — succeeds
        subprocess.CalledProcessError(1, "record_paper_trade"),  # short_call — crashes
        MagicMock(),  # compensating close for short_put
        MagicMock(),  # compensating close for long_put_hedge
    ]

    def _get_position(strategy_name, leg_role, instrument_key=None):
        persisted = leg_role in ("short_put", "long_put_hedge")
        return PaperPosition(
            strategy_name=strategy_name,
            leg_role=leg_role,
            net_qty=-65 if persisted else 0,
            avg_cost=Decimal("0"),
            avg_sell_price=Decimal("20.0") if persisted else Decimal("0"),
            instrument_key=instrument_key or "NSE_FO|MOCK",
        )

    mock_store.get_position.side_effect = _get_position

    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with (
        patch.object(sys, "argv", test_args),
        pytest.raises(SystemExit) as excinfo,
    ):
        await run()

    assert excinfo.value.code == 1
    # 3 entry attempts (stopped at the failing leg) + 2 compensating closes.
    assert mock_subprocess.call_count == 5
    compensating_calls = mock_subprocess.call_args_list[3:5]
    compensating_roles = {call.args[0][6] for call in compensating_calls}  # "--leg" value
    assert compensating_roles == {"short_put", "long_put_hedge"}
    for call in compensating_calls:
        cmd = call.args[0]
        assert "--force-entry" in cmd
        # short_put was SELL at entry -> compensating close is BUY; long_put_hedge
        # was BUY at entry -> compensating close is SELL.
        action_idx = cmd.index("--action") + 1
        leg_idx = cmd.index("--leg") + 1
        if cmd[leg_idx] == "short_put":
            assert cmd[action_idx] == "BUY"
        else:
            assert cmd[action_idx] == "SELL"

    assert mock_telegram.send_notification.call_count == 1
    sent_msg = mock_telegram.send_notification.call_args[0][0]
    assert "⚠️" in sent_msg
    assert "✅" not in sent_msg
    assert "Compensating closes succeeded" in sent_msg
    assert "MANUAL INTERVENTION" not in sent_msg


@pytest.mark.asyncio
async def test_compensation_failure_alerts_manual_intervention(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
):
    """RH-1 worst case: the compensating close itself fails.

    Same mid-sequence crash as the happy-path test, but the compensating
    subprocess call for one of the two persisted legs also raises. This is
    an unrecoverable state (naked exposure remains) — the Telegram alert
    must say so explicitly rather than implying cleanup succeeded.
    """
    mock_subprocess.side_effect = [
        MagicMock(),  # short_put — succeeds
        MagicMock(),  # long_put_hedge — succeeds
        subprocess.CalledProcessError(1, "record_paper_trade"),  # short_call — crashes
        MagicMock(),  # compensating close for short_put — succeeds
        subprocess.CalledProcessError(1, "record_paper_trade"),  # compensating close fails
    ]

    def _get_position(strategy_name, leg_role, instrument_key=None):
        persisted = leg_role in ("short_put", "long_put_hedge")
        return PaperPosition(
            strategy_name=strategy_name,
            leg_role=leg_role,
            net_qty=-65 if persisted else 0,
            avg_cost=Decimal("0"),
            avg_sell_price=Decimal("20.0") if persisted else Decimal("0"),
            instrument_key=instrument_key or "NSE_FO|MOCK",
        )

    mock_store.get_position.side_effect = _get_position

    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with (
        patch.object(sys, "argv", test_args),
        pytest.raises(SystemExit) as excinfo,
    ):
        await run()

    assert excinfo.value.code == 1
    assert mock_subprocess.call_count == 5
    assert mock_telegram.send_notification.call_count == 1
    sent_msg = mock_telegram.send_notification.call_args[0][0]
    assert "⚠️" in sent_msg
    assert "MANUAL INTERVENTION REQUIRED" in sent_msg


# ---------------------------------------------------------------------------
# B010.3 — structlog migration (setup_logging() entrypoint call)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_calls_setup_logging_first(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
):
    """run() must call setup_logging() as its first action (LOGGING.md standard)."""
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    with (
        patch.object(sys, "argv", test_args),
        patch("scripts.strategies.ic.paper_ic_entry.setup_logging") as mock_setup,
    ):
        await run()

    mock_setup.assert_called_once()


@pytest.mark.asyncio
async def test_duplicate_guard_logs_structured_error(
    mock_vix_data,
    mock_store,
    mock_lookup,
):
    """Duplicate-position guard fires ic_entry.duplicate_position at ERROR, no print()."""
    from src.paper.models import PaperPosition

    mock_store.get_positions.return_value = [
        PaperPosition(
            strategy_name="paper_ic_nifty_v1_weekly",
            leg_role="short_put",
            net_qty=-65,
            avg_cost=Decimal("0"),
            avg_sell_price=Decimal("20.0"),
            instrument_key="NSE_FO|MOCK",
        )
    ]
    test_args = [
        "paper_ic_entry.py",
        "--expiry-type",
        "weekly",
        "--no-dry-run",
        "--bod-path",
        "dummy.json",
    ]
    import structlog.testing

    with (
        patch.object(sys, "argv", test_args),
        patch("scripts.strategies.ic.paper_ic_entry.setup_logging"),
        structlog.testing.capture_logs() as logs,
        pytest.raises(SystemExit) as excinfo,
    ):
        await run()

    assert excinfo.value.code == 1
    events = [entry["event"] for entry in logs]
    assert "ic_entry.duplicate_position" in events
