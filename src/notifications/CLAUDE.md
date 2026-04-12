# src/notifications — Module Context

> Auto-loaded when working inside `src/notifications/`. Read this before touching any file here.

---

## Non-Fatal Contract

The notifier **must never abort the cron job**. This is the core design constraint.

- `send()` catches all `Exception` broadly, logs `WARNING`, returns `False`. It never re-raises.
- The cron (`daily_snapshot.py`) wraps the `send()` call without a try/except — it relies entirely on `send()`'s own catch. Do not change `send()` to raise.

---

## `build_notifier()` Returns `None` When Unconfigured

```python
notifier = build_notifier()  # returns TelegramNotifier | None
if notifier:
    notifier.send(message)
```

`build_notifier()` checks for `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in the environment. If either is absent, returns `None`. Callers must guard with `if notifier:` — never assume it's configured.

---

## Message Format

- **Transport:** Raw `requests.post` to the Telegram Bot API `sendMessage` endpoint.
- **`parse_mode`:** `HTML` (not Markdown — Telegram's Markdown v1 is fragile with special chars).
- **Body format:** `<pre>` block for monospace alignment on mobile.

```python
# Canonical message structure
text = f"<pre>{summary_string}</pre>"
```

The `_format_combined_summary()` function in `daily_snapshot.py` produces the summary string. `send()` wraps it in `<pre>` tags before sending.

---

## Adding New Notifier Types

Follow the same pattern:
1. Constructor reads env vars, raises `ValueError` if misconfigured (caught by `build_notifier` equivalent)
2. `send(message: str) -> bool` — returns `True` on success, `False` on any failure (never raises)
3. Add a `build_<type>_notifier()` factory function that returns `None` when unconfigured
4. Callers guard with `if notifier:`

Do not make notifications blocking — fire-and-forget with a short timeout is preferred.
