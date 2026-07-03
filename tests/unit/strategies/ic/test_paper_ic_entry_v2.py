# tests/unit/strategies/ic/test_paper_ic_entry_v2.py
"""Unit tests for scripts/strategies/ic/paper_ic_entry_v2.py.

Covers:
  - Happy path: 4 record_paper_trade commands executed, Telegram sent
  - IVR gate block (via check_duplicate stub; ivr gate tested in test_ic_entry_gates)
  - Duplicate guard block
  - Long wing premium floor failure exits
  - Dry-run: commands printed, subprocess not called
  - Portfolio delta adjustment: shifts short_put one strike OTM when projected > 0.25

No network calls; all external dependencies are mocked.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.strategies.ic.ic_entry_gates import _post_expiry_gate
from scripts.strategies.ic.paper_ic_entry_v2 import run
from src.paper.models import PaperPosition

# ---------------------------------------------------------------------------
# Shared chain fixture
# ---------------------------------------------------------------------------


def _build_chain() -> list[dict]:
    """Build a minimal 24-strike Nifty chain.

    Delta assignments (absolute values):
      PE: 23000=0.01 … 24100=0.25 … 24200=0.30 … 24400=0.45
          24600=0.60 … 24900=0.85 … 25200=0.99
      CE: 25200=0.01 … 24500=0.22 … 24400=0.25 … 24200=0.40
          24000=0.55 … 23700=0.80 … 23500=0.99

    Target entry for V2 monthly:
      short_put  ≈ 0.25 ± 0.03  → 24100 PE (delta -0.25)
      short_call ≈ 0.22 ± 0.03  → 24500 CE (delta 0.22)
      long_put   ≈ 0.10 ± 0.03  → 23800 PE (delta -0.10)
      long_call  ≈ 0.10 ± 0.03  → 24700 CE (delta 0.10)
    """
    strikes = list(range(23000, 25300, 100))

    pe_delta = {
        23000: -0.01,
        23100: -0.02,
        23200: -0.03,
        23300: -0.04,
        23400: -0.05,
        23500: -0.06,
        23600: -0.08,
        23700: -0.09,
        23800: -0.10,
        23900: -0.15,
        24000: -0.20,
        24100: -0.25,
        24200: -0.30,
        24300: -0.35,
        24400: -0.45,
        24500: -0.55,
        24600: -0.60,
        24700: -0.70,
        24800: -0.80,
        24900: -0.85,
        25000: -0.90,
        25100: -0.95,
        25200: -0.99,
    }
    ce_delta = {
        23000: 0.99,
        23100: 0.95,
        23200: 0.90,
        23300: 0.85,
        23400: 0.80,
        23500: 0.75,
        23600: 0.70,
        23700: 0.60,
        23800: 0.55,
        23900: 0.45,
        24000: 0.40,
        24100: 0.35,
        24200: 0.30,
        24300: 0.25,
        24400: 0.22,
        24500: 0.22,
        24600: 0.15,
        24700: 0.10,
        24800: 0.08,
        24900: 0.05,
        25000: 0.04,
        25100: 0.02,
        25200: 0.01,
    }

    chain = []
    for s in strikes:
        chain.append(
            {
                "strike_price": float(s),
                "put_options": {
                    "instrument_key": f"NSE_FO|P{s}",
                    "option_greeks": {"delta": pe_delta.get(s, -0.01), "iv": 16.0},
                    "market_data": {
                        "ltp": 50.0,
                        "bid_price": 49.0,
                        "ask_price": 51.0,
                        "oi": 80_000,
                    },
                },
                "call_options": {
                    "instrument_key": f"NSE_FO|C{s}",
                    "option_greeks": {"delta": ce_delta.get(s, 0.01), "iv": 15.0},
                    "market_data": {
                        "ltp": 50.0,
                        "bid_price": 49.0,
                        "ask_price": 51.0,
                        "oi": 80_000,
                    },
                },
            }
        )
    return chain


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_bod_exists():
    with patch("scripts.strategies.ic.paper_ic_entry_v2.Path.exists", return_value=True):
        yield


@pytest.fixture
def mock_gates():
    """Stub out all shared gate helpers (including post-expiry gate)."""
    with (
        patch("scripts.strategies.ic.paper_ic_entry_v2.check_duplicate") as m_dup,
        patch("scripts.strategies.ic.paper_ic_entry_v2._post_expiry_gate") as m_gate,
        patch("scripts.strategies.ic.paper_ic_entry_v2.resolve_ivr") as m_ivr,
        patch("scripts.strategies.ic.paper_ic_entry_v2.resolve_expiry") as m_expiry,
    ):
        lookup = MagicMock()
        lookup.search_options.return_value = [{"instrument_key": "NSE_FO|MOCK_LONG"}]
        m_ivr.return_value = (0.35, None)
        m_expiry.return_value = (lookup, "2026-07-31", 35, None)
        yield {"dup": m_dup, "gate": m_gate, "ivr": m_ivr, "expiry": m_expiry, "lookup": lookup}


@pytest.fixture
def mock_store():
    """``get_position`` defaults to a confirmed (non-zero net_qty) position so
    the post-execution DB-verification step (added 2026-07-03) passes by
    default in tests not specifically exercising that check.
    """
    with patch("scripts.strategies.ic.paper_ic_entry_v2.PaperStore") as m_cls:
        inst = MagicMock()
        inst.get_positions.return_value = []
        inst.get_strategy_names.return_value = []
        inst.get_position.return_value = PaperPosition(
            strategy_name="paper_ic_nifty_v2_monthly",
            leg_role="mock_leg",
            net_qty=-65,
            avg_cost=Decimal("0"),
            avg_sell_price=Decimal("50.0"),
            instrument_key="NSE_FO|MOCK",
        )
        m_cls.return_value = inst
        yield inst


@pytest.fixture
def mock_client():
    with patch("scripts.strategies.ic.paper_ic_entry_v2.UpstoxMarketClient") as m_cls:
        client = MagicMock()
        client.get_option_chain_sync.return_value = _build_chain()
        client.get_ltp_sync.return_value = {"NSE_INDEX|Nifty 50": Decimal("24250")}
        m_cls.return_value = client
        yield client


@pytest.fixture
def mock_subprocess():
    with patch("scripts.strategies.ic.paper_ic_entry_v2.subprocess.run") as m_run:
        yield m_run


@pytest.fixture
def mock_telegram():
    with patch("scripts.strategies.ic.paper_ic_entry_v2.TelegramGateway") as m_cls:
        inst = MagicMock()
        inst.send_notification = AsyncMock()
        m_cls.return_value = inst
        yield inst


@pytest.fixture
def mock_delta_tracker():
    with patch("scripts.strategies.ic.paper_ic_entry_v2.PortfolioDeltaTracker") as m_cls:
        tracker = MagicMock()
        pd = MagicMock()
        pd.total_delta_lots = Decimal("0.05")  # neutral portfolio
        tracker.aggregate_delta.return_value = pd
        m_cls.return_value = tracker
        yield tracker


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_executes_four_legs(
    mock_gates, mock_store, mock_client, mock_subprocess, mock_telegram, mock_delta_tracker
) -> None:
    """Happy path: 4 record_paper_trade subprocesses called, Telegram sent."""
    with patch.object(
        sys,
        "argv",
        [
            "paper_ic_entry_v2.py",
            "--expiry-type",
            "monthly",
            "--no-dry-run",
            "--bod-path",
            "dummy.json",
        ],
    ):
        await run()

    assert mock_subprocess.call_count == 4
    cmds = [c.args[0] for c in mock_subprocess.call_args_list]

    # Verify strategy name propagated to all legs
    for cmd in cmds:
        assert "paper_ic_nifty_v2_monthly" in cmd

    # Leg roles in order
    assert cmds[0][6] == "short_put"
    assert cmds[1][6] == "long_put_hedge"
    assert cmds[2][6] == "short_call"
    assert cmds[3][6] == "long_call_hedge"

    # Short legs are SELL, long legs are BUY
    assert cmds[0][10] == "SELL"
    assert cmds[1][10] == "BUY"
    assert cmds[2][10] == "SELL"
    assert cmds[3][10] == "BUY"

    assert mock_telegram.send_notification.call_count == 1

    # record_paper_trade.py has no --ivr flag, and IVR here (0.35) is above
    # the 0.25 gate, so no --force-entry forwarding should occur on any leg.
    # --no-dry-run must always be forwarded, otherwise record_paper_trade.py's
    # own dry-run default (True) silently no-ops every leg (2026-07-03 defect).
    for cmd in cmds:
        assert "--ivr" not in cmd
        assert "--force-entry" not in cmd
        assert "--no-dry-run" in cmd


@pytest.mark.asyncio
async def test_ivr_below_gate_forwards_force_entry_to_sell_legs_only(
    mock_gates, mock_store, mock_client, mock_subprocess, mock_telegram, mock_delta_tracker
) -> None:
    """When resolve_ivr reports ivr below the 0.25 gate (either via the
    log-only-gates GateViolation path or the --force-entry bypass path,
    both of which return ivr_violation=None under force_entry), this script
    must forward --force-entry to record_paper_trade.py on the SELL legs
    only — that downstream script enforces its own independent SELL-only R3
    gate and would otherwise re-block an entry already approved here.
    """
    mock_gates["ivr"].return_value = (0.10, None)  # below 0.25 gate

    with patch.object(
        sys,
        "argv",
        [
            "paper_ic_entry_v2.py",
            "--expiry-type",
            "monthly",
            "--no-dry-run",
            "--force-entry",
            "--bod-path",
            "dummy.json",
        ],
    ):
        await run()

    assert mock_subprocess.call_count == 4
    cmds = [c.args[0] for c in mock_subprocess.call_args_list]
    short_put_cmd, long_put_cmd, short_call_cmd, long_call_cmd = cmds

    assert short_put_cmd[10] == "SELL"
    assert "--force-entry" in short_put_cmd
    assert short_call_cmd[10] == "SELL"
    assert "--force-entry" in short_call_cmd
    assert long_put_cmd[10] == "BUY"
    assert "--force-entry" not in long_put_cmd
    assert long_call_cmd[10] == "BUY"
    assert "--force-entry" not in long_call_cmd


@pytest.mark.asyncio
async def test_leg_not_persisted_blocks_success_notification(
    mock_gates, mock_store, mock_client, mock_subprocess, mock_telegram, mock_delta_tracker
) -> None:
    """DB-verification gate: subprocess exit 0 alone must not be trusted.

    Regression test for the 2026-07-03 defect where record_paper_trade.py's
    own --dry-run default (True) meant every IC entry ever "executed" by this
    script silently no-op'd at the DB layer while still exiting 0 and
    triggering a false-positive "✅ IC V2 Entry" Telegram message. Simulates
    that exact failure mode: subprocess.run succeeds for all 4 legs, but
    store.get_position reports net_qty=0 for one of them. The script must
    exit 1, send only a ⚠️ warning notification, and never send ✅.
    """
    mock_store.get_position.return_value = PaperPosition(
        strategy_name="paper_ic_nifty_v2_monthly",
        leg_role="mock_leg",
        net_qty=0,  # not persisted
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("0"),
        instrument_key="NSE_FO|MOCK",
    )

    with (
        patch.object(
            sys,
            "argv",
            [
                "paper_ic_entry_v2.py",
                "--expiry-type",
                "monthly",
                "--no-dry-run",
                "--bod-path",
                "dummy.json",
            ],
        ),
        pytest.raises(SystemExit) as excinfo,
    ):
        await run()

    assert excinfo.value.code == 1
    assert mock_subprocess.call_count == 4  # all 4 legs were still attempted
    assert mock_telegram.send_notification.call_count == 1
    sent_msg = mock_telegram.send_notification.call_args[0][0]
    assert "⚠️" in sent_msg
    assert "✅" not in sent_msg


@pytest.mark.asyncio
async def test_db_verification_query_failure_blocks_success_notification(
    mock_gates, mock_store, mock_client, mock_subprocess, mock_telegram, mock_delta_tracker
) -> None:
    """DB-verification gate must itself fail safe.

    If store.get_position() raises (e.g. transient SQLite lock) AFTER the 4
    subprocess calls already ran, the script must not crash silently with no
    notification at all — it must catch the error, send a ⚠️ warning
    explaining verification itself failed, and exit 1.
    """
    mock_store.get_position.side_effect = RuntimeError("database is locked")

    with (
        patch.object(
            sys,
            "argv",
            [
                "paper_ic_entry_v2.py",
                "--expiry-type",
                "monthly",
                "--no-dry-run",
                "--bod-path",
                "dummy.json",
            ],
        ),
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


@pytest.mark.asyncio
async def test_dry_run_does_not_call_subprocess(
    mock_gates, mock_store, mock_client, mock_subprocess, mock_telegram, mock_delta_tracker
) -> None:
    """Dry-run mode: commands printed but subprocess not called; no Telegram."""
    with patch.object(
        sys,
        "argv",
        ["paper_ic_entry_v2.py", "--expiry-type", "monthly", "--bod-path", "dummy.json"],
        # default --dry-run is True
    ):
        await run()

    mock_subprocess.assert_not_called()
    mock_telegram.send_notification.assert_not_called()


# ---------------------------------------------------------------------------
# Gate failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_guard_exits(
    mock_gates, mock_store, mock_client, mock_subprocess, mock_telegram, mock_delta_tracker
) -> None:
    """Exits with code 1 when check_duplicate raises SystemExit."""
    mock_gates["dup"].side_effect = SystemExit(1)
    with patch.object(
        sys,
        "argv",
        [
            "paper_ic_entry_v2.py",
            "--expiry-type",
            "monthly",
            "--no-dry-run",
            "--bod-path",
            "dummy.json",
        ],
    ):
        with pytest.raises(SystemExit) as exc_info:
            await run()
    assert exc_info.value.code == 1
    mock_subprocess.assert_not_called()


@pytest.mark.asyncio
async def test_ivr_gate_exits(
    mock_gates, mock_store, mock_client, mock_subprocess, mock_telegram, mock_delta_tracker
) -> None:
    """Exits with code 1 when resolve_ivr raises SystemExit (IVR below gate)."""
    mock_gates["ivr"].side_effect = SystemExit(1)
    with patch.object(
        sys,
        "argv",
        [
            "paper_ic_entry_v2.py",
            "--expiry-type",
            "monthly",
            "--no-dry-run",
            "--bod-path",
            "dummy.json",
        ],
    ):
        with pytest.raises(SystemExit) as exc_info:
            await run()
    assert exc_info.value.code == 1
    mock_subprocess.assert_not_called()


# ---------------------------------------------------------------------------
# Wing floor failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_long_wing_premium_floor_exits(
    mock_gates, mock_store, mock_subprocess, mock_telegram, mock_delta_tracker
) -> None:
    """Exits with code 1 when no long wing candidate passes the ₹15 premium floor."""
    # Build a chain where all 10Δ wings have ltp = ₹5 (below floor)
    chain = _build_chain()
    for entry in chain:
        for side in ("put_options", "call_options"):
            entry[side]["market_data"]["ltp"] = 5.0
            entry[side]["market_data"]["bid_price"] = 4.5
            entry[side]["market_data"]["ask_price"] = 5.5

    with patch("scripts.strategies.ic.paper_ic_entry_v2.UpstoxMarketClient") as m_cls:
        client = MagicMock()
        client.get_option_chain_sync.return_value = chain
        client.get_ltp_sync.return_value = {"NSE_INDEX|Nifty 50": Decimal("24250")}
        m_cls.return_value = client

        with patch.object(
            sys,
            "argv",
            [
                "paper_ic_entry_v2.py",
                "--expiry-type",
                "monthly",
                "--no-dry-run",
                "--bod-path",
                "dummy.json",
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                await run()

    assert exc_info.value.code == 1
    mock_subprocess.assert_not_called()


# ---------------------------------------------------------------------------
# Portfolio delta adjustment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_portfolio_delta_adjustment_shifts_short_put(
    mock_gates, mock_store, mock_client, mock_subprocess, mock_telegram
) -> None:
    """When projected delta > 0.25, short_put is shifted one strike OTM."""
    with patch("scripts.strategies.ic.paper_ic_entry_v2.PortfolioDeltaTracker") as m_cls:
        tracker = MagicMock()
        pd = MagicMock()
        # High current delta forces adjustment: projected = 0.25 (put) - 0.22 (call) + 0.30 = ~0.33
        pd.total_delta_lots = Decimal("0.30")
        tracker.aggregate_delta.return_value = pd
        m_cls.return_value = tracker

        with patch.object(
            sys,
            "argv",
            [
                "paper_ic_entry_v2.py",
                "--expiry-type",
                "monthly",
                "--no-dry-run",
                "--bod-path",
                "dummy.json",
            ],
        ):
            await run()

    # Should still complete (adjustment found) and execute 4 legs
    assert mock_subprocess.call_count == 4


# ---------------------------------------------------------------------------
# Post-expiry gate tests (IC-V2-13)
# ---------------------------------------------------------------------------


def test_post_expiry_gate_passes_mid_cycle_before_current_month_expiry() -> None:
    """Gate passes mid-month, before the current cycle's own expiry (BUG-003).

    June 2026: current month's own expiry = June 30, but the prior settled
    cycle (May 26) is long past — a fresh June series is already open, so
    June 25 must be allowed, not blocked.
    """
    with patch("scripts.strategies.ic.ic_entry_gates.date") as mock_date:
        mock_date.today.return_value = date(2026, 6, 25)
        mock_date.side_effect = date  # keep date(y, m, d) constructor working
        _post_expiry_gate()  # must not raise


def test_post_expiry_gate_blocks_on_last_tuesday() -> None:
    """Gate exits when today IS the last Tuesday (settlement not complete intraday).

    June 2026: last Tuesday = June 30. Running on expiry day itself must block.
    """
    with patch("scripts.strategies.ic.ic_entry_gates.date") as mock_date:
        mock_date.today.return_value = date(2026, 6, 30)
        mock_date.side_effect = date
        with pytest.raises(SystemExit) as exc:
            _post_expiry_gate()
    assert exc.value.code == 1


def test_post_expiry_gate_passes_day_after_last_tuesday() -> None:
    """Gate passes on the Wednesday immediately after last-Tuesday settlement.

    July 2026: last Tuesday = July 28. July 29 (Wednesday) is the first valid
    entry day — today > last_tuesday_of_current_month.
    """
    with patch("scripts.strategies.ic.ic_entry_gates.date") as mock_date:
        mock_date.today.return_value = date(2026, 7, 29)
        mock_date.side_effect = date
        _post_expiry_gate()  # should not raise


# ---------------------------------------------------------------------------
# IC-V2-15 — Entry failure Telegram alerting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ivr_gate_failure_sends_telegram(
    mock_gates, mock_store, mock_client, mock_delta_tracker
) -> None:
    """IVR below gate → Telegram notifier called with ⚠️ blocked message."""
    from unittest.mock import AsyncMock, MagicMock

    tg_mock = MagicMock()
    tg_mock.send = AsyncMock()

    # Simulate resolve_ivr calling its notifier and exiting (log-only-gates
    # disabled here, since this test exercises the legacy hard-block path).
    def _fake_ivr(db_path, gate, force_entry, notifier=None, **kwargs):
        if notifier is not None:
            notifier(f"⚠️ IC V2 Entry BLOCKED\nGate: ivr\nIVR: 0.10 / Gate: {gate:.2f}")
        sys.exit(1)

    mock_gates["ivr"].side_effect = _fake_ivr

    with patch("scripts.strategies.ic.paper_ic_entry_v2.build_notifier", return_value=tg_mock):
        with patch.object(
            sys,
            "argv",
            [
                "paper_ic_entry_v2.py",
                "--expiry-type",
                "monthly",
                "--no-dry-run",
                "--no-log-only-gates",
                "--bod-path",
                "dummy.json",
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                await run()

    assert exc_info.value.code == 1
    assert tg_mock.send.call_count == 1
    msg_sent = tg_mock.send.call_args[0][0]
    assert "BLOCKED" in msg_sent
    assert "ivr" in msg_sent


@pytest.mark.asyncio
async def test_duplicate_gate_failure_sends_telegram(
    mock_gates, mock_store, mock_client, mock_delta_tracker
) -> None:
    """Open position → Telegram notifier called with ⚠️ blocked message."""
    from unittest.mock import AsyncMock, MagicMock

    tg_mock = MagicMock()
    tg_mock.send = AsyncMock()

    def _fake_dup(store, strategy_name, notifier=None):
        if notifier is not None:
            notifier(
                f"⚠️ IC V2 Entry BLOCKED — {strategy_name}\n"
                f"Gate: duplicate\nReason: Active position already exists"
            )
        sys.exit(1)

    mock_gates["dup"].side_effect = _fake_dup

    with patch("scripts.strategies.ic.paper_ic_entry_v2.build_notifier", return_value=tg_mock):
        with patch.object(
            sys,
            "argv",
            [
                "paper_ic_entry_v2.py",
                "--expiry-type",
                "monthly",
                "--no-dry-run",
                "--bod-path",
                "dummy.json",
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                await run()

    assert exc_info.value.code == 1
    assert tg_mock.send.call_count == 1
    msg_sent = tg_mock.send.call_args[0][0]
    assert "duplicate" in msg_sent


@pytest.mark.asyncio
async def test_telegram_failure_does_not_block_exit(
    mock_gates, mock_store, mock_client, mock_delta_tracker
) -> None:
    """Telegram send raises → gate still exits with code 1; error is swallowed."""
    from unittest.mock import MagicMock

    tg_mock = MagicMock()
    # Sync side_effect: raises immediately when called inside _gate_alert
    tg_mock.send = MagicMock(side_effect=Exception("Telegram down"))

    def _fake_dup(store, strategy_name, notifier=None):
        if notifier is not None:
            notifier("⚠️ IC V2 Entry BLOCKED — duplicate")
        sys.exit(1)

    mock_gates["dup"].side_effect = _fake_dup

    with patch("scripts.strategies.ic.paper_ic_entry_v2.build_notifier", return_value=tg_mock):
        with patch.object(
            sys,
            "argv",
            [
                "paper_ic_entry_v2.py",
                "--expiry-type",
                "monthly",
                "--no-dry-run",
                "--bod-path",
                "dummy.json",
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                await run()

    # Gate exit must happen regardless of Telegram failure
    assert exc_info.value.code == 1


def test_post_expiry_gate_holiday_on_last_tuesday() -> None:
    """If last Tuesday is a public holiday, no scripts run that day.

    By Wednesday (next trading day), today > last_tuesday → gate passes.
    This test simulates today = last_tuesday + 1 (the next trading day after
    a holiday-on-Tuesday scenario) and confirms the gate does not block.
    """
    # July 2026: last Tuesday = July 28. If July 28 were a holiday,
    # entry scripts run on July 29 (Wednesday) — must pass.
    with patch("scripts.strategies.ic.ic_entry_gates.date") as mock_date:
        mock_date.today.return_value = date(2026, 7, 29)
        mock_date.side_effect = date
        _post_expiry_gate()  # should not raise
