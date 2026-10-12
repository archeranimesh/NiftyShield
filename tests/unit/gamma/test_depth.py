"""Unit tests for DepthSource Protocol, DepthSnapshot, and NullDepth."""

import pytest

from src.gamma.depth import DepthSnapshot, DepthSource, NullDepth


def test_depth_snapshot_fields():
    snap = DepthSnapshot(
        bid_qty_l1=150,
        ask_qty_l1=300,
        total_bid_qty=1500,
        total_ask_qty=2250,
    )
    assert snap.bid_qty_l1 == 150
    assert snap.ask_qty_l1 == 300
    assert snap.total_bid_qty == 1500
    assert snap.total_ask_qty == 2250
    assert snap.timestamp is None


@pytest.mark.asyncio
async def test_null_depth_returns_none():
    null_depth = NullDepth()
    assert isinstance(null_depth, DepthSource)

    res = await null_depth.fetch("49081", "NSE_FNO")
    assert res is None

    res_default = await null_depth.fetch("49081")
    assert res_default is None
