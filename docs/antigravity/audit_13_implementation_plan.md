# Audit Finding [13] Remediation: Async Telegram Notifications (Finalized v2)

Remediate the blocking `requests.post` call in `TelegramNotifier.send` by converting it to an asynchronous method using `aiohttp` with proper resource management, explicitly awaited JSON parsing, unified API call sites, and pinned dependency tracking.

## User Review Required

> [!IMPORTANT]
> This change introduces `aiohttp==3.10.5` as a production dependency. `resp.json()` in `aiohttp` is a coroutine and will be explicitly awaited. Mocking in tests will use `AsyncMock` for `resp.json()`.

## Proposed Changes

### Dependencies

#### [MODIFY] [requirements.txt](file:///Users/abhadra/myWork/myCode/python/NiftyShield/requirements.txt)
- Add `aiohttp==3.10.5`.

### Notifications

#### [MODIFY] [telegram.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/notifications/telegram.py)
- Replace `import requests` with `import aiohttp`.
- Convert `send` to `async def send(self, text: str) -> bool`.
- **Timeout Handling:** Use `timeout = aiohttp.ClientTimeout(total=self._timeout)`.
- **Resource Management:** Use `async with aiohttp.ClientSession(timeout=timeout) as session:`.
- **Request & Parsing:** 
  - `async with session.post(self._url, json=payload) as resp:`.
  - `resp.raise_for_status()`.
  - `data = await resp.json()`.
- Maintain the non-fatal contract: catch `Exception`, log warning, and return `False`.

#### [MODIFY] [CLAUDE.md](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/notifications/CLAUDE.md)
- Update **Transport** documentation to `aiohttp` with `ClientTimeout` and `async with` session management.
- Update code examples to show `await notifier.send(message)`.

### Scripts

#### [MODIFY] [daily_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/daily_snapshot.py)
- Update `notifier.send(summary_text)` to `await notifier.send(summary_text)`.

#### [MODIFY] [send_test_telegram.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/send_test_telegram.py)
- Update to `import asyncio` and wrap the `notifier.send(message)` call in `asyncio.run()`.

#### [MODIFY] [paper_track_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_track_snapshot.py)
- Rename `MockNotifier.send_message` to `send`.
- Update call site from `await notifier.send_message(...)` to `await notifier.send(...)`.

#### [MODIFY] [paper_3track_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_snapshot.py)
- Update call site from `await notifier.send_message(msg)` to `await notifier.send(msg)`.

### Tests

#### [MODIFY] [test_notifications.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/tests/unit/test_notifications.py)
- Remove `import requests`.
- Convert all test functions to `async def test_*`.
- **Mock Strategy:** Patch `aiohttp.ClientSession` directly.
- Mock `__aenter__` on the `ClientSession` mock to return a mock session object.
- Mock `post` on that session object to return a mock response context manager.
- **Async Parsing Mock:** Mock `json()` as an `AsyncMock` to verify `await resp.json()`. Mock `raise_for_status()` as a plain `MagicMock` (synchronous in aiohttp).

## Verification Plan

### Automated Tests
- Run `pip install aiohttp==3.10.5 pytest-asyncio`.
- Run `python -m pytest tests/unit/test_notifications.py`.
- Run full suite: `python -m pytest tests/unit/ --tb=no -q`.

### Manual Verification
- Run `python -m scripts.send_test_telegram`.
