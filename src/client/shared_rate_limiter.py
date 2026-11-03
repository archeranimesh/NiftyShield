"""Cross-process Dhan call throttle.

Mechanism: a lock file taken with ``fcntl.flock`` plus a timestamp file, both
under one state directory. ``flock`` is released by the kernel when the holder
dies, so a crashed process can never wedge the lock (a leftover lock file with
no live holder is simply lockable). A PID-file or ``O_EXCL`` scheme was
rejected because it needs explicit stale-lock detection and can race on it.
"""

from __future__ import annotations

import asyncio
import fcntl
import os
from pathlib import Path

from src.client.dhan_market import Clock
from src.client.exceptions import DataFetchError

_LOCK_NAME = "dhan_throttle.lock"
_STAMP_NAME = "dhan_throttle.ts"


class SharedRateLimiter:
    """``RateLimiter`` whose last-call time is shared by every process.

    Satisfies the ``RateLimiter`` protocol in ``src.client.dhan_market``.
    """

    def __init__(
        self,
        state_dir: Path,
        spacing: float,
        clock: Clock,
        poll_s: float = 0.05,
        lock_timeout_s: float = 60.0,
    ) -> None:
        """Create the limiter.

        Args:
            state_dir: Directory holding the lock and timestamp files.
            spacing: Minimum seconds between grants, from
                ``market_data.chain.dhan_min_interval_s``.
            clock: Injected time source.
            poll_s: Sleep between non-blocking lock attempts.
            lock_timeout_s: Give up waiting for the lock after this long.

        Raises:
            ValueError: ``spacing`` is not positive.
        """
        if spacing <= 0:
            raise ValueError("spacing must be positive")
        self._spacing = spacing
        self._clock = clock
        self._poll_s = poll_s
        self._lock = asyncio.Lock()  # same-process callers queue here, not on the flock poll
        self._lock_timeout_s = lock_timeout_s
        state_dir.mkdir(parents=True, exist_ok=True)
        self._lock_path = state_dir / _LOCK_NAME
        self._stamp_path = state_dir / _STAMP_NAME

    async def acquire(self) -> None:
        """Wait until the floor has elapsed since any process's last grant.

        Raises:
            DataFetchError: The lock could not be taken within the timeout.
        """
        async with self._lock:
            fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR, 0o644)
            try:
                await self._take_lock(fd)
                now = self._clock.time()
                wait = self._spacing - (now - self._read_last())
                if wait > 0:
                    await self._clock.sleep(min(wait, self._spacing))
                self._write_last(self._clock.time())
            finally:
                os.close(fd)  # closing the fd also drops the flock

    async def _take_lock(self, fd: int) -> None:
        deadline = self._clock.time() + self._lock_timeout_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except BlockingIOError:
                if self._clock.time() >= deadline:
                    raise DataFetchError(
                        "timed out waiting for the shared Dhan throttle lock"
                    ) from None
                await self._clock.sleep(self._poll_s)

    def _read_last(self) -> float:
        try:
            return float(self._stamp_path.read_text().strip())
        except (OSError, ValueError):
            return -float("inf")

    def _write_last(self, value: float) -> None:
        tmp = self._stamp_path.with_suffix(".tmp")
        tmp.write_text(repr(value))
        os.replace(tmp, self._stamp_path)
