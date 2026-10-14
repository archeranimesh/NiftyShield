"""Offline walk of a full month across both calendar variants (CB-4).

Drives the real entry script and both real shells (``build_calendar_shell``) over one shared
in-memory ledger, one trading day at a time, the way the two cron entries and the monitor daemon
would. Chains are fixtures; nothing touches the network.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from scripts.strategies.nifty_calendar import paper_calendar_entry as entry_mod
from src.instruments.lookup import InstrumentLookup
from src.market_calendar import is_trading_day
from src.models.options import OptionChain
from src.nifty_calendar.config import BIWEEKLY, MONTHLY
from src.nifty_calendar.cycle import BiweeklyCyclePolicy, MonthlyCyclePolicy, active_variant
from src.paper.cycle_pnl import reconstruct_cycles
from src.paper.models import PaperPosition
from src.paper.store import PaperStore
from src.strategy import nifty_calendar_v1 as shell_module
from src.strategy.nifty_calendar_factory import build_calendar_shell
from src.strategy.nifty_calendar_state import SHORT_CALL, resolve_open_legs
from src.strategy.nifty_calendar_v1 import NiftyCalendarV1
from tests.unit.strategy.test_nifty_calendar_v1 import (
    FAR_ROWS,
    NEAR_ROWS,
    SPOT,
    _chain,
    _to_action,
)

_IST = ZoneInfo("Asia/Kolkata")
LISTED = [
    date(2026, 9, 29), date(2026, 10, 6), date(2026, 10, 13), date(2026, 10, 20),
    date(2026, 10, 27), date(2026, 11, 3), date(2026, 11, 10), date(2026, 11, 17),
    date(2026, 11, 23), date(2026, 12, 1), date(2026, 12, 29),
]  # fmt: skip
MONTHLY_EXPIRIES = [date(2026, 9, 29), date(2026, 10, 27), date(2026, 11, 23), date(2026, 12, 29)]
STRIKES = (22000, 22100, 22200, 22300, 22600, 22700, 23100, 23200, 23300)
# Fixture chains carry the same Greeks the shell tests use; the bi-weekly vega cap is relaxed the
# way those tests relax it, because one static fixture cannot satisfy both variants' real caps.
BW_CFG = dataclasses.replace(BIWEEKLY, vega_cap=Decimal("20"))
CONFIGS = {MONTHLY.name: MONTHLY, BIWEEKLY.name: BW_CFG}


def _lookup() -> InstrumentLookup:
    insts, n = [], 1000
    for exp in LISTED:
        for strike in STRIKES:
            for typ in ("CE", "PE"):
                n += 1
                insts.append(
                    {"segment": "NSE_FO", "instrument_type": typ, "underlying_symbol": "NIFTY",
                     "strike_price": float(strike), "expiry": exp.isoformat(),
                     "instrument_key": f"NSE_FO|{n}"}
                )  # fmt: skip
    return InstrumentLookup(insts)


class Walk:
    """Two wired shells, one ledger, a movable clock and a role-aware chain feed."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.now = datetime(2026, 9, 30, 10, 35, tzinfo=_IST)
        self.near_expiry: date = LISTED[0]  # which expiry the feed serves as the near chain
        self.lookup = _lookup()
        self.store = PaperStore(tmp_path / "db.sqlite", instrument_lookup=self.lookup)
        self.broker = MagicMock()
        self.broker.get_option_chain = AsyncMock(side_effect=lambda _i, exp: [{"expiry": exp}])
        self.broker.get_order_margin = AsyncMock(
            return_value={"required_margin": 238593.0, "final_margin": 90767.0}
        )
        self.notifier = MagicMock()
        self.notifier.send_plain_message = AsyncMock(return_value=True)
        self.notifier.send_notification = AsyncMock()
        self.notifier.send_photo = AsyncMock()
        for module in (entry_mod, shell_module):
            monkeypatch.setattr(module, "parse_upstox_option_chain", self._parse)
        monkeypatch.setattr(entry_mod, "send_payoff_chart", AsyncMock())
        monkeypatch.setattr(entry_mod, "ensure_registered", lambda: None)
        monkeypatch.setattr(
            "src.strategy.reentry_mixin.load_vix_series",
            lambda _d: pd.Series(np.linspace(10, 30, 252)),
        )
        self.shells: dict[str, NiftyCalendarV1] = {
            name: build_calendar_shell(
                broker=self.broker,
                store=self.store,
                notifier=self.notifier,
                lookup=self.lookup,
                config=cfg,
                today=self.now.date(),
                clock=lambda: self.now,
                vix_data_dir=tmp_path,
            )  # fmt: skip
            for name, cfg in CONFIGS.items()
        }

    def _parse(self, raw: list[dict[str, str]]) -> OptionChain:
        expiry = date.fromisoformat(raw[0]["expiry"])
        if expiry != self.near_expiry:
            return _chain(SPOT, expiry, FAR_ROWS)
        return _chain(SPOT, expiry, NEAR_ROWS)

    def held(self, name: str) -> list[PaperPosition]:
        return [p for p in self.store.get_positions(CONFIGS[name].strategy_name) if p.net_qty]

    async def try_entries(self) -> dict[str, str]:
        """Run both entry crons as the day's 10:35 job would; return each outcome code."""
        out: dict[str, str] = {}
        for name, shell in self.shells.items():
            policies = entry_mod.build_cycle_policies(self.lookup, self.now.date())
            plan = policies[name].entry_window(self.now.date())
            self.near_expiry = plan.near_expiry if plan else self.near_expiry
            out[name] = await entry_mod.run_entry(
                shell=shell, store=self.store, broker=self.broker, lookup=self.lookup,
                notifier=self.notifier, now=self.now, dry_run=False,
            )  # fmt: skip
        return out

    async def evaluate_exits(self) -> dict[str, list[str]]:
        """Run the monitor's near-expiry exit check for every open structure."""
        out: dict[str, list[str]] = {}
        for name, shell in self.shells.items():
            held = self.held(name)
            if not held:
                continue
            near = resolve_open_legs(held, self.lookup)[SHORT_CALL].expiry
            self.near_expiry = near
            events = await shell.check_signals(self._parse([{"expiry": near.isoformat()}]), [])
            out[name] = [e.event_type for e in events]
            for event in events:
                await shell.apply_action([], _to_action(event))
        return out


@pytest.fixture
def walk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Walk:
    return Walk(tmp_path, monkeypatch)


async def _run_days(walk: Walk, first: date, last: date) -> list[dict[str, Any]]:
    """One row per calendar day: entry outcomes, who was open after entry, and exit events."""
    log: list[dict[str, Any]] = []
    day = first
    while day <= last:
        walk.now = datetime(day.year, day.month, day.day, 10, 35, tzinfo=_IST)
        entries = await walk.try_entries()
        open_after_entry = {n for n in CONFIGS if walk.held(n)}
        walk.now = walk.now.replace(hour=15, minute=20)
        exits = await walk.evaluate_exits()
        log.append({"day": day, "entries": entries, "open": open_after_entry, "exits": exits})
        day += timedelta(days=1)
    return log


# The entry path builds policies with the real NSE holiday YAML, so the dates below are coupled to it.
FIRST, LAST = date(2026, 9, 30), date(2026, 11, 20)


@pytest.fixture
async def log(walk: Walk) -> list[dict[str, Any]]:
    return await _run_days(walk, FIRST, LAST)


def _entered(log: list[dict[str, Any]]) -> list[tuple[date, str]]:
    return [(r["day"], n) for r in log for n, out in r["entries"].items() if out == "ENTERED"]


@pytest.mark.asyncio
async def test_full_month_two_variants(log: list[dict[str, Any]]) -> None:
    """Monthly, back-to-back bi-weeklies, then the next monthly, each entered once its turn comes."""
    entered = _entered(log)
    names = [n for _, n in entered]
    assert names[0] == "monthly" and entered[0][0] == date(2026, 9, 30)
    first_next_monthly = names.index("monthly", 1)
    assert first_next_monthly >= 2  # at least two bi-weeklies fit before the next monthly
    assert set(names[1:first_next_monthly]) == {"biweekly"}
    assert entered[first_next_monthly][0] == date(2026, 10, 28)  # session after 27 Oct expiry
    assert names[first_next_monthly + 1] == "biweekly"
    for row in log:  # a date never sees two entries
        assert list(row["entries"].values()).count("ENTERED") <= 1


@pytest.mark.asyncio
async def test_no_overlap_between_variants(log: list[dict[str, Any]]) -> None:
    """The bi-weekly waits for the monthly to close; the guard fires at least once in the month."""
    assert all(len(r["open"]) <= 1 for r in log)
    blocked = [r["day"] for r in log if "OTHER_VARIANT_OPEN" in r["entries"].values()]
    assert blocked, "fixture never exercised the guard: monthly closed before the bi-weekly window"
    for day in blocked:  # the blocked variant is the one whose window was open, never the holder
        row = next(r for r in log if r["day"] == day)
        assert row["entries"]["biweekly"] == "OTHER_VARIANT_OPEN"


@pytest.mark.asyncio
async def test_each_close_has_exit_event(walk: Walk, log: list[dict[str, Any]]) -> None:
    """Every close recorded one exit event, and cycle P&L sees one 8-trade round trip each."""
    entered = _entered(log)
    for name, cfg in CONFIGS.items():
        closes = sum(len(r["exits"].get(name, [])) for r in log)
        assert closes > 0
        assert len(walk.store.get_open_exit_events(cfg.strategy_name)) == closes
        closed = [
            c for c in reconstruct_cycles(walk.store.get_trades(cfg.strategy_name)) if not c.is_open
        ]
        assert len(closed) == closes
        assert all(len(c.trades) == 8 for c in closed)  # four legs in, four legs out
        assert closes <= sum(1 for _, n in entered if n == name)
    for cfg in CONFIGS.values():
        assert all(is_trading_day(t.trade_date) for t in walk.store.get_trades(cfg.strategy_name))


@pytest.mark.asyncio
async def test_holiday_month_variant() -> None:
    """A holiday on the monthly entry day moves the window; every date still has one owner."""
    holidays = {date(2026, 9, 30), date(2026, 10, 13)}

    def trading(d: date) -> bool:
        return d.weekday() < 5 and d not in holidays

    policies = {
        "monthly": MonthlyCyclePolicy(MONTHLY_EXPIRIES, trading, MONTHLY),
        "biweekly": BiweeklyCyclePolicy(LISTED, MONTHLY_EXPIRIES, trading, BW_CFG, MONTHLY),
    }
    day = FIRST
    while day <= LAST:
        windows = [n for n, p in policies.items() if p.entry_window(day) is not None]
        assert len(windows) <= 1, (day, windows)
        assert active_variant(day, policies) == (windows[0] if windows else None)
        if day in holidays:
            assert windows == []
        day += timedelta(days=1)
    assert policies["monthly"].entry_window(date(2026, 10, 1)) is not None
