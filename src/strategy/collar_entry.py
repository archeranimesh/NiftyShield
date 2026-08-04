# src/strategy/collar_entry.py
"""Shared Collar two-leg strike selection + PaperTrade construction (Collar3b).

Extracted so both the CLI bootstrap path
(``scripts/strategies/three_track/paper_3track_overlay_entry.py::auto_collar_bootstrap``)
and the backbone strategy's combined close+reenter action
(``CollarOverlayV1.apply_action``) share exactly one selection code path — no
independent "collar reentry" logic invented at either call site.

Layering (Collar3b architecture decision — see DECISIONS.md 2026-08-03):
``src/`` must never import from ``scripts/``. The candidate-ladder search
(``_find_candidates_for_ladder``), collar cross-product
(``build_collar_cross_product`` / ``compute_net_collar_premium``), and ladder
constants (``CC_DELTA_CANDIDATES`` / ``PP_DELTA_CANDIDATES``) already live in
``scripts/lookup/find_strike_by_delta.py`` (Collar1) and are *not* importable
from here. Rather than duplicate that logic wholesale, this module
reimplements the same algorithm directly against the already-``src/``-side
primitives (``src.instruments.strike_selector``) that
``find_strike_by_delta.py`` itself is built on — the ladder constants are
mirrored here (not imported) with an explicit comment pointing back to the
source of truth, so a future ladder tweak (CC4-style round-strike
preference, band widening, etc.) must touch both files, exactly like CC1's
ladder is already duplicated into ``auto_cc_bootstrap`` in the entry script.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from src.backtest.ivr import compute_ivr
from src.backtest.vix_ingest import load_vix_series
from src.config import settings
from src.instruments.lookup import InstrumentLookup
from src.instruments.strike_selector import (
    _apply_liquidity_gate,
    filter_strikes_by_delta,
    rank_strikes,
)
from src.models.portfolio import TradeAction
from src.paper.constants import DEFAULT_BOD_PATH, LOT_SIZE, STRATEGY_OVERLAY
from src.paper.models import PaperTrade

if TYPE_CHECKING:
    from src.client.protocol import BrokerClient
    from src.paper.store import PaperStore

log = structlog.get_logger(__name__)

# Mirrors scripts/lookup/find_strike_by_delta.py::CC_DELTA_CANDIDATES / PP_DELTA_CANDIDATES
# (CC1/PP1/CC2, confirmed live). Duplicated, not imported — src/ must not import scripts/.
_CC_DELTA_CANDIDATES = [0.18, 0.20, 0.15]
_PP_DELTA_CANDIDATES = [0.20, 0.25, 0.15]

_DTE_MIN_GATE = 14
_IVR_MIN_GATE = 0.25

_COLLAR_PUT_ROLE = "overlay_collar_put"
_COLLAR_CALL_ROLE = "overlay_collar_call"


class CollarEntrySelectionError(RuntimeError):
    """Raised when Collar reentry selection cannot produce a valid two-leg pair.

    Callers (bootstrap CLI, ``CollarOverlayV1.apply_action``) must catch this,
    log with full context, notify the operator via Telegram, and leave the
    position flat — no auto-retry, no degraded fallback (Collar3b spec).
    """


@dataclass(frozen=True)
class _Candidate:
    row: dict[str, Any]
    target_delta: float


def _find_candidates_for_ladder(
    raw_chain: list[dict[str, Any]],
    option_type: str,
    ladder: list[float],
) -> list[dict[str, Any]]:
    """Find one best liquidity-gated candidate row per ladder rung.

    Mirrors ``scripts/lookup/find_strike_by_delta.py::_find_candidates_for_ladder``
    but operates on a single already-fetched chain for one expiry (the CLI
    version pools across multiple resolved expiries; the reentry path always
    targets exactly one resolved expiry).
    """
    candidates: list[dict[str, Any]] = []
    for target in ladder:
        delta_min = max(0.0, target - 0.02)
        delta_max = target + 0.02
        rows = filter_strikes_by_delta(
            raw_chain, option_type=option_type, delta_min=delta_min, delta_max=delta_max
        )
        if not rows:
            continue
        gated = _apply_liquidity_gate(rank_strikes(rows))
        if gated:
            candidates.append({**gated[0], "target_delta": target})
    return candidates


def _compute_net_premium(call_row: dict[str, Any], put_row: dict[str, Any]) -> Decimal:
    """Net premium of a collar combo: short-call credit minus long-put debit."""
    call_price = call_row["mid"] if call_row.get("mid", 0) > 0 else call_row["ltp"]
    put_price = put_row["mid"] if put_row.get("mid", 0) > 0 else put_row["ltp"]
    return Decimal(str(round(call_price - put_price, 2)))


def _select_best_combo(
    call_candidates: list[dict[str, Any]], put_candidates: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Cross-product call x put candidates, tiebreak on min |net_premium| (Collar2)."""
    combos = [
        (call, put, _compute_net_premium(call, put))
        for call in call_candidates
        for put in put_candidates
    ]
    if not combos:
        return None
    combos.sort(key=lambda c: abs(c[2]))
    call, put, _net = combos[0]
    return call, put


def _resolve_expiry(bod_path: Path, today: date, *, closing_dte: int | None) -> tuple[str, int]:
    """Resolve the monthly expiry to trade — current month, or next month when
    the position being closed had DTE <= 5 remaining (Collar3b rule #4).

    Returns:
        (expiry_str, dte).

    Raises:
        CollarEntrySelectionError: BOD load failure, or no monthly expiry found.
    """
    try:
        lookup = InstrumentLookup.from_file(bod_path)
    except Exception as exc:  # noqa: BLE001
        raise CollarEntrySelectionError(f"BOD load failed: {exc}") from exc

    min_expiry: str | None = None
    if closing_dte is not None and closing_dte <= 5:
        # Force selection past the current month's own expiry (next month).
        current = lookup.get_expiry_candidates(underlying="NIFTY", today=today, preference=["monthly"])
        current_monthly = next((e for label, e in current if label == "monthly"), None)
        if current_monthly is not None:
            min_expiry = current_monthly

    expiries = lookup.get_expiry_candidates(
        underlying="NIFTY", today=today, preference=["monthly"], min_expiry=min_expiry
    )
    expiry_str = next((e for label, e in expiries if label == "monthly"), None)
    if not expiry_str:
        raise CollarEntrySelectionError("No monthly expiry candidate found")

    expiry_date = date.fromisoformat(expiry_str)
    dte = (expiry_date - today).days
    return expiry_str, dte


def _check_gates(dte: int) -> None:
    """DTE >= 14 gate. IVR >= 0.25 gate (mirrors ReEntryMixin / auto_cc_bootstrap)."""
    if dte < _DTE_MIN_GATE:
        raise CollarEntrySelectionError(f"DTE gate failed: dte={dte} < {_DTE_MIN_GATE}")

    try:
        vix_series = load_vix_series(settings.vix_data_dir)
        if vix_series.empty or len(vix_series) < 252:
            raise CollarEntrySelectionError("IVR history insufficient")
        vix_today = float(vix_series.iloc[-1])
        ivr = compute_ivr(vix_today, vix_series)
    except CollarEntrySelectionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CollarEntrySelectionError(f"IVR check failed: {exc}") from exc

    if ivr is None or ivr < _IVR_MIN_GATE:
        raise CollarEntrySelectionError(f"IVR gate failed: ivr={ivr}")


async def select_and_build_collar_entry(
    broker: "BrokerClient",
    store: "PaperStore",
    today: date,
    triggering_signal: str,
    *,
    closing_dte: int | None = None,
    bod_path: Path | None = None,
    lot_size: int = LOT_SIZE,
) -> list[PaperTrade]:
    """Resolve expiry, run Collar1/Collar2 selection, apply gates, build two legs.

    Resolves current vs next month's expiry per DTE<=5 rule (``closing_dte``),
    runs Collar1's two-leg delta search (mirrored ladders) + Collar2's
    min-|net_premium| tiebreak against the live chain, applies the DTE>=14/
    IVR>=0.25 gates, and returns two ``PaperTrade`` legs (put, call) ready for
    ``store.record_trades()``. Does not itself write to the store — callers
    own the atomic close+reenter transaction boundary.

    Args:
        broker: BrokerClient (or MarketDataProvider-compatible) for chain fetch.
        store: PaperStore — accepted for signature symmetry with the CLI
            bootstrap path; not read here (selection is chain/BOD/VIX-only).
        today: Reference date.
        triggering_signal: The exit signal that triggered this reentry (for
            trade notes/audit only — does not change selection logic).
        closing_dte: DTE remaining on the position being closed, if any.
            None (bootstrap, no prior position) behaves like "far from expiry"
            (current month is selected).
        bod_path: Override for the BOD instrument JSON path.
        lot_size: Quantity per leg.

    Returns:
        [put_trade, call_trade] — always both legs, or raises.

    Raises:
        CollarEntrySelectionError: On any structural failure — no candidate
            clears the ladder, chain fetch fails, or a gate blocks. Callers
            must log ERROR with full context, notify the operator, and leave
            the position flat (no auto-retry, no degraded fallback).
    """
    del store  # unused — kept for signature parity / future audit logging

    resolved_bod_path = bod_path if bod_path is not None else Path(DEFAULT_BOD_PATH)

    expiry_str, dte = _resolve_expiry(resolved_bod_path, today, closing_dte=closing_dte)
    _check_gates(dte)

    try:
        raw_chain = await broker.get_option_chain("NSE_INDEX|Nifty 50", expiry_str)
    except Exception as exc:  # noqa: BLE001
        raise CollarEntrySelectionError(f"Chain fetch failed: {exc}") from exc

    if not raw_chain:
        raise CollarEntrySelectionError("Chain fetch returned empty result")

    call_candidates = _find_candidates_for_ladder(raw_chain, "CE", _CC_DELTA_CANDIDATES)
    put_candidates = _find_candidates_for_ladder(raw_chain, "PE", _PP_DELTA_CANDIDATES)

    combo = _select_best_combo(call_candidates, put_candidates)
    if combo is None:
        raise CollarEntrySelectionError(
            "No viable collar combo — no candidate cleared the ladder/liquidity gate"
        )
    call_row, put_row = combo

    call_price = Decimal(str(call_row["mid"] if call_row.get("mid", 0) > 0 else call_row["ltp"]))
    put_price = Decimal(str(put_row["mid"] if put_row.get("mid", 0) > 0 else put_row["ltp"]))

    notes = f"Collar reentry via {triggering_signal}. Expiry={expiry_str} (DTE={dte})."

    put_trade = PaperTrade(
        strategy_name=STRATEGY_OVERLAY,
        leg_role=_COLLAR_PUT_ROLE,
        instrument_key=put_row["instrument_key"],
        trade_date=today,
        action=TradeAction.BUY,
        quantity=lot_size,
        price=put_price,
        notes=notes,
    )
    call_trade = PaperTrade(
        strategy_name=STRATEGY_OVERLAY,
        leg_role=_COLLAR_CALL_ROLE,
        instrument_key=call_row["instrument_key"],
        trade_date=today,
        action=TradeAction.SELL,
        quantity=lot_size,
        price=call_price,
        notes=notes,
    )
    return [put_trade, call_trade]
