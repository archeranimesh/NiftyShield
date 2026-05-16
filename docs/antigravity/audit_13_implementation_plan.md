# Audit Finding [13] Remediation: Async Telegram Notifications (Revised)

Remediate the blocking `requests.post` call in `TelegramNotifier.send` by converting it to an asynchronous method using `aiohttp` and unifying the API across all call sites.

## User Review Required

> [!IMPORTANT]
> This change converts `TelegramNotifier.send` to an `async` method. All four call sites in the repository will be updated. This includes fixing two scripts (`paper_track_snapshot.py` and `paper_3track_snapshot.py`) that are currently calling a non-existent `send_message()` method.

## Proposed Changes

### Notifications

#### [MODIFY] [telegram.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/notifications/telegram.py)
- Replace `requests` with `aiohttp` (imported inline to match `lookup.py` pattern or at module level).
- Convert `send` to `async def send(self, text: str) -> bool`.
- Use `aiohttp.ClientSession` for the POST request.
- Ensure the "Non-Fatal Contract" (catching all exceptions, returning `False`) is maintained in the async implementation.

#### [MODIFY] [CLAUDE.md](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/notifications/CLAUDE.md)
- Update **Transport** documentation from `requests.post` to `aiohttp`.
- Update code examples to show `await notifier.send(message)`.

### Scripts

#### [MODIFY] [daily_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/daily_snapshot.py)
- Update `notifier.send(summary_text)` to `await notifier.send(summary_text)`.

#### [MODIFY] [send_test_telegram.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/send_test_telegram.py)
- Wrap the single `notifier.send(message)` call in `asyncio.run()`. This preserves the script's synchronous structure while safely executing the now-async notification.

#### [MODIFY] [paper_track_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_track_snapshot.py)
- Rename the local `MockNotifier.send_message` to `send`.
- Update the `TelegramNotifier` call site from `await notifier.send_message(...)` to `await notifier.send(...)`.

#### [MODIFY] [paper_3track_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_snapshot.py)
- Update the `TelegramNotifier` call site from `await notifier.send_message(msg)` to `await notifier.send(msg)`.

### Tests

#### [MODIFY] [test_notifications.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/tests/unit/test_notifications.py)
- Mark tests with `@pytest.mark.asyncio`.
- Replace `requests.post` patching with `aiohttp.ClientSession.post` mocking (using `aresponses` or manual `AsyncMock` patching of `aiohttp`).

## Verification Plan

### Automated Tests
- Run `python -m pytest tests/unit/test_notifications.py`
- Run `python -m pytest tests/unit/ --tb=no -q`

### Manual Verification
- Run `python -m scripts.send_test_telegram` (verify `asyncio.run` integration).
