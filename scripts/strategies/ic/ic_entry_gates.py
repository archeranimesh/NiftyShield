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
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import structlog

from src.backtest.ivr import compute_ivr
from src.backtest.vix_ingest import fetch_vix_latest, load_vix_series
from src.instruments.lookup import InstrumentLookup
from src.intraday.market_store import IntradayMarketStore
from src.paper.constants import STRATEGY_CSP, STRATEGY_FUTURES, STRATEGY_PROXY, STRATEGY_SPOT
from src.paper.models import GateViolation

_log = structlog.get_logger("scripts.strategies.ic.ic_entry_gates")


def make_gate_violation(
    gate_name: str,
    threshold: str,
    actual: str,
    strategy_name: str,
) -> GateViolation:
    """Build a GateViolation stamped with the current UTC time.

    Shared factory so every threshold-gate call site constructs the record
    identically. Only used under ``--log-only-gates`` mode — structural
    gates never produce a GateViolation.
    """
    return GateViolation(
        gate_name=gate_name,
        threshold=threshold,
        actual=actual,
        strategy_name=strategy_name,
        logged_at=datetime.now(timezone.utc),
    )


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

# BUG-004: weekly refresh_vix.py cron + observed ~1-2 trading-day VIX EOD
# publish lag means a few days of gap is routine, not a failure. 7 days
# tolerates a missed/late Monday run plus publish lag without crying wolf;
# anything beyond that is treated as gate-data-unavailable (same as ivr=None).
_MAX_VIX_WINDOW_STALENESS_DAYS = 7


def _is_vix_window_stale(series: pd.Series, today: date) -> bool:
    """Return True if the VIX window's most recent date lags *today* too far.

    Args:
        series: VIX daily-close series, date-indexed (as returned by
            ``load_vix_series``). May be empty or a non-Series stand-in in
            tests — treated as "cannot determine staleness", not stale.
        today: Reference date to compare the window's max date against.

    Returns:
        True if the window's max date lags *today* by more than
        ``_MAX_VIX_WINDOW_STALENESS_DAYS``. False if the window is fresh
        enough, or if its max date can't be determined (empty series, or a
        non-date index) — that case is already handled separately by
        ``compute_ivr``'s own length check.
    """
    try:
        if len(series) == 0:
            return False
        max_date = series.index.max()
    except (AttributeError, TypeError):
        return False
    if isinstance(max_date, pd.Timestamp):
        max_date = max_date.date()
    if not isinstance(max_date, date):
        return False
    return (today - max_date).days > _MAX_VIX_WINDOW_STALENESS_DAYS


def resolve_ivr(
    db_path: Path,
    ivr_gate: Decimal,
    force_entry: bool,
    notifier: Callable[[str], None] | None = None,
    *,
    log_only_gates: bool = True,
    strategy_name: str = "",
) -> tuple[float | None, GateViolation | None]:
    """Load VIX series, compute IVR, apply gate.

    ``ivr is None`` (stale/missing VIX window, per ``_is_vix_window_stale``)
    is a STRUCTURAL data-unavailability guard: ``log_only_gates`` never
    bypasses it (log-only mode only applies to the below-threshold path
    below). The pre-existing ``force_entry`` manual override can still
    bypass it, unchanged from prior behaviour — that flag was never scoped
    to threshold gates only, and changing that is out of scope here.

    The IVR-below-threshold path is a THRESHOLD gate. Under
    ``log_only_gates=True`` (default), a below-gate IVR no longer aborts —
    it returns a ``GateViolation`` for the caller to persist and the entry
    proceeds. ``force_entry`` remains a separate, pre-existing bypass with
    its own logged-WARNING behaviour (kept for backward compatibility).

    Args:
        db_path: Path to paper trading SQLite DB (used by IntradayMarketStore).
        ivr_gate: Minimum acceptable IVR for entry.
        force_entry: When True, bypass the gate with a warning (legacy path).
        notifier: Optional sync callable for gate-failure Telegram alerts.
            Called only when IVR is below the gate threshold (not on data-missing).
            Any exception it raises is swallowed.
        log_only_gates: When True (default), a below-gate IVR is recorded as
            a GateViolation instead of hard-blocking. When False, restores
            the original hard-block behaviour (subject to force_entry).
        strategy_name: DB strategy name, stamped onto any GateViolation.

    Returns:
        Tuple of (computed IVR as float or None, GateViolation or None).
        IVR is None only when VIX data is unavailable — that path always
        exits before returning.
    """
    vix_data_dir = Path("data/historical/ohlc/india_vix")
    ivr: float | None = None

    if vix_data_dir.exists():
        try:
            series = load_vix_series(vix_data_dir)
            if _is_vix_window_stale(series, date.today()):
                _log.warning(
                    "vix.window_stale",
                    window_max_date=str(series.index.max()),
                    threshold_days=_MAX_VIX_WINDOW_STALENESS_DAYS,
                )
            else:
                vix_today = IntradayMarketStore(db_path).get_latest_vix_today()
                if vix_today is None:
                    vix_today = fetch_vix_latest()
                if vix_today is not None:
                    ivr = compute_ivr(vix_today, series)
        except Exception as exc:  # noqa: BLE001 — broad catch by design; IVR is non-fatal
            _log.warning("vix.load_failed", error=str(exc))
    else:
        _log.warning("vix.dir_missing", path=str(vix_data_dir))

    violation: GateViolation | None = None

    # STRUCTURAL: ivr=None (stale/missing window) always hard-blocks,
    # regardless of force_entry or log_only_gates.
    if ivr is None:
        if force_entry:
            _log.warning("force_entry.ivr_bypass", ivr=ivr, gate=ivr_gate)
            return ivr, violation
        print(
            "ERROR: India VIX IVR is None (insufficient data). Stop.",
            file=sys.stderr,
        )
        sys.exit(1)

    if ivr < float(ivr_gate):
        if log_only_gates and not force_entry:
            _log.warning(
                "gate.ivr_violation_logged",
                ivr=ivr,
                gate=float(ivr_gate),
                strategy_name=strategy_name,
            )
            violation = make_gate_violation(
                gate_name="ivr",
                threshold=str(ivr_gate),
                actual=f"{ivr:.4f}",
                strategy_name=strategy_name,
            )
        elif force_entry:
            _log.warning("force_entry.ivr_bypass", ivr=ivr, gate=ivr_gate)
        else:
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

    print(f"INFO: India VIX IVR = {ivr:.2f} (gate={ivr_gate})")

    return ivr, violation


# ---------------------------------------------------------------------------
# Gate 3 — Expiry resolution + DTE window check
# ---------------------------------------------------------------------------


def resolve_expiry(
    bod_path: Path,
    expiry_bucket: str,
    dte_warn_lo: int,
    dte_warn_hi: int,
    *,
    strategy_name: str = "",
) -> tuple[InstrumentLookup, str, int, GateViolation | None]:
    """Resolve the target expiry from the BOD file and validate the DTE window.

    The DTE window is a THRESHOLD gate — it has never hard-blocked entry
    (only logged a WARNING). That behaviour is unchanged; this now also
    returns a ``GateViolation`` when the DTE falls outside the window so
    callers can persist it under ``--log-only-gates`` for retrospective
    analysis, consistent with the other threshold gates.

    Args:
        bod_path: Path to the BOD instruments JSON file.
        expiry_bucket: Expiry bucket label: ``"monthly"``, ``"weekly"``, etc.
        dte_warn_lo: Minimum acceptable DTE (warn if below).
        dte_warn_hi: Maximum acceptable DTE (warn if above).
        strategy_name: DB strategy name, stamped onto any GateViolation.

    Returns:
        Tuple of ``(InstrumentLookup, expiry_str, dte, GateViolation | None)``.
        ``expiry_str`` is ISO-format (``"YYYY-MM-DD"``); ``dte`` is calendar days.

    Raises:
        SystemExit(1): BOD file missing, expiry resolution fails, or no candidate found
            (all STRUCTURAL — never bypassed).
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

    violation: GateViolation | None = None
    if dte < dte_warn_lo or dte > dte_warn_hi:
        _log.warning(
            "dte.outside_range",
            dte=dte,
            min_dte=dte_warn_lo,
            max_dte=dte_warn_hi,
        )
        violation = make_gate_violation(
            gate_name="dte_window",
            threshold=f"[{dte_warn_lo}, {dte_warn_hi}]",
            actual=str(dte),
            strategy_name=strategy_name,
        )
    else:
        print(f"INFO: selected expiry = {expiry_str} (DTE={dte})")

    return lookup, expiry_str, dte, violation


# ---------------------------------------------------------------------------
# Gate 4 — Portfolio-delta scope filter (BUG-005 / B002.2)
# ---------------------------------------------------------------------------

# Non-IC strategies excluded from the IC portfolio-delta gate.
#
# paper_nifty_futures/proxy/spot: separate proxy/hedge books. BUG-002's
# root-cause investigation flagged pooling their delta into the IC
# delta-neutral gate as an open scope question; B002.2 decided to exclude
# them (Animesh, 2026-07-02) but the decision was never wired into the two
# entry scripts until BUG-005. See docs/bugs/bugs.md BUG-002 / BUG-005.
#
# paper_csp_nifty_v1 (STRATEGY_CSP): a separate, independently-managed
# strategy. It IS deliberately coupled into strike *selection* elsewhere in
# this module's callers (mode detection tilts put/call targets when CSP is
# open) — but as of 2026-07-02 there is no chain-derived delta wired into
# the portfolio-delta *gate* for it, only the crude net_qty/lot_size
# fallback, which overstates a short put's real delta ~3x and produces
# false blocks. Animesh (2026-07-02): during the paper-trading/data-
# collection phase, ICs should run independently of CSP for gating
# purposes — excluded here. Revisit before live money, once real
# chain-derived cross-strategy delta is wired (see DECISIONS.md).
_NON_IC_STRATEGIES = frozenset({STRATEGY_SPOT, STRATEGY_FUTURES, STRATEGY_PROXY, STRATEGY_CSP})


def ic_relevant_strategy_names(all_strategy_names: list[str]) -> list[str]:
    """Filter non-IC strategies out of the IC portfolio-delta gate.

    Args:
        all_strategy_names: Every open strategy name, as returned by
            ``PaperStore.get_strategy_names()``.

    Returns:
        The subset of *all_strategy_names* that should count toward an IC
        strategy's own delta-neutral gate — excludes ``paper_nifty_futures``,
        ``paper_nifty_proxy``, ``paper_nifty_spot`` (separate proxy/hedge
        books), and ``paper_csp_nifty_v1`` (separate strategy; paper-phase
        scope decision, see module comment above and ``DECISIONS.md``).
    """
    return [name for name in all_strategy_names if name not in _NON_IC_STRATEGIES]
