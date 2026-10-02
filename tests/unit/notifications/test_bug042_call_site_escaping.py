"""BUG-042 B042.5: every formerly unescaped Telegram caller now sends MarkdownV2-safe text.

One regression test per fixed call site (paper_3track_snapshot.py x5,
paper_3track_overlay_entry.py bootstrap alert) plus the mvp_watch.py sends the
audit found already escaped in their callees. "Safe" = no bare reserved
character outside a fence / code span (tests/helpers/mdv2.py), i.e. Telegram
would not reject it with a 400 "can't parse entities". No network.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import scripts.strategies.three_track.paper_3track_snapshot as snap_mod
from scripts.mvp_watch import _format_alert_message
from scripts.strategies.three_track import paper_3track_overlay_entry as ov_entry
from src.models.options import OptionChain, OptionChainStrike
from src.models.portfolio import TradeAction
from src.mvp.tracker import ProviderRollup, format_eod_summary, format_hourly_summary
from src.paper.constants import STRATEGY_OVERLAY
from src.paper.models import PaperLegSnapshot
from src.strategy.exit_signals import ExitSignalEngine, ExitSignalResult
from tests.helpers.mdv2 import unescaped_reserved
from tests.unit.mvp.test_mvp_tracker import _make_pick as _make_mvp_pick
from tests.unit.mvp.test_mvp_tracker import _make_rollup
from tests.unit.paper.test_paper_3track_snapshot import (
    _KEY_A,
    _SNAP,
    _fake_broker,
    _FakeNotifier,
    _overlay_store,
    _overlay_trade,
    _seed_two_open_instruments,
)
from tests.unit.scripts.test_mvp_watch import _make_close, _make_event, _make_pick, _make_stats
from tests.unit.scripts.test_paper_3track_snapshot_exit import (
    _SPOT,
    _STRIKE,
    _TODAY,
    _make_csp_position,
    _make_leg,
    _make_store,
)

# ── tests/helpers/mdv2.py itself ─────────────────────────────────


def test_unescaped_reserved_accepts_escaped_fenced_and_bold_text() -> None:
    text = "🚨 *ERROR* overlay\\_pp \\(x\\)\n```\nA-B | 1.5\n```\n`NSE_FO|1`"
    assert unescaped_reserved(text) == []


def test_unescaped_reserved_flags_bare_and_unpaired_chars() -> None:
    assert unescaped_reserved("P&L -11.08 (net) *bold") == ["-", ".", "(", ")", "*"]


# ── paper_3track_snapshot.compute_and_record_exit_signals ────────


async def _run_exit_eval(tmp_path: Path, result: ExitSignalResult) -> list[str]:
    pe = _make_leg(ltp=29.0, delta=-0.20)
    chain = OptionChain(
        underlying_spot=_SPOT, expiry=_TODAY, strikes={_STRIKE: OptionChainStrike(ce=None, pe=pe)}
    )
    notifier = MagicMock()
    notifier.send = AsyncMock()
    with patch.object(snap_mod, "_dispatch_evaluate", return_value=[result]):
        await snap_mod.compute_and_record_exit_signals(
            store=_make_store(tmp_path),
            positions=[_make_csp_position(avg_sell_price=100.0)],
            chains={_TODAY: chain},
            snapshot_id=None,
            engine=ExitSignalEngine,
            today=_TODAY,
            notifier=notifier,
            save=True,
        )
    return [c.args[0] for c in notifier.send.call_args_list]


async def test_exit_signal_action_message_is_mdv2_safe(tmp_path: Path) -> None:
    result = ExitSignalResult(
        exit_signal="PROFIT_TARGET", severity="ACTION", notes="LTP 29.0 <= 30% of credit (100.0)"
    )
    sent = await _run_exit_eval(tmp_path, result)
    assert len(sent) == 1
    assert "EXIT SIGNAL \\[ACTION\\]" in sent[0]
    assert unescaped_reserved(sent[0]) == []


async def test_exit_warn_batch_is_mdv2_safe(tmp_path: Path) -> None:
    result = ExitSignalResult(
        exit_signal="DTE_REVIEW", severity="WARN", notes="DTE 5 (<= 7) - review roll"
    )
    sent = await _run_exit_eval(tmp_path, result)
    assert len(sent) == 1
    assert sent[0].startswith("⚠️ EXIT WARN")
    assert "DTE\\_REVIEW" in sent[0]
    assert unescaped_reserved(sent[0]) == []


# ── paper_3track_snapshot BUG-032 multi-instrument alerts ────────


async def test_multi_instrument_warning_alert_is_mdv2_safe(tmp_path: Path) -> None:
    store = _overlay_store(tmp_path)
    _seed_two_open_instruments(store)
    notifier = _FakeNotifier()
    await snap_mod._compute_overlay_leg_totals(
        store, _fake_broker({_KEY_A: "60.00", "NSE_FO|74009": "95.00"}), _SNAP, notifier
    )
    assert len(notifier.messages) == 1
    assert notifier.messages[0].startswith("⚠️ *WARNING* ")
    assert "overlay\\_pp" in notifier.messages[0]
    assert unescaped_reserved(notifier.messages[0]) == []


async def test_multi_instrument_missing_ltp_alert_is_mdv2_safe(tmp_path: Path) -> None:
    store = _overlay_store(tmp_path)
    _seed_two_open_instruments(store)
    notifier = _FakeNotifier()
    await snap_mod._compute_overlay_leg_totals(
        store, _fake_broker({"NSE_FO|74009": "95.00"}), _SNAP, notifier
    )
    missing = [m for m in notifier.messages if "missing LTP" in m]
    assert len(missing) == 1
    assert missing[0].startswith("🚨 *ERROR* ")
    assert "NSE\\_FO\\|61604" in missing[0]
    assert unescaped_reserved(missing[0]) == []


async def test_multi_instrument_recovery_alert_is_mdv2_safe(tmp_path: Path) -> None:
    store = _overlay_store(tmp_path)
    store.record_leg_snapshot(
        PaperLegSnapshot(
            strategy_name=STRATEGY_OVERLAY,
            leg_role="overlay_pp",
            snapshot_date=date(2026, 8, 23),
            unrealized_pnl=Decimal("100"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("100"),
            ltp=None,
        )
    )
    store.record_trade(
        _overlay_trade("overlay_pp", _KEY_A, TradeAction.BUY, 65, "58.85", date(2026, 8, 11))
    )
    notifier = _FakeNotifier()
    await snap_mod._compute_overlay_leg_totals(
        store, _fake_broker({_KEY_A: "60.00"}), date(2026, 8, 24), notifier
    )
    assert len(notifier.messages) == 1
    assert "back to a single open instrument" in notifier.messages[0]
    assert unescaped_reserved(notifier.messages[0]) == []


# ── paper_3track_overlay_entry._alert_bootstrap_failure ──────────


def test_bootstrap_failure_alert_is_mdv2_safe() -> None:
    notifier = MagicMock()
    notifier.send = AsyncMock(return_value=True)
    with patch.object(ov_entry, "build_notifier", return_value=notifier):
        ov_entry._alert_bootstrap_failure("PP", "logs/pp_entry.log")
    msg = notifier.send.await_args.args[0]
    assert "logs/pp\\_entry\\.log" in msg
    assert unescaped_reserved(msg) == []


# ── mvp_watch.py sends (escaped inside callees; audit pins it) ───


def test_mvp_eod_summary_is_mdv2_safe() -> None:
    rollup = _make_rollup(day_chg_pct=Decimal("-1.25"))
    providers = [ProviderRollup(provider_name="DSIJ", short_code="DSIJ", categories=[rollup])]
    msg = format_eod_summary(providers, "2026-09-24", Decimal("-3.5"), Decimal("-0.4"))
    assert msg
    assert unescaped_reserved(msg) == []


def test_mvp_hourly_summary_is_mdv2_safe() -> None:
    pick = _make_mvp_pick(symbol="M&M", instrument_key="NSE_EQ|M&M", avg_cost=Decimal("1200"))
    msg = format_hourly_summary([pick], {"NSE_EQ|M&M": Decimal("1100.5")}, "11:00 AM")
    assert msg
    assert unescaped_reserved(msg) == []


def test_mvp_alert_message_is_mdv2_safe() -> None:
    msg = _format_alert_message(
        _make_event(), _make_pick(), _make_close(), "DSIJ / Value-Picks (v2)", _make_stats()
    )
    assert unescaped_reserved(msg) == []
