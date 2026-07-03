# tests/unit/strategies/ic/test_paper_ic_entry.py
"""Unit tests for scripts/strategies/ic/paper_ic_entry.py."""

# fmt: off
from __future__ import annotations

import sys
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.strategies.ic.paper_ic_entry import run
from src.paper.constants import STRATEGY_CSP
from src.paper.models import PaperPosition
from src.risk.models import PortfolioDelta


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
    """Mock PaperStore to return no open positions by default."""
    with patch("scripts.strategies.ic.paper_ic_entry.PaperStore") as mock_cls:
        store_inst = MagicMock()
        store_inst.get_positions.return_value = []
        store_inst.get_strategy_names.return_value = []
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

    # Verify short put
    assert called_cmds[0] == [
        "python",
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

    assert mock_subprocess.call_count == 4


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
async def test_portfolio_delta_breach_and_adjust(
    mock_vix_data,
    mock_store,
    mock_lookup,
    mock_market_client,
    mock_subprocess,
    mock_telegram,
):
    """Test portfolio delta breach triggers one-strike OTM adjustment."""
    # Current delta = 0.20 lots (very long).
    # Proposed IC: 23800 PE (-0.10 delta) & 24700 CE (+0.08 delta).
    # Net IC delta = 0.02 lots.
    # Projected total = 0.20 + 0.02 = 0.22 lots (passes).
    #
    # Let's mock current delta = 0.24 lots.
    # Net IC delta = 0.02 lots. Projected = 0.26 lots (breach > 0.25).
    # We attempt OTM adjustment: shift short put (23800 PE) one strike lower
    # (23700 PE, delta -0.08).
    # New net IC delta = 0.08 - 0.08 = 0.00 lots.
    # New projected = 0.24 + 0.00 = 0.24 lots (passes!).
    with patch("scripts.strategies.ic.paper_ic_entry.PortfolioDeltaTracker") as mock_tracker_cls:
        tracker_inst = MagicMock()
        tracker_inst.aggregate_delta.return_value = PortfolioDelta(
            options_delta_lots=Decimal("0.26"),
            niftybees_delta_lots=Decimal("0.0"),
            total_delta_lots=Decimal("0.26"),
            warning_breached=False,
            cap_breached=False,
            as_of=datetime.now(),
        )
        mock_tracker_cls.return_value = tracker_inst

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

        # Verify short put was adjusted to 23700
        assert called_cmds[0][8] == "NSE_FO|P23700"
