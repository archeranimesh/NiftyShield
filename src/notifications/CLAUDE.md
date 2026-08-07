# src/notifications — Module Context

> Auto-loaded when working inside `src/notifications/`. Read this before touching any file here.

---

## Non-Fatal Contract

The notifier **must never abort the cron job**. This is the core design constraint.

- `send()` catches all `Exception` broadly, logs `WARNING`, returns `False`. It never re-raises.
- The cron (`daily_snapshot.py`) wraps the `send()` call without a try/except — it relies entirely on `send()`'s own catch. Do not change `send()` to raise.
- Per REVIEW.md G5: this broad catch must carry an inline comment stating it is an intentional isolation point (e.g. `except Exception:  # Intentional: notifier must never abort the caller`) — a bare broad catch without that comment is a `CRITICAL` finding even here.

---

## `build_notifier()` Returns `None` When Unconfigured

```python
notifier = build_notifier()  # returns TelegramNotifier | None
if notifier:
    await notifier.send(message)
```

`build_notifier()` checks for `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in the environment. If either is absent, returns `None`. Callers must guard with `if notifier:` — never assume it's configured.

`TELEGRAM_MESSAGE_BUDGET` (default `10`) caps the total messages a single notifier instance will send per process lifetime. Increment before the HTTP call, so network timeouts still burn a slot (prevents rapid retry loops). Raise the budget via env var for long-lived processes like `intraday_tracker.py`; set to `0` to silence all notifications.

---

## Message Format

- **Transport:** Raw `aiohttp` POST to the Telegram Bot API `sendMessage` endpoint.
- **`parse_mode`:** `HTML` (not Markdown — Telegram's Markdown v1 is fragile with special chars).
- **Body format:** `<pre>` block for monospace alignment on mobile.

```python
# Canonical message structure
text = f"<pre>{summary_string}</pre>"
```

The `_format_combined_summary()` function in `daily_snapshot.py` produces the summary string. `send()` wraps it in `<pre>` tags before sending.

---

## Instrument Label Formatting

Any Telegram or log message that names an option leg in prose must use
`format_leg_label(instrument_key, lookup)` (`src/instruments/lookup.py`) when only the
raw key is on hand, or `format_option_label(underlying, strike, option_type, expiry)`
when strike/type/expiry are already resolved (e.g. from a live chain scan). Never
interpolate a raw Upstox `instrument_key` (e.g. `NSE_FO|65900`) or a hand-rolled
`f"{strike}{side}"` string into message text.

**Exception — CLI commands:** literal commands meant to be copy-pasted and executed
(e.g. `record_paper_trade.py --key NSE_FO|...`) always keep the raw `instrument_key`
verbatim. The formatting rule applies to prose only, never to command arguments.

**Fallback:** unresolvable keys degrade to the raw key + logged WARNING, never raise —
consistent with this module's non-fatal contract above.

Origin: `docs/plan/telegram-leg-labels/` — raw `NSE_FO|65900` shown in an AUTO-CLOSE
Telegram alert with no way to identify the strike.

---

## Adding New Notifier Types

Follow the same pattern:
1. Constructor reads env vars, raises `ValueError` if misconfigured (caught by `build_notifier` equivalent)
2. `async send(message: str) -> bool` — returns `True` on success, `False` on any failure (never raises)
3. Add a `build_<type>_notifier()` factory function that returns `None` when unconfigured
4. Callers guard with `if notifier:`

Do not make notifications blocking — fire-and-forget with a short timeout is preferred.
