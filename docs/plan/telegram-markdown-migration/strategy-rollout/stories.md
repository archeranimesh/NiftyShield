# Telegram Markdown Migration — Strategy Rollout — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.

**Sequencing rationale (why this order, not alphabetical or file-count order):** IC EOD audit
is informational-only — a wrong-looking message costs nothing beyond a re-read. The comparison
report is also informational but touches a known existing bug (hand-counted widths), so it's
worth fixing early while the pattern is fresh. Close/roll notifications fire on real position
events — worth getting right, but a formatting glitch there is still just a notification, not
a trade action. Approval requests are the only message type in this list that gates an actual
trade action via an interactive keyboard callback — highest consequence of a formatting
regression (a broken button or unreadable approval text could block or confuse a real trade
decision), so it goes last and gets the coordination check.

---

## ROLL-1 — IC EOD Audit

**Files to change:**
- `scripts/strategies/ic/paper_ic_snapshot.py` — the message-building function (find via
  `search_graph`, not assumed — TL-3 in `telegram-leg-labels` already touched entry-preview
  text in a related script; confirm this one's current function name/location fresh)
- Matching test file in `tests/unit/`

**Before any code:**
```
get_code_snippet(<message-building function in paper_ic_snapshot.py>)   # find via search_graph first
```
Port the structure validated interactively in
`scratch/2026-08-07_ic_eod_audit_telegram_format.py`'s final `build_message()`: bold header +
identifier line, Snapshot/P&L side-by-side kv table, fenced leg table, bold summary lines below
— using `formatting-rules/`'s `build_kv_table` / `build_side_by_side_kv_table` / `build_leg_table`
/ `format_money` / `format_greek` / `format_strike` / `format_pct`, and `backbone/`'s `mdcode()`
for any signal/action code. Do not hand-roll formatting logic that FMT-2/FMT-3 already built.

**Tests:** update the existing message-format test(s) for this script to assert the new
structure; keep at least one test that constructs a leg with an underscore-bearing signal code
to prove the `mdcode()` wrapping survived the port (this is the exact bug this whole epic
started from — don't let the regression test get lost in the rewrite).

**Commit:** `feat(ic): migrate EOD audit message to Markdown table format`

---

## ROLL-2 — IC Monthly Comparison Report

**⚠️ Supersedes `docs/plan/telegram-ic-comparison-formatting/` TGFMT-2..9 (marked superseded
2026-08-07) — read that folder's `tasks.md` note first.** TGFMT-1 already shipped (SHA
`a69d817`) a dynamic-width fix to `build_comparison_report()` — the hand-counted-20-char-budget
bug is **already fixed**, do not re-fix it from scratch. This task's job is narrower than
originally scoped: port the already-correct alignment logic to use
`formatting-rules/`'s `build_side_by_side_kv_table` (for consistency with every other message
in this epic) and add Markdown bold/parse_mode — not fix a bug that no longer exists.

**Two still-open feature asks carried forward from TGFMT-2/TGFMT-3 — include in this task's
scope, don't drop them:**
1. **Legs row** — open-leg count out of 4, with a 🔴 suffix if <4. No new data dependency;
   `build_stats()` already computes `open_pos` per TGFMT-2's original spec.
2. **Bkd/Flt month-vs-inception split** — `Bkd (M)`/`Bkd (I)` (realized P&L, month vs.
   inception) and `Flt (M)`/`Flt (I)` (unrealized P&L, ditto). `Bkd (M)`/`Bkd (I)` come from
   `paper_nav_snapshots.realized_pnl` (already a cumulative field). **`Flt (M)` is a genuinely
   new calculation** — month-start delta on `unrealized_pnl` (a point-in-time field), via a new
   `_get_unrealized_pnl_month_change()`. Per TGFMT-3's revision note: do NOT implement this as
   a copy of `Flt (I)` — the two are expected to differ, and a test must assert that they do
   (a test that only checks the two are equal would pass on a broken no-op implementation).

**Files to change:**
- `scripts/strategies/ic/paper_ic_monthly_comparison.py` — `build_comparison_report()`,
  `ICMonthlyStats`, new `_get_inception_realized_pnl()` / `_get_unrealized_pnl_month_change()`
- `tests/unit/strategies/ic/test_paper_ic_monthly_comparison.py`

**Before any code:**
```
get_code_snippet("build_comparison_report")   # confirm current (TGFMT-1-fixed) implementation
get_code_snippet("ICMonthlyStats")
get_code_snippet("build_stats")               # confirm open_pos is already available, per TGFMT-2
```
Replace the (already dynamic-width, per TGFMT-1) hand-rolled table logic with
`build_side_by_side_kv_table`, using the V1/V2 monthly columns as `rows_a`/`rows_b`. Preserve
existing warn-emoji-on-value behavior (`🔴` suffix for a flagged value) — check
`_build_side_by_side_report` in `scratch/2026-08-07_telegram_ic_comparison_format_repro.py` for
how that was represented before deciding whether it survives the port unchanged or needs
adjustment for the new table format.

**Tests:** existing `test_comparison_report_format` and `test_comparison_report_one_missing`
must still pass (or be updated if the exact output string changed — expected, since parse_mode
and table-builder call are changing; update assertions to match, don't weaken them). Keep
TGFMT-1's existing long-label regression test (`"Realized (inception)"` or equivalent) — it
must still pass under the new table builder, proving the dynamic-width property survived the
port. Add new tests for the Legs row and the Bkd/Flt split per the feature-ask spec above,
including the "Flt (M) != Flt (I)" assertion.

**Financial-logic commit note:** the Bkd/Flt month-delta calc is P&L-adjacent — real
`@code-reviewer` against `git diff HEAD` required per root `CLAUDE.md`.

**Commit:** `feat(ic): comparison report Markdown migration + Legs row + Bkd/Flt month split`

---

## ROLL-3 — Strategy Close/Roll Notifications

**Files to change:** same 7 files as `backbone/` MD-3 —
`src/strategy/auto_close.py`, `csp_nifty_v1.py`, `cc_overlay_v1.py`, `collar_overlay_v1.py`,
`ic_nifty_v1.py`, `ic_nifty_v2.py`, `pp_overlay_v1.py`.

**Scope judgment call, per method — decide, don't force a table everywhere:** these messages
are typically single-position-event summaries (one leg closed, one roll executed), not
multi-row tables like the EOD audit. Read each method's current message text before deciding
whether it benefits from `build_kv_table` (e.g. a close event with several P&L figures) or just
needs bold headers + `mdcode()`-wrapped identifiers with no table structure at all (e.g. a
short one-line roll confirmation). Do not force every message into a table shape just because
the tooling now exists — match the format to what the message actually needs, using
`formatting-rules/`'s value formatters (`format_money`, `format_greek`, etc.) regardless of
whether a table is used.

**Tests:** update each strategy's existing close/roll-notification tests to assert the new
message structure. Since `MD-3` already added underscore-survival regression tests at the
escaping layer, these tests can focus on visual/structural correctness (bold markers present,
correct formatter used per value type) rather than re-proving the escaping itself.

**Commit:** `feat(strategy): migrate close/roll notifications to Markdown formatting` (one
commit per strategy file is also acceptable given 7 files touched — use judgment per
`CLAUDE.md`'s "typical phase boundaries" guidance; do not bundle all 7 into a single unreviewable
diff if the changes turn out to be substantial per file)

---

## ROLL-4 — Approval Request Messages

**Files to change:**
- `src/notifications/telegram_gateway.py` — `TelegramGateway.send_approval_request`
- `tests/unit/notifications/test_telegram_gateway.py`

**Mandatory pre-step:** re-read `docs/plan/full-repo-review-followups/telegram-approval-auth-fix/tasks.md`
in full before touching this method. If it has open tasks, coordinate (land its fix first, or
do both changes in the same session with the auth fix as the first commit) — do not let this
task's formatting changes and that story's auth changes race as uncoordinated diffs to the same
function.

**Scope:** apply bold/formatting to the approval-request message body using `formatting-rules/`
helpers, consistent with ROLL-3's per-message judgment call. Confirm callback button
label/data are unaffected by the parse-mode change (buttons are a separate Telegram API field,
not part of the parsed message body, but verify against the current implementation rather than
assuming).

**Tests:** existing `test_send_approval_request_returns_message_id_on_success` and related
tests must still pass; add a test proving a strategy_id or instrument label with an underscore
in the approval message body survives correctly (same regression-test pattern as ROLL-1).

**Commit:** `feat(notifications): migrate approval request message to Markdown formatting`

---

## ROLL-5 — Docs Close

**Files to change (targeted `Edit`, never `Write`):**
- `CONTEXT.md` — note the completed migration across all message types
- `DECISIONS.md` — close out the epic-level decision entry (from `backbone/` MD-5) with a note
  that rollout is complete
- `docs/plan/README.md` — mark `telegram-markdown-migration/` epic as shipped, matching the
  convention used for other archived epics in that table
- `TODOS.md` — final session log entry

**Also:** move `scratch/2026-08-07_ic_eod_audit_telegram_format.py` and
`scratch/2026-08-07_telegram_ic_comparison_format_repro.py` out of active scratch — they've
served their purpose as reference implementations now fully ported into `src/`/`scripts/`.
Per this project's scratch convention (dated throwaway files), leaving them in place is
harmless, but note in the commit message that they're now historical/superseded rather than
still-relevant references, so a future session doesn't mistake them for the current source of
truth.

**Commit:** `docs(notifications): close out Telegram Markdown migration epic`
