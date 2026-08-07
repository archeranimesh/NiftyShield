# Telegram Leg Labels — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Origin: `AUTO-CLOSE FAILED` alert showed raw `NSE_FO|65900` instead of a readable strike/type/expiry.

---

## TL-1 — Canonical Formatter in `src/instruments/lookup.py`

**Context:** Upstox instrument keys are opaque numeric tokens (`NSE_FO|65900`) — no
strike/expiry/type can be regex'd out of them. The offline BOD JSON (already loaded via
`InstrumentLookup`) is the only source of truth for those fields, and `format_results()`
already proves the field names: `trading_symbol`, `instrument_type` (`CE`/`PE`),
`strike_price`, `expiry`, `segment`.

**Files to change:**
- `src/instruments/lookup.py` — add two functions
- `tests/unit/instruments/test_lookup.py` — add tests

**Before any code:**
```
get_code_snippet("InstrumentLookup.get_by_key")   # exact current signature/behavior
get_code_snippet("format_results")                # confirm field names + parse_expiry usage
search_code("parse_expiry")                       # existing expiry-formatting helper, reuse it
git log --oneline -10 src/instruments/lookup.py
```

**Functions to add:**

```python
def format_option_label(
    underlying: str, strike: float, option_type: str, expiry: str | date
) -> str:
    """Human-readable option label, e.g. 'NIFTY 22000 CE 07 JUL 26'.

    Args:
        underlying: Underlying symbol, e.g. 'NIFTY'.
        strike: Strike price (formatted with no decimal places).
        option_type: 'CE' or 'PE'.
        expiry: Expiry as 'YYYY-MM-DD' string or date object.

    Returns:
        Formatted label string. Never raises — malformed expiry falls back to the raw
        expiry value rendered as-is.
    """


def format_leg_label(instrument_key: str, lookup: "InstrumentLookup") -> str:
    """Resolve instrument_key via the BOD lookup and format as a human label.

    Args:
        instrument_key: Raw Upstox instrument key, e.g. 'NSE_FO|65900'.
        lookup: InstrumentLookup instance to resolve against.

    Returns:
        `format_option_label(...)` output on successful resolution. Falls back to the
        raw `instrument_key` string (logged WARNING, never raises) when the key is not
        found in the BOD JSON or resolves to a non-option instrument (FUT/EQ) — those
        callers should not have routed through this helper, but it must degrade safely
        rather than crash a notification path.
    """
```

`format_option_label` strike formatting: `int(strike)` if it's a whole number (options
strikes always are), never show `.0` — output `22000` not `22000.0`. Expiry formatting:
reuse `parse_expiry()` to normalize to a `date`, then `date.strftime("%d %b %y").upper()`
→ `07 JUL 26`.

**Tests:**
- `test_format_option_label_happy` — `format_option_label("NIFTY", 22000, "CE", "2026-07-07")` → `"NIFTY 22000 CE 07 JUL 26"`
- `test_format_option_label_date_object` — same but `expiry=date(2026, 7, 7)`
- `test_format_leg_label_resolves_from_bod` — mock lookup returns a matching instrument dict → correct label
- `test_format_leg_label_unresolvable_key_falls_back` — `get_by_key` returns `None` → returns raw `instrument_key`, logs WARNING (assert via `caplog`/structlog capture, not raise)
- `test_format_leg_label_non_option_instrument_falls_back` — resolved dict has `instrument_type="FUT"` → falls back to raw key (never mis-formats a future as an option)

**Commit:** `feat(instruments): format_option_label + format_leg_label for Telegram messages`

---

## TL-2 — Wire Into Overlay Close Notifications

**Context:** Four `_send_close_notification` methods currently interpolate `leg['key']`
(the raw instrument_key) directly into the Telegram message body. Each of these methods
already has access to a `PaperStore`-backed leg dict and, transitively, an
`InstrumentLookup` (constructed the same way `PaperPosition.option_type` resolution
already does — do not build a second BOD-loading path; reuse the existing
`instrument_lookup` construction pattern in the module/class you're editing).

**Files to change:**
- `src/strategy/auto_close.py` — `_send_close_notification`
- `src/strategy/cc_overlay_v1.py` — `CCOverlayV1._send_close_notification`
- `src/strategy/collar_overlay_v1.py` — `CollarOverlayV1._send_close_notification`
- `src/strategy/pp_overlay_v1.py` — `PPOverlayV1._send_close_notification`
- Corresponding test files: `tests/unit/strategy/test_auto_close.py`,
  `test_cc_overlay_v1.py`, `test_collar_overlay_v1.py`, `test_pp_overlay_v1.py`

**Before any code:**
```
get_code_snippet("_send_close_notification")   # returns all 4 — read each
search_code("instrument_lookup")               # find the existing construction pattern to reuse
git log --oneline -10 src/strategy/auto_close.py
```

**Change:** everywhere the message body does `f"...{leg['key']}..."` (or `call_leg['key']`
/ `put_leg['key']`), replace with `format_leg_label(leg['key'], lookup)`. Do **not** change
the dict key names (`leg['key']` stays `leg['key']` in code — only the interpolated
*display value* changes). Do not touch anything outside the f-string message body — P&L
math, `store` calls, and control flow are unaffected.

**Tests:** for each of the 4 files, update (not duplicate) the existing
`_send_close_notification` test(s) to assert the message contains the formatted label
(e.g. `"NIFTY 22000 CE"` substring) instead of the raw instrument key. Add one new test per
file for the fallback path (unresolvable key → raw key still appears, notification still
sends — non-fatal contract preserved).

**Commit:** `feat(strategy): overlay close notifications use human-readable option labels`

---

## TL-3 — Wire Into IC Entry Preview Message (Not Commands)

**Context:** `scripts/strategies/ic/paper_ic_entry.py::run()` builds a Telegram preview
message (`short_put`/`short_call` δ/mid lines) directly from chain-scan dicts that already
carry `strike` and implicit side (`PE`/`CE`) — no `instrument_key` resolution needed here,
just the same output format as TL-1/TL-2 for consistency. Separately, the same function
builds `cmds` (the literal `record_paper_trade.py --key NSE_FO|... ` command list) —
**that block must not change** since it's copy-pasted and executed verbatim.

**Files to change:**
- `scripts/strategies/ic/paper_ic_entry.py` — message-text lines only (search for the
  f-string(s) containing `int(short_put['strike'])` / `int(short_call['strike'])`)
- `tests/unit/strategies/ic/test_paper_ic_entry.py` — add/update tests

**Before any code:**
```
search_code("Short Put")                      # locate exact message-building lines
get_code_snippet("run")                       # scripts.strategies.ic.paper_ic_entry.run — confirm cmds block boundary
git log --oneline -10 scripts/strategies/ic/paper_ic_entry.py
```

**Change:** replace ad hoc `f"Short Put  {int(short_put['strike'])}PE  "`-style
construction with `format_option_label("NIFTY", short_put["strike"], "PE", expiry_str)`
(same for the call leg). Do not touch the `cmds` list, the `subprocess.run` call, or any
line inside the `for role, action, key, price in legs:` loop that builds `cmd = [...]`.

**Bug fix bundled into this task:** the long-leg lines (currently `f"Long Put
{int(long_put_strike)}PE   (hedge)\n"` / `f"Long Call  {int(long_call_strike)}CE  (hedge)\n"`,
around line 559/562) omit the mid price even though `long_put["mid"]` / `long_call["mid"]`
are already fetched (line 422–423) and used in the `net_credit` calc (line 552) — they're
just never interpolated into the message text. Add `mid=₹{long_put['mid']:.2f}` /
`mid=₹{long_call['mid']:.2f}` to those two lines, same style as the short-leg lines, while
converting them to `format_option_label(...)`.

**Tests:**
- `test_entry_preview_message_uses_readable_label` — assert the Telegram preview text
  contains `"NIFTY 23800 PE"`-style label, not `"23800PE"`
- `test_entry_preview_message_shows_long_leg_mid` — assert both long-leg lines contain
  `mid=₹` followed by `long_put["mid"]` / `long_call["mid"]` formatted to 2dp (regression
  guard for the currently-missing hedge-leg mid price)
- `test_entry_command_block_unchanged` — assert the printed/executed command strings
  still contain the raw `--key NSE_FO|...` value verbatim (regression guard so a future
  edit doesn't accidentally reformat the command block too)

**Commit:** `feat(ic): entry preview message uses uniform human-readable option label`

---

## TL-4 — Fold Standard Into Existing Docs (no new files)

**Context:** Without a written-down standard, this convention only lives in code — the
failure mode `LOGGING.md` was written to prevent for logging (see `BUG-010`). Nothing
currently tells a future session, working on a fifth notification builder six months from
now, that `format_leg_label`/`format_option_label` exist and must be used instead of
interpolating a raw `instrument_key`. Per explicit direction: do **not** create a new
standalone markdown file for this — fold the standard into `src/notifications/CLAUDE.md`,
which already auto-loads whenever `src/notifications/` is touched and already documents
the adjacent non-fatal contract + HTML `parse_mode` rules. Then add one pointer row to the
existing "Load additional files when relevant" table in root `CLAUDE.md` — no new doc, a
new *trigger row* referencing a file that already exists.

**Files to change (both existing, targeted `Edit` only — never `Write`):**
- `src/notifications/CLAUDE.md` — add a new section
- `CLAUDE.md` (project root) — add one row to the existing "Additional files to read when
  relevant" list (same table that already has the `LOGGING.md` row)

**`src/notifications/CLAUDE.md` — new section to add** (place after "Message Format",
before "Adding New Notifier Types" — same file structure it already has):
```
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
```

**Root `CLAUDE.md` — trigger row to add** (in the "Load additional files when relevant"
list, immediately after the existing `LOGGING.md` row):
```
- Building or editing any Telegram/notification message text (strategy close/roll/entry
  alerts, gate-violation alerts) → also read `src/notifications/CLAUDE.md` §"Instrument
  Label Formatting" — canonical instrument-label formatting rule
```

**Verify (no code, docs only):**
- `src/notifications/CLAUDE.md` has the new section, in the existing section order
- Root `CLAUDE.md`'s "Additional files to read when relevant" table has the new row
- No new files created anywhere in the repo for this task

**Commit:** `docs: instrument-label formatting standard folded into notifications CLAUDE.md`

---

## TL-5 — Docs Close

**Goal:** Confirm docs updated, add TODOS.md session log line. No further code changes.

**Verify:**
- `CONTEXT.md` — add one clause to the `src/instruments/lookup.py` line noting
  `format_option_label`/`format_leg_label` exist and where they're used (targeted `Edit`,
  never rewrite the whole line/file)
- `TODOS.md` — add one line confirming `telegram-leg-labels` TL-1..TL-4 complete
- No new modules were added → no `CONTEXT_TREE.md` change needed
- `DECISIONS.md` — not needed; this is a formatting/documentation fix, not an architecture
  decision

**Commit:** `docs: telegram-leg-labels TL-1..TL-4 session close`
