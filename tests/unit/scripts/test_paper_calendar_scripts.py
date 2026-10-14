"""Dry-run and full-flow tests for the Nifty calendar entry and snapshot scripts (offline)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.strategies.nifty_calendar import paper_calendar_entry as entry_mod
from scripts.strategies.nifty_calendar import paper_calendar_snapshot as snap_mod
from src.models.portfolio import TradeAction
from src.nifty_calendar.config import MONTHLY
from src.paper.models import PaperTrade
from src.strategy import nifty_calendar_v1 as shell_module
from src.strategy.nifty_calendar_state import ROLES
from tests.unit.strategy.test_nifty_calendar_v1 import FAR, NEAR, Harness

NAME = MONTHLY.strategy_name


class Env:
    """Harness plus a broker serving the harness chains and a recording notifier."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.h = Harness(tmp_path, monkeypatch)
        chains = {NEAR: self.h.near, FAR: self.h.far}

        def parse(raw: list[dict[str, str]]) -> Any:
            return chains[date.fromisoformat(raw[0]["expiry"])]

        for module in (entry_mod, snap_mod, shell_module):
            monkeypatch.setattr(module, "parse_upstox_option_chain", parse)
        self.broker = self.h.broker
        self.broker.get_option_chain = AsyncMock(side_effect=lambda _i, exp: [{"expiry": exp}])
        self.broker.get_order_margin = AsyncMock(
            return_value={"required_margin": 238593.0, "final_margin": 90767.0}
        )
        self.broker.get_ltp = AsyncMock(return_value={})
        self.notifier = MagicMock()
        self.notifier.send_plain_message = AsyncMock(return_value=True)
        self.notifier.send_notification = AsyncMock()
        self.notifier.send_photo = AsyncMock()
        self.chart = AsyncMock()
        for module in (entry_mod, snap_mod):
            monkeypatch.setattr(module, "send_payoff_chart", self.chart)
            monkeypatch.setattr(module, "ensure_registered", lambda: None)

    async def enter(self, *, now: datetime | None = None, dry_run: bool = False) -> str:
        return await entry_mod.run_entry(
            shell=self.h.shell, store=self.h.store, broker=self.broker, lookup=self.h.lookup,
            notifier=self.notifier, now=now or self.h.now, dry_run=dry_run,
        )  # fmt: skip

    async def snapshot(self, *, dry_run: bool = False) -> tuple[str, str | None]:
        ltps = {
            p.instrument_key: Decimal("100") for p in self.h.store.get_positions(NAME) if p.net_qty
        }
        self.broker.get_ltp = AsyncMock(return_value=ltps)
        return await snap_mod.run_snapshot(
            shell=self.h.shell, store=self.h.store, broker=self.broker, lookup=self.h.lookup,
            notifier=self.notifier, snap_date=self.h.now.date(), dry_run=dry_run,
        )  # fmt: skip


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    return Env(tmp_path, monkeypatch)


# --- entry ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_entry_dry_run_writes_and_sends_nothing(env: Env) -> None:
    assert await env.enter(dry_run=True) == "DRY_RUN"
    assert env.h.store.get_trades(NAME) == []
    env.notifier.send_notification.assert_not_awaited()
    env.broker.get_order_margin.assert_not_awaited()


@pytest.mark.asyncio
async def test_entry_persists_four_legs_margin_card_and_chart(env: Env) -> None:
    assert await env.enter() == "ENTERED"
    held = {p.leg_role: p.net_qty for p in env.h.store.get_positions(NAME) if p.net_qty}
    assert set(held) == set(ROLES)
    snap = env.h.store.get_margin_snapshot(NAME, env.h.now.date())
    assert snap is not None and snap.final_margin == Decimal("90767.0")
    card = env.notifier.send_notification.await_args.args[0]
    assert "Cal M" in card and "[S]" in card and "[B]" in card
    env.chart.assert_awaited_once()
    assert env.chart.await_args.kwargs["margin"] == Decimal("90767.0")


@pytest.mark.asyncio
async def test_entry_second_run_hits_the_duplicate_guard(env: Env) -> None:
    assert await env.enter() == "ENTERED"
    assert await env.enter() == "ALREADY_OPEN"
    assert len(env.h.store.get_trades(NAME)) == 4


@pytest.mark.asyncio
async def test_entry_before_entry_time_is_a_quiet_no_entry(env: Env) -> None:
    early = env.h.now.replace(hour=9, minute=20)
    assert await env.enter(now=early) == "NO_ENTRY"
    assert env.h.store.get_trades(NAME) == []
    env.notifier.send_plain_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_entry_chain_failure_alerts_and_writes_nothing(env: Env) -> None:
    env.broker.get_option_chain = AsyncMock(side_effect=RuntimeError("down"))
    assert await env.enter() == "CHAIN_FAILED"
    assert env.h.store.get_trades(NAME) == []
    env.notifier.send_plain_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_entry_reports_incomplete_when_a_leg_does_not_land(env: Env) -> None:
    env.h.shell.apply_action = AsyncMock(return_value=[])  # type: ignore[method-assign]
    assert await env.enter() == "INCOMPLETE"
    assert "INCOMPLETE" in env.notifier.send_plain_message.await_args.args[0]
    env.broker.get_order_margin.assert_not_awaited()  # no margin for a partial structure


@pytest.mark.asyncio
async def test_entry_message_failure_does_not_undo_the_entry(env: Env) -> None:
    env.notifier.send_notification = AsyncMock(side_effect=RuntimeError("telegram down"))
    assert await env.enter() == "ENTERED"
    assert len([p for p in env.h.store.get_positions(NAME) if p.net_qty]) == 4


@pytest.mark.asyncio
async def test_entry_script_noops_when_other_variant_active(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    for active in ("biweekly", None):
        monkeypatch.setattr(entry_mod, "active_variant", lambda _t, _p, a=active: a)
        assert await env.enter() == "NOT_ACTIVE"
    assert env.h.store.get_trades(NAME) == []
    env.broker.get_option_chain.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_day_same_strike_redeploy_is_detected_not_dropped_silently(env: Env) -> None:
    """A ledger collision from the shell reaches the entry script as a labelled NO_ENTRY alert."""
    event = MagicMock(event_type="NC_LEDGER_COLLISION", description="short_call clash")
    env.h.shell.plan_entry = AsyncMock(return_value=[event])  # type: ignore[method-assign]
    assert await env.enter() == "NO_ENTRY"
    alert = env.notifier.send_plain_message.await_args.args[0]
    assert "NC_LEDGER_COLLISION" in alert.replace("\\", "") and "Cal M" in alert
    assert env.h.store.get_trades(NAME) == []


def test_variant_flag_choices_come_from_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    for mod in (entry_mod, snap_mod):
        monkeypatch.setattr("sys.argv", ["x", "--variant", "biweekly"])
        assert mod.parse_args().variant == "biweekly"
        monkeypatch.setattr("sys.argv", ["x", "--variant", "weekly"])
        with pytest.raises(SystemExit):
            mod.parse_args()


# --- snapshot ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_without_trades_does_nothing(env: Env) -> None:
    assert await env.snapshot() == ("NO_TRADES", None)


@pytest.mark.asyncio
async def test_snapshot_dry_run_prints_report_and_writes_nothing(env: Env) -> None:
    await env.h.enter()
    outcome, report = await env.snapshot(dry_run=True)
    assert outcome == "REPORTED" and report is not None and "Cal M EOD Audit" in report
    assert env.h.store.get_latest_nav_snapshot(NAME) is None
    env.notifier.send_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_snapshot_writes_nav_and_four_leg_rows_then_reports(env: Env) -> None:
    await env.h.enter()
    outcome, report = await env.snapshot()
    assert outcome == "REPORTED" and report is not None
    assert "Held" in report and "Exit" in report and "Margin" in report
    day = env.h.now.date()
    assert env.h.store.get_latest_nav_snapshot(NAME) is not None
    rows = [env.h.store.get_leg_snapshot(NAME, role, day) for role in ROLES]
    assert all(r is not None and r.net_qty for r in rows)
    env.notifier.send_notification.assert_awaited_once()
    env.chart.assert_awaited_once()


@pytest.mark.asyncio
async def test_snapshot_flat_after_close_still_records_nav(env: Env) -> None:
    await env.h.enter()
    # Close the book through the ledger so every role is net zero.
    for p in env.h.store.get_positions(NAME):
        env.h.store.record_trade(
            PaperTrade(
                strategy_name=NAME, leg_role=p.leg_role, instrument_key=p.instrument_key,
                trade_date=date(2026, 10, 1),
                action=TradeAction.BUY if p.net_qty < 0 else TradeAction.SELL,
                quantity=abs(p.net_qty), price=Decimal("90"),
            )
        )  # fmt: skip
    outcome, report = await env.snapshot()
    assert (outcome, report) == ("FLAT", None)
    assert env.h.store.get_latest_nav_snapshot(NAME) is not None


@pytest.mark.asyncio
async def test_snapshot_view_failure_still_records_nav_and_fails_closed(env: Env) -> None:
    await env.h.enter()
    env.broker.get_option_chain = AsyncMock(side_effect=RuntimeError("down"))
    outcome, report = await env.snapshot()
    assert (outcome, report) == ("VIEW_FAILED", None)
    assert env.h.store.get_latest_nav_snapshot(NAME) is not None
