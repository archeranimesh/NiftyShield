# Telegram Markdown Migration — Backbone — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Origin: `docs/plan/telegram-markdown-migration/README.md` — read it first.

**Design decision this whole story rests on:** after this migration, `TelegramNotifier.send()`
sends `text` to Telegram largely as-authored (parse_mode=Markdown), not auto-escaped the way
today's HTML+`<pre>` path escapes everything. This is a deliberate choice, not an oversight —
an auto-escaping `send()` would make it impossible for `strategy-rollout/` messages to ever emit
real bold/tables, which is the entire point of this migration (per Animesh's "replace default
globally" decision). The tradeoff: every caller that interpolates a dynamic value into message
text is now responsible for making that value Markdown-safe. MD-1's `mdcode()` helper is how;
MD-3/MD-4 apply it everywhere it's currently missing. If a future caller adds a new
`send_plain_message()` call site without using `mdcode()` on its dynamic values, it will
silently 400 the first time that value contains `_`, `*`, `` ` ``, or `[` — same failure mode
that was found in the original scratch script's `DELTA_WARN`. There is no compiler check for
this; it's a hand-maintained discipline, which is exactly why `src/notifications/CLAUDE.md`
must state it explicitly (MD-5).

---

## MD-1 — Markdown Escaping Helpers

**Context:** Legacy Telegram Markdown (parse_mode=`Markdown`, not `MarkdownV2`) treats a lone
`_`, `*`, `` ` ``, or `[` outside a code span as the start of a formatting entity. Confirmed
2026-08-07: `DELTA_WARN` sent unescaped caused `Bad Request: can't parse entities: Can't find
end of the entity starting at byte offset 455` — Telegram read the `_` in `DELTA_WARN` as
opening `_italic_` with no closing underscore. `TelegramNotifier.send()` currently protects
against this class of bug by HTML-escaping and `<pre>`-wrapping everything; that protection
goes away in MD-2, so this helper module is what replaces it for dynamic-value interpolation.

**Files to change:**
- `src/notifications/markdown.py` — new module, two functions
- `tests/unit/notifications/test_markdown.py` — new test file

**Before any code:**
```
get_code_snippet("TelegramNotifier.send")   # confirm current _html_escape behavior being replaced
search_code("_html_escape")                 # find the function this is analogous to
git log --oneline -10 src/notifications/
```

**Functions to add:**

```python
def escape_markdown(text: str) -> str:
    """Backslash-escape legacy-Markdown special characters in free text.

    Args:
        text: Arbitrary text that may contain _, *, `, [ and should render
              as literal characters, not open a formatting entity.

    Returns:
        text with _, *, `, [ each preceded by a backslash. Safe to interpolate
        into a larger Markdown-formatted message without risk of unbalanced
        entities from this substring specifically.
    """


def mdcode(value: str) -> str:
    """Wrap a dynamic value as an inline code span for safe interpolation.

    Args:
        value: A dynamic identifier/label (strategy_id, signal code, instrument
               key, error message) being interpolated into a larger Markdown
               message.

    Returns:
        `` `value` `` — backtick-wrapped. Telegram does not parse entities
        inside a code span, so any _ * ` [ inside value is inert regardless
        of count or balance. Preferred over escape_markdown() for anything
        that's conceptually an identifier (renders as monospace, which reads
        naturally for strategy IDs / signal codes) — use escape_markdown()
        only for free-form prose that must stay visually plain, not code-styled.
        If value itself contains a literal backtick, falls back to
        escape_markdown(value) instead of producing a broken/nested code span.
    """
```

**Tests:**
- `test_escape_markdown_escapes_all_special_chars` — string with `_`, `*`, `` ` ``, `[` → each backslash-escaped
- `test_escape_markdown_noop_on_plain_text` — no special chars → unchanged
- `test_mdcode_wraps_in_backticks` — `"DELTA_WARN"` → `` "`DELTA_WARN`" ``
- `test_mdcode_falls_back_when_value_contains_backtick` — value with `` ` `` → uses `escape_markdown()` path, asserted via output shape not containing an unescaped/nested backtick pair
- `test_mdcode_empty_string` — edge case, returns `` "``" `` (empty code span) — confirm this doesn't itself confuse Telegram's parser (documented assumption if not verified against live API in this task; flag for manual confirmation during MD-4's real-message testing if any caller can produce an empty value)

**Commit:** `feat(notifications): markdown escaping helpers for Telegram migration`

---

## MD-2 — Switch `TelegramNotifier.send()` to Markdown parse_mode

**Files to change:**
- `src/notifications/telegram.py` — `TelegramNotifier.send()`
- `tests/unit/test_notifications.py` — update `test_send_uses_html_parse_mode` and
  `test_send_escapes_html_in_message` (both currently assert HTML-specific behavior that no
  longer applies), add new entity-parse regression test

**Before any code:**
```
get_code_snippet("TelegramNotifier.send")       # exact current implementation, lines 76-116
get_code_snippet("test_send_uses_html_parse_mode")
get_code_snippet("test_send_escapes_html_in_message")
```

**Change:** `send()`'s payload changes from
`{"text": f"<pre>{_html_escape(text)}</pre>", "parse_mode": "HTML"}` to
`{"text": text, "parse_mode": "Markdown"}`. No `<pre>` wrap, no auto-escaping — per this
story's design-decision note above. Budget/error-handling/non-fatal-contract logic (lines
before/after the payload construction) is unchanged.

**Tests:**
- Rename/rewrite `test_send_uses_html_parse_mode` → `test_send_uses_markdown_parse_mode` —
  asserts payload `parse_mode == "Markdown"`, no `<pre>` in `text`
- Rewrite `test_send_escapes_html_in_message` → `test_send_does_not_auto_escape` — asserts
  text is passed through verbatim (proves the new caller-responsibility model, not a silent
  regression)
- New: `test_send_returns_false_on_telegram_entity_parse_error` — mock the aiohttp response to
  return the exact 400 payload shape confirmed 2026-08-07
  (`{"ok": false, "description": "Bad Request: can't parse entities..."}`), assert `send()`
  returns `False` and does not raise (non-fatal contract preserved) — this is the regression
  test for the original bug this whole epic started from

**Commit:** `refactor(notifications): TelegramNotifier.send uses Markdown parse_mode`

---

## MD-3 — Audit + Fix: Strategy Close/Roll Notifications

**Context:** 7 strategy classes build close/roll notification text with f-string
interpolation of dynamic values (strategy names, instrument labels, P&L figures, signal
codes) that were never written with Markdown in mind. Confirmed callers via graph query
(2026-08-07):

| File | Method |
|---|---|
| `src/strategy/auto_close.py` | `_send_close_notification` |
| `src/strategy/csp_nifty_v1.py` | `_send_notification` |
| `src/strategy/cc_overlay_v1.py` | `_send_close_notification` |
| `src/strategy/collar_overlay_v1.py` | `_send_close_notification` |
| `src/strategy/ic_nifty_v1.py` | `_send_close_notification` |
| `src/strategy/ic_nifty_v2.py` | `_send_close_notification` |
| `src/strategy/pp_overlay_v1.py` | `_send_close_notification` |

**Before any code:** for EACH file, run `get_code_snippet(<method qualified_name>)` — do not
batch-assume they share identical text-building logic; `telegram-leg-labels`'s TL-2 already
touched 4 of these 7 for a different reason (leg-label formatting) and found each had slightly
different interpolation patterns.

**What to change, per method:** identify every dynamic value interpolated into the message
text — strategy_id/name, instrument label, signal/action code, any free-form error string —
and wrap it with `mdcode()` (identifiers) or `escape_markdown()` (free-form prose) from MD-1.
Do NOT change the message's overall wording/structure in this task — that's `strategy-rollout/`'s
job. This task is purely: make the existing text safe under the new parse mode, byte-for-byte
equivalent visual output otherwise (values that never contained special chars render identically;
values that did are now escaped instead of silently breaking the send).

**Tests:** for each of the 7 methods, add/extend one test asserting that a value containing an
underscore (e.g. a strategy_id fixture matching the real convention, `paper_ic_nifty_v1_monthly`)
survives `mdcode()`/`escape_markdown()` wrapping in the constructed message — i.e. the message
text sent to the (mocked) notifier contains the wrapped form, not the raw form.

**Financial-logic commit note:** run real `@code-reviewer` against `git diff HEAD` before
committing — root `CLAUDE.md`'s AutoTrigger table requires it for any Greeks/P&L-adjacent
strategy-file change, and these are the close-notification paths for every live strategy.

**Commit:** `fix(strategy): escape dynamic values in close notifications for Markdown parse_mode`

---

## MD-4 — Audit + Fix: Reporting Scripts + Approval Requests

**Files to change:**
- `scripts/strategies/ic/paper_ic_snapshot.py`
- `scripts/strategies/ic/paper_ic_monthly_comparison.py`
- `scripts/reporting/paper_pnl_report.py`
- `scripts/strategies/three_track/paper_3track_snapshot.py` (`_build_recovery_digest`)
- `src/notifications/telegram_gateway.py` — `TelegramGateway.send_approval_request`

**Same escaping treatment as MD-3.** `send_approval_request` is the highest-consequence one in
this task — it's the interactive-keyboard trade-approval path. Read
`docs/plan/full-repo-review-followups/telegram-approval-auth-fix/tasks.md` first to confirm its
current state (was open, shipped SHA `5cafc3c` as of 2026-08-07 per this epic's README — re-verify,
don't trust that note if time has passed) before touching the same method, to avoid diff
conflicts with that story if it has since gained new tasks.

**Tests:** same pattern as MD-3 — one test per script/method proving underscore-bearing dynamic
values survive escaping. For `send_approval_request` specifically, also assert the callback
button text/data is unaffected (buttons aren't part of the Markdown-parsed message body, but
confirm this explicitly rather than assuming — read the current implementation first).

**Commit:** `fix(notifications): escape dynamic values in reporting scripts and approval requests`

---

## MD-5 — Docs Close

**Files to change (targeted `Edit`, never `Write`):**
- `src/notifications/CLAUDE.md` — replace the HTML parse_mode note with: parse_mode is now
  Markdown; `send()` does not auto-escape; every caller interpolating a dynamic value MUST use
  `mdcode()`/`escape_markdown()` from `src/notifications/markdown.py`; link this rule from the
  existing "Instrument Label Formatting" section since leg labels are exactly the kind of
  dynamic value this applies to
- `DECISIONS.md` — new entry: parse-mode switch (HTML→Markdown), design rationale (real
  bold+table capability vs. auto-escape safety net), link to this epic
- `CONTEXT.md` — module tree: add `src/notifications/markdown.py`
- `TODOS.md` — session log entry for the backbone story's completion

No code in this task. Verify `python -m pytest tests/unit/ --tb=no -q` still green (should be
unaffected by docs-only changes, but confirm per protocol).

**Commit:** `docs(notifications): record Markdown parse-mode migration decision`
