import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from src.backtest.ivr import compute_ivr
from src.backtest.vix_ingest import load_vix_series
from src.paper.models import ExitSignal, PaperPosition
from src.paper.store import PaperStore

log = structlog.get_logger(__name__)


class ReEntryMixin:
    """Mixin providing R5 re-entry check logic for paper trading strategies.

    Expects the following class-level or instance-level attributes to be set:
        strategy_name: str
        reentry_leg_role: str
        reentry_script_hint: str

        _store: PaperStore | None
        _notifier: Any | None
        _vix_data_dir: Path
    """

    strategy_name: str
    reentry_leg_role: str
    reentry_script_hint: str
    reentry_ivr_threshold: float = 0.25

    _store: PaperStore | None
    _notifier: Any | None
    _vix_data_dir: Path

    def _ivr_passes(self, ivr: float) -> tuple[bool, str]:
        """Verify if the IVR passes the strategy criteria.

        Subclasses can override this method to change comparison logic.

        Default (short premium, e.g. CSP/CC): blocks when IVR is too low (below threshold).
        PP (long premium): blocks when IVR is too high (above threshold) to avoid buying
        protection when volatility is already elevated.
        """
        if ivr < self.reentry_ivr_threshold:
            return False, f"IVR={ivr:.2f} < {self.reentry_ivr_threshold:.2f} — low vol, skip cycle"
        return True, ""

    def _reentry_position_active(self, p: PaperPosition) -> bool:
        """Determine if a position leg is active for the strategy.

        Subclasses can override this method to customize leg role/direction matching.
        """
        return p.leg_role == self.reentry_leg_role and p.net_qty < 0

    async def _check_reentry(
        self,
        expiry: date | None,
        today: date,
        instrument_key: str,
        trade_id: int,
    ) -> None:
        """Evaluate re-entry eligibility and write a paper_exit_events row.

        Three gates — all must pass for ELIGIBLE:
        1. (expiry - today).days >= 14 calendar days to expiry.
        2. Trailing 252-day IVR >= 0.25 (None/insufficient history -> blocked conservatively).
        3. No open position with leg_role == self.reentry_leg_role in store for this strategy.

        Always writes to ``paper_exit_events`` (ELIGIBLE or BLOCKED) and sends
        a Telegram notification. Notifier failure is non-fatal — the event is
        written regardless.
        """
        if self._store is None:
            log.warning(
                "reentry.check_skipped",
                strategy=self.strategy_name,
                reason="no store configured",
            )
            return

        # ── Dedup: skip if already evaluated today for this leg ───────────────
        _reentry_signals = {
            ExitSignal.R5_REENTRY_ELIGIBLE.value,
            ExitSignal.R5_REENTRY_BLOCKED.value,
        }
        try:
            existing_events = self._store.get_open_exit_events(self.strategy_name)
            today_str = today.isoformat()
            for ev in existing_events:
                ev_date = str(ev.get("event_time", ""))[:10]
                if (
                    ev.get("leg_name") == self.reentry_leg_role
                    and ev.get("exit_signal") in _reentry_signals
                    and ev_date == today_str
                ):
                    log.info(
                        "reentry_check_skipped",
                        reason="already evaluated today",
                        strategy=self.strategy_name,
                        leg=self.reentry_leg_role,
                        existing_signal=ev.get("exit_signal"),
                    )
                    return
        except Exception as exc:
            log.warning(
                "reentry_dedup_check_failed",
                strategy=self.strategy_name,
                error=str(exc),
            )

        blocked_reason: str | None = None

        # ── Gate 1: DTE ≥ 14 ─────────────────────────────────────────────────
        dte = (expiry - today).days if expiry is not None else 0
        if expiry is None or dte < 14:
            blocked_reason = f"DTE={dte} < 14 — too close to expiry for re-entry"

        # ── Gate 2: IVR passes ───────────────────────────────────────────────
        if blocked_reason is None:
            try:
                vix_series: pd.Series = await asyncio.to_thread(load_vix_series, self._vix_data_dir)
                if vix_series.empty or len(vix_series) < 252:
                    blocked_reason = "IVR history insufficient — cannot verify R3"
                else:
                    vix_today = float(vix_series.iloc[-1])
                    ivr = compute_ivr(vix_today, vix_series)
                    if ivr is None:
                        blocked_reason = "IVR history insufficient — cannot verify R3"
                    else:
                        passed, reason = self._ivr_passes(ivr)
                        if not passed:
                            blocked_reason = reason
            except Exception as exc:
                log.warning(
                    "reentry.ivr_load_failed",
                    strategy=self.strategy_name,
                    error=str(exc),
                )
                blocked_reason = "IVR history insufficient — cannot verify R3"

        # ── Gate 3: No open active position ──────────────────────────────────
        if blocked_reason is None:
            try:
                existing = self._store.get_positions(self.strategy_name)
                if any(self._reentry_position_active(p) for p in existing):
                    blocked_reason = (
                        f"open position: {self.reentry_leg_role} already active "
                        f"for {self.strategy_name}"
                    )
            except Exception as exc:
                log.warning(
                    "reentry.positions_check_failed",
                    strategy=self.strategy_name,
                    error=str(exc),
                )
                blocked_reason = "open position check failed — cannot verify gate 3"

        signal = (
            ExitSignal.R5_REENTRY_ELIGIBLE
            if blocked_reason is None
            else ExitSignal.R5_REENTRY_BLOCKED
        )
        notes = blocked_reason or f"All {self.reentry_leg_role} re-entry gates passed"

        # ── Write exit event ──────────────────────────────────────────────────
        try:
            self._store.create_exit_event(
                strategy_name=self.strategy_name,
                leg_name=self.reentry_leg_role,
                trade_id=str(trade_id),
                event_time=datetime.now(timezone.utc),
                detected_by="MANUAL",
                exit_signal=signal,
                severity="INFO",
                entry_price=Decimal("0"),
                dte=dte,
                notes=notes,
            )
            log.info(
                "reentry.event_written",
                strategy=self.strategy_name,
                signal=signal.value,
                notes=notes,
            )
        except Exception as exc:
            log.error(
                "reentry.event_write_failed",
                strategy=self.strategy_name,
                error=str(exc),
            )

        # ── Notify ────────────────────────────────────────────────────────────
        if self._notifier is not None:
            status_line = (
                f"✅ {self.strategy_name} {self.reentry_leg_role} Re-entry ELIGIBLE — run {self.reentry_script_hint}"
                if signal == ExitSignal.R5_REENTRY_ELIGIBLE
                else f"⛔ {self.strategy_name} {self.reentry_leg_role} Re-entry BLOCKED"
            )
            msg = f"{status_line}\n{notes}"
            try:
                await self._notifier.send_plain_message(msg)
            except Exception as exc:
                log.warning(
                    "reentry.notify_failed",
                    strategy=self.strategy_name,
                    error=str(exc),
                )
