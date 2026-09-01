from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import structlog

from src.backtest.ivr import compute_ivr
from src.backtest.vix_ingest import load_vix_series
from src.notifications.formatting import STRATEGY_LABELS, leg_role_label, strategy_label
from src.notifications.markdown import escape_markdown, mdcode
from src.paper.constants import STRATEGY_OVERLAY
from src.paper.models import ExitSignal, PaperPosition

if TYPE_CHECKING:
    from src.paper.store import PaperStore

log = structlog.get_logger(__name__)


def _block_notes(block: tuple[str, str | None]) -> str:
    """Flatten a (short_reason, detail) gate-block pair to one plain-text line.

    Used for the ``paper_exit_events.notes`` column and structured logs — plain,
    unescaped. The Telegram notice formats the same pair separately with
    MarkdownV2 escaping.
    """
    short_reason, detail = block
    return f"{short_reason} ({detail})" if detail else short_reason


# CC / Collar / PP re-entry all run under the shared ``STRATEGY_OVERLAY`` umbrella
# id, so ``strategy_name`` alone can't name them for the notice headline — the
# re-entry ``leg_role`` does. Label text is sourced from ``STRATEGY_LABELS`` so
# there is one copy of each string.
_OVERLAY_HEADLINE_BY_LEG: dict[str, str] = {
    "covered_call": STRATEGY_LABELS["paper_covered_call_v1"],
    "protective_put": STRATEGY_LABELS["paper_protective_put_v1"],
    "overlay_collar_call": STRATEGY_LABELS["paper_collar_v1"],
}


def _reentry_headline_label(strategy_name: str, leg_role: str) -> str:
    """Human strategy label for the re-entry notice headline.

    Resolves the ``STRATEGY_OVERLAY`` umbrella id (shared by CC/Collar/PP) via
    ``leg_role``; every other id goes straight through ``strategy_label()``.
    An unmapped id or overlay leg_role raises ``ValueError`` either way.
    """
    if strategy_name == STRATEGY_OVERLAY:
        try:
            return _OVERLAY_HEADLINE_BY_LEG[leg_role]
        except KeyError:
            raise ValueError(
                f"no re-entry headline label for overlay leg_role={leg_role!r}"
            ) from None
    return strategy_label(strategy_name)


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

    def _ivr_passes(self, ivr: float) -> tuple[bool, str, str | None]:
        """Verify if the IVR passes the strategy criteria.

        Subclasses can override this method to change comparison logic.

        Default (short premium, e.g. CSP/CC): blocks when IVR is too low (below threshold).
        PP (long premium): blocks when IVR is too high (above threshold) to avoid buying
        protection when volatility is already elevated.

        Returns:
            ``(passed, short_reason, detail)`` — a structured block pair, not one
            prose string. ``short_reason`` is the bare comparison ("IVR=0.19 < 0.25"),
            ``detail`` the human context ("Low vol, skip cycle"). On a pass,
            ``("", None)`` (both ignored by the caller). ROLL-7 refactor — the
            re-entry notice formats the pair, it does not string-split prose.
        """
        if ivr < self.reentry_ivr_threshold:
            return (
                False,
                f"IVR={ivr:.2f} < {self.reentry_ivr_threshold:.2f}",
                "Low vol, skip cycle",
            )
        return True, "", None

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

        # Each gate that blocks re-entry records a structured (short_reason, detail)
        # pair — NOT one prose string to be split apart at render time (ROLL-7).
        # `detail` is None when the short reason stands alone.
        block: tuple[str, str | None] | None = None
        _ivr_insufficient = ("IVR history insufficient", "Cannot verify R3")

        # ── Gate 1: DTE ≥ 14 ─────────────────────────────────────────────────
        dte = (expiry - today).days if expiry is not None else 0
        if expiry is None or dte < 14:
            block = (f"DTE={dte} < 14", "Too close to expiry")

        # ── Gate 2: IVR passes ───────────────────────────────────────────────
        if block is None:
            try:
                vix_series: pd.Series = await asyncio.to_thread(load_vix_series, self._vix_data_dir)
                if vix_series.empty or len(vix_series) < 252:
                    block = _ivr_insufficient
                else:
                    vix_today = float(vix_series.iloc[-1])
                    ivr = compute_ivr(vix_today, vix_series)
                    if ivr is None:
                        block = _ivr_insufficient
                    else:
                        passed, short_reason, detail = self._ivr_passes(ivr)
                        if not passed:
                            block = (short_reason, detail)
            except Exception as exc:
                log.warning(
                    "reentry.ivr_load_failed",
                    strategy=self.strategy_name,
                    error=str(exc),
                )
                block = _ivr_insufficient

        # ── Gate 3: No open active position ──────────────────────────────────
        if block is None:
            try:
                existing = self._store.get_positions(self.strategy_name)
                if any(self._reentry_position_active(p) for p in existing):
                    block = ("Position already active", None)
            except Exception as exc:
                log.warning(
                    "reentry.positions_check_failed",
                    strategy=self.strategy_name,
                    error=str(exc),
                )
                block = ("Open position check failed", "Cannot verify gate 3")

        signal = ExitSignal.R5_REENTRY_ELIGIBLE if block is None else ExitSignal.R5_REENTRY_BLOCKED
        notes = (
            f"All {self.reentry_leg_role} re-entry gates passed"
            if block is None
            else _block_notes(block)
        )

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
            # Label lookups raise ValueError on an unmapped strategy_id / leg_role
            # — a loud config bug, not a swallowed send failure (the non-fatal
            # contract covers transport errors, not a missing display label).
            # ROLL-7 spec mandates the hard raise ("not silently falls back to
            # the raw id"). Blast radius: in the overlay callers this runs before
            # _record_close_trade in apply_action, so an unmapped NEW subclass
            # would skip that close-trade write for the cycle. All four current
            # subclasses are mapped — add any new one to STRATEGY_LABELS /
            # LEG_ROLE_LABELS / _OVERLAY_HEADLINE_BY_LEG before shipping it.
            strategy_lbl = escape_markdown(
                _reentry_headline_label(self.strategy_name, self.reentry_leg_role)
            )
            leg_lbl = escape_markdown(leg_role_label(self.reentry_leg_role))
            if block is None:
                lines = [
                    f"✅ RE\\-ENTRY ELIGIBLE: {strategy_lbl}",
                    f"Leg: {leg_lbl}",
                    "Status: All Gates Passed",
                    "Execute:",
                    mdcode(self.reentry_script_hint),
                ]
            else:
                short_reason, detail = block
                reason_line = (
                    f"Reason: {escape_markdown(short_reason)} \\({escape_markdown(detail)}\\)"
                    if detail
                    else f"Reason: {escape_markdown(short_reason)}"
                )
                lines = [
                    f"⛔ RE\\-ENTRY BLOCKED: {strategy_lbl}",
                    f"Leg: {leg_lbl}",
                    reason_line,
                ]
            msg = "\n".join(lines)
            try:
                await self._notifier.send_plain_message(msg)
            except Exception as exc:
                log.warning(
                    "reentry.notify_failed",
                    strategy=self.strategy_name,
                    error=str(exc),
                )
