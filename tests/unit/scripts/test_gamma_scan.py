"""End-to-end tests for scripts/gamma_scan.py with every collaborator faked."""

from __future__ import annotations

import fcntl
import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import pytest

from scripts import gamma_scan as gs
from src.client.exceptions import DataFetchError
from src.gamma.depth import DepthSnapshot, NullDepth
from src.gamma.exits import ExitConfig
from src.gamma.signals import (
    Layer,
    SignalConfig,
    SignalStack,
    l0_ask_qty,
    l0_premium,
    l0_vix,
)
from src.gamma.store import GammaStore
from src.models.options import OptionChain, OptionChainStrike, OptionLeg

EXPIRY = date(2026, 10, 13)  # Tuesday
MON_10 = datetime(2026, 10, 12, 10, 0, tzinfo=gs.IST)  # DTE 1
CFG = SignalConfig(min_ask_qty=65)


def leg(strike: int, *, gamma: str = "0.001", bid: str = "4.8", ask: str = "5") -> OptionLeg:
    return OptionLeg(
        ltp=D("4.9"),
        bid=D(bid),
        ask=D(ask),
        oi=5000,
        volume=900,
        delta=D("0.4"),
        gamma=D(gamma),
        theta=D("-3"),
        vega=D("2"),
        iv=D("14"),
        strike=D(strike),
    )


def make_chain(**over: OptionChainStrike) -> OptionChain:
    strikes = {
        D(24000): OptionChainStrike(ce=leg(24000, gamma="0.002"), pe=leg(24000)),
        D(24100): OptionChainStrike(ce=leg(24100), pe=None),
    }
    for k, v in over.items():
        strikes[D(int(k.lstrip("s")))] = v
    return OptionChain(underlying_spot=D(24000), expiry=EXPIRY, strikes=strikes)


class FakeChain:
    def __init__(self, chain: OptionChain, log: list[str]) -> None:
        self.chain = chain
        self.log = log
        self.calls = 0
        self.fail = False

    async def get_chain(self, underlying: str, expiry: str) -> OptionChain:
        self.calls += 1
        self.log.append("chain")
        if self.fail:
            raise DataFetchError("boom")
        return self.chain


class FakeDepth:
    def __init__(self, log: list[str], ask_qty: dict[str, int] | None = None) -> None:
        self.log = log
        self.ask_qty = ask_qty or {}

    async def fetch(self, security_id: str, exchange_segment: str = "NSE_FNO") -> DepthSnapshot:
        self.log.append("depth")
        qty = self.ask_qty.get(security_id, 130)
        return DepthSnapshot(bid_qty_l1=100, ask_qty_l1=qty, total_bid_qty=900, total_ask_qty=900)


class FakeVix:
    def __init__(self, value: D | None = D("15")) -> None:
        self.value = value

    async def india_vix(self) -> D | None:
        return self.value


class FakeResolver:
    def resolve(self, expiry: date, strike: int, option_type: str) -> str | None:
        return f"NSE_FO|{strike}{1 if option_type == 'PE' else 0}"


class FakeNotifier:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[str] = []
        self.fail = fail

    async def send(self, text: str) -> bool:
        if self.fail:
            raise RuntimeError("telegram down")
        self.sent.append(text)
        return True


def permissive_stack() -> SignalStack:
    return SignalStack(CFG, layers=(Layer(0, (l0_premium, l0_ask_qty, l0_vix)),))


@pytest.fixture
def env(tmp_path: Path):
    log: list[str] = []
    db = tmp_path / "p.sqlite"
    deps = gs.ScanDeps(
        chain_source=FakeChain(make_chain(), log),
        depth=FakeDepth(log),
        store=GammaStore(),
        stack=permissive_stack(),
        exit_config=ExitConfig(),
        paper=gs.PaperLedgerAdapter(db),
        notifier=FakeNotifier(),
        vix=FakeVix(),
        resolver=FakeResolver(),
        db_path=db,
        lot_size=65,
    )
    return deps, log, db


def q(db: Path, sql: str, *args: Any) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def trades(db: Path) -> list[tuple[str, str, str, int, str]]:
    rows = q(
        db,
        "SELECT leg_role, action, instrument_key, quantity, price FROM paper_trades ORDER BY id",
    )
    return [tuple(r) for r in rows]  # type: ignore[misc]


async def test_end_to_end_stages_in_order_and_one_trade_per_direction(env):
    deps, log, db = env
    out = await gs.run_scan(deps, MON_10)

    assert out.evaluated == 3 and out.triggered == 3 and out.entered == 2
    assert log[0] == "chain" and set(log[1:]) == {"depth"}
    rows = q(
        db,
        "SELECT strike, option_type, paper_trade_filled, unfilled_reason, india_vix "
        "FROM gamma_signal_log ORDER BY strike, option_type",
    )
    assert len(rows) == 3
    by = {(r["strike"], r["option_type"]): r for r in rows}
    assert by[(24000, "CE")]["paper_trade_filled"] == 1
    assert by[(24000, "PE")]["paper_trade_filled"] == 1
    assert by[(24100, "CE")]["unfilled_reason"] == "not_top_ranked"
    assert by[(24000, "CE")]["india_vix"] == "15"
    assert trades(db) == [
        ("gamma_call", "BUY", "NSE_FO|240000", 65, "5"),
        ("gamma_put", "BUY", "NSE_FO|240001", 65, "5"),
    ]
    assert len(deps.notifier.sent) == 3  # signal fired + two entries


async def test_default_stack_first_scan_logs_reason_and_trades_nothing(env):
    deps, _, db = env
    deps = gs.ScanDeps(**{**deps.__dict__, "stack": SignalStack(CFG)})
    out = await gs.run_scan(deps, MON_10)
    assert out.evaluated == 3 and out.triggered == 0 and out.entered == 0
    rows = q(db, "SELECT DISTINCT unfilled_reason, speed_5m_unavailable FROM gamma_signal_log")
    assert {r["unfilled_reason"] for r in rows} == {"L1_INPUT_UNAVAILABLE"}
    assert trades(db) == []


def test_lock_held_second_run_exits_without_trading(tmp_path, monkeypatch):
    lock = tmp_path / "scan.lock"
    called: list[bool] = []

    async def fake_main(dry_run: bool) -> int:
        called.append(dry_run)
        return 0

    monkeypatch.setattr(gs, "_main", fake_main)
    with open(lock, "a") as holder:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert gs.main([], lock_path=lock) == 0
        assert called == []
    assert gs.main(["--dry-run"], lock_path=lock) == 0
    assert called == [True]


async def test_open_position_same_direction_blocks_second_entry(env):
    deps, _, db = env
    await gs.run_scan(deps, MON_10)
    out = await gs.run_scan(deps, MON_10 + timedelta(minutes=5))

    assert out.entered == 0
    assert len([t for t in trades(db) if t[1] == "BUY"]) == 2
    reasons = {
        r["unfilled_reason"]
        for r in q(db, "SELECT unfilled_reason FROM gamma_signal_log WHERE signal_triggered = 1")
    }
    assert "open_position_same_direction" in reasons


async def test_ledger_position_without_log_row_also_blocks(env):
    deps, _, db = env
    with sqlite3.connect(db) as c:
        c.execute(
            "INSERT INTO paper_trades (strategy_name, leg_role, instrument_key, trade_date,"
            " action, quantity, price, notes, state) VALUES ('paper_negamma_v1', 'gamma_call',"
            " 'NSE_FO|1', '2026-10-09', 'BUY', 65, '4', '', 'OPEN')"
        )
    out = await gs.run_scan(deps, MON_10)
    assert out.entered == 1  # only the put
    assert [t[0] for t in trades(db) if t[1] == "BUY"] == ["gamma_call", "gamma_put"]


async def test_reduced_mode_null_depth_still_evaluates(env):
    deps, _, db = env
    deps = gs.ScanDeps(**{**deps.__dict__, "depth": NullDepth()})
    out = await gs.run_scan(deps, MON_10)
    assert out.evaluated == 3 and out.entered == 2
    nulls = q(db, "SELECT COUNT(*) AS n FROM gamma_signal_log WHERE ask_qty_l1 IS NULL")
    assert nulls[0]["n"] == 3


async def test_notifier_failure_is_non_fatal(env):
    deps, _, db = env
    deps = gs.ScanDeps(**{**deps.__dict__, "notifier": FakeNotifier(fail=True)})
    out = await gs.run_scan(deps, MON_10)
    assert out.entered == 2
    assert len(trades(db)) == 2


async def test_non_dte_day_and_non_trading_day_are_noops(env):
    deps, log, db = env
    wed = datetime(2026, 10, 14, 10, 0, tzinfo=gs.IST)  # next expiry is 6 days out
    sat = datetime(2026, 10, 17, 10, 0, tzinfo=gs.IST)
    early = datetime(2026, 10, 12, 9, 0, tzinfo=gs.IST)
    assert (await gs.run_scan(deps, wed)).skipped == "dte_out_of_range"
    assert (await gs.run_scan(deps, sat)).skipped == "non_trading_day"
    assert (await gs.run_scan(deps, early)).skipped == "outside_scan_window"
    assert log == []
    assert (
        not db.exists()
        or q(db, "SELECT name FROM sqlite_master WHERE name='gamma_signal_log'") == []
    )


async def test_dry_run_writes_log_rows_but_no_trade_or_telegram(env):
    deps, _, db = env
    out = await gs.run_scan(deps, MON_10, dry_run=True)
    assert out.evaluated == 3 and out.triggered == 3 and out.entered == 0
    assert q(db, "SELECT COUNT(*) AS n FROM gamma_signal_log")[0]["n"] == 3
    assert (
        q(db, "SELECT COUNT(*) AS n FROM gamma_signal_log WHERE paper_trade_filled = 1")[0]["n"]
        == 0
    )
    assert trades(db) == []
    assert deps.notifier.sent == []


async def test_entry_window_closed_after_1430(env):
    deps, _, db = env
    out = await gs.run_scan(deps, MON_10.replace(hour=14, minute=35))
    assert out.entered == 0 and trades(db) == []
    reasons = {r["unfilled_reason"] for r in q(db, "SELECT unfilled_reason FROM gamma_signal_log")}
    assert "entry_window_closed" in reasons


async def test_chain_fetch_failure_skips_cleanly(env):
    deps, _, db = env
    deps.chain_source.fail = True
    assert (await gs.run_scan(deps, MON_10)).skipped == "chain_fetch_failed"


async def test_missing_vix_fails_layer_zero_closed(env):
    deps, _, _ = env
    deps = gs.ScanDeps(**{**deps.__dict__, "vix": FakeVix(None)})
    out = await gs.run_scan(deps, MON_10)
    assert out.triggered == 0


# --- exits ---------------------------------------------------------------


def set_ce_24000(deps: gs.ScanDeps, **kw: str) -> None:
    chain = deps.chain_source.chain
    strikes = dict(chain.strikes)
    strikes[D(24000)] = OptionChainStrike(ce=leg(24000, gamma="0.002", **kw), pe=leg(24000))
    deps.chain_source.chain = chain.model_copy(update={"strikes": strikes})


def exit_row(db: Path) -> sqlite3.Row:
    return q(
        db,
        "SELECT exit_reason, exit_price, realised_r_multiple, mfe, mae FROM gamma_signal_log"
        " WHERE option_type = 'CE' AND paper_trade_filled = 1",
    )[0]


async def test_e1_profit_target_exit_closes_ledger_and_log(env):
    deps, _, db = env
    await gs.run_scan(deps, MON_10)
    set_ce_24000(deps, bid="25", ask="26")
    out = await gs.run_scan(deps, MON_10 + timedelta(minutes=5))

    assert out.exited == 1
    r = exit_row(db)
    assert r["exit_reason"] == "E1_PROFIT_TARGET"
    assert r["exit_price"] == "25" and r["realised_r_multiple"] == "4"
    assert r["mfe"] == "20" and r["mae"] == "0.2"
    sells = [t for t in trades(db) if t[1] == "SELL"]
    assert sells == [("gamma_call", "SELL", "NSE_FO|240000", 65, "25")]
    state = q(db, "SELECT state FROM paper_trades WHERE leg_role = 'gamma_call'")
    assert {s["state"] for s in state} == {"CLOSED"}


async def test_liquidity_exit_needs_two_consecutive_zero_scans(env):
    deps, _, db = env
    await gs.run_scan(deps, MON_10)
    ce = "24000" + "0"
    deps.depth.ask_qty[ce] = 0
    out1 = await gs.run_scan(deps, MON_10 + timedelta(minutes=5))
    assert out1.exited == 0
    deps.depth.ask_qty[ce] = 50  # streak resets on any non-zero ask qty
    assert (await gs.run_scan(deps, MON_10 + timedelta(minutes=10))).exited == 0
    deps.depth.ask_qty[ce] = 0
    assert (await gs.run_scan(deps, MON_10 + timedelta(minutes=15))).exited == 0
    out4 = await gs.run_scan(deps, MON_10 + timedelta(minutes=20))
    assert out4.exited == 1
    assert exit_row(db)["exit_reason"] == "E2_LIQUIDITY"


async def test_dte1_time_stop_with_no_bid_exits_with_null_price(env):
    deps, _, db = env
    await gs.run_scan(deps, MON_10)
    set_ce_24000(deps, bid="0", ask="5")
    out = await gs.run_scan(deps, MON_10.replace(hour=15, minute=0))
    assert out.exited == 2  # the put also reaches the DTE-1 15:00 stop
    r = exit_row(db)
    assert r["exit_reason"] == "E3_TIME_STOP" and r["exit_price"] is None
    call_sell = [t for t in trades(db) if t[:2] == ("gamma_call", "SELL")][0]
    assert call_sell[4] == str(gs.MIN_LEDGER_PRICE)


async def test_exit_not_performed_in_dry_run(env):
    deps, _, db = env
    await gs.run_scan(deps, MON_10)
    set_ce_24000(deps, bid="25", ask="26")
    out = await gs.run_scan(deps, MON_10 + timedelta(minutes=5), dry_run=True)
    assert out.exited == 0
    assert exit_row(db)["exit_reason"] is None


# --- transaction safety ---------------------------------------------------


async def test_entry_rolls_back_ledger_when_log_insert_fails(env):
    deps, _, db = env

    class Boom(GammaStore):
        def insert_signal_log(self, conn, entry):  # type: ignore[no-untyped-def]
            if entry.paper_trade_attempted:
                raise sqlite3.IntegrityError("simulated")
            super().insert_signal_log(conn, entry)

    deps = gs.ScanDeps(**{**deps.__dict__, "store": Boom()})
    out = await gs.run_scan(deps, MON_10)
    assert out.entered == 0
    assert trades(db) == []  # ledger INSERT rolled back with the failed log insert
    err = q(db, "SELECT unfilled_reason FROM gamma_signal_log WHERE paper_trade_attempted = 1")
    assert err == []  # the fallback row hit the same simulated failure; the scan survived


def test_begin_immediate_blocks_a_concurrent_writer(env):
    """A second connection cannot write while the entry transaction holds the lock."""
    deps, _, db = env
    a = sqlite3.connect(db, isolation_level=None, timeout=0.1)
    b = sqlite3.connect(db, timeout=0.1)
    a.execute("BEGIN IMMEDIATE")
    with pytest.raises(sqlite3.OperationalError):
        b.execute("BEGIN IMMEDIATE")
    a.execute("ROLLBACK")
    a.close()
    b.close()


# --- config / helpers -----------------------------------------------------


def test_build_signal_config_applies_env_overrides_once():
    cfg = gs.build_signal_config(
        65, {"GAMMA_MIN_GEARING": "7.5", "GAMMA_MIN_PREMIUM": "3", "GAMMA_MAX_PREMIUM": "8"}
    )
    assert (cfg.min_ask_qty, cfg.gearing_threshold) == (65, D("7.5"))
    assert (cfg.min_premium, cfg.max_premium) == (D(3), D(8))


def test_build_signal_config_defaults_and_bad_value():
    cfg = gs.build_signal_config(65, {})
    assert cfg.gearing_threshold == D("5.0") and cfg.min_premium == D(2)
    with pytest.raises(Exception):  # noqa: B017,PT011 - decimal.InvalidOperation
        gs.build_signal_config(65, {"GAMMA_MIN_GEARING": "abc"})


def test_zero_ask_streak_counts_trailing_zeros_only():
    assert gs._zero_ask_streak([(None, 0), (None, 5), (None, 0), (None, 0)]) == 2
    assert gs._zero_ask_streak([(None, 0), (None, None)]) == 0
    assert gs._zero_ask_streak([]) == 0


def test_paper_ledger_duplicate_buy_is_skipped(tmp_path):
    from src.paper.models import PaperTrade

    db = tmp_path / "p.sqlite"
    ledger = gs.PaperLedgerAdapter(db)
    t = PaperTrade(
        strategy_name=gs.STRATEGY,
        leg_role="gamma_call",
        instrument_key="NSE_FO|1",
        trade_date=date(2026, 10, 12),
        action="BUY",
        quantity=65,
        price=D("5"),
    )  # type: ignore[arg-type]
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    assert ledger.open_long(conn, t) is True
    assert ledger.open_long(conn, t) is False
    assert ledger.net_qty(conn, "gamma_call") == 65
    conn.close()
