# Audit Finding [13] Remediation: Async Telegram Notifications

Remediate the blocking `requests.post` call in `TelegramNotifier.send` by converting it to an asynchronous method using `aiohttp`.

## User Review Required

> [!IMPORTANT]
> This change converts a synchronous method `TelegramNotifier.send` to `async def send`. All callers must be updated to `await` this method. This is a breaking change for synchronous codebases, but the target callers (`daily_snapshot.py`) are already async-capable.

## Proposed Changes

### Notifications

#### [MODIFY] [telegram.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/notifications/telegram.py)
- Replace `requests` with `aiohttp`.
- Convert `send` to `async def send`.
- Implement non-blocking POST using `aiohttp.ClientSession`.

### Scripts

#### [MODIFY] [daily_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/daily_snapshot.py)
- Update `notifier.send()` call to `await notifier.send()`.

#### [MODIFY] [send_test_telegram.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/send_test_telegram.py)
- Wrap `notifier.send()` in `asyncio.run()`.

### Tests

#### [MODIFY] [test_notifications.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/tests/unit/test_notifications.py)
- Update tests to be async using `pytest.mark.asyncio`.
- Replace `requests.post` patching with `aiohttp.ClientSession.post` mocking.

## Verification Plan

### Automated Tests
- Run `python -m pytest tests/unit/test_notifications.py`
- Run `python -m pytest tests/unit/ --tb=no -q` (Full suite check)

### Manual Verification
- Run `python -m scripts.send_test_telegram` (requires environment variables, but tests cover the logic).
