# src/notifications — Module Context

> Auto-loaded when working inside `src/notifications/`. Read this before touching any file here.
> Invariants and caller contracts only — history, worked examples, and the full per-formatter
> enumeration live in **`NOTES.md`** (same directory, not auto-loaded).

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
- **`parse_mode`:** `MarkdownV2`. `TelegramNotifier.send()` (`src/notifications/telegram.py`)
  and `TelegramGateway.send_notification` / `send_approval_request`
  (`src/notifications/telegram_gateway.py`) all send `parse_mode: MarkdownV2`.
- **`send()` does NOT auto-escape.** Every caller that interpolates a dynamic value, or writes
  static template prose containing MarkdownV2-reserved punctuation, is responsible for escaping
  it itself — see "Escaping Helpers (mandatory)" below. This is a deliberate design choice (not
  an oversight): auto-escaping inside `send()` would double-escape callers who already wrap a
  value in `mdcode()`.
- **No wrapping.** `send()` posts `text` exactly as authored — it does not wrap the body in
  `<pre>`, a code fence, or anything else. A caller that wants a monospace block emits its own
  ```` ``` ```` fence. (Migration history: `NOTES.md`.)
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
arrives. (Origin of this bug class: `NOTES.md`.)

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
does not escape literal backslashes in the input text.

**Guard test:** `tests/unit/notifications/test_escaping_guard.py` asserts every dynamic value
interpolated into a `send(`/`send_plain_message(`/`send_notification(` call site is escaped
upstream. Do not add a `_BASELINE_UNESCAPED` entry to silence a newly-introduced unescaped call
site — fix the call site instead. Allowlist mechanics and the audited-call-site history:
`NOTES.md`.

---

## Value Formatting & Table Builders — `src/notifications/formatting.py`

Canonical per-parameter-type rules live in root **`FORMATTING.md`**. Full signatures, examples,
and the rationale behind each rule: **`NOTES.md`**. The contracts that bind a caller:

- **Formatters return plain, unescaped text.** Callers still run the result through
  `mdcode()`/`escape_markdown()` per the escaping contract above before interpolating into a
  `send()` call. Formatters: `format_money` (rejects `float` with `TypeError`), `format_greek`
  (`"-"` for `None` — not-applicable, not zero), `format_strike` (`ValueError` on a
  non-whole-number), `format_pct` (`4` means 4%, not `0.04`).
- **Table builders never add their own fence** — `build_kv_table`,
  `build_side_by_side_kv_table`, `build_leg_table` all expect a caller-supplied
  ` ```fenced block``` `, which keeps them reusable for plain console output. All raise
  `ValueError` on empty rows/legs.
- **Widths are always computed from the actual content** (`max(len(x) for x in ...)`), never a
  hand-counted constant — that constant is the bug class that broke
  `build_comparison_report()`.
- **`build_leg_table` LTP/Entry columns are 1dp, not `format_money`'s 2dp** — a locked-in
  exception (`FORMATTING.md` §3) to fit a narrow mobile screen. Do not "fix" it into a
  `format_money()` call.
- **`strategy_label()` / `leg_role_label()` / `strategy_short_label()` raise `ValueError` on
  an unmapped id** — never a fallback to the raw id. Extend the dict when a new caller needs
  one. `strategy_short_label()` returns the compact all-caps header token (`PROXY` /
  `FUTURES` / `SPOT`), distinct from `strategy_label()`'s fuller "Proxy Track" form.

Tests: `tests/unit/notifications/test_formatting.py`.

---

## Message Construction Patterns

Two canonical shapes for building a full message body from a typed input, both reusable and
transport-agnostic (return a string, never call `send()` themselves):

- **`_format_combined_summary()`** (`src/portfolio/formatting.py`) — the portfolio EOD summary.
- **`entry_message.py`** — `EntryMessage` dataclass + `format_entry_message()` renders a
  strategy-agnostic entry confirmation (`headline_label` picks the strategy — IC v1/v2, CSP,
  CC, Collar, PP, three-track bootstrap, …) as a headline + optional `*Mode:*` line + kv row +
  fenced `build_leg_table()` block + net line. `ivr` / `mode` / `expiry_type` are optional; the
  kv row omits `IVR:` when `ivr is None`. Each dynamic value is `escape_markdown()`'d
  individually; the fence is emitted literally. ROLL-17, generalized UEM-1. UEM-2 wired
  `record_paper_trade.py --notify` to emit a one-leg CSP / CC card on a successful open via
  `TelegramNotifier` (`headline_label` / `role` derived from `--strategy` and option type);
  silent no-op on close / roll. **The net line is sign-aware (OEM-1):** `net_credit < 0` renders
  `💰 *Net debit:*` with the absolute value and the label flipped; positive / zero is
  byte-identical to the original credit-only line. OEM-2 wired a successful automated
  `CollarOverlayV1._reenter_collar` re-entry onto the shared card (non-fatal); OEM-4 migrated
  the three-track bootstrap message (`paper_3track_overlay_entry.py`, CC / PP / Collar) onto it
  too, with the `⚠️ Gate Logged` line appended by the caller after the rendered card.
- **`exit_message.py`** — `ExitMessage` dataclass + `format_exit_message()` renders a
  strategy-agnostic close card: Act/Instrument/Entry/Exit/P&L leg table + a three-level P&L
  footer (this-exit / cycle / inception), rows collapsing when this-exit == cycle. The
  **inception** number is `get_strategy_realized_pnl(store, ...)` — authoritative, store-derived
  — never the summed cycle P&L, which is only an approximation. Win-rate + avg-decay-% (from
  `cycle_stats`) appear only when `closed_count >= 5`. IC v1/v2, CSP, CC, PP, and Collar all
  route through this one renderer (UXM-1..6), including the `auto_close.py` daemon paths.

A new multi-line message that interpolates several typed values follows this pattern — a
builder function taking one dataclass — rather than a hand-rolled f-string at the call site.

The S9 "NiftyBees vs overlays" recovery digest (`_build_recovery_digest`,
`scripts/strategies/three_track/paper_3track_snapshot.py`) is not a renderer-lineage caller —
it builds its own single MarkdownV2 fenced block (ORD-3, matching the `pre_market_brief.py`
house style) rather than going through `entry_message.py` / `exit_message.py`, since it has no
leg table or P&L footer shape in common with either. `_overlay_type_groups` always emits a
standalone `cc` `OverlayPnLSnapshot` alongside `collar` (BUG-044 fix, ORD-2) — never merge a
standalone CC bootstrap into the collar total.

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

---

## Adding New Notifier Types

Follow the same pattern:
1. Constructor reads env vars, raises `ValueError` if misconfigured (caught by `build_notifier` equivalent)
2. `async send(message: str) -> bool` — returns `True` on success, `False` on any failure (never raises)
3. Add a `build_<type>_notifier()` factory function that returns `None` when unconfigured
4. Callers guard with `if notifier:`

Do not make notifications blocking — fire-and-forget with a short timeout is preferred.
