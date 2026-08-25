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
- **`parse_mode`:** `MarkdownV2` (migrated from HTML — `docs/plan/telegram-markdown-migration/`,
  MD-1 through MD-7.3, completed 2026-08-25). `TelegramNotifier.send()`
  (`src/notifications/telegram.py`) and `TelegramGateway.send_notification` /
  `send_approval_request` (`src/notifications/telegram_gateway.py`) all send `parse_mode:
  MarkdownV2`.
- **`send()` does NOT auto-escape.** Every caller that interpolates a dynamic value, or writes
  static template prose containing MarkdownV2-reserved punctuation, is responsible for escaping
  it itself — see "Escaping Helpers (mandatory)" below. This is a deliberate design choice (not
  an oversight): auto-escaping inside `send()` would double-escape callers who already wrap a
  value in `mdcode()`.
- **No wrapping.** `send()` posts `text` exactly as authored — it does not wrap the body in
  `<pre>`, a code fence, or anything else. A caller that wants a monospace block emits its own
  ```` ``` ```` fence. (This paragraph previously described an HTML `<pre>` wrap that
  `TelegramNotifier.send()` performed under the old parse_mode; that wrap was removed with the
  MarkdownV2 migration and the description was left behind — corrected 2026-08-25, FMT-1.)
- **Value formatting:** how a money figure, Greek, strike, percentage, expiry, or fenced table is
  rendered is not this module's call to make ad hoc — see **`FORMATTING.md`** (project root) for
  the canonical per-parameter-type rules, the context-override registry, and the
  formatter-returns-unescaped contract that pairs with the escaping helpers below.

---

## Escaping Helpers (mandatory) — `src/notifications/markdown.py`

MarkdownV2 reserves 18 characters outside a code span: `` _*[]()~`>#+-=|{}.! ``. Any of these
appearing unescaped in plain text either opens an unintended formatting entity or causes the
send to be rejected outright with a 400 ("can't parse entities") — silently swallowed by the
non-fatal `send()` contract above, so a bad message doesn't crash the caller, it just never
arrives. This was the original `DELTA_WARN` bug class that motivated the whole migration
(`docs/plan/telegram-markdown-migration/`).

Two helpers, both in `src/notifications/markdown.py`:

- **`mdcode(value: str) -> str`** — wraps a dynamic value as an inline code span
  (`` `value` ``). Preferred for anything that's conceptually an identifier (strategy_id, signal
  code, instrument key, error message) — Telegram never parses entities inside a code span, so
  any reserved character inside is inert regardless of count/balance. Falls back to
  `escape_markdown()` internally if `value` itself contains a literal backtick or backslash
  (nesting code spans isn't possible).
- **`escape_markdown(text: str) -> str`** — backslash-escapes every reserved character.
  Use for free-form prose that must render visually plain (not code-styled), and for static
  template punctuation (MarkdownV2's reserved set includes `.`, `(`, `)`, `-` — ordinary prose
  punctuation, not just markup characters, so hand-written template strings need this too, not
  only interpolated values).

**Known limitation (not fixed, tracked in `docs/bugs/bugs.md` BUG-038):** `escape_markdown()`
does not escape literal backslashes in the input text — pre-existing gap in the MD-1 helper,
surfaced during MD-7.3's review, out of scope for that escaping-only task.

**Guard test:** `tests/unit/notifications/test_escaping_guard.py` (added MD-6, SHA `ce95bbd`)
statically walks `src/`/`scripts/` for `notifier.send(`/`send_plain_message(`/
`send_notification(` call sites and asserts every interpolated dynamic value is escaped via
`escape_markdown()`/`mdcode()` somewhere upstream. Pre-existing unescaped call sites that
predate the guard are tracked individually in its `_BASELINE_UNESCAPED` allowlist with a reason
string per entry — do not add a new entry to silence a newly-introduced unescaped call site;
fix the call site instead. Remove a call site's baseline entry in the same commit that fixes it
(`test_baseline_entries_are_still_unescaped` / `test_baseline_has_no_duplicate_or_unused_entries`
enforce this). Confirmed permanent won't-fix baseline entry: `scripts/dev/send_test_telegram.py`
(manual dev/debug utility, not a cron or strategy event path — Animesh, 2026-08-25).

All currently-known production call sites were audited and fixed under this epic (MD-3, MD-4.1–
4.3, MD-7.1–7.3): strategy close/roll notifications, the three reporting builders, both IC
entry-signal scripts (`send_notification` + `_gate_alert` paths), `pre_market_brief.py`,
`auto_close.py`, and `overlay_closer.py`. Any new `.send()`/`.send_plain_message()`/
`.send_notification()` call site added after 2026-08-25 is caught by the guard test at commit
time, not audited retroactively.

---

## Value Formatting & Table Builders — `src/notifications/formatting.py`

Canonical per-parameter-type rules live in root **`FORMATTING.md`** — this section is the
module-level pointer to the code that implements them (formatting-rules epic, FMT-1..FMT-4,
`docs/plan/telegram-markdown-migration/formatting-rules/`).

**Value formatters** (all return plain, unescaped text — callers still run the result through
`mdcode()`/`escape_markdown()` per the contract above before interpolating into a `send()` call):

- **`format_money(value: Decimal) -> str`** — 2dp, comma thousands, `₹` prefix, sign before `₹`
  on negatives. Rejects `float` with `TypeError` — never silently coerces. `Decimal("82628")` ->
  `"₹82,628.00"`, `Decimal("-11.08")` -> `"-₹11.08"`.
- **`format_greek(value: float | None, *, width: int | None = None) -> str`** — 2dp, always
  signed, `"-"` placeholder for `None` (not-applicable, not zero). `0.28` -> `"+0.28"`. `width`
  right-aligns for `build_leg_table`'s reuse.
- **`format_strike(value: float | int) -> str`** — integer string, no decimal, no thousands
  separator (an identifier, not a quantity). Raises `ValueError` on a non-whole-number input.
- **`format_pct(value: float) -> str`** — 1dp; whole-number inputs print bare (`4` -> `"4%"`,
  not `"4.0%"`). `value` is a plain percentage number, `4` means 4%, not `0.04`.

**Table builders** (all wrap in a caller-supplied ` ```fenced block``` ` — none of these add
the fence themselves, so they stay reusable for plain console output too):

- **`build_kv_table(title, rows: list[tuple[str, str]]) -> str`** — bordered two-column
  label/value table. Width is always computed from the actual content
  (`max(len(x) for x in ...)`), never a hand-counted constant — this is the exact bug class
  that broke `build_comparison_report()`'s original fixed 20-char budget (see
  `formatting-rules/prompt.md`). Raises `ValueError` on empty `rows` — a titled table with
  nothing to show is a caller bug, not a valid empty table.
- **`build_side_by_side_kv_table(title_a, rows_a, title_b, rows_b) -> str`** — two `build_kv_table`
  outputs joined with `" | "`, shorter side blank-padded to stay aligned when row counts differ
  (the real Snapshot/P&L comparison case). Built on top of `build_kv_table` rather than
  reimplementing its width/border logic.
- **`build_leg_table(legs: list[LegRow]) -> str`** — position table: `[S]`/`[B]` badge (from
  whether `LegRow.role` starts with `"Short"`/`"Long"`), instrument, Δ, LTP, entry. LTP/Entry
  columns use a local 1dp format, **not** `format_money`'s 2dp — a locked-in exception (see
  `FORMATTING.md` §3) to fit numeric columns on a narrow mobile screen inside a fenced block; do
  not "fix" this into a `format_money()` call. Raises `ValueError` on empty `legs`.
- **`LegRow`** (frozen dataclass) — one input row for `build_leg_table`: `role`, `instrument`
  (pre-formatted, e.g. `"23000 PE"`), `delta: float | None`, `ltp: float`, `entry: float | None`.

**Known risk, not yet guarded in code:** any Unicode symbol with an emoji-presentation variant
(not just literal emoji) renders double-width on Telegram even inside a monospace fence and can
break column alignment — e.g. `▶`. Extends the emoji-breaks-alignment warning above from
literal emoji to that wider glyph class. See `FORMATTING.md` (FMT-1e).

Tests: `tests/unit/notifications/test_formatting.py`.

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
