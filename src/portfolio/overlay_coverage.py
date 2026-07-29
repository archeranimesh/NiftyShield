"""Query-time overlay coverage ratio per 3-track base (S3r).

Overlay legs (CC/PP/Collar) live in one track-independent strategy_name
(``STRATEGY_OVERLAY``, S1r) — there is no per-track duplicate to sum. This
module answers "how much protection does the current overlay give Spot /
Futures / Proxy right now" as a live join, recomputed on every call. See
docs/plan/3track-consolidation/stories.md S3r for the full design rationale.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.client.protocol import BrokerClient
from src.instruments.lookup import InstrumentLookup
from src.models.options import OptionChain
from src.paper.constants import STRATEGY_OVERLAY
from src.paper.models import OverlayCoverage
from src.paper.store import PaperStore
from src.paper.track_snapshot import resolve_leg_delta

# Base leg_role per track — mirrors
# scripts/strategies/three_track/paper_3track_snapshot._base_leg_role, kept as
# a local mapping (not imported) since src/ must not depend on scripts/.
_BASE_LEG_ROLE_BY_TRACK: dict[str, str] = {
    "paper_nifty_spot": "base_etf",
    "paper_nifty_futures": "base_futures",
    "paper_nifty_proxy": "base_ditm_call",
}


async def compute_overlay_coverage(
    store: PaperStore,
    broker: BrokerClient,
    lookup: InstrumentLookup,
    track_namespace: str,
    snapshot_date: date,
) -> OverlayCoverage:
    """Compute the overlay coverage ratio for one track, at query time.

    Coverage % = overlay delta-equivalent exposure / the track's own
    effective Nifty-point exposure. Qty/lot values are used as-is, never
    resized — capital parity across tracks (~15L margin at entry, confirmed
    by operator) is what makes them comparable, not exposure parity, so this
    function deliberately does NOT normalize Spot/Futures/Proxy quantities
    against each other.

    Args:
        store: PaperStore for both the track's own base position and the
            shared overlay namespace.
        broker: BrokerClient used for live chain Greeks (Proxy base leg and
            any overlay leg — both option-based, both delta-drifting).
        lookup: BOD instrument lookup for expiry/strike/type resolution.
        track_namespace: One of ``STRATEGY_SPOT``/``STRATEGY_FUTURES``/
            ``STRATEGY_PROXY`` (src.paper.constants).
        snapshot_date: Date this ratio is computed for — a label on the
            result, not a persistence key (nothing here is written to disk).

    Returns:
        OverlayCoverage with ``coverage_pct=None`` when the track has no
        open base position (undefined, not zero — a flat track has no
        exposure for an overlay to cover).

    Raises:
        KeyError: If ``track_namespace`` is not one of the three known
            3-track base strategy names — a caller bug, not a runtime data
            condition, so this is not swallowed.
    """
    base_role = _BASE_LEG_ROLE_BY_TRACK[track_namespace]
    base_pos = store.get_position(track_namespace, base_role)

    overlay_trades = store.get_trades(STRATEGY_OVERLAY)
    overlay_roles = {t.leg_role for t in overlay_trades if t.leg_role.startswith("overlay_")}
    overlay_positions = [store.get_position(STRATEGY_OVERLAY, role) for role in overlay_roles]
    open_overlay_positions = [p for p in overlay_positions if p.net_qty != 0]

    fetched_chains: dict[str, OptionChain | None] = {}

    track_effective_units = Decimal("0")
    if base_pos.net_qty != 0:
        base_delta, _theta, _vega = await resolve_leg_delta(
            base_pos, lookup, broker, fetched_chains
        )
        track_effective_units = base_delta * Decimal(str(base_pos.net_qty))

    overlay_effective_units = Decimal("0")
    for pos in open_overlay_positions:
        leg_delta, _theta, _vega = await resolve_leg_delta(pos, lookup, broker, fetched_chains)
        overlay_effective_units += leg_delta * Decimal(str(pos.net_qty))

    coverage_pct: Decimal | None = None
    if track_effective_units != 0:
        coverage_pct = (overlay_effective_units / track_effective_units) * Decimal("100")

    return OverlayCoverage(
        track_name=track_namespace,
        track_effective_units=track_effective_units,
        overlay_effective_units=overlay_effective_units,
        coverage_pct=coverage_pct,
        as_of=snapshot_date,
    )
