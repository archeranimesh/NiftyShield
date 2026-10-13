"""Unit tests for NiftyCalendarV1: entry, exits, idempotency and variant-agnosticism."""

from __future__ import annotations

import dataclasses
import inspect
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
import structlog

from src.instruments.lookup import InstrumentLookup
from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.nifty_calendar.config import MONTHLY
from src.nifty_calendar.cycle import MonthlyCyclePolicy
from src.nifty_calendar.exit_rules import ExitDecision, MonthlyExitRule
from src.nifty_calendar.selector import WingStructureSelector
from src.paper.models import PaperPosition
from src.paper.store import PaperStore
from src.strategy import nifty_calendar_v1 as shell_module
from src.strategy.executor import PaperFillSimulator
from src.strategy.nifty_calendar_v1 import NiftyCalendarV1
from src.strategy.protocol import ApprovedAction, LegClose, SignalEvent

_IST = ZoneInfo("Asia/Kolkata")
NEAR, FAR = date(2026, 10, 27), date(2026, 11, 23)
SPOT = Decimal("22700")
Quote = tuple[str, str, str, str, str]  # bid, ask, delta, vega, iv


def _leg(strike: int, q: Quote | None) -> OptionLeg | None:
    if q is None:
        return None
    bid, ask, vega, iv = Decimal(q[0]), Decimal(q[1]), Decimal(q[3]), Decimal(q[4])
    delta = None if q[2] == "none" else Decimal(q[2])
    return OptionLeg(
        strike=Decimal(strike), ltp=(bid + ask) / 2, bid=bid, ask=ask, oi=1, volume=1,
        delta=delta, gamma=None, theta=None, vega=vega, iv=iv,
    )  # fmt: skip


def _chain(
    spot: Decimal, expiry: date, rows: dict[int, tuple[Quote | None, Quote | None]]
) -> OptionChain:
    strikes = {
        Decimal(k): OptionChainStrike(ce=_leg(k, ce), pe=_leg(k, pe))
        for k, (ce, pe) in rows.items()
    }
    return OptionChain(underlying_spot=spot, expiry=expiry, strikes=strikes)


NEAR_ROWS: dict[int, tuple[Quote | None, Quote | None]] = {
    22700: (("320", "322", "0.5", "20", "14"), ("310", "312", "-0.5", "20", "14"))
}
FAR_ROWS: dict[int, tuple[Quote | None, Quote | None]] = {
    22700: (("420", "421.5", "0.52", "25", "13.5"), ("390", "391.5", "-0.48", "25", "13.5")),
    22100: (None, ("150", "151.5", "-0.22", "23", "14")),
    22200: (None, ("180", "182", "-0.26", "24", "14")),
    23200: (("185", "187", "0.26", "24", "13.5"), None),
    23300: (("155", "156.5", "0.22", "23", "13.5"), None),
}


def _lookup() -> InstrumentLookup:
    insts, n = [], 1000
    for exp in (NEAR, FAR):
        for strike in (22100, 22200, 22700, 23200, 23300):
            for typ in ("CE", "PE"):
                n += 1
                insts.append(
                    {"segment": "NSE_FO", "instrument_type": typ, "underlying_symbol": "NIFTY",
                     "strike_price": float(strike), "expiry": exp.isoformat(),
                     "instrument_key": f"NSE_FO|{n}"}
                )  # fmt: skip
    return InstrumentLookup(insts)


class _Rule:
    """Exit rule stub returning a fixed decision."""

    def __init__(self, decision: ExitDecision) -> None:
        self.decision = decision

    def evaluate(self, state: Any, snapshot: Any, now: datetime) -> ExitDecision:
        return self.decision


class Harness:
    """Shell wired with a tmp store, a patched far-chain fetch and a movable clock."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> None:
        self.now = datetime(2026, 9, 30, 10, 35, tzinfo=_IST)
        self.far = _chain(SPOT, FAR, FAR_ROWS)
        self.near = _chain(SPOT, NEAR, NEAR_ROWS)
        self.lookup = _lookup()
        self.store = PaperStore(tmp_path / "db.sqlite", instrument_lookup=self.lookup)
        self.broker = MagicMock()
        self.broker.get_option_chain = AsyncMock(return_value=[{"raw": 1}])
        monkeypatch.setattr(shell_module, "parse_upstox_option_chain", lambda raw: self.far)
        self.notifier = MagicMock()
        self.notifier.send_plain_message = AsyncMock(return_value=True)
        config = overrides.pop("config", MONTHLY)
        policy = overrides.pop(
            "cycle_policy",
            MonthlyCyclePolicy([date(2026, 9, 29), NEAR, FAR], lambda d: d.weekday() < 5, config),
        )
        self.shell = NiftyCalendarV1(
            broker=self.broker, store=self.store, notifier=self.notifier,
            simulator=PaperFillSimulator(), selector=WingStructureSelector(),
            exit_rule=overrides.pop("exit_rule", MonthlyExitRule(config)),
            cycle_policy=policy, config=config, lookup=self.lookup,
            vix_data_dir=tmp_path, clock=lambda: self.now,
        )  # fmt: skip

    async def enter(self) -> list[PaperPosition]:
        events = await self.shell.check_signals(self.near, [])
        assert [e.event_type for e in events] == ["NC_ENTRY"]
        return await self.shell.apply_action([], _to_action(events[0]))

    def reprice_near(self, ce: tuple[str, str], pe: tuple[str, str], spot: Decimal = SPOT) -> None:
        rows = {22700: ((*ce, "0.5", "20", "14"), (*pe, "-0.5", "20", "14"))}
        self.near = _chain(spot, NEAR, rows)  # type: ignore[arg-type]


def _to_action(event: SignalEvent) -> ApprovedAction:
    p = event.payload
    return ApprovedAction(
        action_type=p["auto_action"],
        legs_to_close=[LegClose(d["leg_role"], d["instrument_key"]) for d in p["legs_to_close"]],
        legs_to_open=p["legs_to_open"],
        rationale="auto-execute",
        council_rank=1,
        metadata=dict(p),
    )


@pytest.fixture
def h(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    return Harness(tmp_path, monkeypatch)


@pytest.mark.asyncio
async def test_enters_monthly_cycle_records_four_legs(h: Harness) -> None:
    positions = await h.enter()
    assert {p.leg_role: p.net_qty for p in positions} == {
        "short_call": -65, "short_put": -65, "long_call_wing": 65, "long_put_wing": 65,
    }  # fmt: skip
    short = next(p for p in positions if p.leg_role == "short_call")
    assert short.avg_sell_price == Decimal("321") - Decimal("1.5")  # mid less default slippage
    assert short.entry_date == date(2026, 9, 30)


@pytest.mark.asyncio
async def test_no_entry_when_greeks_missing(h: Harness) -> None:
    h.near = _chain(SPOT, NEAR, {22700: (("320", "322", "none", "20", "14"), NEAR_ROWS[22700][1])})
    events = await h.shell.check_signals(h.near, [])
    assert [(e.event_type, e.severity) for e in events] == [("NC_NO_ENTRY", "WARN")]
    assert h.store.get_trades(MONTHLY.strategy_name) == []


@pytest.mark.asyncio
async def test_no_entry_outside_window_or_before_entry_time(h: Harness) -> None:
    h.now = h.now.replace(hour=9, minute=20)
    assert await h.shell.check_signals(h.near, []) == []
    h.now = datetime(2026, 10, 6, 11, 0, tzinfo=_IST)
    assert await h.shell.check_signals(h.near, []) == []


@pytest.mark.asyncio
async def test_target_closes_all_legs(h: Harness) -> None:
    await h.enter()
    h.now = datetime(2026, 10, 1, 11, 0, tzinfo=_IST)
    h.reprice_near(("100", "101"), ("90", "91"))
    events = await h.shell.check_signals(h.near, [])
    assert [e.event_type for e in events] == ["NC_TARGET"]
    assert await h.shell.apply_action([], _to_action(events[0])) == []
    trades = h.store.get_trades(MONTHLY.strategy_name)
    assert len(trades) == 8
    assert [e["exit_signal"] for e in h.store.get_open_exit_events(MONTHLY.strategy_name)] == [
        "PROFIT_TARGET"
    ]


@pytest.mark.asyncio
async def test_hold_when_nothing_triggers_and_far_group_call_is_ignored(h: Harness) -> None:
    await h.enter()
    h.now = datetime(2026, 10, 1, 11, 0, tzinfo=_IST)
    assert await h.shell.check_signals(h.near, []) == []
    fetches = h.broker.get_option_chain.await_count
    assert await h.shell.check_signals(h.far, []) == []  # far-expiry group call
    assert h.broker.get_option_chain.await_count == fetches  # it fetched nothing


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "signal"),
    [(ExitDecision.TIME_EXIT, "TIME_STOP"), (ExitDecision.DTE_GUARD, "DTE_FORCED"),
     (ExitDecision.CLOSE_BREACH_LATE, "LOSS_STOP")],
)  # fmt: skip
async def test_other_exits_close_with_mapped_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, decision: ExitDecision, signal: str
) -> None:
    h = Harness(tmp_path, monkeypatch, exit_rule=_Rule(ExitDecision.HOLD))
    await h.enter()
    h.shell._exit_rule = _Rule(decision)
    h.now = datetime(2026, 10, 12, 15, 20, tzinfo=_IST)
    events = await h.shell.check_signals(h.near, [])
    assert await h.shell.apply_action([], _to_action(events[0])) == []
    assert [e["exit_signal"] for e in h.store.get_open_exit_events(MONTHLY.strategy_name)] == [
        signal
    ]


async def _breach_recentre(
    h: Harness, monkeypatch: pytest.MonkeyPatch, series: pd.Series
) -> list[str]:
    """Enter, breach the upper breakeven for 30 minutes, apply the recentre; return event signals."""
    monkeypatch.setattr("src.strategy.reentry_mixin.load_vix_series", lambda _d: series)
    await h.enter()
    breached = Decimal("23700")
    atm_rows = {23700: (("50", "51", "0.4", "20", "13"), ("20", "21", "-0.4", "20", "13"))}
    h.far = _chain(SPOT, FAR, {**FAR_ROWS, **atm_rows})  # type: ignore[arg-type]
    h.reprice_near(("900", "902"), ("5", "6"), spot=breached)
    events: list[SignalEvent] = []
    for minute in (0, 15, 30):
        h.now = datetime(2026, 10, 1, 11, minute, tzinfo=_IST)
        events = await h.shell.check_signals(h.near, [])
    assert [e.event_type for e in events] == ["NC_RECENTRE"], events
    assert await h.shell.apply_action([], _to_action(events[0])) == []
    return [e["exit_signal"] for e in h.store.get_open_exit_events(MONTHLY.strategy_name)]


@pytest.mark.asyncio
async def test_breach_early_recentres(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    signals = await _breach_recentre(h, monkeypatch, pd.Series(np.linspace(10.0, 30.0, 252)))
    assert sorted(signals) == ["LOSS_STOP", "R5_REENTRY_ELIGIBLE"]
    h.notifier.send_plain_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_low_ivr_is_logged_but_does_not_block_recentre_or_entry(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """IVR is log-only (as IC/CC/PP): a low reading lands on the R5 event, nothing acts on it."""
    low_ivr = pd.Series(np.linspace(30.0, 10.0, 252))  # today's VIX is the 1-year low
    signals = await _breach_recentre(h, monkeypatch, low_ivr)
    assert sorted(signals) == ["LOSS_STOP", "R5_REENTRY_BLOCKED"]
    notes = [e["notes"] for e in h.store.get_open_exit_events(MONTHLY.strategy_name)]
    assert any("IVR" in n for n in notes)
    held = [p for p in h.store.get_positions(MONTHLY.strategy_name) if p.net_qty != 0]
    assert held == []  # the recentre close was not blocked


@pytest.mark.asyncio
async def test_entry_is_not_gated_on_low_ivr(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.strategy.reentry_mixin.load_vix_series", lambda _d: pd.Series(np.linspace(30, 10, 252))
    )
    events = await h.shell.check_signals(h.near, [])
    assert [e.event_type for e in events] == ["NC_ENTRY"]


@pytest.mark.asyncio
async def test_double_apply_is_idempotent_and_dropped_duplicate_is_logged(h: Harness) -> None:
    events = await h.shell.check_signals(h.near, [])
    action = _to_action(events[0])
    first = await h.shell.apply_action([], action)
    assert await h.shell.apply_action([], action) == first
    assert len(h.store.get_trades(MONTHLY.strategy_name)) == 4

    h.now = h.now.replace(hour=11)
    h.reprice_near(("100", "101"), ("90", "91"))
    close = (await h.shell.check_signals(h.near, []))[0]
    assert close.event_type == "NC_TARGET"
    assert await h.shell.apply_action([], _to_action(close)) == []
    assert await h.shell.apply_action([], _to_action(close)) == []  # second close is a no-op
    with structlog.testing.capture_logs() as logs:
        assert await h.shell.apply_action([], action) == []  # same-day reopen hits UNIQUE key
    assert any(r["event"] == "nifty_calendar.duplicate_trade_dropped" for r in logs)


@pytest.mark.asyncio
async def test_close_without_mid_raises_before_writing(h: Harness) -> None:
    await h.enter()
    pos = h.store.get_positions(MONTHLY.strategy_name)
    action = ApprovedAction(
        "CLOSE_X", [LegClose(p.leg_role, p.instrument_key) for p in pos], [], "x", 1, {"mids": {}}
    )
    with pytest.raises(ValueError, match="no mid"):
        await h.shell.apply_action([], action)
    assert len(h.store.get_positions(MONTHLY.strategy_name)) == 4


@pytest.mark.asyncio
async def test_missing_quote_fails_closed_with_warn(h: Harness) -> None:
    await h.enter()
    h.now = datetime(2026, 10, 1, 11, 0, tzinfo=_IST)
    h.near = _chain(SPOT, NEAR, {22700: (("0", "0", "0.5", "20", "14"), NEAR_ROWS[22700][1])})
    events = await h.shell.check_signals(h.near, [])
    assert [(e.event_type, e.severity) for e in events] == [("NC_SNAPSHOT_UNAVAILABLE", "WARN")]


@pytest.mark.asyncio
async def test_no_variant_branch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    alt = dataclasses.replace(MONTHLY, name="alt", strategy_name="paper_nifty_calendar_alt")
    h = Harness(tmp_path, monkeypatch, config=alt)
    positions = await h.enter()
    assert {p.strategy_name for p in positions} == {"paper_nifty_calendar_alt"}
    source = inspect.getsource(shell_module)
    for needle in (
        "variant ==",
        "config.name ==",
        "MONTHLY",
        "BIWEEKLY",
        '"monthly"',
        '"biweekly"',
    ):
        assert needle not in source
