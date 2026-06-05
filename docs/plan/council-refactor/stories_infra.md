# council-refactor — Infrastructure Stories

> Shared context and signal tables: `README.md`

---

## CR0 `[Claude]` — Fix `send_approval_request` signature mismatch ✅ SHA: 4ce6d99

**Files:** `src/strategy/monitor.py`, `src/notifications/telegram_gateway.py`,
`tests/unit/notifications/test_telegram_gateway.py`,
`tests/unit/strategy/test_strategy_monitor.py`

**The bug:**

`monitor.py` calls:
```python
await self._notifier.send_approval_request(event, context_str)
```

`telegram_gateway.py` signature was:
```python
async def send_approval_request(self, council_output: CouncilOutput, event: SignalEvent, strategy_name: str)
```

This was a `TypeError` at runtime whenever any ACTION event fired.

**What was changed:**

Refactored `TelegramGateway.send_approval_request` to:
```python
async def send_approval_request(
    self,
    event: SignalEvent,
    context_str: str,
    action_options: list[str],
) -> int | None:
```

Removed `CouncilOutput` import and parameter entirely.

`pending_approvals.council_output` column renamed to `action_options_json`.
`PaperStore.create_approval` stores `json.dumps(action_options)`.
`on_approved` callback in `monitor_daemon.py` reads `action_options_json`,
picks `action_options[rank]`, builds `ApprovedAction` directly.

**Commit:** `fix(strategy): remove CouncilOutput from approval flow; fix send_approval_request signature`
