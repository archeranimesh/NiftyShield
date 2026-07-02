# scripts/strategies/ic/ic_entry_gates.py
"""Shared pre-entry gate helpers for Iron Condor entry scripts.

Three checks are identical between V1 and V2:
  - Duplicate position guard
  - IVR gate (load VIX series, compute IVR, block or bypass)
  - Expiry resolution + DTE window check

The portfolio-delta gate is NOT here — V1 adjusts wings via fixed points
(wing_width_points) while V2 rescans the chain at long_wing_delta_target.
That divergence makes a shared helper awkward; each entry script keeps it
inline.

Usage::

    from scripts.strategies.ic.ic_entry_gates import (
        check_duplicate,
        resolve_ivr,
        resolve_expiry,
    )
"""

from __future__ import annotations

import calendar
import sys
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import structlog

from src.backtest.ivr import compute_ivr
from src.backtest.vix_ingest import fetch_vix_latest, load_vix_series
from src.instruments.lookup import InstrumentLookup
from src.intraday.market_store import IntradayMarketStore

_log = structlog.get_logger("scripts.strategies.ic.ic_entry_gates")


# ---------------------------------------------------------------------------
# Calendar helper
# ---------------------------------------------------------------------------


def _last_tuesday_of_month(year: int, month: int) -> date:
    """Return the last Tuesday of *month* in *year*.

    Nifty monthly expiry falls on the last Tuesday of each calendar month
    (SEBI change effective April 2026). This function computes that date
    purely from the calendar — no market-data dependency.

    Args:
        year: Calendar year (e.g. 2026).
        month: Calendar month (1–12).

    Returns:
        The last Tuesday as a ``datetime.date``.
    """
    _, last_day = calendar.monthrange(year, month)
    last = date(year, month, last_day)
    # weekday(): Monday=0 … Sunday=6; Tuesday=1
    days_back = (last.weekday() - 1) % 7
    return last - timedelta(days=days_back)


# ---------------------------------------------------------------------------
# Gate 0 — Post-expiry guard (monthly cadence)
# ---------------------------------------------------------------------------


def _most_recently_settled_expiry(today: date) -> date:
    """Return the last Nifty monthly expiry that has settled on or before *today*.

    Checks the current calendar month's last Tuesday first; if that date is
    still in the future relative to *today*, the settled cycle is the
    previous calendar month's last Tuesday instead. This is the reference
    point for the same-day settlement guard — never the expiry of the cycle
    being entered.

    Args:
        today: The date to evaluate against.

    Returns:
        The most recently settled (or currently settling) expiry date.
    """
    current = _last_tuesday_of_month(today.year, today.month)
    if current <= today:
        return current
    year, month = today.year, today.month - 1
    if month == 0:
        year, month = year - 1, 12
    return _last_tuesday_of_month(year, month)


def _post_expiry_gate() -> None:
    """Block entry only on the same day the most recent monthly expiry settles.

    Computes the most recently settled Nifty monthly expiry (current month's
    last Tuesday if it has already occurred, otherwise the previous month's)
    and exits with code 1 only if today is on or before that settlement date.
    A fresh new-cycle entry (today > last settled expiry) is always allowed,
    even on the very next day after settlement.

    Holiday handling: if the last Tuesday is a trading holiday, no one runs
    entry scripts that day. The next trading day will always satisfy
    ``today > settled_expiry`` — so the calendar gate passes without any
    special-case code.

    Raises:
        SystemExit(1): If today ≤ the most recently settled expiry.
    """
    today = date.today()
    expiry = _most_recently_settled_expiry(today)
    if today <= expiry:
        print(
            f"ERROR: post_expiry_gate: settlement for {expiry} has not yet "
            f"completed (today={today}). Entry is only valid after settlement.",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Gate 1 — Duplicate position guard
# ---------------------------------------------------------------------------


def check_duplicate(
    store: object,
    strategy_name: str,
    notifier: Callable[[str], None] | None = None,
) -> None:
    """Exit with code 1 if an active position already exists for *strategy_name*.

    Args:
        store: Open PaperStore instance.
        strategy_name: Exact DB strategy name (e.g. ``paper_ic_nifty_v2_monthly``).
        notifier: Optional sync callable for gate-failure Telegram alerts.
            Called before sys.exit(1); any exception it raises is swallowed.
    """
    open_positions = store.get_positions(strategy_name)
    if any(pos.net_qty != 0 for pos in open_positions):
        if notifier is not None:
            try:
                notifier(
                    f"⚠️ IC V2 Entry BLOCKED — {strategy_name}\n"
                    f"Gate: duplicate\n"
                    f"Reason: Active position already exists"
                )
            except Exception:  # noqa: BLE001
                pass
        print(
            f"ERROR: active position already exists for {strategy_name}",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Gate 2 — IVR gate
# ---------------------------------------------------------------------------


def resolve_ivr(
    db_path: Path,
    ivr_gate: Decimal,
    force_entry: bool,
    notifier: Callable[[str], None] | None = None,
) -> float | None:
    """Load VIX series, compute IVR, apply gate.

    Returns the computed IVR value (float) or ``None`` if data is unavailable.
    Calls ``sys.exit(1)`` when IVR is below *ivr_gate* and *force_entry* is False.
    Logs a WARNING and continues when *force_entry* is True.

    Args:
        db_path: Path to paper trading SQLite DB (used by IntradayMarketStore).
        ivr_gate: Minimum acceptable IVR for entry.
        force_entry: When True, bypass the gate with a warning.
        notifier: Optional sync callable for gate-failure Telegram alerts.
            Called only when IVR is below the gate threshold (not on data-missing).
            Any exception it raises is swallowed.

    Returns:
        Computed IVR as float, or None if VIX data is unavailable.
    """
    vix_data_dir = Path("data/historical/ohlc/india_vix")
    ivr: float | None = None

    if vix_data_dir.exists():
        try:
            series = load_vix_series(vix_data_dir)
            vix_today = IntradayMarketStore(db_path).get_latest_vix_today()
            if vix_today is None:
                vix_today = fetch_vix_latest()
            if vix_today is not None:
                ivr = compute_ivr(vix_today, series)
        except Exception as exc:  # noqa: BLE001 — broad catch by design; IVR is non-fatal
            _log.warning("vix.load_failed", error=str(exc))
    else:
        _log.warning("vix.dir_missing", path=str(vix_data_dir))

    if not force_entry:
        if ivr is None:
            print(
                "ERROR: India VIX IVR is None (insufficient data). Stop.",
                file=sys.stderr,
            )
            sys.exit(1)
        if ivr < float(ivr_gate):
            if notifier is not None:
                try:
                    notifier(
                        f"⚠️ IC V2 Entry BLOCKED\nGate: ivr\nIVR: {ivr:.2f} / Gate: {ivr_gate:.2f}"
                    )
                except Exception:  # noqa: BLE001
                    pass
            print(
                f"ERROR: India VIX IVR = {ivr:.2f} below gate threshold of {ivr_gate:.2f}.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        if ivr is None or ivr < float(ivr_gate):
            _log.warning("force_entry.ivr_bypass", ivr=ivr, gate=ivr_gate)

    if ivr is not None:
        print(f"INFO: India VIX IVR = {ivr:.2f} (gate={ivr_gate})")

    return ivr


# ---------------------------------------------------------------------------
# Gate 3 — Expiry resolution + DTE window check
# ---------------------------------------------------------------------------


def resolve_expiry(
    bod_path: Path,
    expiry_bucket: str,
    dte_warn_lo: int,
    dte_warn_hi: int,
) -> tuple[InstrumentLookup, str, int]:
    """Resolve the target expiry from the BOD file and validate the DTE window.

    Args:
        bod_path: Path to the BOD instruments JSON file.
        expiry_bucket: Expiry bucket label: ``"monthly"``, ``"weekly"``, etc.
        dte_warn_lo: Minimum acceptable DTE (warn if below).
        dte_warn_hi: Maximum acceptable DTE (warn if above).

    Returns:
        Tuple of ``(InstrumentLookup, expiry_str, dte)``.
        ``expiry_str`` is ISO-format (``"YYYY-MM-DD"``); ``dte`` is calendar days.

    Raises:
        SystemExit(1): BOD file missing, expiry resolution fails, or no candidate found.
    """
    if not bod_path.exists():
        print(f"ERROR: BOD file not found at {bod_path}", file=sys.stderr)
        sys.exit(1)

    try:
        lookup = InstrumentLookup.from_file(bod_path)
        expiries = lookup.get_expiry_candidates(
            underlying="NIFTY",
            today=date.today(),
            preference=[expiry_bucket],
        )
    except Exception as exc:  # noqa: BLE001 — broad catch; BOD failures must exit cleanly
        print(
            f"ERROR: failed to load BOD or resolve expiries: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    expiry_str: str | None = None
    for label, exp_str in expiries:
        if label == expiry_bucket:
            expiry_str = exp_str
            break

    if expiry_str is None:
        print(
            f"ERROR: no {expiry_bucket} expiry candidate found. Stop.",
            file=sys.stderr,
        )
        sys.exit(1)

    expiry_date = date.fromisoformat(expiry_str)
    dte = (expiry_date - date.today()).days

    if dte < dte_warn_lo or dte > dte_warn_hi:
        _log.warning(
            "dte.outside_range",
            dte=dte,
            min_dte=dte_warn_lo,
            max_dte=dte_warn_hi,
        )
    else:
        print(f"INFO: selected expiry = {expiry_str} (DTE={dte})")

    return lookup, expiry_str, dte
