"""S5 — automated base-leg roll tests (Futures/DITM).

See docs/plan/3track-consolidation/stories.md S5 for the confirmed decision log
(per-leg DTE thresholds, warn-only liquidity gates, atomic close+open persistence).
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import scripts.strategies.three_track.paper_3track_roll as roll_mod
from src.instruments.lookup import InstrumentLookup
from src.paper.models import PaperPosition
from src.paper.store import PaperStore
from src.strategy.nifty_track_comparison_v1 import NiftyTrackComparisonV1


def _make_store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "test.db")


# ── Trigger threshold tests ─────────────────────────────────────────────────


def test_futures_roll_triggers_at_dte_1() -> None:
    assert roll_mod.should_roll_futures(1) is True
    assert roll_mod.should_roll_futures(0) is True


def test_futures_roll_does_not_trigger_above_dte_1() -> None:
    assert roll_mod.should_roll_futures(2) is False
    assert roll_mod.should_roll_futures(5) is False


def test_ditm_roll_triggers_at_dte_20() -> None:
    # DTE < 20 rolls — 19 is the first triggering value, 20 does not trigger.
    assert roll_mod.should_roll_ditm(19) is True
    assert roll_mod.should_roll_ditm(0) is True


def test_ditm_roll_does_not_trigger_above_dte_20() -> None:
    assert roll_mod.should_roll_ditm(20) is False
    assert roll_mod.should_roll_ditm(25) is False


def test_futures_and_ditm_use_independent_trigger_thresholds() -> None:
    """Regression guard: the two legs' DTE thresholds must never be unified."""
    dte = 5
    assert roll_mod.should_roll_futures(dte) is False
    assert roll_mod.should_roll_ditm(dte) is True
    assert roll_mod.FUTURES_ROLL_DTE != roll_mod.DITM_ROLL_DTE


# ── Liquidity gate tests (warn-only, never blocking) ────────────────────────


def test_futures_relative_oi_gate_warns_not_blocks() -> None:
    # Below 10% of near-month OI -> gate fails (caller still rolls; gate is diagnostic).
    assert roll_mod.check_futures_liquidity_gate(next_oi=500, near_oi=10_000) is False
    # At/above threshold -> gate passes.
    assert roll_mod.check_futures_liquidity_gate(next_oi=1_000, near_oi=10_000) is True
    # Missing data -> treated as a failure, never raises.
    assert roll_mod.check_futures_liquidity_gate(next_oi=None, near_oi=10_000) is False
    assert roll_mod.check_futures_liquidity_gate(next_oi=100, near_oi=0) is False


def test_ditm_liquidity_gate_reuses_existing_constants() -> None:
    from scripts.strategies.three_track.paper_3track_entry import (
        PROXY_OI_MIN,
        PROXY_SPREAD_MAX,
    )

    assert roll_mod.PROXY_OI_MIN == PROXY_OI_MIN
    assert roll_mod.PROXY_SPREAD_MAX == PROXY_SPREAD_MAX

    # Passes: OI at minimum, spread within max.
    assert roll_mod.check_ditm_liquidity_gate(oi=PROXY_OI_MIN, bid=100.0, ask=101.0) is True
    # Fails: OI below minimum.
    assert roll_mod.check_ditm_liquidity_gate(oi=PROXY_OI_MIN - 1, bid=100.0, ask=101.0) is False
    # Fails: spread above max.
    assert (
        roll_mod.check_ditm_liquidity_gate(
            oi=PROXY_OI_MIN, bid=100.0, ask=100.0 + PROXY_SPREAD_MAX + 1
        )
        is False
    )


# ── Atomic persistence tests ─────────────────────────────────────────────────


def _futures_lookup() -> InstrumentLookup:
    return InstrumentLookup(
        [
            {
                "instrument_key": "NSE_FO|NIFTY26JULFUT",
                "underlying_symbol": "NIFTY",
                "instrument_type": "FUT",
                "expiry": "2026-07-30",
                "trading_symbol": "NIFTY JUL FUT",
            },
            {
                "instrument_key": "NSE_FO|NIFTY26AUGFUT",
                "underlying_symbol": "NIFTY",
                "instrument_type": "FUT",
                "expiry": "2026-08-27",
                "trading_symbol": "NIFTY AUG FUT",
            },
        ]
    )


def _seed_entry_trade(store: PaperStore) -> None:
    """Seed the original entry BUY so get_positions() nets correctly after a roll.

    Mirrors production reality: paper_3track_entry.py always records the opening
    BUY before any roll can occur. Without this, a bare SELL-only roll would leave
    a spurious naked -qty position on the old (now-closed) contract.
    """
    from src.models.portfolio import TradeAction
    from src.paper.models import PaperTrade

    store.record_trade(
        PaperTrade(
            strategy_name="paper_nifty_futures",
            leg_role="base_futures",
            instrument_key="NSE_FO|NIFTY26JULFUT",
            trade_date=date(2026, 6, 25),
            action=TradeAction.BUY,
            quantity=50,
            price=Decimal("23000.0"),
        )
    )


@pytest.mark.asyncio
async def test_roll_persists_both_close_and_open_atomically(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    _seed_entry_trade(store)
    lookup = _futures_lookup()
    today = date(2026, 7, 29)  # 1 DTE on the July future -> due to roll

    pos = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JULFUT",
    )

    broker = MagicMock()
    broker.get_ltp = AsyncMock(
        return_value={
            "NSE_FO|NIFTY26JULFUT": Decimal("23100.0"),
            "NSE_FO|NIFTY26AUGFUT": Decimal("23150.0"),
        }
    )

    summary = await roll_mod.check_and_roll_leg(
        pos, lookup, store, broker, notifier=None, today=today, dry_run=False
    )

    assert summary is not None
    assert summary["inserted"] == 2
    assert summary["skipped"] == 0

    positions = store.get_positions("paper_nifty_futures")
    # Old contract fully closed (flat), new contract open with the same qty.
    open_keys = {p.instrument_key: p.net_qty for p in positions}
    assert open_keys.get("NSE_FO|NIFTY26AUGFUT") == 50
    assert "NSE_FO|NIFTY26JULFUT" not in open_keys

    # BUG-037: the closed leg's opening row must transition to CLOSED, not
    # stay OPEN forever (mirrors BUG-035's overlay fix; this roll path was
    # found to have the same wiring gap for base_futures/base_ditm_call).
    closed_trade = next(
        t
        for t in store.get_trades("paper_nifty_futures", "base_futures")
        if t.instrument_key == "NSE_FO|NIFTY26JULFUT"
    )
    assert closed_trade.state.value == "CLOSED"


@pytest.mark.asyncio
async def test_roll_skips_mark_closed_when_close_leg_is_duplicate_skipped(
    tmp_path: Path,
) -> None:
    """BUG-037: if record_trades skips the close leg as a duplicate, the
    opening row must NOT be marked CLOSED — mirrors the CC/PP/overlay
    `if inserted:` guard, applied here via `if close_trade in inserted`."""
    store = _make_store(tmp_path)
    _seed_entry_trade(store)
    lookup = _futures_lookup()
    today = date(2026, 7, 29)

    from src.models.portfolio import TradeAction
    from src.paper.models import PaperTrade

    store.record_trade(
        PaperTrade(
            strategy_name="paper_nifty_futures",
            leg_role="base_futures",
            instrument_key="NSE_FO|NIFTY26JULFUT",
            trade_date=today,
            action=TradeAction.SELL,
            quantity=50,
            price=Decimal("1.0"),
        )
    )

    pos = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JULFUT",
    )

    broker = MagicMock()
    broker.get_ltp = AsyncMock(
        return_value={
            "NSE_FO|NIFTY26JULFUT": Decimal("23100.0"),
            "NSE_FO|NIFTY26AUGFUT": Decimal("23150.0"),
        }
    )

    summary = await roll_mod.check_and_roll_leg(
        pos, lookup, store, broker, notifier=None, today=today, dry_run=False
    )

    assert summary is not None
    assert summary["partial"] is True

    # The original entry row (the one actually opened) must stay OPEN —
    # the close attempt never landed, so nothing should have transitioned.
    entry_trade = next(
        t
        for t in store.get_trades("paper_nifty_futures", "base_futures")
        if t.action == TradeAction.BUY
    )
    assert entry_trade.state.value != "CLOSED"


@pytest.mark.asyncio
async def test_roll_notifies_telegram_on_success(tmp_path: Path) -> None:
    """S6: a successful roll must notify, and the message must not contain
    markdown asterisks (TelegramNotifier.send() wraps in <pre> with
    parse_mode HTML — a leftover *bold* marker would render literally)."""
    store = _make_store(tmp_path)
    _seed_entry_trade(store)
    lookup = _futures_lookup()
    today = date(2026, 7, 29)

    pos = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JULFUT",
    )

    broker = MagicMock()
    broker.get_ltp = AsyncMock(
        return_value={
            "NSE_FO|NIFTY26JULFUT": Decimal("23100.0"),
            "NSE_FO|NIFTY26AUGFUT": Decimal("23150.0"),
        }
    )
    notifier = MagicMock()
    notifier.send = AsyncMock(return_value=True)

    summary = await roll_mod.check_and_roll_leg(
        pos, lookup, store, broker, notifier=notifier, today=today, dry_run=False
    )

    assert summary is not None
    notifier.send.assert_awaited_once()
    msg = notifier.send.await_args[0][0]
    assert "*" not in msg
    # ROLL-9: confirmed MarkdownV2 layout, not the old "BASE LEG ROLLED" kv lines.
    assert msg.startswith("🔄 ROLL: NIFTY FUT \\[JUL ➡️ AUG\\]")
    assert "💰 P&L: \\+₹5,000\\.00 🟢" in msg
    assert "⚠️ L\\-Gate: WARN" in msg


@pytest.mark.asyncio
async def test_roll_notify_failure_does_not_block_trade(tmp_path: Path) -> None:
    """Non-fatal contract: a Telegram failure must never roll back or fail
    an already-executed roll."""
    store = _make_store(tmp_path)
    _seed_entry_trade(store)
    lookup = _futures_lookup()
    today = date(2026, 7, 29)

    pos = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JULFUT",
    )

    broker = MagicMock()
    broker.get_ltp = AsyncMock(
        return_value={
            "NSE_FO|NIFTY26JULFUT": Decimal("23100.0"),
            "NSE_FO|NIFTY26AUGFUT": Decimal("23150.0"),
        }
    )
    notifier = MagicMock()
    notifier.send = AsyncMock(side_effect=RuntimeError("network down"))

    summary = await roll_mod.check_and_roll_leg(
        pos, lookup, store, broker, notifier=notifier, today=today, dry_run=False
    )

    # Roll itself must have completed despite the notify failure.
    assert summary is not None
    assert summary["inserted"] == 2
    positions = store.get_positions("paper_nifty_futures")
    open_keys = {p.instrument_key: p.net_qty for p in positions}
    assert open_keys.get("NSE_FO|NIFTY26AUGFUT") == 50


@pytest.mark.asyncio
async def test_roll_dry_run_does_not_persist(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    lookup = _futures_lookup()
    today = date(2026, 7, 29)

    pos = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JULFUT",
    )

    broker = MagicMock()
    broker.get_ltp = AsyncMock(
        return_value={
            "NSE_FO|NIFTY26JULFUT": Decimal("23100.0"),
            "NSE_FO|NIFTY26AUGFUT": Decimal("23150.0"),
        }
    )

    summary = await roll_mod.check_and_roll_leg(
        pos, lookup, store, broker, notifier=None, today=today, dry_run=True
    )

    assert summary is not None
    assert "inserted" not in summary
    # dry_run never calls store.record_trades — DB stays empty regardless of the
    # (synthetic, not DB-backed) `pos` fixture passed in.
    assert store.get_positions("paper_nifty_futures") == []


@pytest.mark.asyncio
async def test_roll_not_due_returns_none(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    lookup = _futures_lookup()
    today = date(2026, 6, 1)  # far from July 30 expiry -> not due

    pos = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JULFUT",
    )

    broker = MagicMock()
    result = await roll_mod.check_and_roll_leg(
        pos, lookup, store, broker, notifier=None, today=today, dry_run=True
    )
    assert result is None
    broker.get_ltp.assert_not_called()


@pytest.mark.asyncio
async def test_roll_partial_insert_flagged(tmp_path: Path) -> None:
    """If record_trades only lands one of the two legs (duplicate skip), the
    summary must flag it — Telegram is the sole visibility mechanism once this
    pipeline runs unattended, so a half-open roll can't look like a clean one."""
    store = _make_store(tmp_path)
    _seed_entry_trade(store)
    lookup = _futures_lookup()
    today = date(2026, 7, 29)

    # Pre-insert the close leg with the exact same (strategy, leg_role,
    # instrument_key, trade_date, action) tuple the roll will attempt, so
    # record_trades' ON CONFLICT DO NOTHING skips it on the real roll call.
    from src.models.portfolio import TradeAction
    from src.paper.models import PaperTrade

    store.record_trade(
        PaperTrade(
            strategy_name="paper_nifty_futures",
            leg_role="base_futures",
            instrument_key="NSE_FO|NIFTY26JULFUT",
            trade_date=today,
            action=TradeAction.SELL,
            quantity=50,
            price=Decimal("1.0"),  # different price, same conflict key -> still skipped
        )
    )

    pos = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JULFUT",
    )

    broker = MagicMock()
    broker.get_ltp = AsyncMock(
        return_value={
            "NSE_FO|NIFTY26JULFUT": Decimal("23100.0"),
            "NSE_FO|NIFTY26AUGFUT": Decimal("23150.0"),
        }
    )

    summary = await roll_mod.check_and_roll_leg(
        pos, lookup, store, broker, notifier=None, today=today, dry_run=False
    )

    assert summary is not None
    assert summary["inserted"] == 1
    assert summary["partial"] is True


# ── DITM orchestration path ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ditm_roll_persists_via_band_aware_lookup(tmp_path: Path) -> None:
    """DITM roll must use get_next_contract_in_band (never plain get_next_contract,
    which would land on a weekly contract) and persist atomically like futures."""
    store = _make_store(tmp_path)
    lookup = InstrumentLookup(
        [
            {
                "instrument_key": "NSE_FO|NIFTY26JUL23000CE",
                "segment": "NSE_FO",
                "underlying_symbol": "NIFTY",
                "instrument_type": "CE",
                "strike_price": 23000.0,
                "expiry": "2026-07-30",
                "trading_symbol": "NIFTY JUL 23000 CE",
            },
            {
                "instrument_key": "NSE_FO|NIFTY26AUG23000CE",
                "segment": "NSE_FO",
                "underlying_symbol": "NIFTY",
                "instrument_type": "CE",
                "strike_price": 23000.0,
                "expiry": "2026-08-27",
                "trading_symbol": "NIFTY AUG 23000 CE",
            },
        ]
    )
    today = date(2026, 7, 15)  # 15 DTE on the July CE -> under DITM_ROLL_DTE (20)

    from src.models.portfolio import TradeAction
    from src.paper.models import PaperTrade

    store.record_trade(
        PaperTrade(
            strategy_name="paper_nifty_proxy",
            leg_role="base_ditm_call",
            instrument_key="NSE_FO|NIFTY26JUL23000CE",
            trade_date=date(2026, 6, 25),
            action=TradeAction.BUY,
            quantity=50,
            price=Decimal("1000.0"),
        )
    )

    pos = PaperPosition(
        strategy_name="paper_nifty_proxy",
        leg_role="base_ditm_call",
        net_qty=50,
        avg_cost=Decimal("1000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JUL23000CE",
    )

    broker = MagicMock()
    broker.get_ltp = AsyncMock(
        return_value={
            "NSE_FO|NIFTY26JUL23000CE": Decimal("1050.0"),
            "NSE_FO|NIFTY26AUG23000CE": Decimal("1100.0"),
        }
    )

    summary = await roll_mod.check_and_roll_leg(
        pos, lookup, store, broker, notifier=None, today=today, dry_run=False
    )

    assert summary is not None
    assert summary["new_key"] == "NSE_FO|NIFTY26AUG23000CE"
    assert summary["inserted"] == 2

    positions = store.get_positions("paper_nifty_proxy")
    open_keys = {p.instrument_key: p.net_qty for p in positions}
    assert open_keys.get("NSE_FO|NIFTY26AUG23000CE") == 50
    assert "NSE_FO|NIFTY26JUL23000CE" not in open_keys


# ── Regression guard: overlay automation untouched ──────────────────────────


@pytest.mark.asyncio
async def test_niftytrackcomparisonv1_untouched() -> None:
    """S5 touches only base-leg rolling — NiftyTrackComparisonV1's overlay
    evaluation must emit nothing for a plain base_futures position (no overlay,
    no proxy-delta leg)."""
    strategy = NiftyTrackComparisonV1()

    pos_fut = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JULFUT",
    )

    events = await strategy.check_signals(market=None, positions=[pos_fut])
    assert events == []


# ── ROLL-9: build_roll_notification MarkdownV2 layout ───────────────────────────
#
# One test per confirmed scenario in the reference script
# (scratch/2026-08-10_3track_roll_notification_format.py), asserting the exact
# layout + escaping for its leg role, plus the label / partial / escape regressions
# the epic carries forward.

_AUG = date(2026, 8, 25)
_SEP = date(2026, 9, 29)
_OCT = date(2026, 10, 27)


def _futures_msg(**over: object) -> str:
    kw: dict = dict(
        leg_role="base_futures",
        strategy_name="paper_nifty_futures",
        close_price=Decimal("24812.50"),
        open_price=Decimal("24855.75"),
        avg_cost=Decimal("24500.00"),
        qty=25,
        old_expiry=_AUG,
        new_expiry=_SEP,
        gate_passed=True,
        partial=False,
    )
    kw.update(over)
    return roll_mod.build_roll_notification(**kw)


def _ditm_msg(**over: object) -> str:
    kw: dict = dict(
        leg_role="base_ditm_call",
        strategy_name="paper_nifty_proxy",
        close_price=Decimal("86.68"),
        open_price=Decimal("112.30"),
        avg_cost=Decimal("102.40"),
        qty=25,
        old_expiry=_AUG,
        new_expiry=_SEP,
        gate_passed=False,
        partial=False,
        strike=24000,
    )
    kw.update(over)
    return roll_mod.build_roll_notification(**kw)


def test_roll_notification_futures_clean_pass() -> None:
    msg = _futures_msg()
    assert msg == (
        "🔄 ROLL: NIFTY FUT \\[AUG ➡️ SEP\\]\n"
        "💰 P&L: \\+₹7,812\\.50 🟢\n"
        "📐 Spread: 43\\.25 pts \\(Contango\\)\n"
        "\n"
        "⬇️ OUT: ₹24,812\\.50\n"
        "⬆️ IN: ₹24,855\\.75\n"
        "✅ L\\-Gate: PASS"
    )


def test_roll_notification_futures_loss_backwardation() -> None:
    msg = _futures_msg(open_price=Decimal("24780.25"), avg_cost=Decimal("25100.00"))
    assert "💰 P&L: \\-₹7,187\\.50 🔴" in msg
    assert "📐 Spread: 32\\.25 pts \\(Backwardation\\)" in msg


def test_roll_notification_futures_gate_warn() -> None:
    assert "⚠️ L\\-Gate: WARN" in _futures_msg(gate_passed=False)


def test_roll_notification_futures_partial_roll() -> None:
    msg = _futures_msg(partial=True, gate_passed=True)
    assert "🚨 PARTIAL ROLL — VERIFY POSITIONS MANUALLY" in msg
    assert "L\\-Gate" not in msg


def test_roll_notification_ditm_call_warn() -> None:
    msg = _ditm_msg()
    assert msg == (
        "🔄 ROLL: PROXY DITM CALL\n"
        "🎟️ \\[NIFTY 24000 CE\\] AUG ➡️ SEP\n"
        "💰 P&L: \\-₹393\\.00 🔴\n"
        "📐 Spread: 25\\.62 pts \\(Debit\\)\n"
        "\n"
        "⬇️ OUT: ₹86\\.68\n"
        "⬆️ IN: ₹112\\.30\n"
        "⚠️ L\\-Gate: WARN"
    )


def test_roll_notification_ditm_call_profit_credit() -> None:
    msg = _ditm_msg(
        close_price=Decimal("112.30"),
        open_price=Decimal("86.68"),
        avg_cost=Decimal("70.00"),
        gate_passed=True,
        old_expiry=_SEP,
        new_expiry=_OCT,
    )
    assert "💰 P&L: \\+₹1,057\\.50 🟢" in msg
    assert "📐 Spread: 25\\.62 pts \\(Credit\\)" in msg
    assert "✅ L\\-Gate: PASS" in msg


def test_roll_notification_ditm_call_partial_roll() -> None:
    msg = _ditm_msg(partial=True, gate_passed=True)
    assert "🚨 PARTIAL ROLL — VERIFY POSITIONS MANUALLY" in msg
    assert "L\\-Gate" not in msg


def test_futures_spread_label_contango_backwardation_flat() -> None:
    assert roll_mod._futures_spread_label(Decimal("1")) == "Contango"
    assert roll_mod._futures_spread_label(Decimal("-1")) == "Backwardation"
    assert roll_mod._futures_spread_label(Decimal("0")) == "Flat"


def test_ditm_spread_label_debit_credit_flat() -> None:
    assert roll_mod._ditm_spread_label(Decimal("1")) == "Debit"
    assert roll_mod._ditm_spread_label(Decimal("-1")) == "Credit"
    assert roll_mod._ditm_spread_label(Decimal("0")) == "Flat"
    # The two leg roles never share a label function.
    assert roll_mod._futures_spread_label is not roll_mod._ditm_spread_label


def test_ditm_gate_warn_has_no_reason_parenthetical() -> None:
    """ROLL-9 item 6: a WARN-state DITM roll ships '⚠️ L-Gate: WARN' with no
    parenthetical reason — check_ditm_liquidity_gate returns a bare bool, and a
    future edit must not silently half-implement a gate-reason feature."""
    msg = _ditm_msg(gate_passed=False)
    gate_line = msg.splitlines()[-1]
    assert gate_line == "⚠️ L\\-Gate: WARN"
    assert "(" not in gate_line and "\\(" not in gate_line


def test_roll_notification_escapes_underscore_strategy_name() -> None:
    """Epic-wide regression: an identifier-shaped dynamic value with an
    underscore must survive escaped. paper_nifty_proxy -> short label 'PROXY',
    but a hypothetical unmapped id must raise rather than leak a raw underscore."""
    # Mapped short label carries no underscore.
    assert "PROXY" in _ditm_msg()
    # Unmapped strategy id is a loud failure, never a raw-underscore leak.
    with pytest.raises(ValueError):
        _ditm_msg(strategy_name="paper_nifty_proxy_v99")


def test_roll_notification_partial_overrides_gate_line() -> None:
    """partial=True always produces the 🚨 line regardless of gate_passed, both roles."""
    for builder in (_futures_msg, _ditm_msg):
        for gate in (True, False):
            msg = builder(partial=True, gate_passed=gate)
            assert msg.splitlines()[-1] == "🚨 PARTIAL ROLL — VERIFY POSITIONS MANUALLY"


@pytest.mark.asyncio
async def test_roll_notification_pnl_uses_avg_cost_not_avg_sell_price(tmp_path: Path) -> None:
    """Regression for the entry-basis: a PaperPosition with a non-zero
    avg_sell_price must not leak into the closed-leg P&L — check_and_roll_leg
    passes pos.avg_cost, and both rollable legs are always long."""
    store = _make_store(tmp_path)
    _seed_entry_trade(store)
    lookup = _futures_lookup()
    today = date(2026, 7, 29)

    pos = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("99999.0"),  # must be ignored
        instrument_key="NSE_FO|NIFTY26JULFUT",
    )
    broker = MagicMock()
    broker.get_ltp = AsyncMock(
        return_value={
            "NSE_FO|NIFTY26JULFUT": Decimal("23100.0"),
            "NSE_FO|NIFTY26AUGFUT": Decimal("23150.0"),
        }
    )
    notifier = MagicMock()
    notifier.send = AsyncMock(return_value=True)

    await roll_mod.check_and_roll_leg(
        pos, lookup, store, broker, notifier=notifier, today=today, dry_run=False
    )
    msg = notifier.send.await_args[0][0]
    # (23100 - 23000) * 50 = +5,000.00 — not driven by avg_sell_price.
    assert "💰 P&L: \\+₹5,000\\.00 🟢" in msg
