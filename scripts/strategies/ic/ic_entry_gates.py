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

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import structlog

from src.backtest.ivr import compute_ivr
from src.backtest.vix_ingest import fetch_vix_latest, load_vix_series
from src.instruments.lookup import InstrumentLookup
from src.intraday.market_store import IntradayMarketStore

_log = structlog.get_logger("scripts.strategies.ic.ic_entry_gates")


# ---------------------------------------------------------------------------
# Gate 1 — Duplicate position guard
# ---------------------------------------------------------------------------


def check_duplicate(store: object, strategy_name: str) -> None:
    """Exit with code 1 if an active position already exists for *strategy_name*.

    Args:
        store: Open PaperStore instance.
        strategy_name: Exact DB strategy name (e.g. ``paper_ic_nifty_v2_monthly``).
    """
    open_positions = store.get_positions(strategy_name)
    if any(pos.net_qty != 0 for pos in open_positions):
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
) -> float | None:
    """Load VIX series, compute IVR, apply gate.

    Returns the computed IVR value (float) or ``None`` if data is unavailable.
    Calls ``sys.exit(1)`` when IVR is below *ivr_gate* and *force_entry* is False.
    Logs a WARNING and continues when *force_entry* is True.

    Args:
        db_path: Path to paper trading SQLite DB (used by IntradayMarketStore).
        ivr_gate: Minimum acceptable IVR for entry.
        force_entry: When True, bypass the gate with a warning.

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
