# Audit Finding [13] Remediation: Async Telegram Notifications (Finalized)

Remediate the blocking `requests.post` call in `TelegramNotifier.send` by converting it to an asynchronous method using `aiohttp` with proper resource management, unified API call sites, and explicit dependency tracking.

## User Review Required

> [!IMPORTANT]
> This change introduces `aiohttp` as a production dependency. I will add it to `requirements.txt`. The implementation will use `aiohttp.ClientTimeout` as required by the library.

## Proposed Changes

### Dependencies

#### [MODIFY] [requirements.txt](file:///Users/abhadra/myWork/myCode/python/NiftyShield/requirements.txt)
- Add `aiohttp`.

### Notifications

#### [MODIFY] [telegram.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/notifications/telegram.py)
- Replace `import requests` with `import aiohttp`.
- Convert `send` to `async def send(self, text: str) -> bool`.
- **Timeout Handling:** Use `timeout = aiohttp.ClientTimeout(total=self._timeout)`.
- **Resource Management:** Use `async with aiohttp.ClientSession(timeout=timeout) as session:`.
- Perform the POST: `async with session.post(self._url, json=payload) as resp:`.
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
- Mock `post` on that session object to return a mock response context manager (`AsyncMock` for `__aenter__`).
- Mock `json()` and `raise_for_status()` on the mock response.

## Verification Plan

### Automated Tests
- Run `pip install aiohttp pytest-asyncio`.
- Run `python -m pytest tests/unit/test_notifications.py`.
- Run full suite: `python -m pytest tests/unit/ --tb=no -q`.

### Manual Verification
- Run `python -m scripts.send_test_telegram`.
