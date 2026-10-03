"""Pure watchlist rules for the near-expiry gamma strategy (strategy doc §5b).

No I/O and no store access: the caller passes today's snapshots, the prior
snapshot history and the currently active entries, and applies the returned
decision. Rule semantics are fixed by decisions D3/D4 of the
``risk-gamma-phase-a`` story.
"""

from __future__ import annotations

import datetime
import typing
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from src.gamma.models import GammaChainSnapshot, GammaWatchlistEntry

MIN_DTE = 2
MAX_DTE = 6
MAX_DISTANCE_ADD = Decimal("0.04")
MIN_GEARING = Decimal("3.0")
MIN_OI = 1000
ELEVATE_DISTANCE = Decimal("0.03")
ELEVATE_OI_CHANGE = Decimal("0.10")
REMOVE_DISTANCE = Decimal("0.05")
REMOVE_OI_CHANGE = Decimal("-0.20")
GEARING_AVG_DAYS = 3

_Key = tuple[datetime.date, int, str]


@dataclass(frozen=True)
class WatchlistRemoval:
    """An active entry to mark removed, with the §5b reason."""

    expiry_date: datetime.date
    strike: int
    option_type: typing.Literal["CE", "PE"]
    removal_reason: str


@dataclass(frozen=True)
class WatchlistDecision:
    """Outcome of one watchlist evaluation.

    Attributes:
        add: New (or revived) entries to upsert.
        retain: Existing active entries with refreshed state to upsert.
        remove: Active entries to mark removed.
        elevate: Entries from ``add`` / ``retain`` flagged elevated today.
    """

    add: tuple[GammaWatchlistEntry, ...]
    retain: tuple[GammaWatchlistEntry, ...]
    remove: tuple[WatchlistRemoval, ...]
    elevate: tuple[GammaWatchlistEntry, ...]


def _qualifies(s: GammaChainSnapshot) -> bool:
    """Return True when the five §5b inclusion criteria hold (D4 None handling)."""
    if s.gamma_gearing is None or s.oi is None or s.distance_pct is None:
        return False
    return (
        MIN_DTE <= s.dte_calendar <= MAX_DTE
        and s.distance_pct <= MAX_DISTANCE_ADD
        and s.gamma_gearing >= MIN_GEARING
        and s.oi >= MIN_OI
        and (s.oi_change_1d is None or s.oi_change_1d >= Decimal("0"))
    )


def _elevated(
    s: GammaChainSnapshot,
    yesterday: GammaChainSnapshot | None,
    prior_gearing: list[Decimal | None],
) -> bool:
    """Return True when inclusion plus all elevation criteria hold today."""
    if not _qualifies(s) or yesterday is None or yesterday.distance_pct is None:
        return False
    if s.oi_change_1d is None or s.oi_change_1d < ELEVATE_OI_CHANGE:
        return False
    if len(prior_gearing) < GEARING_AVG_DAYS or None in prior_gearing:
        return False
    avg = sum(prior_gearing, Decimal(0)) / len(prior_gearing)
    return (
        s.distance_pct <= ELEVATE_DISTANCE
        and s.distance_pct < yesterday.distance_pct
        and s.gamma_gearing > avg
    )


def _removal_reason(s: GammaChainSnapshot, yesterday: GammaChainSnapshot | None) -> str | None:
    """Return the removal reason if a two-consecutive-day rule fires, else None."""
    if yesterday is None:
        return None
    if (
        s.distance_pct is not None
        and yesterday.distance_pct is not None
        and s.distance_pct > REMOVE_DISTANCE
        and yesterday.distance_pct > REMOVE_DISTANCE
    ):
        return "spot_moved_away"
    if (
        s.oi_change_1d is not None
        and yesterday.oi_change_1d is not None
        and s.oi_change_1d < REMOVE_OI_CHANGE
        and yesterday.oi_change_1d < REMOVE_OI_CHANGE
    ):
        return "oi_unwinding"
    return None


def _entry(
    s: GammaChainSnapshot,
    today: datetime.date,
    added_date: datetime.date,
    elevated: bool,
) -> GammaWatchlistEntry:
    return GammaWatchlistEntry(
        expiry_date=s.expiry_date,
        strike=s.strike,
        option_type=s.option_type,
        added_date=added_date,
        last_seen_date=today,
        removed_date=None,
        removal_reason=None,
        distance_pct=s.distance_pct,
        gamma_gearing=s.gamma_gearing,
        oi=s.oi,
        oi_change_1d=s.oi_change_1d,
        days_on_watchlist=(today - added_date).days + 1,
        elevated=elevated,
        elevation_reason="closing_gearing_oi_growth" if elevated else None,
    )


def evaluate_watchlist(
    today_snaps: Sequence[GammaChainSnapshot],
    history: Sequence[GammaChainSnapshot],
    active: Sequence[GammaWatchlistEntry],
    today: datetime.date,
) -> WatchlistDecision:
    """Apply the §5b add / retain / remove / elevate rules.

    Add criteria gate new entries only; an active entry that stops qualifying
    is retained unless a removal rule fires (D4). "Yesterday" is the most
    recent prior snapshot date in ``history`` and the gearing average is the
    mean over the last three prior dates (D3); a strike missing from
    yesterday never triggers a removal.

    Args:
        today_snaps: Today's snapshots for the current-week expiry only.
        history: Latest snapshot per (strike, option_type) for each prior
            snapshot date, strictly before ``today`` (any order).
        active: All currently active watchlist entries, any expiry.
        today: Evaluation date.

    Returns:
        The decision; the caller applies it through the store.
    """
    dates = sorted({h.snapshot_date for h in history}, reverse=True)
    by_key = {(h.snapshot_date, h.strike, h.option_type): h for h in history}
    today_by = {(s.expiry_date, s.strike, s.option_type): s for s in today_snaps}
    active_by = {(e.expiry_date, e.strike, e.option_type): e for e in active}

    def on(day: datetime.date, s: GammaChainSnapshot) -> GammaChainSnapshot | None:
        return by_key.get((day, s.strike, s.option_type))

    yest_date = dates[:1]

    add, retain, remove, elevate = [], [], [], []
    for key, e in active_by.items():
        s = today_by.get(key)
        if e.expiry_date < today:
            reason = "expired"
        elif s is None:
            continue
        else:
            reason = _removal_reason(s, on(yest_date[0], s) if yest_date else None)
        if reason is not None:
            remove.append(WatchlistRemoval(e.expiry_date, e.strike, e.option_type, reason))

    removed = {(r.expiry_date, r.strike, r.option_type) for r in remove}
    for key, s in today_by.items():
        if key in removed or (key not in active_by and not _qualifies(s)):
            continue
        yest = on(yest_date[0], s) if yest_date else None
        prior = [
            g.gamma_gearing if g else None for g in (on(d, s) for d in dates[:GEARING_AVG_DAYS])
        ]
        is_elev = _elevated(s, yest, prior)
        existing = active_by.get(key)
        e = _entry(s, today, existing.added_date if existing else today, is_elev)
        (retain if existing else add).append(e)
        if is_elev:
            elevate.append(e)
    return WatchlistDecision(tuple(add), tuple(retain), tuple(remove), tuple(elevate))
