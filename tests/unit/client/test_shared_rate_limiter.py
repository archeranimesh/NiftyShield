"""Offline tests for the cross-process Dhan throttle."""

from __future__ import annotations

import asyncio
import fcntl
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.client.dhan_market import SpacingRateLimiter
from src.client.exceptions import DataFetchError
from src.client.factory import create_dhan_rate_limiter
from src.client.shared_rate_limiter import SharedRateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


async def test_two_instances_respect_the_floor(tmp_path: Path) -> None:
    clock = FakeClock()
    a = SharedRateLimiter(tmp_path, 4.0, clock)
    b = SharedRateLimiter(tmp_path, 4.0, clock)
    grants: list[float] = []
    for limiter in (a, b, a, b, b):
        await limiter.acquire()
        grants.append(clock.time())
    gaps = [y - x for x, y in zip(grants, grants[1:], strict=False)]
    assert all(g >= 4.0 for g in gaps)


async def test_concurrent_callers_respect_the_floor(tmp_path: Path) -> None:
    clock = FakeClock()
    limiter = SharedRateLimiter(tmp_path, 4.0, clock)
    grants: list[float] = []

    async def one() -> None:
        await limiter.acquire()
        grants.append(clock.time())

    await asyncio.gather(one(), one(), one())
    assert all(b - a >= 4.0 for a, b in zip(grants, grants[1:], strict=False))


async def test_first_call_does_not_wait(tmp_path: Path) -> None:
    clock = FakeClock()
    await SharedRateLimiter(tmp_path, 4.0, clock).acquire()
    assert clock.sleeps == []


async def test_stale_lock_is_recovered(tmp_path: Path) -> None:
    code = (
        "import fcntl, os, sys;"
        "fd = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR);"
        "fcntl.flock(fd, fcntl.LOCK_EX);"
        "os._exit(0)"
    )
    subprocess.run([sys.executable, "-c", code, str(tmp_path / "dhan_throttle.lock")], check=True)
    assert (tmp_path / "dhan_throttle.lock").exists()
    clock = FakeClock()
    await SharedRateLimiter(tmp_path, 4.0, clock).acquire()
    assert clock.sleeps == []


async def test_live_holder_times_out(tmp_path: Path) -> None:
    fd = os.open(tmp_path / "dhan_throttle.lock", os.O_CREAT | os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        limiter = SharedRateLimiter(tmp_path, 4.0, FakeClock(), lock_timeout_s=1.0)
        with pytest.raises(DataFetchError):
            await limiter.acquire()
    finally:
        os.close(fd)


async def test_corrupt_timestamp_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "dhan_throttle.ts").write_text("garbage")
    clock = FakeClock()
    await SharedRateLimiter(tmp_path, 4.0, clock).acquire()
    assert clock.sleeps == []


async def test_future_timestamp_waits_at_most_one_floor(tmp_path: Path) -> None:
    (tmp_path / "dhan_throttle.ts").write_text(repr(1_000_000.0))
    clock = FakeClock()
    await SharedRateLimiter(tmp_path, 4.0, clock).acquire()
    assert clock.sleeps == [4.0]


def test_non_positive_spacing_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        SharedRateLimiter(tmp_path, 0, FakeClock())


def test_factory_default_is_in_process() -> None:
    limiter = create_dhan_rate_limiter(FakeClock())
    assert isinstance(limiter, SpacingRateLimiter)


def test_factory_with_state_dir_is_shared(tmp_path: Path) -> None:
    limiter = create_dhan_rate_limiter(FakeClock(), state_dir=tmp_path)
    assert isinstance(limiter, SharedRateLimiter)


def test_factory_spacing_error_propagates(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        create_dhan_rate_limiter(FakeClock(), state_dir=tmp_path, spacing=-1)
