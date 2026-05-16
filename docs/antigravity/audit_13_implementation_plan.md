# Audit Finding [13] Remediation: Async Telegram Notifications (Final)

Remediate the blocking `requests.post` call in `TelegramNotifier.send` by converting it to an asynchronous method using `aiohttp` with proper resource management and unified API call sites.

## User Review Required

> [!IMPORTANT]
> This change converts `TelegramNotifier.send` to an `async` method. All four call sites in the repository will be updated. `pytest-asyncio` is required for testing; I will verify its installation (as it is listed in `requirements-dev.txt`) before running tests.

## Proposed Changes

### Notifications

#### [MODIFY] [telegram.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/notifications/telegram.py)
- Replace `requests` with `aiohttp` (imported at module level).
- Convert `send` to `async def send(self, text: str) -> bool`.
- **Resource Management:** Use `async with aiohttp.ClientSession(timeout=timeout) as session:` inside `send()` to ensure the session is closed after the request.
- Use `await session.post(self._url, json=payload)` for the request.
- Maintain the non-fatal contract: catch `Exception` and return `False`.

#### [MODIFY] [CLAUDE.md](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/notifications/CLAUDE.md)
- Update **Transport** documentation to `aiohttp` with `async with` session management.
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
- Mark tests with `@pytest.mark.asyncio`.
- Replace `requests.post` patching with `unittest.mock.patch("aiohttp.ClientSession.post", new_callable=AsyncMock)`.
- Verify response handling for `ok=True/False` using `AsyncMock` to simulate `resp.json()` and `resp.raise_for_status()`.

## Verification Plan

### Automated Tests
- Confirm `pytest-asyncio` is installed: `pip install pytest-asyncio` (if missing).
- Run `python -m pytest tests/unit/test_notifications.py`.
- Run full suite: `python -m pytest tests/unit/ --tb=no -q`.

### Manual Verification
- Run `python -m scripts.send_test_telegram`.
