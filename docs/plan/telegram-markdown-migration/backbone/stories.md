# Telegram Markdown Migration — Backbone — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Origin: `docs/plan/telegram-markdown-migration/README.md` — read it first.

**Design decision this whole story rests on:** after this migration, `TelegramNotifier.send()`
sends `text` to Telegram largely as-authored (parse_mode=`MarkdownV2`), not auto-escaped the way
today's HTML+`<pre>` path escapes everything. This is a deliberate choice, not an oversight —
an auto-escaping `send()` would make it impossible for `strategy-rollout/` messages to ever emit
real bold/tables, which is the entire point of this migration (per Animesh's "replace default
globally" decision). The tradeoff: every caller that interpolates a dynamic value into message
text is now responsible for making that value Markdown-safe. MD-1's `mdcode()` helper is how;
MD-3/MD-4 apply it everywhere it's currently missing. If a future caller adds a new
`send_plain_message()` call site without using `mdcode()` on its dynamic values, it will
silently 400 the first time that value contains a MarkdownV2 reserved character — same failure
mode that was found in the original scratch script's `DELTA_WARN`. There is no compiler check
for this; it's a hand-maintained discipline, which is exactly why `src/notifications/CLAUDE.md`
must state it explicitly (MD-5).

**Revised 2026-08-07 — MarkdownV2, not legacy Markdown v1:** the epic originally prototyped
legacy `parse_mode=Markdown`. Switched to `MarkdownV2` on review: MarkdownV2 requires escaping
a much larger reserved-character set (`_ * [ ] ( ) ~ \` > # + - = | { } . !`, vs. legacy's just
`_ * \` [`), which is more upfront work but eliminates the *ambiguity* that caused the original
bug — legacy Markdown's "smart" entity-pairing is exactly what silently misread the lone `_` in
`DELTA_WARN` as opening italics; MarkdownV2 has no such smart-pairing, every reserved character
is either escaped or it isn't, no guessing. It's also Telegram's actively-recommended mode going
forward, legacy Markdown is not.

**This materially raises MD-3/MD-4's scope, not just MD-1/MD-2's.** Under MarkdownV2, common
prose punctuation — periods, parentheses, hyphens — are ALL reserved, not just underscores/
asterisks/backticks/brackets. A static message *template* like `"Captured: ₹{amt} ({pct}%)"`
now needs its own literal `.`/`(`/`)` characters escaped in the template text itself (e.g.
`"Captured: ₹{amt} \\({pct}%\\)"`), not just the dynamic `{amt}`/`{pct}` values. MD-3/MD-4's
audit-and-fix pass must therefore check every message's literal template text for reserved
punctuation, not only its interpolated values — read each method's current f-string in full
before editing, don't just grep for `{` placeholders.

---

## MD-1 — Markdown Escaping Helpers

**Context:** Telegram MarkdownV2 reserves 18 characters outside a code span:
`` _ * [ ] ( ) ~ ` > # + - = | { } . ! ``. Any of these appearing unescaped in plain text
either opens an unintended formatting entity or 400s the send. Confirmed 2026-08-07 (under
legacy Markdown, same underlying class of bug applies to MarkdownV2's larger set): `DELTA_WARN`
sent unescaped caused `Bad Request: can't parse entities: Can't find end of the entity starting
at byte offset 455` — Telegram read the `_` as opening `_italic_` with no closing underscore.
`TelegramNotifier.send()` currently protects against this class of bug by HTML-escaping and
`<pre>`-wrapping everything; that protection goes away in MD-2, so this helper module is what
replaces it for dynamic-value interpolation AND static template text (see the story-level
"Revised 2026-08-07" note above — MarkdownV2's reserved set includes common prose punctuation
like `.`/`(`/`)`, unlike legacy Markdown's narrower set).

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
MARKDOWNV2_RESERVED = "_*[]()~`>#+-=|{}.!"


def escape_markdown(text: str) -> str:
    """Backslash-escape MarkdownV2 reserved characters in free text.

    Args:
        text: Arbitrary text that may contain any of MARKDOWNV2_RESERVED and
              should render as literal characters, not open/be part of a
              formatting entity. Covers both dynamic interpolated values AND
              static template prose (MarkdownV2's reserved set includes '.',
              '(', ')', '-' — ordinary punctuation, not just markup characters).

    Returns:
        text with every character in MARKDOWNV2_RESERVED preceded by a
        backslash. Safe to interpolate into or use as a larger
        MarkdownV2-formatted message without risk of unescaped entities
        from this substring specifically.
    """


def mdcode(value: str) -> str:
    """Wrap a dynamic value as an inline code span for safe interpolation.

    Args:
        value: A dynamic identifier/label (strategy_id, signal code, instrument
               key, error message) being interpolated into a larger MarkdownV2
               message.

    Returns:
        `` `value` `` — backtick-wrapped. Telegram does not parse entities
        inside a code span, so any MARKDOWNV2_RESERVED character inside value
        is inert regardless of count or balance. Preferred over
        escape_markdown() for anything that's conceptually an identifier
        (renders as monospace, which reads naturally for strategy IDs / signal
        codes) — use escape_markdown() only for free-form prose that must stay
        visually plain, not code-styled. If value itself contains a literal
        backtick or backslash (MarkdownV2 also requires escaping backslash
        inside code spans specifically — confirm exact rule against Telegram's
        current API docs during implementation, don't assume it's identical to
        the non-code-span escaping rule), falls back to escape_markdown(value)
        instead of producing a broken/nested code span.
    """
```

**Tests:**
- `test_escape_markdown_escapes_all_reserved_chars` — string containing every character in
  `MARKDOWNV2_RESERVED` → each backslash-escaped
- `test_escape_markdown_noop_on_plain_text` — no reserved chars → unchanged
- `test_escape_markdown_handles_prose_punctuation` — a realistic prose fragment with a period
  and parentheses (e.g. `"Captured: 4% (up from 2%)."`) → escaped correctly; this is the test
  that proves the MarkdownV2 scope expansion (vs. legacy Markdown) is actually handled, not just
  the underscore case that started this epic
- `test_mdcode_wraps_in_backticks` — `"DELTA_WARN"` → `` "`DELTA_WARN`" ``
- `test_mdcode_falls_back_when_value_contains_backtick` — value with `` ` `` → uses `escape_markdown()` path, asserted via output shape not containing an unescaped/nested backtick pair
- `test_mdcode_empty_string` — edge case, returns `` "``" `` (empty code span)
— confirm this doesn't itself confuse Telegram's parser (documented assumption if not verified against live API in this task;
flag for manual confirmation during MD-4's real-message testing if any caller can produce an empty value)

**Addendum (2026-08-11, `ROLL-13` workshop session — two live-caught escaping bugs, both
missed by every prior scratch script's print-only testing since this was the first message in
the epic actually exercised via a real `--send` round trip):**
- `test_escape_markdown_does_not_escape_non_reserved_unicode` — an em dash (`—`, U+2014) or
  other non-ASCII symbol/emoji passed through `escape_markdown()` must come back unescaped.
  Caught live: a hand-written `\—` in static template text (typed by analogy with an adjacent
  ASCII hyphen that DOES need escaping) doesn't 400 — Telegram just renders the stray `\` as a
  literal backslash — so this class of bug survives a failed-send check and needs its own
  assertion against `MARKDOWNV2_RESERVED`'s exact membership, not just "did it send."
- A regression case for `=` specifically: none of ROLL-7 through ROLL-12's confirmed messages
  used a bare `=` in static template text, so `=`'s presence in `MARKDOWNV2_RESERVED` (it's
  been in the constant since MD-1 was first specced) never actually got exercised end-to-end
  until `ROLL-13`. Add a case to `test_escape_markdown_escapes_all_reserved_chars` that isn't
  just "every char in the constant" but a realistic `"qty=480"`-shaped fragment, so a future
  caller copy-pasting static text past `escape_markdown()`'s dynamic-value-only call sites (the
  actual bug — `escape_markdown()` itself was never wrong) gets caught by a test that looks
  like real usage, not just the exhaustive-alphabet one.

**Commit:** `feat(notifications): MarkdownV2 escaping helpers for Telegram migration`

**As-built (SHA `786e8096`):** Owner Claude / Sonnet. `Review: code-reviewer` — deliberately not the financial-logic tier, but foundational-correctness edge cases
(Unicode, empty string) warrant inline judgment over pure mechanical delegation. The 2026-08-11 `ROLL-13` addendum cases (non-reserved-Unicode passthrough, realistic `qty=480`-shaped `=` fragment)
were added to this module's tests then, not at MD-1 time.

---

## MD-2 — Switch `TelegramNotifier.send()` to MarkdownV2 parse_mode

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
`{"text": text, "parse_mode": "MarkdownV2"}`. No `<pre>` wrap, no auto-escaping — per this
story's design-decision note above. Budget/error-handling/non-fatal-contract logic (lines
before/after the payload construction) is unchanged.

**Tests:**
- Rename/rewrite `test_send_uses_html_parse_mode` → `test_send_uses_markdownv2_parse_mode` —
  asserts payload `parse_mode == "MarkdownV2"`, no `<pre>` in `text`
- Rewrite `test_send_escapes_html_in_message` → `test_send_does_not_auto_escape` — asserts
  text is passed through verbatim (proves the new caller-responsibility model, not a silent
  regression)
- New: `test_send_returns_false_on_telegram_entity_parse_error` — mock the aiohttp response to
  return the exact 400 payload shape confirmed 2026-08-07
  (`{"ok": false, "description": "Bad Request: can't parse entities..."}`), assert `send()`
  returns `False` and does not raise (non-fatal contract preserved) — this is the regression
  test for the original bug this whole epic started from

**Commit:** `refactor(notifications): TelegramNotifier.send uses MarkdownV2 parse_mode`

**As-built (SHA `721daf9`):** Owner Claude / Sonnet, `Review: code-reviewer` (touches the non-fatal send contract — verified by hand, not just spec-following). **MD-2 landed alone**, not bundled
with MD-3/MD-4 as the epic README's live-risk-window constraint asks — Animesh explicitly chose the one-task-per-session protocol over bundling (asked and confirmed at session start), fully aware
that this opened the window: from `721daf9` until MD-3/MD-4 landed, every existing caller's dynamic values were unescaped against MarkdownV2's reserved set in production. MD-3 and MD-4 were treated
as urgent, not routine backlog, and picked up next.

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

**What to change, per method:** two passes, not one — this is where MarkdownV2's wider reserved
set (vs. legacy Markdown) actually bites:
1. Every dynamic value interpolated into the message text — strategy_id/name, instrument
   label, signal/action code, any free-form error string — wrap with `mdcode()` (identifiers)
   or `escape_markdown()` (free-form prose) from MD-1.
2. The **static template text itself** — read the literal f-string/format-string content for
   `.`, `(`, `)`, `-`, `!` and any other `MARKDOWNV2_RESERVED` character that appears as
   ordinary prose punctuation (e.g. `"P&L: {amt} (delta-neutral)."`), and escape those literal
   characters in the template too. This did not exist as a concern under legacy Markdown and is
   easy to miss if this task is approached as "just wrap the f-string variables."

Do NOT change the message's overall wording/structure in this task — that's `strategy-rollout/`'s
job. This task is purely: make the existing text safe under the new parse mode, equivalent
visual output otherwise (values/punctuation that never needed escaping render identically;
values/punctuation that did are now escaped instead of silently breaking the send).

**Tests:** for each of the 7 methods, add/extend one test asserting that a value containing an
underscore (e.g. a strategy_id fixture matching the real convention, `paper_ic_nifty_v1_monthly`)
survives `mdcode()`/`escape_markdown()` wrapping in the constructed message — i.e. the message
text sent to the (mocked) notifier contains the wrapped form, not the raw form.

**Financial-logic commit note:** run real `@code-reviewer` against `git diff HEAD` before
committing — root `CLAUDE.md`'s AutoTrigger table requires it for any Greeks/P&L-adjacent
strategy-file change, and these are the close-notification paths for every live strategy.

**Commit:** `fix(strategy): escape dynamic values in close notifications for Markdown parse_mode`

**As-built (SHA `62d0172`):** Owner Antigravity — mechanical per-class audit-and-fix with a fully unambiguous spec — but `Review: code-reviewer` was the **real `@code-reviewer` (Opus)** gate against
`git diff HEAD`, mandatory regardless of implementer because these are the close-notification paths for every live strategy (financial-logic tier per the root `CLAUDE.md` AutoTrigger table).

---

## MD-4 — Audit + Fix: Reporting Scripts + Approval Requests

**Files to change:**
- `scripts/strategies/ic/paper_ic_snapshot.py`
- `scripts/strategies/ic/paper_ic_monthly_comparison.py`
- `scripts/strategies/three_track/paper_3track_snapshot.py` (`_build_recovery_digest`)
- `src/notifications/telegram_gateway.py` — `TelegramGateway.send_approval_request`

**Correction (2026-08-12):** `scripts/reporting/paper_pnl_report.py` was removed from this list
— it is a CLI-only tool (`--strategy`, `--json`, prints via `_report_to_json`/`_report_to_text`)
with no `TelegramNotifier`/`TelegramGateway` call anywhere in its one-commit history (`04687f1`,
SNAP-4). It was never a real Telegram caller; its inclusion here was a miscategorization, not a
scope decision. See `TODO.md`'s "Correction (2026-08-12)" section for the full write-up.

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

**As-built — split + scope expansion (2026-08-25, Animesh, explicit decision — not Antigravity-initiated).** `tasks.md`'s `MD-4` line is an umbrella; the work landed as `MD-4.1` / `MD-4.2` /
`MD-4.3` below. Original scope was the 3 reporting builders only. A Cowork review (Claude) surfaced that `TelegramGateway.send_notification` was still hardcoded to `parse_mode: HTML` — escaping
dynamic values in the 3 reporting builders without migrating the gateway itself would have corrupted output (literal backslashes rendered, since HTML mode never strips MarkdownV2 escaping). Further
review found `send_notification` is also called from `paper_ic_entry.py` and `paper_ic_entry_v2.py` (entry-signal alerts) — migrating the gateway's parse_mode without escaping those two callers in
the same sitting would recreate MD-2's live-risk-window bug for entry notifications. Animesh chose to fold the gateway migration and both entry scripts into MD-4 rather than spin off a blocking
sub-task.

### MD-4.1 — flip `TelegramGateway.send_notification` HTML → MarkdownV2

`src/notifications/telegram_gateway.py`. **As-built (commit `cd1e554`):** Owner Antigravity, `Review: code-reviewer`. Touches a shared gateway method with 5 live call sites (3 reporting scripts + 2
entry scripts, all in MD-4.2) — the reviewer had to verify all 5 callers are escaped and land in the **same commit** as MD-4.2. Landing MD-4.1 alone reopens the exact MD-2 live-risk-window bug.
Tests: `tests/unit/notifications/test_telegram_gateway.py`.

### MD-4.2 — escape the 5 reporting/entry scripts that call `send_notification`

**As-built (commit `cd1e554`, same commit as MD-4.1):** Owner Antigravity, `Review: code-reviewer` — mechanical escaping pass, no auth/judgment. Files: `paper_ic_snapshot.py` (`process_variant`,
`get_action_taken`); `paper_ic_monthly_comparison.py` (`build_comparison_report` + `fmt_*` helpers); `paper_3track_snapshot.py` (`_build_recovery_digest` **only** — the other `notifier.send()` sites
in that file are out of scope, tracked separately); `paper_ic_entry.py` (~L743/~L806); `paper_ic_entry_v2.py` (~L663/~L725). Tests: the matching `test_*` file for each.

### MD-4.3 — escape `TelegramGateway.send_approval_request`

**As-built (commit `aa58f44`):** Owner Claude / Sonnet, `Review: code-reviewer` was the **real `@code-reviewer` (Opus)** gate — auth-sensitive interactive-keyboard path, required a live
coordination-check against `telegram-approval-auth-fix` before touching. Independent of MD-4.1/4.2 — `send_approval_request` already hardcodes its own `parse_mode: HTML` separately from
`send_notification` and was untouched by that migration, so the MD-4.1/4.2 scope expansion did not affect it.

---

## MD-6 — Static-Scan Escaping Guard

**As-built (SHA `ce95bbd`):** Owner Claude / Sonnet, `Review: code-reviewer` — design judgment on what counts as "escaped" (AST-based vs. regex call-site detection, false-positive handling). Adds
`tests/unit/notifications/test_escaping_guard.py`: a test that walks `src/` / `scripts/` for `notifier.send(` / `send_plain_message(` call sites and asserts every interpolated dynamic value passed
through `escape_markdown()` / `mdcode()` somewhere upstream, plus `test_baseline_entries_are_still_unescaped` / `test_baseline_has_no_duplicate_or_unused_entries` guarding the `_BASELINE_UNESCAPED`
won't-fix / not-yet-migrated list. **Sequencing (corrected 2026-08-12):** an earlier session proposed landing this right after MD-2. That was wrong — MD-3/MD-4 are the audit-and-fix pass that
actually escapes the currently-unescaped call sites; a guard introduced before they land fails against the codebase it is meant to protect. Correct position is after both audits complete, so the
guard starts from a clean baseline and then protects every `send()` call site added by `formatting-rules/` and `strategy-rollout/`.

**Contract for downstream tasks:** every `strategy-rollout/` / `formatting-rules/` task that adds or fixes a `send()` call site removes that site's `_BASELINE_UNESCAPED` entry in the same commit, or
the two baseline tests fail. `scripts/dev/send_test_telegram.py:65` is a documented permanent won't-fix in that list (manual dev/debug utility, not a cron or strategy path — Animesh, 2026-08-25).

---

## MD-7 — Audit + Fix: Gaps Surfaced by MD-6's Guard

**Context:** MD-6's static-scan guard (`tests/unit/notifications/test_escaping_guard.py`) found
29 unescaped `.send()`/`.send_plain_message()` call sites when it first ran (2026-08-25). Most
are `strategy-rollout/` messages already format-confirmed but not yet implemented in real code
(tracked via their ROLL-N reason in the guard's `_BASELINE_UNESCAPED`) — those stay baselined
until their ROLL-* task lands, not this task's job. A smaller set were never named in *any*
prior MD-*/ROLL-* task or `TODO.md` queue entry — real production call sites this epic's
original code-graph sweep (README.md's "Confirmed real callers" list, 2026-08-07) simply missed.
This task closes that smaller set — pure escaping safety, not a format migration, same contract
as MD-3/MD-4.

**Split 2026-08-25 (Animesh's request):** too many unrelated files for one session — split into
three independently-completable sub-tasks below, each with its own commit/review/baseline-update
cycle. `tasks.md`'s `MD-7` line is now an umbrella; work the `MD-7.1`/`MD-7.2`/`MD-7.3` entries.

**`scripts/dev/send_test_telegram.py:65` — confirmed out of scope (2026-08-25, Animesh):** it's a
manual dev/debug utility invoked ad hoc by whoever's testing, not a cron or strategy event path —
excluded from all three sub-tasks below. Its reason string in MD-6's `_BASELINE_UNESCAPED` should
read as a deliberate won't-fix, not an open gap — update it in whichever sub-task lands first
(see each sub-task's baseline-maintenance note).

**Before any code (all sub-tasks):** the graph was stale relative to the working tree as of MD-6
(confirmed via `detect_changes` reporting no drift while `search_graph`/`get_code_snippet` still
missed real `src/notifications/markdown.py` symbols) — re-verify graph freshness first; if still
stale, fall back to `git log` → `grep`/`sed -n` → `Read` per the folder `prompt.md`'s escalation
order, same as MD-6 had to. For each method: read the current f-string/format-string in full (not
just `{placeholder}` locations) — per the story-level note at the top of this file, MarkdownV2
reserves ordinary prose punctuation, not just markup characters, so static template text needs
the same audit as MD-3/MD-4 gave their files.

**What to change, per method (all sub-tasks):** same two-pass treatment as MD-3/MD-4 —
1. Every dynamic value interpolated into the message text gets `mdcode()` (identifiers) or
   `escape_markdown()` (free-form prose).
2. The static template text itself gets checked for literal `.`/`(`/`)`/`-`/`!` and other
   `MARKDOWNV2_RESERVED` characters appearing as ordinary prose punctuation.

Do NOT change message wording/structure — that's `strategy-rollout/`'s job if any of these ever
get a ROLL-N format pass. This task is purely: make the existing text safe under MarkdownV2.

**Tests (all sub-tasks):** one test per method proving an underscore-bearing dynamic value (e.g.
a strategy_id fixture matching the real convention) survives `mdcode()`/`escape_markdown()`
wrapping in the constructed message — same pattern as MD-3/MD-4.

**Baseline maintenance (mandatory, all sub-tasks):** remove each fixed call site's entry from
`_BASELINE_UNESCAPED` in `tests/unit/notifications/test_escaping_guard.py` in the *same commit*
as its fix — `test_baseline_entries_are_still_unescaped` and
`test_baseline_has_no_duplicate_or_unused_entries` will fail otherwise (that file's own
maintenance contract, see its module docstring).

---

### MD-7.1 — `scripts/pre_market_brief.py`

**Files to change:** `scripts/pre_market_brief.py` — both `gateway.send_plain_message()` calls
(~L144, ~L197).

**Commit:** `fix(scripts): escape dynamic values in pre_market_brief Telegram sends`

**As-built (SHA `39993bf`):** Owner Antigravity, `Review: code-reviewer` — single file, mechanical.

---

### MD-7.2 — IC entry `_gate_alert` paths

**Files to change:**
- `scripts/strategies/ic/paper_ic_entry.py` — `_gate_alert` (~L255)
- `scripts/strategies/ic/paper_ic_entry_v2.py` — `_gate_alert` (~L313)

Both are a separate code path from the `send_notification()` calls MD-4.2 already escaped in
these same two files — confirm the two paths don't share a text-building helper before assuming
identical treatment.

**Commit:** `fix(scripts): escape dynamic values in IC entry _gate_alert notifications`

**As-built (SHA `adfae40`):** Owner Antigravity, `Review: code-reviewer` — `_gate_alert` is a separate path from the `send_notification()` calls MD-4.2 already escaped in these two files; same
mechanical pattern.

---

### MD-7.3 — `auto_close.py` + `overlay_closer.py` close/monetize paths

**Files to change:**
- `src/strategy/auto_close.py` — `auto_close_overlay` (~L235), `evaluate_pp_reentry_eod` (~L404)
  — both outside MD-3's `_send_close_notification`-only scope
- `src/strategy/overlay_closer.py` — `close_collar_all` (~L268), `monetize_collar_put` (~L328,
  ~L392)

**Financial-logic commit note:** run real `@code-reviewer` (Opus) against `git diff HEAD` before
committing — root `CLAUDE.md`'s AutoTrigger table requires it for close/monetize paths on live
overlay strategies, the same tier as MD-3's audit, even though this task only touches escaping,
not P&L computation.

**Commit:** `fix(strategy): escape dynamic values in auto_close/overlay_closer notifications`

**As-built (SHA `04b469d`):** Owner Claude / Sonnet. `Review` was the real `@code-reviewer` (Opus) tier — close/monetize paths for live overlay strategies, same financial-logic tier as MD-3 even
though the change is escaping-only. This Cowork session could not spawn `.claude/agents/code-reviewer.md` directly (same structural limitation as BUG-037 B037.6) — substituted a `general-purpose`
agent loaded with the full code-reviewer persona + `REVIEW.md` checklist against the isolated diff. 0 CRITICAL/ERROR, 2 WARNING — both investigated post-review and logged as pre-existing findings,
not defects in this diff: **BUG-038** (`OverlayCloser`'s 3 `notifier.send()` calls are unawaited against an `async def` method, likely never delivered) and a note that `escape_markdown()` does not
escape literal backslashes. Neither fixed here (out of this task's escaping-only scope) — see `docs/bugs/bugs.md` BUG-038.

---

## MD-5 — Docs Close

**Files to change (targeted `Edit`, never `Write`):**
- `src/notifications/CLAUDE.md` — replace the HTML parse_mode note with: parse_mode is now
  MarkdownV2; `send()` does not auto-escape; every caller interpolating a dynamic value MUST
  use `mdcode()`/`escape_markdown()` from `src/notifications/markdown.py`; **static template
  text must also be checked for reserved punctuation** (`.`/`(`/`)`/`-`/`!` etc.), not just
  interpolated values — this is the part most likely to be forgotten by a future editor used to
  legacy-Markdown's narrower rules; link this rule from the existing "Instrument Label
  Formatting" section since leg labels are exactly the kind of dynamic value this applies to
- `DECISIONS.md` — new entry: parse-mode switch (HTML→MarkdownV2, with the legacy-Markdown
  detour noted), design rationale (real bold+table capability vs. auto-escape safety net, and
  why V2 over v1 specifically — no smart-pairing ambiguity), link to this epic
- `CONTEXT.md` — module tree: add `src/notifications/markdown.py`
- `TODOS.md` — session log entry for the backbone story's completion

No code in this task. Verify `python -m pytest tests/unit/ --tb=no -q` still green (should be
unaffected by docs-only changes, but confirm per protocol).

**Commit:** `docs(notifications): record Markdown parse-mode migration decision`

**As-built (SHA `57c1c3c`):** Owner Antigravity, `Review: none` (docs only). Also documented MD-6's guard contract and the MD-7.1/7.2/7.3 fixes in `src/notifications/CLAUDE.md` alongside the
escaping-helper rule. This is the closing task of the `backbone/` story.
