"""IronCondorV2 — high-delta IC with 10Δ wings and partial-roll adjustments.

Phase 1 (IC-V2-1): entry logic.
  - _select_short_put / _select_short_call: 25Δ/22Δ via find_strike_by_delta
  - _select_long_wing: 10Δ with delta/premium/liquidity floors
  - _sd_sanity_check: warn-only SD guard (never blocks entry)
  - enter(): assemble 4-leg IC; returns PositionUpdate or None

Phase 2 (IC-V2-2): adjustment logic — implemented here.
  - _evaluate_adjustment(): detects DELTA_WARN / ROLL_WING / DELTA_STOP / FORCED_CLOSE
  - _execute_partial_roll(): builds 4-leg atomic PositionUpdate for challenged vertical
  - 7 roll guards (DTE, candidate, width, debit-cap, max-rolls, inverted-condor, wing-floor)
  - State: _rolls_executed dict + _original_ic_credit per strategy_name

Phase 3 (IC-V2-3): _evaluate_dte_action, _should_close_full, _roll_allowed_by_dte — implemented.
Phase 4 (IC-V2-4): check_signals, apply_action — PaperStrategy protocol compliance.

Council ruling (authoritative): docs/archive/council/strategy/2026-06-26_ic-v2-core-design.md
Stage 3 — D1 (entry deltas), D2 (wings), D3 (adjustment), D4 (DTE tiering).

Structural differences from V1
-------------------------------
| Dimension         | V1                    | V2                             |
|-------------------|-----------------------|--------------------------------|
| Entry deltas      | 15Δ put / 10Δ call    | 25Δ put / 22Δ call (D1)        |
| Wing construction | Fixed points          | 10Δ placement + floors (D2)    |
| Adjustment        | ROLL_WING only        | Full partial vertical (D3)     |
| Roll accounting   | Single leg            | 4-leg atomic, max 1/side (D3)  |
| DTE hard-close    | None                  | DTE≤7 CLOSE_FULL monthly (D4)  |
| Debit guards      | None                  | ≤50% of original IC credit (D3)|
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Literal

import structlog

from src.instruments.lookup import InstrumentLookup
from src.instruments.lookup import parse_expiry as _parse_expiry_epoch
from src.market_calendar.holidays import market_today
from src.models.options import OptionChain, OptionLeg
from src.paper.constants import DEFAULT_BOD_PATH
from src.paper.models import PaperPosition, PaperTrade
from src.strategy import roll_utils
from src.strategy.ic_close_executor import close_ic_legs, roll_ic_legs
from src.strategy.profit_lock_engine import ProfitLockDecision, ProfitLockEngine, ProfitLockState
from src.strategy.protocol import ApprovedAction, LegClose, LegSpec, SignalEvent

if TYPE_CHECKING:
    from src.client.protocol import BrokerClient
    from src.notifications.telegram_gateway import TelegramGateway
    from src.paper.store import PaperStore
    from src.strategy.ic_expiry_config_v2 import IronCondorV2ExpiryConfig

log = structlog.get_logger(__name__)

# ── Regexes (copied verbatim from ic_nifty_v1) ───────────────────────────────

_EXPIRY_RE = re.compile(
    r"NSE_FO\|NIFTY(\d{2}[A-Za-z]{3}\d{4})",
    re.IGNORECASE,
)
_STRIKE_RE = re.compile(r"NIFTY(\d+)(PE|CE)", re.IGNORECASE)

# ── Leg role sets (copied verbatim from ic_nifty_v1) ─────────────────────────

_SHORT_ROLES = {"short_call", "short_put"}
_LONG_ROLES = {"long_call_hedge", "long_put_hedge"}

# ── Liquidity gate constant ───────────────────────────────────────────────────

_LIQUIDITY_GATE_PCT = Decimal("0.05")  # max bid/ask spread as fraction of mid

# ── Long-wing delta search ceiling ───────────────────────────────────────────
# Upper bound for the delta band passed to find_strike_by_delta when selecting
# long wings. Generous enough to include 10Δ–20Δ candidates while excluding
# near-ATM strikes (>20Δ).
_LONG_WING_DELTA_CEILING = Decimal("0.20")

# ── Protocol constants (IC-V2-4) ──────────────────────────────────────────────
# Profit target: close when mark ≤ 30% of entry credit (70% captured).
_PROFIT_TARGET_RETENTION = Decimal("0.30")

# Allowed action types for apply_action.
_ALLOWED_V2_ACTIONS = frozenset(
    {"CLOSE_FULL", "CLOSE_CALL_SPREAD", "CLOSE_PUT_SPREAD", "ROLL_WING", "PROFIT_LOCK_ZONE2"}
)


def _leg_close_matches(pos: PaperPosition, leg: LegClose) -> bool:
    """Return True when ``leg`` identifies ``pos`` as the position to close.

    Matches on ``leg_role`` always; additionally matches on ``instrument_key``
    when the ``LegClose`` supplies one, so that a roll overlap (two positions
    sharing a ``leg_role`` with different ``instrument_key``s) only selects
    the specific instrument being closed (PG-4g, mirrors PG-4f in ic_nifty_v1).
    """
    if pos.leg_role != leg.leg_role:
        return False
    if leg.instrument_key is not None:
        return pos.instrument_key == leg.instrument_key
    return True


def _position_for_role(ic_positions: list[PaperPosition], leg_role: str) -> PaperPosition | None:
    """Resolve the position to close for ``leg_role``.

    When two positions share ``leg_role`` (roll overlap), picks the one with
    the most-recent ``entry_date`` — mirrors ``PaperStore.get_position``'s
    ambiguity handling (PG-2a) and ``ic_nifty_v1``'s equivalent helper (PG-4f)
    so the auto-selected close target is consistent with the rest of the
    codebase.
    """
    matches = [p for p in ic_positions if p.leg_role == leg_role]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    log.warning(
        "ic_nifty_v2.position_for_role_ambiguous",
        leg_role=leg_role,
        match_count=len(matches),
    )
    return max(matches, key=lambda p: p.entry_date or date.min)


# ── Position update ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PositionUpdate:
    """Result of a successful IronCondorV2 entry evaluation.

    Attributes:
        legs: Four LegSpec objects (short_put, short_call, long_put_hedge,
            long_call_hedge) ready to be recorded via record_paper_trade.
        total_credit_pts: Net option credit at entry in index points per unit.
            Computed as (short_put.ltp + short_call.ltp) - (long_put.ltp + long_call.ltp).
    """

    legs: list[LegSpec]
    total_credit_pts: Decimal


# ── Roll result ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RollResult:
    """Output of _evaluate_adjustment().

    Attributes:
        signal_type: One of DELTA_WARN / ROLL_WING / DELTA_STOP / FORCED_CLOSE.
        side: "put" or "call" — which vertical was challenged.
            For DELTA_WARN the field always contains the first side (in iteration order
            "put" then "call") whose |delta| reached the warn threshold.  Both sides
            can reach the warn zone simultaneously in a low-IV aggressively-entered IC;
            the current implementation breaks on the first match.  A future dual-warn
            path could emit two separate events — not implemented in Phase 1.
        roll_update: 4-leg PositionUpdate when signal_type == ROLL_WING and roll
            executes successfully. None for all other signal types.
        block_reason: Guard name that blocked the roll (for logging). None unless
            the roll was attempted but blocked by a guard.
    """

    signal_type: Literal["DELTA_WARN", "ROLL_WING", "DELTA_STOP", "FORCED_CLOSE"]
    side: Literal["put", "call"]
    roll_update: PositionUpdate | None
    block_reason: str | None


# ── Strategy class ────────────────────────────────────────────────────────────


class IronCondorV2:
    """Iron Condor V2: high-delta (25Δ/22Δ) IC with 10Δ wings and partial-roll adjustments.

    Separate from V1. Entry in this story; adjustment/exit in IC-V2-2/IC-V2-3;
    PaperStrategy protocol compliance in IC-V2-4.
    """

    auto_execute: bool = True

    def __init__(
        self,
        config: IronCondorV2ExpiryConfig | None = None,
        broker: BrokerClient | None = None,
        store: PaperStore | None = None,
        notifier: TelegramGateway | None = None,
    ) -> None:
        from src.strategy.ic_expiry_config_v2 import IC_V2_MONTHLY

        self._config = config if config is not None else IC_V2_MONTHLY
        self._broker = broker
        self._store = store
        self._notifier = notifier

        # ── Adjustment state (reset on new entry cycle via reset_roll_state()) ──
        # Keyed by side ("put" | "call"). Counts partial rolls executed this cycle.
        self._rolls_executed: dict[str, int] = {"put": 0, "call": 0}
        # Original total IC credit at entry (option points per unit).
        # Set by the caller after a successful enter() via set_original_credit().
        self._original_ic_credit: Decimal = Decimal("0")

    @property
    def strategy_name(self) -> str:
        """DB discriminator derived from injected config expiry type."""
        return f"paper_ic_nifty_v2_{self._config.expiry_type}"

    # ── Entry ─────────────────────────────────────────────────────────────────

    def enter(self, market: OptionChain) -> PositionUpdate | None:
        """Evaluate entry conditions and return a 4-leg PositionUpdate or None.

        Selection order: short put → short call → long put wing → long call wing.
        Any selection failure logs the reason and returns None (skip entry).
        SD sanity check fires warnings but never blocks entry.

        Args:
            market: Live Nifty 50 option chain snapshot for the target expiry.

        Returns:
            PositionUpdate with 4 LegSpec objects when all conditions pass,
            or None when any selection or floor check fails.
        """
        dte = (market.expiry - market_today()).days
        expiry_str = market.expiry.isoformat()

        short_put = self._select_short_put(market, expiry=expiry_str, dte=dte)
        if short_put is None:
            return None

        short_call = self._select_short_call(market, expiry=expiry_str, dte=dte)
        if short_call is None:
            return None

        long_put = self._select_long_wing(market, "put", expiry=expiry_str, dte=dte)
        if long_put is None:
            return None

        long_call = self._select_long_wing(market, "call", expiry=expiry_str, dte=dte)
        if long_call is None:
            return None

        # SD sanity check (warn only — never blocks entry)
        atm_iv = self._atm_iv(market)
        if atm_iv is not None and dte > 0:
            put_width = short_put.strike - long_put.strike
            call_width = long_call.strike - short_call.strike
            self._sd_sanity_check(market.underlying_spot, atm_iv, dte, put_width)
            self._sd_sanity_check(market.underlying_spot, atm_iv, dte, call_width)

        total_credit = (short_put.ltp + short_call.ltp) - (long_put.ltp + long_call.ltp)
        ivr_str = self._compute_ivr_str()

        short_put_key = self._resolve_instrument_key(short_put.strike, "PE", expiry_str)
        short_call_key = self._resolve_instrument_key(short_call.strike, "CE", expiry_str)
        long_put_key = self._resolve_instrument_key(long_put.strike, "PE", expiry_str)
        long_call_key = self._resolve_instrument_key(long_call.strike, "CE", expiry_str)
        if None in (short_put_key, short_call_key, long_put_key, long_call_key):
            # BUG-024: one or more legs picked by the delta/liquidity scan
            # aren't present in the same-expiry BOD file. Abort the whole
            # entry rather than persist a partial or unresolvable position —
            # same skip-on-failure contract as the selection checks above.
            # Deliberately logged before entry_recorded below, and entry_recorded
            # is skipped entirely on this path — entry_recorded must only ever
            # describe entries that actually proceed, not attempted-then-aborted
            # ones (a reviewer-flagged log-semantics issue in an earlier revision
            # of this diff, where entry_recorded fired unconditionally).
            log.warning(
                "ic_nifty_v2.entry_key_resolution_failed",
                strategy_name=self.strategy_name,
                expiry=expiry_str,
                short_put_key=short_put_key,
                short_call_key=short_call_key,
                long_put_key=long_put_key,
                long_call_key=long_call_key,
            )
            return None

        log.info(
            "ic_nifty_v2.entry_recorded",
            strategy_name=self.strategy_name,
            expiry=expiry_str,
            dte=dte,
            short_put_strike=str(short_put.strike),
            short_call_strike=str(short_call.strike),
            long_put_strike=str(long_put.strike),
            long_call_strike=str(long_call.strike),
            total_credit_pts=str(total_credit),
            ivr=ivr_str,
        )

        legs = [
            LegSpec(
                instrument_key=short_put_key,
                action="SELL",
                quantity=1,
                leg_role="short_put",
                notes=f"delta={short_put.delta}",
            ),
            LegSpec(
                instrument_key=short_call_key,
                action="SELL",
                quantity=1,
                leg_role="short_call",
                notes=f"delta={short_call.delta}",
            ),
            LegSpec(
                instrument_key=long_put_key,
                action="BUY",
                quantity=1,
                leg_role="long_put_hedge",
                notes=f"delta={long_put.delta}",
            ),
            LegSpec(
                instrument_key=long_call_key,
                action="BUY",
                quantity=1,
                leg_role="long_call_hedge",
                notes=f"delta={long_call.delta}",
            ),
        ]
        return PositionUpdate(legs=legs, total_credit_pts=total_credit)

    # ── Selection helpers ─────────────────────────────────────────────────────

    def _select_short_put(
        self,
        chain: OptionChain,
        *,
        expiry: str,
        dte: int,
    ) -> OptionLeg | None:
        """Select the short put leg at ~25Δ.

        Uses config.short_put_delta_target ± config.delta_range as the search band.
        Returns the candidate with delta closest to target, or None if no match.

        Args:
            chain: Current option chain snapshot.
            expiry: ISO expiry string for structured logging.
            dte: Days to expiry for structured logging.

        Returns:
            Matching OptionLeg, or None when no candidate exists in the band.
        """
        cfg = self._config
        lo = cfg.short_put_delta_target - cfg.delta_range
        hi = cfg.short_put_delta_target + cfg.delta_range
        candidate = roll_utils.find_strike_by_delta(
            chain, "PE", (lo, hi), cfg.short_put_delta_target
        )
        if candidate is None:
            log.warning(
                "ic_nifty_v2.entry_skip_no_short_put",
                strategy_name=self.strategy_name,
                expiry=expiry,
                dte=dte,
                delta_range=f"[{lo},{hi}]",
                best_available_delta=self._best_available_delta(
                    chain, "PE", cfg.short_put_delta_target
                ),
            )
            return None
        return candidate

    def _select_short_call(
        self,
        chain: OptionChain,
        *,
        expiry: str,
        dte: int,
    ) -> OptionLeg | None:
        """Select the short call leg at ~22Δ.

        Uses config.short_call_delta_target ± config.delta_range as the search band.
        3Δ below put target per D1 ruling: skew-aware, reduces call-side whipsaw.

        Args:
            chain: Current option chain snapshot.
            expiry: ISO expiry string for structured logging.
            dte: Days to expiry for structured logging.

        Returns:
            Matching OptionLeg, or None when no candidate exists in the band.
        """
        cfg = self._config
        lo = cfg.short_call_delta_target - cfg.delta_range
        hi = cfg.short_call_delta_target + cfg.delta_range
        candidate = roll_utils.find_strike_by_delta(
            chain, "CE", (lo, hi), cfg.short_call_delta_target
        )
        if candidate is None:
            log.warning(
                "ic_nifty_v2.entry_skip_no_short_call",
                strategy_name=self.strategy_name,
                expiry=expiry,
                dte=dte,
                delta_range=f"[{lo},{hi}]",
                best_available_delta=self._best_available_delta(
                    chain, "CE", cfg.short_call_delta_target
                ),
            )
            return None
        return candidate

    def _select_long_wing(
        self,
        chain: OptionChain,
        side: Literal["put", "call"],
        *,
        expiry: str,
        dte: int,
    ) -> OptionLeg | None:
        """Select the long wing leg at ~10Δ, enforcing delta/premium/liquidity floors.

        Floor enforcement order (all three must pass):
          1. abs(delta) ≥ long_wing_delta_floor (default 0.05)
          2. mid_premium ≥ long_wing_min_premium (default ₹15 monthly)
          3. bid/ask spread ≤ 5% of mid price (liquidity gate)

        If any floor is not met, logs ic_nifty_v2.entry_skip_wing_floor_miss and
        returns None (entry is skipped).

        Args:
            chain: Current option chain snapshot.
            side: "put" for long_put_hedge, "call" for long_call_hedge.
            expiry: ISO expiry string for structured logging.
            dte: Days to expiry for structured logging.

        Returns:
            Matching OptionLeg satisfying all floors, or None.
        """
        cfg = self._config
        option_type: Literal["CE", "PE"] = "CE" if side == "call" else "PE"

        candidate = roll_utils.find_strike_by_delta(
            chain,
            option_type,
            (cfg.long_wing_delta_floor, _LONG_WING_DELTA_CEILING),
            cfg.long_wing_delta_target,
        )
        if candidate is None:
            log.warning(
                "ic_nifty_v2.entry_skip_wing_floor_miss",
                strategy_name=self.strategy_name,
                expiry=expiry,
                dte=dte,
                side=side,
                reason="delta",
                floor_value=str(cfg.long_wing_delta_floor),
                actual_value="none",
            )
            return None

        # Defensive: find_strike_by_delta only returns candidates within the delta band,
        # but OptionLeg.delta is Optional — a chain snapshot with missing Greeks can
        # produce a leg with delta=None that passed the ltp > 0 filter. Guard explicitly.
        if candidate.delta is None:
            log.warning(
                "ic_nifty_v2.entry_skip_wing_floor_miss",
                strategy_name=self.strategy_name,
                expiry=expiry,
                dte=dte,
                side=side,
                reason="delta_none",
                floor_value=str(cfg.long_wing_delta_floor),
                actual_value="none",
            )
            return None

        abs_delta = abs(candidate.delta)
        if abs_delta < cfg.long_wing_delta_floor:
            log.warning(
                "ic_nifty_v2.entry_skip_wing_floor_miss",
                strategy_name=self.strategy_name,
                expiry=expiry,
                dte=dte,
                side=side,
                reason="delta",
                floor_value=str(cfg.long_wing_delta_floor),
                actual_value=str(abs_delta),
            )
            return None

        mid = self._mid_price(candidate)
        if mid < cfg.long_wing_min_premium:
            log.warning(
                "ic_nifty_v2.entry_skip_wing_floor_miss",
                strategy_name=self.strategy_name,
                expiry=expiry,
                dte=dte,
                side=side,
                reason="premium",
                floor_value=str(cfg.long_wing_min_premium),
                actual_value=str(mid),
            )
            return None

        if not self._passes_liquidity_gate(candidate):
            spread_pct = self._spread_pct(candidate)
            log.warning(
                "ic_nifty_v2.entry_skip_wing_floor_miss",
                strategy_name=self.strategy_name,
                expiry=expiry,
                dte=dte,
                side=side,
                reason="liquidity",
                floor_value=str(_LIQUIDITY_GATE_PCT),
                actual_value=str(spread_pct),
            )
            return None

        return candidate

    # ── SD sanity guard ───────────────────────────────────────────────────────

    def _sd_sanity_check(
        self,
        spot: Decimal,
        atm_iv_pct: Decimal,
        dte: int,
        actual_width: Decimal,
    ) -> None:
        """Compare actual wing width against expected 1-SD move; emit warns only.

        Formula (D2 ruling):
            sd_width = spot × (atm_iv_pct / 100) × sqrt(dte / 365) × k

        where k = config.sd_atm_iv_multiplier (default 1.25).

        Warns if actual_width > 1.5 × sd_width (wing unusually wide)
        or if actual_width < 0.4 × sd_width (wing tight/expensive vs regime).
        Entry is never blocked by this check.

        Args:
            spot: Nifty spot price.
            atm_iv_pct: ATM implied volatility in percentage terms (e.g. 15.0 = 15%).
            dte: Days to expiry.
            actual_width: Actual wing width in index points.
        """
        cfg = self._config
        iv_decimal = atm_iv_pct / Decimal("100")
        # math.sqrt returns float; Decimal(str(...)) is the safe pattern to convert
        # float → Decimal without IEEE-754 rounding artifacts (float → repr → Decimal).
        sd_width = spot * iv_decimal * Decimal(str(math.sqrt(dte / 365))) * cfg.sd_atm_iv_multiplier

        if actual_width > cfg.sd_width_warn_upper_multiplier * sd_width:
            log.warning(
                "ic_nifty_v2.entry_sd_warn_wide",
                strategy_name=self.strategy_name,
                actual_width_pts=str(actual_width),
                sd_width_pts=str(sd_width.quantize(Decimal("0.01"))),
                multiplier=str(cfg.sd_width_warn_upper_multiplier),
            )
        elif actual_width < cfg.sd_width_warn_lower_multiplier * sd_width:
            log.warning(
                "ic_nifty_v2.entry_sd_warn_tight",
                strategy_name=self.strategy_name,
                actual_width_pts=str(actual_width),
                sd_width_pts=str(sd_width.quantize(Decimal("0.01"))),
                multiplier=str(cfg.sd_width_warn_lower_multiplier),
            )

    # ── Adjustment state helpers ──────────────────────────────────────────────

    def reset_roll_state(self) -> None:
        """Reset per-cycle roll counters and original credit. Call on new entry.

        Must be called by the orchestrator (IC-V2-4) immediately after a
        successful enter() so that _rolls_executed starts at zero and
        the debit-cap guard uses the correct reference credit.
        """
        self._rolls_executed = {"put": 0, "call": 0}
        self._original_ic_credit = Decimal("0")

    def set_original_credit(self, credit_pts: Decimal) -> None:
        """Store the original IC credit for debit-cap guard evaluation.

        Args:
            credit_pts: Total IC credit at entry in option index points per unit.
        """
        self._original_ic_credit = credit_pts

    # ── Adjustment evaluation ─────────────────────────────────────────────────

    def _evaluate_adjustment(
        self,
        positions: list[PaperPosition],
        market: OptionChain,
        dte: int,
        expiry: str,
        *,
        roll_allowed_by_dte: bool = True,
    ) -> RollResult | None:
        """Evaluate delta signals on current IC positions and decide adjustment.

        Signal hierarchy (D3 ruling):
            |short_delta| ≥ 0.30  → DELTA_WARN (log only, no roll)
            |short_delta| ≥ 0.35  → ROLL_WING  (attempt partial roll)
            |short_delta| ≥ 0.35 AND roll blocked → DELTA_STOP (close challenged spread)
            |short_delta| ≥ 0.45 OR max_rolls exhausted → FORCED_CLOSE (close full IC)

        Args:
            positions: Current open IC paper positions.
            market: Live Nifty 50 option chain snapshot.
            dte: Days to expiry (used for roll-guard context).
            expiry: ISO expiry string for structured logging.
            roll_allowed_by_dte: Injected predicate from IC-V2-3. When False the
                DTE-tiered exit has already determined no roll is permitted; this
                guard is checked first inside ROLL_WING escalation.

        Returns:
            RollResult describing the signal and any roll update, or None when
            delta levels are below all thresholds (healthy IC — hold).
        """
        cfg = self._config
        baseline = {
            "strategy_name": self.strategy_name,
            "trade_id": "",
            "expiry": expiry,
            "dte": dte,
            "roll_count_put": self._rolls_executed["put"],
            "roll_count_call": self._rolls_executed["call"],
            "profit_lock_zone": 0,
        }

        # Locate short legs in current positions
        short_put_pos = next((p for p in positions if p.leg_role == "short_put"), None)
        short_call_pos = next((p for p in positions if p.leg_role == "short_call"), None)

        # Collect delta readings for each short leg from the live chain
        deltas: dict[str, Decimal | None] = {
            "put": self._get_short_delta(market, short_put_pos),
            "call": self._get_short_delta(market, short_call_pos),
        }

        # ── FORCED_CLOSE: extreme delta (≥ 0.45) — skip all guards ────────────
        for side, delta_val in deltas.items():
            if delta_val is None:
                continue
            if abs(delta_val) >= cfg.forced_close_delta:
                log.warning(
                    "ic_nifty_v2.forced_close_delta",
                    **baseline,
                    side=side,
                    short_delta=str(delta_val),
                    threshold=str(cfg.forced_close_delta),
                )
                return RollResult(
                    signal_type="FORCED_CLOSE",
                    side=side,  # type: ignore[arg-type]
                    roll_update=None,
                    block_reason=None,
                )

        # ── ROLL_WING / DELTA_STOP: trigger delta (≥ 0.35) ───────────────────
        for side in ("put", "call"):
            delta_val = deltas[side]
            if delta_val is None:
                continue
            if abs(delta_val) < cfg.roll_trigger_delta:
                continue

            # Check max_rolls guard first — exhausted → immediate FORCED_CLOSE
            if self._rolls_executed[side] >= cfg.max_rolls_per_side_per_cycle:
                log.warning(
                    "ic_nifty_v2.forced_close_rolls_exhausted",
                    **baseline,
                    side=side,
                    roll_count=self._rolls_executed[side],
                )
                return RollResult(
                    signal_type="FORCED_CLOSE",
                    side=side,  # type: ignore[arg-type]
                    roll_update=None,
                    block_reason="max_rolls_exhausted",
                )

            log.info(
                "ic_nifty_v2.roll_wing_attempt",
                **baseline,
                side=side,
                short_delta=str(delta_val),
                original_short_strike=str(
                    self._position_strike(short_put_pos if side == "put" else short_call_pos)
                ),
                original_long_strike=str(self._long_wing_strike(positions, side)),
            )

            roll_result, block_reason = self._execute_partial_roll(
                side=side,  # type: ignore[arg-type]
                positions=positions,
                market=market,
                dte=dte,
                expiry=expiry,
                roll_allowed_by_dte=roll_allowed_by_dte,
                baseline=baseline,
            )

            if roll_result is not None:
                # Roll succeeded — update counter and return ROLL_WING
                self._rolls_executed[side] += 1
                log.info(
                    "ic_nifty_v2.roll_wing_executed",
                    **baseline,
                    side=side,
                    old_short_strike=str(
                        self._position_strike(short_put_pos if side == "put" else short_call_pos)
                    ),
                    old_long_strike=str(self._long_wing_strike(positions, side)),
                    new_short_strike=str(
                        self._leg_strike_from_update(roll_result, "new_short", side)
                    ),
                    new_long_strike=str(
                        self._leg_strike_from_update(roll_result, "new_long", side)
                    ),
                    roll_debit_pts=str(self._compute_roll_debit(positions, roll_result, market)),
                    roll_count_after=self._rolls_executed[side],
                )
                return RollResult(
                    signal_type="ROLL_WING",
                    side=side,  # type: ignore[arg-type]
                    roll_update=roll_result,
                    block_reason=None,
                )
            else:
                # Roll blocked → escalate to DELTA_STOP
                log.warning(
                    "ic_nifty_v2.delta_stop",
                    **baseline,
                    side=side,
                    short_delta=str(delta_val),
                    block_reason=block_reason,
                )
                return RollResult(
                    signal_type="DELTA_STOP",
                    side=side,  # type: ignore[arg-type]
                    roll_update=None,
                    block_reason=block_reason,
                )

        # ── DELTA_WARN: warn delta (≥ 0.30 but < 0.35) ───────────────────────
        warn_side: Literal["put", "call"] | None = None
        warn_delta: Decimal | None = None
        for side in ("put", "call"):
            delta_val = deltas[side]
            if delta_val is None:
                continue
            if abs(delta_val) >= cfg.roll_warn_delta:
                warn_side = side  # type: ignore[assignment]
                warn_delta = delta_val
                break

        if warn_side is not None and warn_delta is not None:
            log.warning(
                "ic_nifty_v2.delta_warn",
                **baseline,
                side=warn_side,
                short_delta=str(warn_delta),
                threshold=str(cfg.roll_warn_delta),
            )
            return RollResult(
                signal_type="DELTA_WARN",
                side=warn_side,
                roll_update=None,
                block_reason=None,
            )

        # Below all thresholds — healthy IC, hold
        return None

    def _execute_partial_roll(
        self,
        side: Literal["put", "call"],
        positions: list[PaperPosition],
        market: OptionChain,
        dte: int,
        expiry: str,
        *,
        roll_allowed_by_dte: bool,
        baseline: dict,
    ) -> tuple[PositionUpdate | None, str]:
        """Attempt a 4-leg atomic close+reopen of the challenged vertical.

        Returns a ``(update, block_reason)`` tuple so callers never read
        instance state for the outcome.  When the roll succeeds ``update`` is
        the 4-leg ``PositionUpdate`` and ``block_reason`` is an empty string.
        When any guard fails ``update`` is ``None`` and ``block_reason`` is the
        name of the guard that rejected the roll.

        Guard order (D3 ruling):
          1. DTE above expiry-specific cutoff (injected predicate roll_allowed_by_dte)
          2. Replacement short exists in delta range on current chain
          3. Replacement long wing satisfies delta/premium/liquidity floors
          4. replacement_width ≤ original_spread_width (no max-loss expansion)
          5. roll_debit ≤ roll_debit_cap_fraction × original_ic_credit;
             guard fails (chain_data_missing) when old legs absent from snapshot
          6. rolls_executed_this_side < max_rolls_per_side_per_cycle
          7. New short does not cross opposite side's short strike (no inverted condor)

        Args:
            side: "put" or "call" — which vertical is challenged.
            positions: Current open IC paper positions.
            market: Live Nifty 50 option chain snapshot.
            dte: Days to expiry.
            expiry: ISO expiry string for structured logging.
            roll_allowed_by_dte: False blocks roll immediately (guard 1).
            baseline: Shared log kwargs dict.

        Returns:
            ``(PositionUpdate, "")`` on success, or ``(None, guard_name)`` on
            any guard failure.
        """
        cfg = self._config
        option_type: Literal["CE", "PE"] = "CE" if side == "call" else "PE"
        role_short = f"short_{side}"
        role_long = f"long_{side}_hedge"

        # Locate old positions
        old_short_pos = next((p for p in positions if p.leg_role == role_short), None)
        old_long_pos = next((p for p in positions if p.leg_role == role_long), None)
        opposite_short_role = "short_call" if side == "put" else "short_put"
        opposite_short_pos = next((p for p in positions if p.leg_role == opposite_short_role), None)

        if old_short_pos is None or old_long_pos is None:
            return None, "no_short_candidate"

        # Derive original spread width from stored strikes
        old_short_strike = self._position_strike(old_short_pos)
        old_long_strike = self._position_strike(old_long_pos)
        if old_short_strike is None or old_long_strike is None:
            return None, "no_short_candidate"
        original_width = abs(old_short_strike - old_long_strike)

        # Locate opposite short strike (for inverted-condor guard)
        opposite_short_strike: Decimal | None = None
        if opposite_short_pos is not None:
            opposite_short_strike = self._position_strike(opposite_short_pos)

        # ── Guard 1: DTE cutoff ────────────────────────────────────────────────
        if not roll_allowed_by_dte:
            log.warning(
                "ic_nifty_v2.roll_guard_failed",
                **baseline,
                side=side,
                guard="dte_cutoff",
                detail=f"dte={dte} at or below close_full threshold",
            )
            return None, "dte_cutoff"

        # ── Guard 6 (checked early for efficiency): max_rolls ─────────────────
        # Already checked in _evaluate_adjustment before calling this method,
        # so this is a defensive double-check only.
        if self._rolls_executed[side] >= cfg.max_rolls_per_side_per_cycle:
            log.warning(
                "ic_nifty_v2.roll_guard_failed",
                **baseline,
                side=side,
                guard="max_rolls_exhausted",
                detail=f"rolls_executed={self._rolls_executed[side]}",
            )
            return None, "max_rolls_exhausted"

        # ── Guard 2: replacement short exists in delta range ───────────────────
        new_short = roll_utils.find_strike_by_delta(
            market,
            option_type,
            (
                cfg.short_put_delta_target - cfg.delta_range
                if side == "put"
                else cfg.short_call_delta_target - cfg.delta_range,
                cfg.short_put_delta_target + cfg.delta_range
                if side == "put"
                else cfg.short_call_delta_target + cfg.delta_range,
            ),
            cfg.short_put_delta_target if side == "put" else cfg.short_call_delta_target,
        )
        if new_short is None:
            log.warning(
                "ic_nifty_v2.roll_guard_failed",
                **baseline,
                side=side,
                guard="no_short_candidate",
                detail="no replacement short in delta range",
            )
            return None, "no_short_candidate"

        # ── Guard 3: replacement long wing passes all floors ───────────────────
        new_long = self._select_long_wing(market, side, expiry=expiry, dte=dte)
        if new_long is None:
            log.warning(
                "ic_nifty_v2.roll_guard_failed",
                **baseline,
                side=side,
                guard="wing_floor_miss",
                detail=(
                    "replacement long fails delta/premium/liquidity floor; "
                    "searching progressively narrower candidates (BUG-022)"
                ),
            )
            new_long = self._search_narrower_wing_candidate(
                side=side,
                market=market,
                old_long_strike=old_long_strike,
                new_short_strike=new_short.strike,
                positions=positions,
            )
            if new_long is None:
                log.warning(
                    "ic_nifty_v2.roll_guard_failed",
                    **baseline,
                    side=side,
                    guard="wing_search_exhausted",
                    detail=(
                        "no candidate between the original wing and the new short "
                        "strike cleared the liquidity/premium floor and the "
                        "floor-guarantee inequality"
                    ),
                )
                return None, "wing_search_exhausted"

        # ── Guard 4: replacement width ≤ original spread width ─────────────────
        new_width = abs(new_short.strike - new_long.strike)
        if new_width > original_width:
            log.warning(
                "ic_nifty_v2.roll_guard_failed",
                **baseline,
                side=side,
                guard="width_expansion",
                detail=f"new_width={new_width} > original_width={original_width}",
            )
            return None, "width_expansion"

        # ── Guard 5: roll debit ≤ roll_debit_cap_fraction × original_ic_credit ─
        # Fail-close when chain data is stale: absent legs mean we cannot price
        # the roll, and proceeding without the guard is riskier than aborting.
        old_short_leg = self._find_leg(market, old_short_pos.instrument_key)
        old_long_leg = self._find_leg(market, old_long_pos.instrument_key)
        if old_short_leg is None or old_long_leg is None:
            log.warning(
                "ic_nifty_v2.roll_guard_failed",
                **baseline,
                side=side,
                guard="chain_data_missing",
                detail=(
                    f"old_short_in_chain={old_short_leg is not None} "
                    f"old_long_in_chain={old_long_leg is not None}"
                ),
            )
            return None, "chain_data_missing"

        # Both legs resolved — compute roll debit and check cap.
        close_debit = old_short_leg.ltp - old_long_leg.ltp  # buy back short, sell long
        open_credit = new_short.ltp - new_long.ltp  # sell new short, buy new long
        roll_debit = close_debit - open_credit  # net debit of entire 4-leg transaction
        if (
            self._original_ic_credit > Decimal("0")
            and roll_debit > cfg.roll_debit_cap_fraction * self._original_ic_credit
        ):
            log.warning(
                "ic_nifty_v2.roll_guard_failed",
                **baseline,
                side=side,
                guard="debit_cap",
                detail=(
                    f"roll_debit={roll_debit} > "
                    f"{cfg.roll_debit_cap_fraction}×{self._original_ic_credit}"
                ),
            )
            return None, "debit_cap"

        # ── Guard 7: no inverted condor ────────────────────────────────────────
        if opposite_short_strike is not None:
            if side == "put" and new_short.strike >= opposite_short_strike:
                log.warning(
                    "ic_nifty_v2.roll_guard_failed",
                    **baseline,
                    side=side,
                    guard="inverted_condor",
                    detail=(
                        f"new put short {new_short.strike} >= "
                        f"existing call short {opposite_short_strike}"
                    ),
                )
                return None, "inverted_condor"
            if side == "call" and new_short.strike <= opposite_short_strike:
                log.warning(
                    "ic_nifty_v2.roll_guard_failed",
                    **baseline,
                    side=side,
                    guard="inverted_condor",
                    detail=(
                        f"new call short {new_short.strike} <= "
                        f"existing put short {opposite_short_strike}"
                    ),
                )
                return None, "inverted_condor"

        # ── All guards pass — build 4-leg atomic PositionUpdate ───────────────
        # Leg 1: Buy back old short (close challenged short)
        close_short_key = old_short_pos.instrument_key
        # Leg 2: Sell back old long hedge (close challenged long)
        close_long_key = old_long_pos.instrument_key
        # Leg 3: Sell new replacement short
        new_short_key = self._resolve_instrument_key(
            new_short.strike, "PE" if side == "put" else "CE", expiry
        )
        # Leg 4: Buy new replacement long wing
        new_long_key = self._resolve_instrument_key(
            new_long.strike, "PE" if side == "put" else "CE", expiry
        )
        if new_short_key is None or new_long_key is None:
            return None, "bod_key_unresolved"

        legs = [
            LegSpec(
                instrument_key=close_short_key,
                action="BUY",
                quantity=1,
                leg_role=role_short,
                notes=f"roll_close_short delta={new_short.delta}",
                price=old_short_leg.ltp,
            ),
            LegSpec(
                instrument_key=close_long_key,
                action="SELL",
                quantity=1,
                leg_role=role_long,
                notes="roll_close_long",
                price=old_long_leg.ltp,
            ),
            LegSpec(
                instrument_key=new_short_key,
                action="SELL",
                quantity=1,
                leg_role=role_short,
                notes=f"roll_open_short delta={new_short.delta}",
                price=new_short.ltp,
            ),
            LegSpec(
                instrument_key=new_long_key,
                action="BUY",
                quantity=1,
                leg_role=role_long,
                notes=f"roll_open_long delta={new_long.delta}",
                price=new_long.ltp,
            ),
        ]
        # total_credit_pts = net option points received for the roll.
        # Positive = net credit (roll collects more than it costs).
        # Negative = net debit (roll costs more than it returns — possible when
        # rolling aggressively OTM; guard 5 caps this at 50% of original credit).
        roll_net = (old_short_leg.ltp - old_long_leg.ltp) - (new_short.ltp - new_long.ltp)
        return PositionUpdate(legs=legs, total_credit_pts=roll_net), ""

    def _search_narrower_wing_candidate(
        self,
        *,
        side: Literal["put", "call"],
        market: OptionChain,
        old_long_strike: Decimal,
        new_short_strike: Decimal,
        positions: list[PaperPosition],
    ) -> OptionLeg | None:
        """BUG-022: progressively-narrower wing search after a single-candidate wing-floor miss.

        Reuses the same floor-guarantee inequality Zone 2 profit-lock enforces
        (``roll_utils.evaluate_floor_formula``, via
        ``roll_utils.search_narrow_wing_replacement``) instead of the pre-fix
        behavior, which gave up on the very first delta-band candidate that
        failed a liquidity/premium check and fell through to a naked
        single-side spread close.

        ``d_cum``/``d_lock`` are passed as zero: those terms track cumulative
        *profit-lock* roll debit (Zone 2 state), a separate bookkeeping
        concern from a delta-stop roll — conflating them would either
        double-count or require new state tracking with no council/operator
        spec behind it. See DECISIONS.md BUG-022.

        Args:
            side: "put" or "call" — which vertical is being rolled.
            market: Live option chain snapshot.
            old_long_strike: Strike of the existing long hedge being replaced.
            new_short_strike: Strike of the already-selected replacement short.
            positions: Current open IC paper positions (for the opposite
                side's wing width, feeding max(W_put, W_call)).

        Returns:
            The first candidate ``OptionLeg`` clearing both checks, or
            ``None`` if the entire range between ``old_long_strike`` and
            ``new_short_strike`` (exclusive) fails.
        """
        cfg = self._config
        plc = cfg.profit_lock
        option_type: Literal["CE", "PE"] = "CE" if side == "call" else "PE"

        opposite_side: Literal["put", "call"] = "call" if side == "put" else "put"
        opposite_short_pos = next(
            (p for p in positions if p.leg_role == f"short_{opposite_side}"), None
        )
        opposite_long_pos = next(
            (p for p in positions if p.leg_role == f"long_{opposite_side}_hedge"), None
        )
        opposite_width = Decimal("0")
        if opposite_short_pos is not None and opposite_long_pos is not None:
            opp_short_strike = self._position_strike(opposite_short_pos)
            opp_long_strike = self._position_strike(opposite_long_pos)
            if opp_short_strike is not None and opp_long_strike is not None:
                opposite_width = abs(opp_short_strike - opp_long_strike)

        entry_credit = self._original_ic_credit
        if self._store is not None:
            try:
                persisted = self._store.get_original_entry_credit(self.strategy_name)
            except Exception:  # Intentional: a transient store read failure must
                # degrade to the in-memory value, not abort the wing search.
                log.warning(
                    "ic_nifty_v2.original_entry_credit_read_failed",
                    strategy=self.strategy_name,
                    context="wing_search",
                    exc_info=True,
                )
                persisted = None
            if persisted is not None:
                entry_credit = persisted

        return roll_utils.search_narrow_wing_replacement(
            chain=market,
            option_type=option_type,
            short_strike=new_short_strike,
            current_wing_strike=old_long_strike,
            other_side_width_pts=opposite_width,
            d_cum_pts=Decimal("0"),
            d_lock_pts=Decimal("0"),
            k_pts=plc.cost_buffer_pts,
            entry_credit_pts=entry_credit,
            floor_budget=plc.floor_budget_zone2,
            min_premium=plc.zone2_long_wing_min_premium,
        )

    # ── DTE-tiered exit (IC-V2-3) ────────────────────────────────────────────

    def _evaluate_dte_action(
        self,
        dte: int,
        *,
        trade_id: str = "",
        expiry: str = "",
    ) -> Literal["NORMAL", "CLOSE_FULL", "FORCE_CLOSE"]:
        """Return the DTE-tiered exit decision for the current IC.

        Decision table (monthly, D4 ruling):
            dte ≤ 1  →  FORCE_CLOSE  (unconditional; logs dte_force_close)
            dte ≤ 7  →  CLOSE_FULL   (hard-close threshold; logs dte_close_full)
            dte > 7  →  NORMAL        (normal roll rules apply)

        The force-close threshold (DTE ≤ 1) supersedes CLOSE_FULL regardless of
        all other conditions. Both checks emit their own log event before returning
        so that the caller never needs to log the DTE decision separately.

        Args:
            dte: Days to expiry for the current monthly IC.
            trade_id: Trade ID for structured logging context (omit if unknown).
            expiry: ISO expiry string for structured logging context.

        Returns:
            One of ``"NORMAL"``, ``"CLOSE_FULL"``, or ``"FORCE_CLOSE"``.
        """
        if dte <= 1:
            log.warning(
                "ic_nifty_v2.dte_force_close",
                strategy_name=self.strategy_name,
                trade_id=trade_id,
                expiry=expiry,
                dte=dte,
            )
            return "FORCE_CLOSE"

        if dte <= self._config.monthly_close_full_dte:
            log.warning(
                "ic_nifty_v2.dte_close_full",
                strategy_name=self.strategy_name,
                trade_id=trade_id,
                expiry=expiry,
                dte=dte,
                threshold=self._config.monthly_close_full_dte,
            )
            return "CLOSE_FULL"

        return "NORMAL"

    def _should_close_full(self, dte: int) -> bool:
        """Return True when DTE triggers CLOSE_FULL or FORCE_CLOSE.

        Convenience predicate for callers that only need a boolean close decision
        and do not need to distinguish between CLOSE_FULL and FORCE_CLOSE.

        Args:
            dte: Days to expiry.

        Returns:
            True when DTE is at or below the monthly hard-close threshold (DTE ≤ 7),
            including the force-close boundary (DTE ≤ 1).
        """
        return dte <= self._config.monthly_close_full_dte

    def _roll_allowed_by_dte(self, dte: int) -> bool:
        """Return True only when the DTE level permits a partial roll.

        A roll is blocked whenever the DTE action is CLOSE_FULL or FORCE_CLOSE.
        This predicate is injected as ``roll_allowed_by_dte`` into
        ``_evaluate_adjustment()`` (implemented in IC-V2-2).

        Args:
            dte: Days to expiry.

        Returns:
            True when dte > monthly_close_full_dte (i.e., dte > 7 by default);
            False otherwise.
        """
        return dte > self._config.monthly_close_full_dte

    # ── Signal evaluation (IC-V2-4 + IC-V2-10) ──────────────────────────────

    async def check_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """Evaluate exit/adjustment signals for the open IronCondorV2 position."""
        events = await self._evaluate_signals(market, positions)
        if events:
            ic_positions = [
                p for p in positions if p.strategy_name == self.strategy_name and p.net_qty != 0
            ]
            for e in events:
                if e.severity == "ACTION":
                    self._log_counterfactual_exit(e, market, ic_positions)
        return events

    async def _evaluate_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """Evaluate exit/adjustment signals for the open IronCondorV2 position.

        Filters positions to ``strategy_name == self.strategy_name`` and to
        ``net_qty != 0``. A flat leg's ``instrument_key`` is its most
        recently *closed* contract (``PaperStore.get_positions`` still
        returns one ``PaperPosition`` per ``leg_role`` regardless of
        flatness, per BUG-014) — once that contract settles, Upstox's BOD
        file drops it permanently, so resolving it via the chain/BOD lookups
        used below can never succeed again. Without this filter, a
        fully-closed V2 IC keeps getting evaluated (and warning) on every
        tick indefinitely. Same defect class as BUG-014 and the
        ``ic_nifty_v1.py`` fix (see DECISIONS.md 2026-07-21).

        8-level precedence ladder (council ruling IC-V2-4 + IC-V2-10):
          1. DTE ≤ hard-close cutoff → FORCED_CLOSE (FORCE_CLOSE or CLOSE_FULL both fire here)
          2. |short_delta| ≥ 0.45   → FORCED_CLOSE (extreme delta)
          3. D3 roll budget exhausted + delta breach → FORCED_CLOSE
          4. captured ≥ 70%          → CLOSE_FULL (profit target)
          5. captured ≥ 50% (Zone 2) → PROFIT_LOCK_ZONE2 / FORCED_CLOSE / continue
          6. captured ≥ 25% (Zone 1) → PROFIT_LOCK_ZONE1 INFO (log-only milestone)
          7. |short_delta| ≥ 0.35   → D3 roll (ROLL_WING / DELTA_STOP)
          8. |short_delta| ≥ 0.30   → DELTA_WARN
          Hold → []

        Args:
            market: Current Nifty 50 option chain snapshot.
            positions: All open paper positions (may include other strategies).

        Returns:
            List of SignalEvents; empty when no action is warranted.
        """
        ic_positions = [
            p for p in positions if p.strategy_name == self.strategy_name and p.net_qty != 0
        ]
        # TEMP DIAGNOSTIC (BUG-018, remove after 2026-07-24 verification —
        # see docs/bugs/bugs.md): confirms live ticks now reach this point
        # and resolve an expiry, instead of silently short-circuiting.
        log.debug(
            "ic_nifty_v2.check_signals_entry_diag",
            strategy=self.strategy_name,
            positions_total=len(positions),
            ic_positions_count=len(ic_positions),
        )
        if not ic_positions:
            return []

        # ── DTE / expiry ─────────────────────────────────────────────────────
        expiry = next(
            (
                self._parse_expiry(p.instrument_key)
                for p in ic_positions
                if self._parse_expiry(p.instrument_key) is not None
            ),
            None,
        )
        log.debug(
            "ic_nifty_v2.check_signals_expiry_diag",
            strategy=self.strategy_name,
            expiry=str(expiry) if expiry is not None else None,
        )
        if expiry is None:
            return []
        dte = (expiry - market_today()).days
        expiry_str = str(expiry)

        # ── Priority 1: DTE hard-close (FORCE_CLOSE or CLOSE_FULL) ───────────
        dte_action = self._evaluate_dte_action(dte, expiry=expiry_str)
        if dte_action in ("FORCE_CLOSE", "CLOSE_FULL"):
            reason = "dte_force_close" if dte_action == "FORCE_CLOSE" else "dte_close_full"
            desc = (
                f"DTE {dte} ≤ 1 — force close; expiry imminent"
                if dte_action == "FORCE_CLOSE"
                else f"DTE {dte} ≤ {self._config.monthly_close_full_dte} — monthly hard close"
            )
            return [
                SignalEvent(
                    event_type="FORCED_CLOSE",
                    severity="ACTION",
                    description=desc,
                    payload={
                        "dte": dte,
                        "reason": reason,
                        "auto_execute": True,
                        "auto_action": "CLOSE_FULL",
                        "valid_actions": ["CLOSE_FULL"],
                    },
                )
            ]

        # ── Priority 2 & 3: Hard delta signals → FORCED_CLOSE ────────────────
        _baseline = {
            "strategy_name": self.strategy_name,
            "trade_id": "",
            "expiry": expiry_str,
            "dte": dte,
            "roll_count_put": self._rolls_executed["put"],
            "roll_count_call": self._rolls_executed["call"],
            "profit_lock_zone": 0,
        }
        short_put_pos = next((p for p in ic_positions if p.leg_role == "short_put"), None)
        short_call_pos = next((p for p in ic_positions if p.leg_role == "short_call"), None)
        for side, pos in (("put", short_put_pos), ("call", short_call_pos)):
            delta_val = self._get_short_delta(market, pos)
            if delta_val is None:
                continue
            abs_delta = abs(delta_val)
            # Priority 2: extreme delta ≥ 0.45
            if abs_delta >= self._config.forced_close_delta:
                log.warning(
                    "ic_nifty_v2.forced_close_delta",
                    **_baseline,
                    side=side,
                    short_delta=str(delta_val),
                    threshold=str(self._config.forced_close_delta),
                )
                return [
                    SignalEvent(
                        event_type="FORCED_CLOSE",
                        severity="ACTION",
                        description=(
                            f"{side} |delta| ≥ {self._config.forced_close_delta} — forced full close"
                        ),
                        payload={
                            "side": side,
                            "dte": dte,
                            "reason": "extreme_delta",
                            "auto_execute": True,
                            "auto_action": "CLOSE_FULL",
                            "valid_actions": ["CLOSE_FULL"],
                        },
                    )
                ]
            # Priority 3: rolls exhausted + delta breach ≥ 0.35
            if (
                abs_delta >= self._config.roll_trigger_delta
                and self._rolls_executed[side] >= self._config.max_rolls_per_side_per_cycle
            ):
                log.warning(
                    "ic_nifty_v2.forced_close_rolls_exhausted",
                    **_baseline,
                    side=side,
                    roll_count=self._rolls_executed[side],
                )
                return [
                    SignalEvent(
                        event_type="FORCED_CLOSE",
                        severity="ACTION",
                        description=(
                            f"{side} rolls exhausted ({self._rolls_executed[side]}) — forced full close"
                        ),
                        payload={
                            "side": side,
                            "dte": dte,
                            "reason": "rolls_exhausted",
                            "auto_execute": True,
                            "auto_action": "CLOSE_FULL",
                            "valid_actions": ["CLOSE_FULL"],
                        },
                    )
                ]

        # ── Compute PnL (needed for priorities 4–6) ───────────────────────────
        combined_mark, entry_credit = self._compute_combined_pnl(market, ic_positions)
        # BUG-020 Phase 3: anchor captured-fraction calc (profit target +
        # profit-lock zones) to the atomic 4-leg credit persisted at entry,
        # not the recomputed sum over currently-open legs — a partial close
        # (e.g. one spread closed) must not re-scope the target to the
        # smaller surviving-legs credit. `None` (pre-Phase-2 positions, or
        # no store injected) falls back to today's recompute, unchanged.
        original_entry_credit: Decimal | None = None
        if self._store is not None:
            try:
                original_entry_credit = self._store.get_original_entry_credit(self.strategy_name)
            except Exception:  # Intentional: a transient store read failure must
                # not skip priorities 4-8 for this tick (delta-roll evaluation
                # included) — degrade to the pre-Phase-3 recompute, same as the
                # "never persisted" (None) case, rather than propagating.
                log.warning(
                    "ic_nifty_v2.original_entry_credit_read_failed",
                    strategy=self.strategy_name,
                    exc_info=True,
                )
        if original_entry_credit is not None:
            entry_credit = original_entry_credit
        captured_fraction: Decimal | None = None
        if combined_mark is not None and entry_credit > Decimal("0"):
            captured_fraction = (entry_credit - combined_mark) / entry_credit
            # TEMP DIAGNOSTIC (BUG-018, remove after 2026-07-24 verification):
            # unconditional per-tick visibility into the live captured_fraction,
            # to compare against paper_snapshot.py's independently-computed
            # EOD unrealized_pnl for the same strategy/day.
            log.debug(
                "ic_nifty_v2.check_signals_pnl_diag",
                strategy=self.strategy_name,
                combined_mark_pts=str(combined_mark),
                entry_credit_pts=str(entry_credit),
                captured_fraction=str(captured_fraction.quantize(Decimal("0.0001"))),
            )
        else:
            # 2026-07-20: makes the priorities-4-6 skip visible — see
            # ic_nifty_v1.py's identical fix and DECISIONS.md 2026-07-20.
            log.debug(
                "ic_nifty_v2.pnl_gate_skipped",
                strategy=self.strategy_name,
                reason="mark_unavailable" if combined_mark is None else "entry_credit_not_positive",
                entry_credit=str(entry_credit),
            )

        # ── Priority 4: Profit target ≥ 70% → CLOSE_FULL ─────────────────────
        if captured_fraction is not None and combined_mark is not None:
            if combined_mark <= _PROFIT_TARGET_RETENTION * entry_credit:
                log.info(
                    "ic_nifty_v2.profit_target_close",
                    strategy_name=self.strategy_name,
                    trade_id="",
                    expiry=expiry_str,
                    dte=dte,
                    captured_fraction=str(captured_fraction.quantize(Decimal("0.01"))),
                    current_mark_pts=str(combined_mark),
                    entry_credit_pts=str(entry_credit),
                )
                return [
                    SignalEvent(
                        event_type="CLOSE_FULL",
                        severity="ACTION",
                        description=(
                            f"Profit target: {float(captured_fraction):.0%} of entry credit captured"
                        ),
                        payload={
                            "captured_fraction": str(captured_fraction.quantize(Decimal("0.01"))),
                            "current_mark_pts": str(combined_mark),
                            "entry_credit_pts": str(entry_credit),
                            "auto_execute": True,
                            "auto_action": "CLOSE_FULL",
                            "valid_actions": ["CLOSE_FULL"],
                        },
                    )
                ]

        # ── Priorities 5 & 6: Profit-lock zones ───────────────────────────────
        if captured_fraction is not None and self._store is not None:
            pl_signals = self._check_profit_lock(
                captured_fraction=captured_fraction,
                entry_credit_pts=entry_credit,
                combined_mark=combined_mark if combined_mark is not None else Decimal("0"),
                dte=dte,
                expiry_str=expiry_str,
                market=market,
                ic_positions=ic_positions,
            )
            if pl_signals:
                return pl_signals

        # ── Priorities 7 & 8: Soft delta signals — D3 roll / DELTA_WARN ───────
        # At this point priorities 2+3 have already caught all FORCED_CLOSE cases.
        # _evaluate_adjustment may still return FORCED_CLOSE as belt-and-suspenders;
        # if so, the signal is correct.
        roll_allowed = self._roll_allowed_by_dte(dte)
        roll_result = self._evaluate_adjustment(
            ic_positions, market, dte, expiry_str, roll_allowed_by_dte=roll_allowed
        )
        if roll_result is not None:
            return [self._roll_result_to_signal(roll_result, dte, expiry_str, dte_action)]

        # ── Hold ──────────────────────────────────────────────────────────────
        return []

    def _check_profit_lock(
        self,
        captured_fraction: Decimal,
        entry_credit_pts: Decimal,
        combined_mark: Decimal,
        dte: int,
        expiry_str: str,
        market: OptionChain,
        ic_positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """Evaluate profit-lock priorities 5 (Zone 2) and 6 (Zone 1).

        Priority 5: Zone 2 (≥ 50%) — attempt wing contraction or CLOSE_FULL.
        Priority 6: Zone 1 (≥ 25%) — emit INFO milestone, log and persist state.

        Returns [] when no profit-lock signal fires (zone not yet reached, guards
        blocked it, or zone already acted upon).

        Council ruling: docs/archive/council/strategy/2026-06-27_ic-v2-profit-lock-adjustment.md Stage 3.

        Args:
            captured_fraction: (entry_credit - current_mark) / entry_credit.
            entry_credit_pts: Original IC entry credit in option points per unit.
            combined_mark: Current combined mark in option points.
            dte: Days to expiry.
            expiry_str: ISO expiry string for structured logging.
            market: Live option chain snapshot.
            ic_positions: IC positions for this strategy.

        Returns:
            List of SignalEvents; empty when no profit-lock action is warranted.
        """
        # self._store is not None — guarded by caller (check_signals line 1236)
        pl_state = self._store.get_profit_lock_state(self.strategy_name)
        pl_config = self._config.profit_lock
        _plog = {
            "strategy_name": self.strategy_name,
            "trade_id": "",
            "expiry": expiry_str,
            "dte": dte,
            "roll_count_put": self._rolls_executed["put"],
            "roll_count_call": self._rolls_executed["call"],
        }

        # ── Priority 5: Zone 2 (≥ 50%) ───────────────────────────────────────
        if captured_fraction >= pl_config.zone2_trigger:
            if not pl_state.zone2_lock_executed:
                short_put_pos = next((p for p in ic_positions if p.leg_role == "short_put"), None)
                short_call_pos = next((p for p in ic_positions if p.leg_role == "short_call"), None)
                short_put_strike = self._position_strike(short_put_pos)
                short_call_strike = self._position_strike(short_call_pos)

                if short_put_strike is None or short_call_strike is None:
                    log.warning(
                        "ic_nifty_v2.chain_lookup_failed",
                        **_plog,
                        profit_lock_zone=pl_state.profit_lock_zone,
                        instrument_key="short_strikes",
                    )
                    return []

                long_put_pos = next(
                    (p for p in ic_positions if p.leg_role == "long_put_hedge"), None
                )
                long_call_pos = next(
                    (p for p in ic_positions if p.leg_role == "long_call_hedge"), None
                )
                old_long_put = (
                    self._find_leg(market, long_put_pos.instrument_key) if long_put_pos else None
                )
                old_long_call = (
                    self._find_leg(market, long_call_pos.instrument_key) if long_call_pos else None
                )
                vix, ivr = self._load_vix_ivr()

                decision: ProfitLockDecision = ProfitLockEngine().evaluate(
                    captured_fraction=captured_fraction,
                    entry_credit_pts=entry_credit_pts,
                    current_mark_pts=combined_mark,
                    dte=dte,
                    expiry_type=self._config.expiry_type,
                    vix=vix,
                    ivr=ivr,
                    state=pl_state,
                    chain=market,
                    config=pl_config,
                    short_put_strike=short_put_strike,
                    short_call_strike=short_call_strike,
                    old_long_put=old_long_put,
                    old_long_call=old_long_call,
                )

                # Log Zone 2 attempt evaluation
                log.info(
                    "ic_nifty_v2.profit_lock_zone2_attempt",
                    **_plog,
                    captured_fraction=str(captured_fraction.quantize(Decimal("0.01"))),
                    zone=2,
                    formula_passes=(decision.action in ("ZONE2_LOCK", "CLOSE_FULL")),
                )

                if decision.action == "ZONE2_LOCK":
                    new_put_wing = decision.new_put_wing
                    new_call_wing = decision.new_call_wing
                    new_put_width = (
                        int(short_put_strike - new_put_wing.strike) if new_put_wing else 0
                    )
                    new_call_width = (
                        int(new_call_wing.strike - short_call_strike) if new_call_wing else 0
                    )
                    log.info(
                        "ic_nifty_v2.profit_lock_zone2_executed",
                        **_plog,
                        profit_lock_zone=2,
                        new_put_wing_strike=str(new_put_wing.strike) if new_put_wing else "",
                        new_call_wing_strike=str(new_call_wing.strike) if new_call_wing else "",
                        net_debit_pts=str(decision.net_debit_pts),
                        guaranteed_floor_fraction=str(decision.guaranteed_floor_fraction),
                    )
                    old_long_put_key = long_put_pos.instrument_key if long_put_pos else ""
                    old_long_call_key = long_call_pos.instrument_key if long_call_pos else ""
                    new_put_key = (
                        self._resolve_instrument_key(new_put_wing.strike, "PE", expiry_str)
                        if new_put_wing
                        else None
                    ) or ""
                    new_call_key = (
                        self._resolve_instrument_key(new_call_wing.strike, "CE", expiry_str)
                        if new_call_wing
                        else None
                    ) or ""
                    new_cum_debit = pl_state.cumulative_lock_debit_pts + (
                        decision.net_debit_pts or Decimal("0")
                    )
                    zone2_legs_to_open: list[LegSpec] = []
                    if new_put_wing and new_put_key:
                        zone2_legs_to_open.append(
                            LegSpec(
                                instrument_key=new_put_key,
                                action="BUY",
                                quantity=1,
                                leg_role="long_put_hedge",
                                notes="profit_lock_zone2_open_put",
                                price=new_put_wing.ltp,
                            )
                        )
                    if new_call_wing and new_call_key:
                        zone2_legs_to_open.append(
                            LegSpec(
                                instrument_key=new_call_key,
                                action="BUY",
                                quantity=1,
                                leg_role="long_call_hedge",
                                notes="profit_lock_zone2_open_call",
                                price=new_call_wing.ltp,
                            )
                        )
                    return [
                        SignalEvent(
                            event_type="PROFIT_LOCK_ZONE2",
                            severity="ACTION",
                            description=(
                                f"Zone 2 profit-lock: {float(captured_fraction):.0%} captured — "
                                f"rolling wings inward; floor "
                                f"≥{float(decision.guaranteed_floor_fraction or 0):.0%}"
                            ),
                            payload={
                                "zone": 2,
                                "captured_fraction": str(
                                    captured_fraction.quantize(Decimal("0.01"))
                                ),
                                "new_put_wing_strike": (
                                    str(new_put_wing.strike) if new_put_wing else ""
                                ),
                                "new_call_wing_strike": (
                                    str(new_call_wing.strike) if new_call_wing else ""
                                ),
                                "new_put_width_pts": new_put_width,
                                "new_call_width_pts": new_call_width,
                                "net_debit_pts": str(decision.net_debit_pts),
                                "guaranteed_floor_fraction": str(
                                    decision.guaranteed_floor_fraction
                                ),
                                "entry_credit_pts": str(entry_credit_pts),
                                "old_long_put_key": old_long_put_key,
                                "old_long_call_key": old_long_call_key,
                                "new_put_wing_key": new_put_key,
                                "new_call_wing_key": new_call_key,
                                "dte": dte,
                                "auto_execute": True,
                                "auto_action": "PROFIT_LOCK_ZONE2",
                                "valid_actions": ["PROFIT_LOCK_ZONE2", "CLOSE_FULL"],
                                # State update fields consumed by apply_action
                                "new_profit_lock_zone": 2,
                                "zone2_lock_executed": True,
                                "cumulative_lock_debit_pts": str(new_cum_debit),
                                "cycle_id": pl_state.cycle_id,
                                "legs_to_open": zone2_legs_to_open,
                            },
                        )
                    ]

                if decision.action == "CLOSE_FULL":
                    log.warning(
                        "ic_nifty_v2.profit_lock_close_full",
                        **_plog,
                        profit_lock_zone=pl_state.profit_lock_zone,
                        reason=decision.skip_reason or "formula_failed",
                        captured_fraction=str(captured_fraction.quantize(Decimal("0.01"))),
                    )
                    return [
                        SignalEvent(
                            event_type="FORCED_CLOSE",
                            severity="ACTION",
                            description=(
                                f"Zone 2 profit-lock formula failed "
                                f"({decision.skip_reason}) — closing full IC"
                            ),
                            payload={
                                "reason": f"profit_lock_close_full:{decision.skip_reason}",
                                "captured_fraction": str(
                                    captured_fraction.quantize(Decimal("0.01"))
                                ),
                                "dte": dte,
                                "auto_execute": True,
                                "auto_action": "CLOSE_FULL",
                                "valid_actions": ["CLOSE_FULL"],
                            },
                        )
                    ]

                # action == "NONE": guard blocked lock — log and fall through
                if decision.skip_reason:
                    log.warning(
                        "ic_nifty_v2.profit_lock_zone2_skipped",
                        **_plog,
                        profit_lock_zone=pl_state.profit_lock_zone,
                        skip_reason=decision.skip_reason,
                        captured_fraction=str(captured_fraction.quantize(Decimal("0.01"))),
                    )
            # zone2_lock_executed=True or NONE guard: fall through without signal

        # ── Priority 6: Zone 1 (≥ 25%) — log INFO milestone ──────────────────
        elif captured_fraction >= pl_config.zone1_trigger:
            if pl_state.profit_lock_zone < 1:
                log.info(
                    "ic_nifty_v2.profit_lock_zone1",
                    **_plog,
                    profit_lock_zone=1,
                    captured_fraction=str(captured_fraction.quantize(Decimal("0.01"))),
                    zone=1,
                )
                new_state = ProfitLockState(
                    profit_lock_zone=1,
                    zone2_lock_executed=pl_state.zone2_lock_executed,
                    zone3_lock_executed=pl_state.zone3_lock_executed,
                    cumulative_lock_debit_pts=pl_state.cumulative_lock_debit_pts,
                    active_put_width_pts=pl_state.active_put_width_pts,
                    active_call_width_pts=pl_state.active_call_width_pts,
                    cycle_id=pl_state.cycle_id,
                )
                self._store.set_profit_lock_state(self.strategy_name, new_state)
                return [
                    SignalEvent(
                        event_type="PROFIT_LOCK_ZONE1",
                        severity="INFO",
                        description=(
                            f"Zone 1 reached: {float(captured_fraction):.0%} of entry credit captured"
                        ),
                        payload={
                            "zone": 1,
                            "captured_fraction": str(captured_fraction.quantize(Decimal("0.01"))),
                        },
                    )
                ]

        return []

    def _resolve_instrument_key(
        self, strike: Decimal, option_type: str, expiry_str: str
    ) -> str | None:
        """Resolve a chain-scanned candidate leg to its real BOD instrument_key.

        Shared by entry (``enter()``, BUG-024) and roll/profit-lock target
        selection (``_execute_partial_roll``, Zone 2 profit-lock in
        ``_roll_result_to_signal``, BUG-023) — all three build the
        candidate leg from an ``OptionLeg`` (chain scan result), which
        carries no ``instrument_key`` at all. String-formatting the strike
        into a symbol-style key produces one that can never resolve, since
        real Upstox keys are numeric-only. Route through the offline BOD
        instrument master instead, same as every other persisting call site
        in this codebase.

        Args:
            strike: Candidate leg's strike price.
            option_type: ``"CE"`` or ``"PE"``.
            expiry_str: Already-resolved expiry (ISO string), to
                disambiguate the same strike across multiple live expiries.

        Returns:
            Real numeric ``instrument_key``, or ``None`` when the
            strike/type/expiry combination isn't present in BOD — treated
            as a failed candidate, not an exception.
        """
        try:
            lookup = InstrumentLookup.from_file(DEFAULT_BOD_PATH)
            matches = lookup.search_options(
                underlying="NIFTY",
                strike=float(strike),
                option_type=option_type,
                expiry=expiry_str,
            )
        except Exception as exc:  # Intentional: fail-safe BOD lookup
            log.warning(
                "ic_nifty_v2.instrument_key_bod_lookup_failed",
                strike=str(strike),
                option_type=option_type,
                error=str(exc),
            )
            return None

        if not matches:
            log.warning(
                "ic_nifty_v2.instrument_key_not_in_bod",
                strike=str(strike),
                option_type=option_type,
                expiry=expiry_str,
            )
            return None

        return matches[0]["instrument_key"]

    def _roll_result_to_signal(
        self,
        roll_result: RollResult,
        dte: int,
        expiry_str: str,
        dte_action: str,
    ) -> SignalEvent:
        """Convert a RollResult from _evaluate_adjustment to a SignalEvent.

        DELTA_STOP with block_reason=="dte_cutoff" escalates to FORCED_CLOSE when
        DTE action is CLOSE_FULL, because the whole IC must close rather than
        just the challenged spread.

        Args:
            roll_result: Output of _evaluate_adjustment.
            dte: Days to expiry (for payload logging).
            expiry_str: ISO expiry string.
            dte_action: Output of _evaluate_dte_action ("NORMAL"/"CLOSE_FULL"/"FORCE_CLOSE").

        Returns:
            The appropriate SignalEvent for this roll result.
        """
        sig = roll_result.signal_type
        side = roll_result.side

        if sig == "DELTA_WARN":
            return SignalEvent(
                event_type="DELTA_WARN",
                severity="WARN",
                description=f"{side} leg |delta| ≥ {self._config.roll_warn_delta} — delta warning",
                payload={"side": side, "dte": dte, "expiry": expiry_str},
            )

        if sig == "ROLL_WING":
            legs_to_open = (
                [leg for leg in roll_result.roll_update.legs if leg.notes.startswith("roll_open_")]
                if roll_result.roll_update is not None
                else []
            )
            return SignalEvent(
                event_type="ROLL_WING",
                severity="ACTION",
                description=f"{side} spread rolled farther OTM",
                payload={
                    "side": side,
                    "dte": dte,
                    "expiry": expiry_str,
                    "auto_execute": True,
                    "auto_action": "ROLL_WING",
                    "valid_actions": ["ROLL_WING", "CLOSE_FULL"],
                    "legs_to_open": legs_to_open,
                },
            )

        if sig == "DELTA_STOP":
            # dte_cutoff guard with CLOSE_FULL DTE → escalate to full close
            if roll_result.block_reason == "dte_cutoff" and dte_action == "CLOSE_FULL":
                return SignalEvent(
                    event_type="FORCED_CLOSE",
                    severity="ACTION",
                    description=(
                        f"{side} delta breached roll threshold but DTE {dte} blocks roll"
                        " — forcing full close"
                    ),
                    payload={
                        "side": side,
                        "dte": dte,
                        "reason": "delta_breach_dte_cutoff",
                        "auto_execute": True,
                        "auto_action": "CLOSE_FULL",
                        "valid_actions": ["CLOSE_FULL"],
                    },
                )
            # BUG-022: a roll failure — for any guard reason, not just a wing-
            # floor miss (which now has its own narrower-search fallback in
            # _execute_partial_roll before ever reaching DELTA_STOP) — must
            # never fall through to a naked single-side CLOSE_CALL_SPREAD/
            # CLOSE_PUT_SPREAD. Escalate to a full close instead; the IC never
            # ends up structurally one-sided as its final state.
            return SignalEvent(
                event_type="DELTA_STOP",
                severity="ACTION",
                description=(
                    f"{side} spread delta stop — roll blocked "
                    f"({roll_result.block_reason}); escalating to full close (BUG-022)"
                ),
                payload={
                    "side": side,
                    "block_reason": roll_result.block_reason,
                    "dte": dte,
                    "auto_execute": True,
                    "auto_action": "CLOSE_FULL",
                    "valid_actions": ["CLOSE_FULL"],
                },
            )

        # sig == "FORCED_CLOSE"
        return SignalEvent(
            event_type="FORCED_CLOSE",
            severity="ACTION",
            description=f"{side} |delta| ≥ {self._config.forced_close_delta} — forced full close",
            payload={
                "side": side,
                "dte": dte,
                "reason": roll_result.block_reason or "extreme_delta",
                "auto_execute": True,
                "auto_action": "CLOSE_FULL",
                "valid_actions": ["CLOSE_FULL"],
            },
        )

    def describe_context(
        self,
        event: SignalEvent,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> str:
        """Build a plain-text context block for the council prompt.

        Summarises: spot, DTE, IVR, entry credit, combined mark, per-leg Greeks.

        Args:
            event: Signal event that triggered the context request.
            market: Current Nifty 50 option chain snapshot.
            positions: All open paper positions.

        Returns:
            Multi-line plain-text context string; no HTML markup.
        """
        ic_positions = [p for p in positions if p.strategy_name == self.strategy_name]
        expiry = next(
            (self._parse_expiry(p.instrument_key) for p in ic_positions),
            None,
        )
        dte = (expiry - market_today()).days if expiry is not None else None
        combined_mark, entry_credit = self._compute_combined_pnl(market, ic_positions)

        lines: list[str] = [
            f"Strategy: {self.strategy_name}",
            f"Signal: {event.event_type} ({event.severity})",
            f"Nifty spot: {market.underlying_spot}",
            f"DTE: {dte if dte is not None else 'unavailable'}",
            self._compute_ivr_str(),
            f"Entry credit: {entry_credit}",
            f"Combined mark: {combined_mark if combined_mark is not None else 'unavailable'}",
            f"Roll counts: put={self._rolls_executed['put']} call={self._rolls_executed['call']}",
        ]
        for pos in ic_positions:
            opt_leg = self._find_leg(market, pos.instrument_key)
            lines.append(f"Leg: {pos.leg_role} | key: {pos.instrument_key}")
            if opt_leg is not None:
                lines.append(f"  Delta: {opt_leg.delta}  IV: {opt_leg.iv}  LTP: {opt_leg.ltp}")
            else:
                lines.append("  Chain lookup: unavailable")

        if not ic_positions:
            lines.append("No open IC V2 positions found.")

        return "\n".join(lines)

    async def apply_action(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> list[PaperPosition]:
        """Validate and apply an approved action for IronCondorV2.

        Accepted action types: ``CLOSE_FULL``, ``CLOSE_CALL_SPREAD``,
        ``CLOSE_PUT_SPREAD``, and ``ROLL_WING``.  Any other action_type
        raises ``ValueError``.

        For auto-executed actions the legs_to_close set is derived from
        the action_type rather than relying on caller-populated legs_to_close.

        Args:
            positions: Current open paper positions.
            action: Approved action; must have an allowed action_type.

        Returns:
            Updated positions with closed legs filtered out.

        Raises:
            ValueError: When action_type is not in the allowed set.
        """
        if action.action_type not in _ALLOWED_V2_ACTIONS:
            raise ValueError(
                f"IronCondorV2 does not permit {action.action_type!r} — "
                f"allowed: {sorted(_ALLOWED_V2_ACTIONS)}."
            )

        # ic_positions: this strategy's open legs, used to resolve the exact
        # instrument to close per role (PG-4g) — mirrors ic_nifty_v1's
        # _auto_select_action / effective_legs pattern (PG-4f) so a roll
        # overlap (two positions sharing a leg_role with different
        # instrument_keys) only matches the specific instrument identified
        # by signal evaluation, not "a" position with that role.
        ic_positions = [
            p for p in positions if p.strategy_name == self.strategy_name and p.net_qty != 0
        ]

        closed = {leg.leg_role for leg in action.legs_to_close}
        if self._is_auto_execute(action):
            if action.action_type == "CLOSE_FULL":
                closed = _SHORT_ROLES | _LONG_ROLES
            elif action.action_type == "CLOSE_CALL_SPREAD":
                closed = {"short_call", "long_call_hedge"}
            elif action.action_type == "CLOSE_PUT_SPREAD":
                closed = {"short_put", "long_put_hedge"}
            elif action.action_type == "PROFIT_LOCK_ZONE2":
                closed = {"long_put_hedge", "long_call_hedge"}
            # ROLL_WING / PROFIT_LOCK_ZONE2: legs_to_close comes from the payload;
            # persistence of both sides (old leg close + new leg open) happens
            # below via roll_ic_legs, after effective_legs is built, mirroring
            # the CLOSE_* pattern. BUG-025 W2: for PROFIT_LOCK_ZONE2, the
            # ProfitLockState write and Telegram notification used to happen
            # here — before roll_ic_legs was even called — so a roll_ic_legs
            # failure (broker/store exception, or its own price guard aborting)
            # left the state store saying the zone-2 lock executed while the
            # leg replacement never persisted. Both now happen after
            # roll_ic_legs, gated on rolled_trades being non-empty, below.

        # Populate instrument_key per role from ic_positions so a roll overlap
        # only matches the exact instrument, not any position sharing the role.
        effective_legs = [
            LegClose(
                leg_role=r,
                instrument_key=(
                    pos.instrument_key
                    if (pos := _position_for_role(ic_positions, r)) is not None
                    else None
                ),
            )
            for r in closed
        ]

        log.info(
            "ic_nifty_v2.apply_action",
            strategy_name=self.strategy_name,
            action_type=action.action_type,
            legs_to_close=list(closed),
        )

        if action.action_type in ("CLOSE_FULL", "CLOSE_CALL_SPREAD", "CLOSE_PUT_SPREAD") and (
            self._is_auto_execute(action)
        ):
            if self._broker is None or self._store is None:
                log.warning(
                    "ic_nifty_v2.apply_action.no_broker_or_store",
                    action_type=action.action_type,
                    strategy_name=self.strategy_name,
                )
            else:
                triggering_signal = (action.metadata or {}).get("event_type", action.action_type)
                closed_trades = await close_ic_legs(
                    broker=self._broker,
                    store=self._store,
                    positions=[
                        p
                        for p in positions
                        if any(_leg_close_matches(p, leg) for leg in effective_legs)
                    ],
                    closed_roles=closed,
                    strategy_name=self.strategy_name,
                    notes=f"ic_nifty_v2 auto-close: {triggering_signal}",
                )
                # BUG-013 (2026-07-20): only PROFIT_LOCK_ZONE2 sent a Telegram
                # confirmation — CLOSE_FULL/CLOSE_CALL_SPREAD/CLOSE_PUT_SPREAD
                # (the far more common full-close actions, including the one
                # triggered by PROFIT_TARGET) were silent. See DECISIONS.md
                # 2026-07-20 and docs/bugs/bugs.md BUG-013.
                await self._send_close_notification(
                    action.action_type, triggering_signal, closed_trades
                )
        elif action.action_type in ("ROLL_WING", "PROFIT_LOCK_ZONE2") and self._is_auto_execute(
            action
        ):
            if self._broker is None or self._store is None:
                log.warning(
                    "ic_nifty_v2.apply_action.no_broker_or_store",
                    action_type=action.action_type,
                    strategy_name=self.strategy_name,
                )
            else:
                triggering_signal = (action.metadata or {}).get("event_type", action.action_type)
                rolled_trades = await roll_ic_legs(
                    broker=self._broker,
                    store=self._store,
                    close_positions=[
                        p
                        for p in positions
                        if any(_leg_close_matches(p, leg) for leg in effective_legs)
                    ],
                    closed_roles=closed,
                    open_legs=action.legs_to_open,
                    strategy_name=self.strategy_name,
                    notes=f"ic_nifty_v2 roll: {triggering_signal}",
                )
                log.info(
                    "ic_nifty_v2.roll_persisted",
                    strategy_name=self.strategy_name,
                    action_type=action.action_type,
                    legs=[t.leg_role for t in rolled_trades],
                )
                if action.action_type == "PROFIT_LOCK_ZONE2" and rolled_trades:
                    # BUG-025 W2: persist the zone-2 lock state and send the
                    # Telegram confirmation only once roll_ic_legs has actually
                    # written the new wings — an empty/failed roll must not
                    # claim the lock executed.
                    if self._store is not None:
                        meta = action.metadata or {}
                        new_state = ProfitLockState(
                            profit_lock_zone=int(meta.get("new_profit_lock_zone", 2)),
                            zone2_lock_executed=True,
                            zone3_lock_executed=False,
                            cumulative_lock_debit_pts=Decimal(
                                meta.get("cumulative_lock_debit_pts", "0")
                            ),
                            active_put_width_pts=int(meta.get("new_put_width_pts", 0)),
                            active_call_width_pts=int(meta.get("new_call_width_pts", 0)),
                            cycle_id=str(meta.get("cycle_id", "")),
                        )
                        self._store.set_profit_lock_state(self.strategy_name, new_state)
                    if self._notifier is not None:
                        try:
                            await self._send_profit_lock_notification(action.metadata or {})
                        except Exception as exc:
                            log.error("ic_nifty_v2.send_notification_failed", error=str(exc))
        return [
            p for p in positions if not any(_leg_close_matches(p, leg) for leg in effective_legs)
        ]

    async def _send_close_notification(
        self,
        action_type: str,
        triggering_signal: str,
        closed_trades: list[PaperTrade],
    ) -> None:
        """Send a plain HTML close-confirmation notification. Non-fatal.

        Mirrors IronCondorV1._send_close_notification and the existing
        _send_profit_lock_notification pattern already used here for Zone 2.

        Args:
            action_type: The ApprovedAction.action_type that was executed
                (CLOSE_FULL, CLOSE_CALL_SPREAD, or CLOSE_PUT_SPREAD).
            triggering_signal: The SignalEvent.event_type that caused the
                auto-execute (e.g. the profit-target/DTE/delta FORCED_CLOSE
                reasons this strategy uses).
            closed_trades: The closing PaperTrade rows actually persisted by
                close_ic_legs(); empty when nothing was open to close.
        """
        if self._notifier is None:
            return
        if not closed_trades:
            return
        legs_text = "\n".join(
            f"  {t.leg_role}: {t.action.value} {t.quantity} @ {t.price}" for t in closed_trades
        )
        try:
            # Deferred import: src.paper.tracker -> src.paper.store ->
            # src.strategy.profit_lock_engine creates a circular import if
            # hoisted to module level, since src/strategy/__init__.py eagerly
            # imports this module.
            from src.paper.tracker import get_strategy_realized_pnl

            net_pnl = get_strategy_realized_pnl(self._store, self.strategy_name)
            pnl_text = f"Net P&L: ₹{net_pnl:,.2f}\n"
        except Exception as exc:
            log.warning("ic_nifty_v2.net_pnl_calc_failed", error=str(exc))
            pnl_text = ""
        text = (
            f"✅ <b>IC V2 closed — {triggering_signal}</b>\n"
            f"Strategy: <code>{self.strategy_name}</code>\n"
            f"Action: {action_type}\n"
            f"{pnl_text}"
            f"{legs_text}"
        )
        try:
            await self._notifier.send_notification(text)
        except Exception as exc:
            log.error("ic_nifty_v2.send_notification_failed", error=str(exc))

    # ── Private helpers (copied verbatim from ic_nifty_v1) ───────────────────

    def _is_auto_execute(self, action: ApprovedAction) -> bool:
        """Determine if an action was initiated automatically or manually."""
        if action.metadata and action.metadata.get("auto_selected"):
            return True
        return action.rationale == "auto-execute"

    def _find_leg(self, market: OptionChain, instrument_key: str) -> OptionLeg | None:
        """Locate a CE or PE leg in the chain for the given instrument key.

        Parses the strike and option type (CE/PE) from ``instrument_key`` via
        regex first. Real Upstox keys are numeric-only (e.g. ``NSE_FO|63930``)
        and never match the regex (BUG-009/BUG-012) — those fall back to a
        BOD instrument-master lookup for ``strike_price``/``instrument_type``,
        mirroring ``CSPNiftyV1._find_put_leg`` / ``IronCondorV1._find_leg``.

        Args:
            market: Current option chain.
            instrument_key: Position's Upstox instrument key.

        Returns:
            Matching OptionLeg, or None when unavailable.
        """
        m = _STRIKE_RE.search(instrument_key)
        if not m:
            return self._find_leg_via_bod(market, instrument_key)

        try:
            strike = Decimal(m.group(1))
        except InvalidOperation:
            log.warning(
                "ic_nifty_v2.strike_parse_failed",
                instrument_key=instrument_key,
            )
            return None

        option_type = m.group(2).upper()
        strike_data = market.strikes.get(strike)
        if strike_data is None:
            return None

        return strike_data.ce if option_type == "CE" else strike_data.pe

    def _find_leg_via_bod(self, market: OptionChain, instrument_key: str) -> OptionLeg | None:
        """Resolve a numeric-only instrument key via the offline BOD master.

        Args:
            market: Current option chain.
            instrument_key: Position's Upstox instrument key (numeric form,
                e.g. ``NSE_FO|63930``, no embedded strike/type substring).

        Returns:
            Matching OptionLeg, or None when the key can't be resolved
            (missing from BOD, no strike/type recorded, absent from the
            live chain, or an unexpected ``instrument_type``).
        """
        try:
            lookup = InstrumentLookup.from_file(DEFAULT_BOD_PATH)
            inst = lookup.get_by_key(instrument_key)
            if inst is None or inst.get("strike_price") is None:
                log.warning(
                    "ic_nifty_v2.strike_parse_failed",
                    instrument_key=instrument_key,
                    reason="not_found_in_bod",
                )
                return None

            option_type = inst.get("instrument_type")
            if option_type not in ("CE", "PE"):
                log.warning(
                    "ic_nifty_v2.strike_parse_failed",
                    instrument_key=instrument_key,
                    reason="unexpected_instrument_type",
                    instrument_type=option_type,
                )
                return None

            strike = Decimal(str(inst["strike_price"]))
            strike_data = market.strikes.get(strike)
            if strike_data is None:
                return None

            leg = strike_data.ce if option_type == "CE" else strike_data.pe
            if leg is not None:
                log.debug(
                    "ic_nifty_v2.leg_resolved_via_bod",
                    instrument_key=instrument_key,
                    strike=str(strike),
                    option_type=option_type,
                )
            return leg
        except Exception as exc:  # Intentional: fail-safe BOD lookup
            log.warning(
                "ic_nifty_v2.strike_parse_failed",
                instrument_key=instrument_key,
                reason="bod_lookup_failed",
                error=str(exc),
            )
            return None

    def _compute_combined_pnl(
        self,
        market: OptionChain,
        ic_positions: list[PaperPosition],
    ) -> tuple[Decimal | None, Decimal]:
        """Compute the combined current mark and entry credit for the IC.

        Returns (None, entry_credit) when any leg's chain data is missing.

        Args:
            market: Current option chain snapshot.
            ic_positions: All IC positions for this strategy.

        Returns:
            Tuple of (combined_mark or None, entry_credit).
        """
        entry_credit = Decimal("0")
        combined_mark = Decimal("0")
        mark_available = True

        for pos in ic_positions:
            opt_leg = self._find_leg(market, pos.instrument_key)

            if pos.leg_role in _SHORT_ROLES:
                entry_credit += pos.avg_sell_price
                if opt_leg is not None:
                    combined_mark += opt_leg.ltp
                else:
                    mark_available = False
            elif pos.leg_role in _LONG_ROLES:
                entry_credit -= pos.avg_cost
                if opt_leg is not None:
                    combined_mark -= opt_leg.ltp
                else:
                    mark_available = False

            if opt_leg is None:
                # 2026-07-20: mirrors the ic_nifty_v1.py fix — a leg not found
                # in `market` used to flip mark_available=False with zero
                # logging, silently suppressing profit-target/loss-stop/
                # profit-lock signals. See DECISIONS.md 2026-07-20.
                log.warning(
                    "ic_nifty_v2.mark_unavailable",
                    strategy=self.strategy_name,
                    leg_role=pos.leg_role,
                    instrument_key=pos.instrument_key,
                    market_expiry=str(market.expiry),
                )

        return (combined_mark if mark_available else None, entry_credit)

    def _parse_expiry(self, instrument_key: str) -> date | None:
        """Extract the option expiry date from an instrument key.

        Parses via regex first (``NSE_FO|NIFTY<DDMonYYYY>...`` trading-symbol
        form). Real Upstox keys are numeric-only (e.g. ``NSE_FO|63930``) and
        never match — BUG-018 (2026-07-23): this silently made
        check_signals's expiry lookup return None on every real leg, every
        tick, since the strategy's first entry (2026-07-03), because there
        was no fallback — check_signals hit `if expiry is None: return []`
        before ever reaching DTE/profit-target/profit-lock evaluation.
        Identical root cause to BUG-009 (paper_ic_snapshot.py) and BUG-012's
        ``_find_leg``/``_position_strike`` (this file). Fixed the same way:
        numeric keys fall back to a BOD instrument-master reverse lookup.
        See docs/bugs/bugs.md BUG-018.

        Args:
            instrument_key: Upstox instrument key for the option leg.

        Returns:
            Parsed expiry date, or None if the key can't be resolved.
        """
        m = _EXPIRY_RE.search(instrument_key)
        if m:
            try:
                return datetime.strptime(m.group(1).upper(), "%d%b%Y").date()
            except ValueError:
                return None

        try:
            lookup = InstrumentLookup.from_file(DEFAULT_BOD_PATH)
            inst = lookup.get_by_key(instrument_key)
            if inst is None:
                log.warning(
                    "ic_nifty_v2.expiry_parse_failed",
                    instrument_key=instrument_key,
                    reason="not_found_in_bod",
                )
                return None
            expiry_str = _parse_expiry_epoch(inst.get("expiry"))
            if expiry_str is None:
                log.warning(
                    "ic_nifty_v2.expiry_parse_failed",
                    instrument_key=instrument_key,
                    reason="no_expiry_field",
                )
                return None
            return date.fromisoformat(expiry_str)
        except (ValueError, OSError) as exc:
            log.warning(
                "ic_nifty_v2.expiry_parse_failed",
                instrument_key=instrument_key,
                reason="exception",
                error=str(exc),
            )
            return None

    def _log_counterfactual_exit(
        self,
        event: SignalEvent,
        market: OptionChain,
        ic_positions: list[PaperPosition],
    ) -> None:
        """Create a counterfactual exit event in the DB for ACTION signals."""
        if self._store is None:
            return

        try:
            import json

            from src.paper.models import ExitSignal

            expiry = next((self._parse_expiry(p.instrument_key) for p in ic_positions), None)
            dte = (expiry - market_today()).days if expiry is not None else None
            combined_mark, _ = self._compute_combined_pnl(market, ic_positions)

            def _get_delta(role: str) -> str | None:
                pos = _position_for_role(ic_positions, role)
                if pos is None:
                    return None
                leg = self._find_leg(market, pos.instrument_key)
                if leg is None or leg.delta is None:
                    return None
                return str(leg.delta)

            def _get_spread_pct(short_role: str, long_role: str) -> str | None:
                short_pos = _position_for_role(ic_positions, short_role)
                long_pos = _position_for_role(ic_positions, long_role)
                if not short_pos or not long_pos:
                    return None
                short_leg = self._find_leg(market, short_pos.instrument_key)
                long_leg = self._find_leg(market, long_pos.instrument_key)
                if not short_leg or not long_leg or short_leg.ltp is None or long_leg.ltp is None:
                    return None
                mark = short_leg.ltp - long_leg.ltp
                credit = short_pos.avg_sell_price - long_pos.avg_cost
                if credit <= Decimal("0"):
                    return None
                pct = mark / credit
                return str(pct.quantize(Decimal("0.01")))

            blob = {
                "exit_dte": dte,
                "mark_at_exit": str(combined_mark) if combined_mark is not None else None,
                "short_put_delta": _get_delta("short_put"),
                "short_call_delta": _get_delta("short_call"),
                "spread_pct_put": _get_spread_pct("short_put", "long_put_hedge"),
                "spread_pct_call": _get_spread_pct("short_call", "long_call_hedge"),
            }

            try:
                exit_signal = ExitSignal(event.event_type)
            except ValueError:
                exit_signal = ExitSignal.NONE

            sev = "WARNING" if event.severity == "WARN" else event.severity

            self._store.create_exit_event(
                strategy_name=self.strategy_name,
                leg_name="ALL",
                trade_id="0",
                event_time=datetime.now(timezone.utc),
                detected_by="INTRADAY",
                exit_signal=exit_signal,
                severity=sev,  # type: ignore[arg-type]
                entry_price=Decimal("0"),
                counterfactual_dte_marks=json.dumps(blob),
                notes=event.description,
            )
        except Exception:  # Intentional: do not crash tick loop if counterfactual log fails
            log.warning(
                "ic_nifty_v2.counterfactual_log_failed",
                strategy=self.strategy_name,
                exc_info=True,
            )

    def _compute_ivr_str(self) -> str:
        """Load VIX Parquet series and compute IVR; returns formatted string.

        Returns:
            ``"IVR: 0.42"`` on success, ``"IVR: unavailable"`` on any data gap.
        """
        from pathlib import Path

        from src.backtest.ivr import compute_ivr
        from src.backtest.vix_ingest import fetch_vix_latest, load_vix_series

        vix_dir = Path("data/historical/ohlc/india_vix")
        ivr_str = "unavailable"
        if vix_dir.exists():
            try:
                vix_series = load_vix_series(vix_dir)
                vix_today = fetch_vix_latest()
                if vix_today is not None:
                    ivr = compute_ivr(vix_today, vix_series)
                    ivr_str = f"{ivr:.2f}" if ivr is not None else "unavailable"
            except Exception:
                # Intentional: VIX data unavailability is non-fatal for entry context.
                # IVR is logged as "unavailable" and entry proceeds without it.
                pass
        return f"IVR: {ivr_str}"

    def _load_vix_ivr(self) -> tuple[Decimal | None, Decimal | None]:
        """Load current VIX and IVR from Parquet store. Returns (None, None) on failure.

        Non-fatal: any IO or parsing error returns (None, None) so the profit-lock
        engine falls back to its IV-guard bypass path (formula with K ≥ 15 pts).

        Returns:
            Tuple of (vix as Decimal, ivr as Decimal); either may be None.
        """
        from pathlib import Path

        from src.backtest.ivr import compute_ivr
        from src.backtest.vix_ingest import fetch_vix_latest, load_vix_series

        vix_dir = Path("data/historical/ohlc/india_vix")
        if not vix_dir.exists():
            return None, None
        try:
            vix_series = load_vix_series(vix_dir)
            vix_today = fetch_vix_latest()
            if vix_today is None:
                return None, None
            vix_decimal = Decimal(str(vix_today))
            ivr_raw = compute_ivr(vix_today, vix_series)
            ivr_decimal = Decimal(str(ivr_raw)) if ivr_raw is not None else None
            return vix_decimal, ivr_decimal
        except Exception:
            return None, None

    async def _send_profit_lock_notification(self, meta: dict) -> None:
        """Send post-execution Zone 2 profit-lock Telegram notification. Non-fatal.

        Fires via TelegramGateway.send_notification() (not send_approval_request —
        this is a confirmation, not an approval gate).

        Args:
            meta: ApprovedAction.metadata dict from the PROFIT_LOCK_ZONE2 payload.
        """
        if self._notifier is None:
            return
        text = self._build_profit_lock_notification_text(meta)
        try:
            await self._notifier.send_notification(text)
        except Exception as exc:
            log.error("ic_nifty_v2.send_notification_failed", error=str(exc))

    def _build_profit_lock_notification_text(self, meta: dict) -> str:
        """Format the Zone 2 profit-lock Telegram confirmation message.

        Args:
            meta: ApprovedAction.metadata dict containing new wing strikes, widths,
                net debit, guaranteed floor fraction, and DTE.

        Returns:
            HTML-formatted Telegram message string.
        """
        captured_pct = float(Decimal(meta.get("captured_fraction", "0"))) * 100
        net_debit = meta.get("net_debit_pts", "?")
        floor_fraction_raw = meta.get("guaranteed_floor_fraction", "0")
        try:
            floor_pct = float(Decimal(str(floor_fraction_raw))) * 100
        except Exception:
            floor_pct = 0.0
        new_put_strike = meta.get("new_put_wing_strike", "?")
        new_call_strike = meta.get("new_call_wing_strike", "?")
        new_put_w = meta.get("new_put_width_pts", "?")
        new_call_w = meta.get("new_call_width_pts", "?")
        dte = meta.get("dte", "?")
        return (
            f"🔒 <b>IC V2 Profit-Lock Executed — Zone 2</b>\n"
            f"Strategy: {self.strategy_name}\n"
            f"Captured: {captured_pct:.1f}% of entry credit\n"
            f"Action: Long wings rolled inward\n"
            f"  PUT:  → {new_put_strike}PE (width {new_put_w} pts)\n"
            f"  CALL: → {new_call_strike}CE (width {new_call_w} pts)\n"
            f"Net debit: {net_debit} pts\n"
            f"Floor locked: ≥{floor_pct:.0f}% guaranteed\n"
            f"DTE: {dte}"
        )

    # ── Private helpers (V2-specific) ─────────────────────────────────────────

    def _get_short_delta(self, market: OptionChain, pos: PaperPosition | None) -> Decimal | None:
        """Look up the live delta of a short position from the chain.

        PE deltas are negative by convention; we return the raw signed value.
        Returns None when the position is missing, not in the chain, or delta
        is not available in the snapshot.

        Args:
            market: Current option chain snapshot.
            pos: Paper position to look up (short_put or short_call).

        Returns:
            Signed delta (Decimal) or None.
        """
        if pos is None:
            return None
        leg = self._find_leg(market, pos.instrument_key)
        if leg is None:
            return None
        return leg.delta  # None when Greeks unavailable

    def _position_strike(self, pos: PaperPosition | None) -> Decimal | None:
        """Extract strike price from the instrument key of a position.

        Falls back to a BOD instrument-master lookup for numeric-only keys
        (e.g. ``NSE_FO|63930``) that don't match ``_STRIKE_RE`` — same
        BUG-012 fallback as ``_find_leg``/``_find_leg_via_bod``. Without
        this, Zone 2 profit-lock (which calls this for both short strikes)
        silently no-ops on every real Upstox key.

        Args:
            pos: Paper position.

        Returns:
            Strike as Decimal, or None if key cannot be parsed or resolved.
        """
        if pos is None:
            return None
        m = _STRIKE_RE.search(pos.instrument_key)
        if m:
            try:
                return Decimal(m.group(1))
            except InvalidOperation:
                return None

        try:
            lookup = InstrumentLookup.from_file(DEFAULT_BOD_PATH)
            inst = lookup.get_by_key(pos.instrument_key)
            if inst is None or inst.get("strike_price") is None:
                return None
            return Decimal(str(inst["strike_price"]))
        except Exception:  # Intentional: fail-safe BOD lookup
            return None

    def _long_wing_strike(self, positions: list[PaperPosition], side: str) -> Decimal | None:
        """Return the strike of the existing long wing for the given side.

        Args:
            positions: Current IC paper positions.
            side: "put" or "call".

        Returns:
            Strike as Decimal, or None if position not found.
        """
        role = f"long_{side}_hedge"
        pos = next((p for p in positions if p.leg_role == role), None)
        return self._position_strike(pos)

    def _leg_strike_from_update(self, update: PositionUpdate, which: str, side: str) -> str:
        """Extract strike string from a roll PositionUpdate for logging.

        Args:
            update: The 4-leg PositionUpdate returned by _execute_partial_roll.
            which: "new_short" or "new_long" — which of the two new legs to inspect.
            side: "put" or "call".

        Returns:
            Strike string, or "?" if extraction fails.
        """
        action = "SELL" if which == "new_short" else "BUY"
        option_type = "PE" if side == "put" else "CE"
        for leg in update.legs:
            if leg.action == action and "open" in leg.notes:
                m = _STRIKE_RE.search(leg.instrument_key)
                if m and leg.instrument_key.endswith(option_type):
                    return m.group(1)
        return "?"

    def _compute_roll_debit(
        self,
        positions: list[PaperPosition],
        roll_update: PositionUpdate,
        market: OptionChain,
    ) -> str:
        """Return string representation of roll net debit for logging.

        Approximated from the roll_update's total_credit_pts (negative = debit).

        Args:
            positions: Current IC paper positions.
            roll_update: The 4-leg PositionUpdate.
            market: Live chain (unused here; kept for future mark-to-market).

        Returns:
            String of net debit points.
        """
        return str(abs(roll_update.total_credit_pts))

    def _mid_price(self, leg: OptionLeg) -> Decimal:
        """Compute mid price from bid/ask; fall back to ltp when spread missing.

        Args:
            leg: Option leg with price data.

        Returns:
            Mid price as Decimal.
        """
        if leg.bid > Decimal("0") and leg.ask > Decimal("0"):
            return (leg.bid + leg.ask) / Decimal("2")
        return leg.ltp

    def _spread_pct(self, leg: OptionLeg) -> Decimal:
        """Return bid/ask spread as a fraction of mid price.

        Returns Decimal('1') (100%) when bid/ask/mid are unavailable,
        which fails the liquidity gate.

        Args:
            leg: Option leg with price data.

        Returns:
            Spread fraction in [0, 1] range.
        """
        if leg.bid <= Decimal("0") or leg.ask <= Decimal("0"):
            return Decimal("1")
        mid = (leg.bid + leg.ask) / Decimal("2")
        if mid <= Decimal("0"):
            return Decimal("1")
        return (leg.ask - leg.bid) / mid

    def _passes_liquidity_gate(self, leg: OptionLeg) -> bool:
        """Return True when bid/ask spread ≤ 5% of mid price.

        Mirrors _apply_liquidity_gate from src/instruments/strike_selector.py
        but operates directly on OptionLeg rather than list[dict].

        Args:
            leg: Option leg to check.

        Returns:
            True if liquidity gate passes, False otherwise.
        """
        return self._spread_pct(leg) <= _LIQUIDITY_GATE_PCT

    def _atm_iv(self, market: OptionChain) -> Decimal | None:
        """Return IV of the chain strike closest to spot (ATM IV proxy).

        Prefers CE IV; falls back to PE IV. Returns None when no IV data
        available on the ATM strike.

        Args:
            market: Current option chain snapshot.

        Returns:
            ATM IV in percentage terms (e.g. 15.0 for 15%), or None.
        """
        if not market.strikes:
            return None
        closest = min(
            market.strikes.keys(),
            key=lambda s: abs(s - market.underlying_spot),
        )
        strike_data = market.strikes[closest]
        if strike_data.ce is not None and strike_data.ce.iv is not None:
            return strike_data.ce.iv
        if strike_data.pe is not None and strike_data.pe.iv is not None:
            return strike_data.pe.iv
        return None

    def _best_available_delta(
        self,
        chain: OptionChain,
        option_type: Literal["CE", "PE"],
        target: Decimal,
    ) -> str:
        """Return the delta string of the chain leg with abs(delta) closest to target.

        Used only on the "skip" path for structured logging. Scans the full
        chain regardless of any delta band.

        Args:
            chain: Current option chain snapshot.
            option_type: "CE" or "PE".
            target: Target absolute delta to compare against.

        Returns:
            String representation of closest delta found, or "none".
        """
        best_delta: Decimal | None = None
        best_dist = Decimal("999")
        for strike_data in chain.strikes.values():
            leg: OptionLeg | None = strike_data.ce if option_type == "CE" else strike_data.pe
            if leg is None or leg.delta is None or leg.ltp <= Decimal("0"):
                continue
            dist = abs(abs(leg.delta) - target)
            if dist < best_dist:
                best_dist = dist
                best_delta = leg.delta
        return str(best_delta) if best_delta is not None else "none"
