"""IronCondorV2 — high-delta IC with 10Δ wings and partial-roll adjustments.

Phase 1 (this file: IC-V2-1): entry logic only.
  - _select_short_put / _select_short_call: 25Δ/22Δ via find_strike_by_delta
  - _select_long_wing: 10Δ with delta/premium/liquidity floors
  - _sd_sanity_check: warn-only SD guard (never blocks entry)
  - enter(): assemble 4-leg IC; returns PositionUpdate or None

Phase 2 (IC-V2-2): _evaluate_adjustment, _execute_partial_roll, roll guards.
Phase 3 (IC-V2-3): _evaluate_dte_action, _roll_allowed_by_dte.
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
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Literal

import structlog

from src.market_calendar.holidays import market_today
from src.models.options import OptionChain, OptionLeg
from src.paper.models import PaperPosition
from src.strategy import roll_utils
from src.strategy.protocol import ApprovedAction, LegSpec, SignalEvent

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
                instrument_key=f"NSE_FO|NIFTY{int(short_put.strike)}PE",
                action="SELL",
                quantity=1,
                leg_role="short_put",
                notes=f"delta={short_put.delta}",
            ),
            LegSpec(
                instrument_key=f"NSE_FO|NIFTY{int(short_call.strike)}CE",
                action="SELL",
                quantity=1,
                leg_role="short_call",
                notes=f"delta={short_call.delta}",
            ),
            LegSpec(
                instrument_key=f"NSE_FO|NIFTY{int(long_put.strike)}PE",
                action="BUY",
                quantity=1,
                leg_role="long_put_hedge",
                notes=f"delta={long_put.delta}",
            ),
            LegSpec(
                instrument_key=f"NSE_FO|NIFTY{int(long_call.strike)}CE",
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

    # ── Protocol stubs (implemented in IC-V2-4) ──────────────────────────────

    async def check_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """Not yet implemented — wired in IC-V2-4."""
        raise NotImplementedError("IronCondorV2.check_signals implemented in IC-V2-4")

    async def apply_action(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> list[PaperPosition]:
        """Not yet implemented — wired in IC-V2-4."""
        raise NotImplementedError("IronCondorV2.apply_action implemented in IC-V2-4")

    # ── Private helpers (copied verbatim from ic_nifty_v1) ───────────────────

    def _is_auto_execute(self, action: ApprovedAction) -> bool:
        """Determine if an action was initiated automatically or manually."""
        if action.metadata and action.metadata.get("auto_selected"):
            return True
        return action.rationale == "auto-execute"

    def _find_leg(self, market: OptionChain, instrument_key: str) -> OptionLeg | None:
        """Locate a CE or PE leg in the chain for the given instrument key.

        Args:
            market: Current option chain.
            instrument_key: Position's Upstox instrument key.

        Returns:
            Matching OptionLeg, or None when unavailable.
        """
        m = _STRIKE_RE.search(instrument_key)
        if not m:
            log.warning(
                "ic_nifty_v2.strike_parse_failed",
                instrument_key=instrument_key,
            )
            return None

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

        return (combined_mark if mark_available else None, entry_credit)

    def _parse_expiry(self, instrument_key: str) -> date | None:
        """Extract the option expiry date from an instrument key.

        Args:
            instrument_key: Upstox instrument key for the option leg.

        Returns:
            Parsed expiry date, or None if key carries no date.
        """
        m = _EXPIRY_RE.search(instrument_key)
        if not m:
            return None
        try:
            return datetime.strptime(m.group(1).upper(), "%d%b%Y").date()
        except ValueError:
            return None

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

    # ── Private helpers (V2-specific) ─────────────────────────────────────────

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
