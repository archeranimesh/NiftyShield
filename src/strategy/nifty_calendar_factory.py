"""Builds a wired NiftyCalendarV1 for the entry script, snapshot script and monitor daemon."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.client.protocol import BrokerClient
from src.instruments.lookup import InstrumentLookup
from src.nifty_calendar.config import BIWEEKLY, MONTHLY, CalendarVariantConfig
from src.nifty_calendar.cycle import BiweeklyCyclePolicy, CyclePolicy, MonthlyCyclePolicy
from src.nifty_calendar.exit_rules import BiweeklyExitRule, MonthlyExitRule
from src.nifty_calendar.expiries import monthly_expiries
from src.nifty_calendar.selector import WingStructureSelector
from src.notifications.protocol import NotifierProtocol
from src.paper.store import PaperStore
from src.strategy.executor import PaperFillSimulator
from src.strategy.nifty_calendar_v1 import NiftyCalendarV1

_IST = ZoneInfo("Asia/Kolkata")

PolicyBuilder = Callable[[list[date], date, CalendarVariantConfig], CyclePolicy]


@dataclass(frozen=True)
class VariantEntry:
    """One registered variant: its config, cycle-policy builder and exit-rule class."""

    config: CalendarVariantConfig
    build_policy: PolicyBuilder
    rule_cls: type[MonthlyExitRule] | type[BiweeklyExitRule]


def _monthly_policy(listed: list[date], today: date, config: CalendarVariantConfig) -> CyclePolicy:
    return MonthlyCyclePolicy(monthly_expiries(listed, today), config=config)


def _biweekly_policy(listed: list[date], today: date, config: CalendarVariantConfig) -> CyclePolicy:
    return BiweeklyCyclePolicy(
        sorted(set(listed)), monthly_expiries=monthly_expiries(listed, today), config=config
    )


# Variant name -> entry; a further variant is one more row.
REGISTRY: dict[str, VariantEntry] = {
    MONTHLY.name: VariantEntry(MONTHLY, _monthly_policy, MonthlyExitRule),
    BIWEEKLY.name: VariantEntry(BIWEEKLY, _biweekly_policy, BiweeklyExitRule),
}


def build_cycle_policies(lookup: InstrumentLookup, today: date) -> dict[str, CyclePolicy]:
    """Build every registered variant's cycle policy, keyed by variant name.

    Used by the entry handoff: ``active_variant(today, policies)`` names the one variant
    whose entry window is open.

    Args:
        lookup: BOD instrument lookup; supplies the listed expiries.
        today: Date the expiry sets are built for.
    """
    listed = [date.fromisoformat(e) for e in lookup.get_all_option_expiries("NIFTY")]
    return {n: v.build_policy(listed, today, v.config) for n, v in REGISTRY.items()}


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
    entry = REGISTRY[config.name]
    listed = [date.fromisoformat(e) for e in lookup.get_all_option_expiries("NIFTY")]
    return NiftyCalendarV1(
        broker=broker,
        store=store,
        notifier=notifier,
        simulator=PaperFillSimulator(),
        selector=WingStructureSelector(),
        exit_rule=entry.rule_cls(config),
        cycle_policy=entry.build_policy(listed, today or clock().date(), config),
        config=config,
        lookup=lookup,
        vix_fn=vix_fn,
        clock=clock,
        vix_data_dir=vix_data_dir,
    )
