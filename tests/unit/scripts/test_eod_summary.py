r"""Unit tests for scripts/eod_summary.py — ROLL-6 EOD Paper Summary migration.

Coverage (ROLL-6 spec, strategy-rollout/stories.md):
- build_eod_summary_message: confirmed MarkdownV2 structure (header / summary
  line / fenced bucketed table / hashtag after the fence).
- bucket subtotal rows equal the sum of their member rows, independently per
  bucket (not just the grand Net P&L total).
- Net P&L line equals the sum of every bucket subtotal.
- an unmapped strategy_id raises ValueError, never silently drops.
- table money renders as signed integer, no decimals (FMT-1d override).
- a real measured zero renders as "-", not "0"/"+0".
- the #EOD_SUMMARY tag survives escaping as literal \#EOD\_SUMMARY.
- main() sources Bkd from get_strategy_realized_pnl(), not
  paper_nav_snapshots.realized_pnl's latest row.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from scripts.eod_summary import _BUCKET_ORDER, build_eod_summary_message

# (strategy_id, floating, booked) — one per bucket, deterministic values.
_SAMPLE: list[tuple[str, Decimal, Decimal]] = [
    ("paper_nifty_futures", Decimal("-149.50"), Decimal("0.00")),
    ("paper_nifty_proxy", Decimal("-2970.50"), Decimal("-3443.38")),
    ("paper_nifty_spot", Decimal("50640.05"), Decimal("0.00")),
    ("paper_ic_nifty_v1_weekly", Decimal("0.00"), Decimal("2759.25")),
    ("paper_ic_nifty_v1_monthly", Decimal("359.12"), Decimal("3486.44")),
    ("paper_collar_v1", Decimal("210.00"), Decimal("-85.50")),
    ("paper_csp_nifty_v1", Decimal("0.00"), Decimal("11024.00")),
]


def _table_lines(message: str) -> list[str]:
    """The lines strictly inside the single fenced code block."""
    parts = message.split("```")
    assert len(parts) == 3, "expected exactly one fenced block"
    return parts[1].strip("\n").split("\n")


def _row_cells(line: str) -> list[str]:
    return [c.strip() for c in line.split("|")]


def _is_rule(line: str) -> bool:
    return set(line) <= set("-=|")


def _money_to_int(cell: str) -> int:
    if cell == "-":
        return 0
    return int(cell.replace(",", "").replace("+", ""))


def test_build_eod_summary_message_matches_confirmed_format():
    msg = build_eod_summary_message("07 Aug 2026", 0, _SAMPLE)
    lines = msg.split("\n")

    # Header line, then summary line, then the fence.
    assert lines[0] == "📝 NiftyShield Paper EOD \\| 07 Aug 2026"
    assert lines[1].startswith("Activities: 0 \\| Net P&L: ")
    assert lines[2] == "```"
    assert lines[-1] == "\\#EOD\\_SUMMARY"
    assert lines[-2] == "```"

    table = _table_lines(msg)
    header_cells = _row_cells(table[0])
    assert header_cells == ["STRATEGY", "FLT", "BKD", "TOTAL"]
    assert set(table[1]) == {"=", "|"}  # double rule under the header

    # Bucket order + totals-first: a "> X TOTAL" line appears before its members.
    total_labels = [_row_cells(ln)[0] for ln in table if _row_cells(ln)[0].startswith("> ")]
    assert total_labels == ["> TRACK TOTAL", "> IC TOTAL", "> OVERLAY TOTAL", "> CSP TOTAL"]


def test_eod_summary_bucket_subtotal_is_sum_of_members():
    msg = build_eod_summary_message("07 Aug 2026", 0, _SAMPLE)
    table = _table_lines(msg)

    current_total: list[int] | None = None
    running = [0, 0]
    for line in table:
        if _is_rule(line):
            continue
        cells = _row_cells(line)
        if cells[0].startswith("> "):
            if current_total is not None:
                assert running == current_total
            current_total = [_money_to_int(cells[1]), _money_to_int(cells[2])]
            running = [0, 0]
        elif len(cells) == 4 and cells[0] not in ("STRATEGY", ""):
            running[0] += _money_to_int(cells[1])
            running[1] += _money_to_int(cells[2])
    assert current_total is not None
    assert running == current_total


def test_eod_summary_net_pnl_sums_all_buckets():
    msg = build_eod_summary_message("07 Aug 2026", 3, _SAMPLE)
    table = _table_lines(msg)

    subtotal_sum = 0
    for line in table:
        if _is_rule(line):
            continue
        cells = _row_cells(line)
        if cells[0].startswith("> "):
            subtotal_sum += _money_to_int(cells[3])

    net_match = re.search(r"Net P&L: ([+-])₹([\d,]+)", msg.replace("\\", ""))
    assert net_match is not None
    net = int(net_match.group(2).replace(",", ""))
    net = net if net_match.group(1) == "+" else -net
    assert net == subtotal_sum


def test_eod_summary_unmapped_strategy_raises():
    with pytest.raises(ValueError, match="not mapped to a bucket"):
        build_eod_summary_message(
            "07 Aug 2026", 0, [("paper_brand_new_strategy", Decimal("1"), Decimal("2"))]
        )


def test_eod_summary_table_money_no_decimals():
    msg = build_eod_summary_message(
        "07 Aug 2026", 0, [("paper_ic_nifty_v1_monthly", Decimal("359.12"), Decimal("0.00"))]
    )
    table = _table_lines(msg)
    member = next(ln for ln in table if _row_cells(ln)[0] == "V1 Mth")
    assert _row_cells(member)[1] == "+359"  # 359.12 -> +359, not +359.12 / +359.1


def test_eod_summary_zero_value_renders_dash():
    msg = build_eod_summary_message(
        "07 Aug 2026", 0, [("paper_nifty_spot", Decimal("0.00"), Decimal("1000.00"))]
    )
    table = _table_lines(msg)
    member = next(ln for ln in table if _row_cells(ln)[0] == "Spot")
    assert _row_cells(member)[1] == "-"  # real zero -> "-", not "0"/"+0"/"-0"


def test_eod_summary_hashtag_survives_escaping():
    msg = build_eod_summary_message("07 Aug 2026", 0, _SAMPLE)
    assert msg.endswith("\n\\#EOD\\_SUMMARY")


def test_bucket_order_constant_is_the_four_buckets():
    assert _BUCKET_ORDER == ["Track", "IC", "Overlay", "CSP"]


@pytest.mark.asyncio
async def test_eod_summary_bkd_uses_get_strategy_realized_pnl(tmp_path, monkeypatch):
    """main() must source Bkd from get_strategy_realized_pnl(), not the
    paper_nav_snapshots.realized_pnl column (which resets on a reopen cycle)."""
    from datetime import date

    from src.db import connect
    from src.paper.store import PaperStore

    db_path = tmp_path / "paper.db"
    PaperStore(db_path)  # create schema
    today = date.today().isoformat()
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO paper_nav_snapshots "
            "(strategy_name, snapshot_date, unrealized_pnl, realized_pnl, total_pnl) "
            "VALUES (?, ?, ?, ?, ?)",
            ("paper_csp_nifty_v1", today, "12.00", "999999.00", "999999.00"),
        )

    sent: list[str] = []

    class _Notifier:
        async def send(self, text: str) -> bool:
            sent.append(text)
            return True

    import scripts.eod_summary as mod

    monkeypatch.setattr(mod.settings, "db_path", str(db_path))
    monkeypatch.setattr(mod.settings, "telegram_bot_token", "x")
    monkeypatch.setattr(mod.settings, "telegram_chat_id", "y")
    monkeypatch.setattr(mod, "build_notifier", lambda: _Notifier())
    monkeypatch.setattr(mod, "get_strategy_realized_pnl", lambda store, name: Decimal("11024.00"))

    rc = await mod.main()
    assert rc == 0
    assert sent, "no message sent"
    # get_strategy_realized_pnl's return (11,024), not the snapshot column (999,999).
    assert "+11,024" in sent[0]
    assert "999,999" not in sent[0]
