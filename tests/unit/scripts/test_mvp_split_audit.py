"""Tests for the read-only MVP split-candidate audit script."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from scripts.dev.mvp_split_audit import audit_picks, find_gap_candidates, main
from src.backtest.equity_bhavcopy_ingest import EquityBhavRecord, write_equity_to_parquet
from src.mvp.models import CorporateAction, CorporateActionType, Pick, PickStatus
from src.mvp.store import MVPStore

_TS = "2025-09-08T00:00:00Z"


def _closes() -> list[tuple[date, Decimal]]:
    return [
        (date(2025, 12, 11), Decimal("1400")),
        (date(2025, 12, 12), Decimal("1390")),  # -0.7%: organic
        (date(2025, 12, 15), Decimal("280")),  # 5:1 gap
        (date(2025, 12, 16), Decimal("240")),  # -14%: organic crash, no match
    ]


def test_find_gap_candidates_flags_only_the_ratio_match() -> None:
    (cand,) = find_gap_candidates("BECTORFOOD", _closes())
    assert cand.gap_date == date(2025, 12, 15) and cand.match.label == "5:1"


def test_find_gap_candidates_skips_recorded_action_and_empty() -> None:
    action = CorporateAction(
        action_id="a",
        symbol="BECTORFOOD",
        ex_date="2025-12-15",
        action_type=CorporateActionType.SPLIT,
        new_shares=5,
        old_shares=1,
        source="t",
        created_at=_TS,
    )
    assert find_gap_candidates("BECTORFOOD", _closes(), [action]) == []
    assert find_gap_candidates("X", []) == []


def _seed(tmp_path: Path) -> tuple[MVPStore, Path]:
    store = MVPStore(tmp_path / "audit.db")
    store.init_db()
    store.add_pick(
        Pick(
            pick_id="e30d0a11-0000-0000-0000-000000000000",
            symbol="BECTORFOOD",
            pick_date="2025-12-01",
            status=PickStatus.PENDING,
            created_at=_TS,
            updated_at=_TS,
        )
    )
    data_dir = tmp_path / "equity"
    for d, c in _closes():
        write_equity_to_parquet(
            [EquityBhavRecord(trade_date=d, symbol="BECTORFOOD", close=c)], d, data_dir
        )
    return store, data_dir


def test_audit_picks_is_read_only_and_reports_candidate(tmp_path: Path, capsys) -> None:
    store, data_dir = _seed(tmp_path)
    (found,) = audit_picks(store, data_dir=data_dir, to_date=date(2025, 12, 31))
    assert found[0].symbol == "BECTORFOOD" and found[1].match.label == "5:1"
    assert store.get_corporate_actions() == []
    assert main(["--db", str(tmp_path / "missing.db")]) == 1
    assert "DB not found" in capsys.readouterr().out
