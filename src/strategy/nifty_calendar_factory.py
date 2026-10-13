"""Builds a wired NiftyCalendarV1 for the entry script, snapshot script and monitor daemon."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.client.protocol import BrokerClient
from src.instruments.lookup import InstrumentLookup
from src.nifty_calendar.config import MONTHLY, CalendarVariantConfig
from src.nifty_calendar.cycle import MonthlyCyclePolicy
from src.nifty_calendar.exit_rules import MonthlyExitRule
from src.nifty_calendar.expiries import monthly_expiries
from src.nifty_calendar.selector import WingStructureSelector
from src.notifications.protocol import NotifierProtocol
from src.paper.store import PaperStore
from src.strategy.executor import PaperFillSimulator
from src.strategy.nifty_calendar_v1 import NiftyCalendarV1

_IST = ZoneInfo("Asia/Kolkata")

# Variant name -> (policy class, exit-rule class); a second variant is one more entry.
_VARIANTS = {MONTHLY.name: (MonthlyCyclePolicy, MonthlyExitRule)}


def build_calendar_shell(
    *,
    broker: BrokerClient,
    store: PaperStore,
    notifier: NotifierProtocol | None,
    lookup: InstrumentLookup,
    config: CalendarVariantConfig = MONTHLY,
    today: date | None = None,
    vix_fn: Callable[[], float | None] = lambda: None,
    clock: Callable[[], datetime] = lambda: datetime.now(tz=_IST),
    vix_data_dir: Path = Path("data/historical/ohlc/india_vix"),
) -> NiftyCalendarV1:
    """Wire the shell for ``config`` with its cycle policy, exit rule and wing selector.

    Args:
        broker: Far-chain source.
        store: Paper ledger.
        notifier: Telegram notifier (may be None).
        lookup: BOD instrument lookup; also supplies the listed expiries.
        config: Variant configuration; picks the policy and exit rule.
        today: Date the expiry set is built for (defaults to the clock's date).
        vix_fn: Returns current India VIX for fill slippage, or None.
        clock: IST clock.
        vix_data_dir: VIX history used by the re-entry check.

    Raises:
        KeyError: ``config.name`` has no registered variant.
    """
    policy_cls, rule_cls = _VARIANTS[config.name]
    listed = [date.fromisoformat(e) for e in lookup.get_all_option_expiries("NIFTY")]
    expiries = monthly_expiries(listed, today or clock().date())
    return NiftyCalendarV1(
        broker=broker,
        store=store,
        notifier=notifier,
        simulator=PaperFillSimulator(),
        selector=WingStructureSelector(),
        exit_rule=rule_cls(config),
        cycle_policy=policy_cls(expiries, config=config),
        config=config,
        lookup=lookup,
        vix_fn=vix_fn,
        clock=clock,
        vix_data_dir=vix_data_dir,
    )
