"""Phase B exit rules E1/E2/E3 (strategy doc section 8).

Pure and zero-I/O. Each rule is a small predicate
``(ExitPosition, ExitTick, ExitConfig) -> ExitReason | None``; ``evaluate_exit``
walks an ordered rule list (E1, E2, E3) and the first rule to fire wins.
Thresholds live in ``ExitConfig``; rule bodies hold no threshold literals.

Interpretations chosen where section 8 is silent (they change P&L):

* "mark" is the **bid** at the scan, the price a paper exit fills at
  (section 8 exit accounting: never mid). A ``None`` bid never fires a
  price rule (E1, E2 stop) and counts as "not in profit" for the E3 carry.
* E1 target is ``bid >= profit_multiple * entry_ask`` (inclusive); E2 stop is
  ``bid <= stop_mark`` (inclusive, absolute rupees, not a multiple).
* E2 liquidity: ``ask_qty == 0`` on this scan and on the preceding
  ``zero_ask_scans - 1`` scans. The caller owns the streak counter
  (``ExitPosition.prior_zero_ask_scans``, consecutive earlier scans with zero
  ask qty); ``None`` ask qty (reduced mode) never fires it.
* E3 time stop is wall-clock IST time of the tick, keyed on the tick's
  calendar DTE (not on position age): DTE 0 closes at ``dte0_cutoff``
  (inclusive); DTE 1 closes at ``dte1_cutoff`` (inclusive) unless
  ``bid >= carry_multiple * entry_ask``. Overnight carries are re-checked on
  the next day's DTE 0 tick.
* Priority E1, E2 (stop, then liquidity), E3. E1 and the E2 stop cannot
  coincide (entry premium >= min_premium keeps 5x entry above the stop mark);
  an E1 and E2-liquidity tie resolves to E1 (priority order).
* ``exit_price`` on the decision is the tick bid (may be None); ``realised_r``
  is ``(exit_price - entry_ask) / entry_ask`` or None without a bid.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from enum import Enum

_DTE_EXPIRY_DAY = 0
_DTE_PRE_EXPIRY = 1


class ExitReason(str, Enum):
    """Why a position is closed."""

    E1_PROFIT_TARGET = "E1_PROFIT_TARGET"
    E2_STOP_LOSS = "E2_STOP_LOSS"
    E2_LIQUIDITY = "E2_LIQUIDITY"
    E3_TIME_STOP = "E3_TIME_STOP"


@dataclass(frozen=True)
class ExitConfig:
    """Every exit threshold (strategy doc section 8)."""

    profit_multiple: Decimal = Decimal(5)
    stop_mark: Decimal = Decimal("0.25")
    zero_ask_scans: int = 2
    dte0_cutoff: time = time(14, 30)
    dte1_cutoff: time = time(15, 0)
    carry_multiple: Decimal = Decimal("1.5")


@dataclass(frozen=True)
class ExitPosition:
    """Open paper position as the exit rules see it.

    Args:
        entry_ask: Ask at signal time (the conservative paper entry price).
        prior_zero_ask_scans: Consecutive earlier scans with zero ask qty.
    """

    entry_ask: Decimal
    prior_zero_ask_scans: int = 0


@dataclass(frozen=True)
class ExitTick:
    """One scan observation of the held contract (IST wall-clock time)."""

    at: time
    dte: int
    bid: Decimal | None
    ask_qty: int | None


@dataclass(frozen=True)
class ExitDecision:
    """A fired exit: reason, bid-based fill price and realised R."""

    reason: ExitReason
    exit_price: Decimal | None
    realised_r: Decimal | None


ExitRule = Callable[[ExitPosition, ExitTick, ExitConfig], "ExitReason | None"]


def e1_profit_target(p: ExitPosition, t: ExitTick, cfg: ExitConfig) -> ExitReason | None:
    if t.bid is None:
        return None
    hit = t.bid >= cfg.profit_multiple * p.entry_ask
    return ExitReason.E1_PROFIT_TARGET if hit else None


def e2_stop_loss(p: ExitPosition, t: ExitTick, cfg: ExitConfig) -> ExitReason | None:
    if t.bid is None:
        return None
    return ExitReason.E2_STOP_LOSS if t.bid <= cfg.stop_mark else None


def e2_liquidity(p: ExitPosition, t: ExitTick, cfg: ExitConfig) -> ExitReason | None:
    if t.ask_qty is None or t.ask_qty != 0:
        return None
    streak = p.prior_zero_ask_scans + 1
    return ExitReason.E2_LIQUIDITY if streak >= cfg.zero_ask_scans else None


def e3_time_stop(p: ExitPosition, t: ExitTick, cfg: ExitConfig) -> ExitReason | None:
    if t.dte == _DTE_EXPIRY_DAY:
        due = t.at >= cfg.dte0_cutoff
    elif t.dte == _DTE_PRE_EXPIRY:
        carry = t.bid is not None and t.bid >= cfg.carry_multiple * p.entry_ask
        due = t.at >= cfg.dte1_cutoff and not carry
    else:
        due = False
    return ExitReason.E3_TIME_STOP if due else None


DEFAULT_EXIT_RULES: tuple[ExitRule, ...] = (
    e1_profit_target,
    e2_stop_loss,
    e2_liquidity,
    e3_time_stop,
)


def evaluate_exit(
    position: ExitPosition,
    tick: ExitTick,
    config: ExitConfig,
    rules: tuple[ExitRule, ...] = DEFAULT_EXIT_RULES,
) -> ExitDecision | None:
    """Return the first exit that fires for this tick, else ``None``.

    Args:
        position: Open position (entry ask, zero-ask streak so far).
        tick: Current scan observation.
        config: Exit thresholds.
        rules: Ordered rules; first to fire wins.

    Returns:
        ``ExitDecision`` with reason, bid exit price and realised R, or None.
    """
    for rule in rules:
        reason = rule(position, tick, config)
        if reason is not None:
            return ExitDecision(reason, tick.bid, _realised_r(position, tick.bid))
    return None


def _realised_r(position: ExitPosition, exit_price: Decimal | None) -> Decimal | None:
    if exit_price is None or position.entry_ask <= 0:
        return None
    return (exit_price - position.entry_ask) / position.entry_ask
