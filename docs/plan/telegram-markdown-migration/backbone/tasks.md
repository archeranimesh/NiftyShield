# Telegram Markdown Migration — Backbone — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/telegram-markdown-migration/backbone/stories.md`.

> **Routing (added 2026-08-12, Cowork design-review session):** `Owner` is who implements —
> `Claude` for judgment-call/exploratory work, `Antigravity` for mechanical multi-file work with
> an unambiguous spec. `Model` is the model the owner should run at. `Review` is the mandatory
> gate per root `CLAUDE.md`'s Agent AutoTrigger table — financial-logic paths require the real
> `@code-reviewer` subagent (Opus), not Antigravity's persona approximation. Routing is a
> recommendation to re-confirm at session start, not a hard override of the AutoTrigger table.

---

- [x] **MD-1** — Add `escape_markdown()` / `mdcode()` helpers to `src/notifications/` + tests
      | SHA: 786e8096698721401a7d3e16039138c9014ce7e6
      | Owner: Claude | Model: Sonnet | Review: code-reviewer (not financial-logic tier) —
      foundational correctness (Unicode/empty-string edge cases) warrants inline judgment over
      pure mechanical delegation
- [x] **MD-2** — Switch `TelegramNotifier.send()` to Markdown parse_mode; update/replace the two
      HTML-specific tests; add an entity-parse regression test | Blocked by: MD-1
      | SHA: 721daf9
      | Owner: Claude | Model: Sonnet | Review: code-reviewer — touches the non-fatal send
      contract, verify by hand, not just spec-following
      **⚠️ Live-risk window (added 2026-08-18):** the moment MD-2 lands, every existing caller's
      dynamic values are unescaped against MarkdownV2's larger reserved-character set — the
      exact `DELTA_WARN` bug class this epic exists to fix, now live for every message, not
      just one. The non-fatal send contract means this fails safe (swallowed exception, no
      raise into strategy logic) rather than fails loud, but it also means notifications —
      including close/roll alerts used for delta-neutral adjustment decisions — can silently
      stop arriving for as long as the gap lasts. MD-3/MD-4 close that gap but are only
      "blocked by" MD-2, not bundled with it, and the one-task-per-session protocol does not
      guarantee they land soon after. **Do not merge MD-2 unless MD-3 and MD-4 are ready to
      follow in the same sitting** — do not leave MD-2 merged on its own between sessions.
      **Status (2026-08-24): MD-2 landed alone, SHA `721daf9`** — Animesh explicitly chose the
      one-task-per-session protocol over bundling MD-3/MD-4 into the same sitting (asked/
      confirmed at session start), fully aware of the live-risk window above. **The gap is
      currently open in production: every existing caller's dynamic values are unescaped
      against MarkdownV2.** MD-3 and MD-4 are next up and should be treated as urgent, not
      routine backlog — pick them up before anything else in this epic or elsewhere.
- [x] **MD-3** (62d0172) — Audit + fix strategy close/roll notifications (7 classes) for unescaped dynamic
      values | Blocked by: MD-2
      | Owner: Antigravity | Model: n/a | Review: **real @code-reviewer, Opus — mandatory**
      (financial-logic close-notification paths per AutoTrigger table). Mechanical per-class
      audit-and-fix with a fully unambiguous spec — good Antigravity fit — but the Opus gate
      applies regardless of implementer.
- [x] **MD-4** — Umbrella: audit + fix all remaining unescaped `TelegramGateway` surfaces
      (reporting, entry, gateway parse_mode, approval-request) | Blocked by: MD-2 | Split into
      MD-4.1 / MD-4.2 / MD-4.3 below (2026-08-25) — track completion on the sub-tasks, not this
      line; check this box only once all three are done.
      | **Scope expanded 2026-08-25 (Animesh, explicit decision — not Antigravity-initiated):**
      original scope was the 3 reporting builders only. Cowork review (Claude) surfaced that
      `TelegramGateway.send_notification` was still hardcoded to `parse_mode: HTML` — escaping
      dynamic values in the 3 reporting builders without migrating the gateway itself would have
      corrupted output (literal backslashes rendered, since HTML mode never strips MarkdownV2
      escaping). Further review found `send_notification` is also called from
      `paper_ic_entry.py` and `paper_ic_entry_v2.py` (entry-signal alerts) — migrating the
      gateway's parse_mode without escaping those two callers in the same sitting would recreate
      MD-2's live-risk-window bug for entry notifications. Animesh chose to fold the gateway
      migration and both entry scripts into MD-4 rather than spin off a blocking sub-task.

- [x] **MD-4.1** (Commit: cd1e554) — Flip `TelegramGateway.send_notification` from `parse_mode: HTML` to
      `MarkdownV2` (`src/notifications/telegram_gateway.py`) | Blocked by: MD-2
      | **Owner: ANTIGRAVITY** | Model: n/a | Review: code-reviewer — mechanical, but touches a
      shared gateway method with 5 live call sites (3 reporting scripts in MD-4.2 + 2 entry
      scripts in MD-4.2); the reviewer must verify all 5 callers are escaped and land in the
      **same commit/sitting** as MD-4.2 — landing MD-4.1 alone reopens the exact live-risk-window
      bug called out on MD-2 (unescaped dynamic values sent through a parser that now enforces
      reserved characters). Do not merge MD-4.1 without MD-4.2 ready to follow immediately.
      | Tests: `tests/unit/notifications/test_telegram_gateway.py`

- [x] **MD-4.2** (Commit: cd1e554) — Apply `escape_markdown`/`mdcode` to all dynamic values + static punctuation
      in the 5 reporting/entry scripts that call `TelegramGateway.send_notification` | Blocked
      by: MD-4.1 (must land together, see note above)
      | **Owner: ANTIGRAVITY** | Model: n/a | Review: code-reviewer — mechanical escaping pass,
      no auth/judgment
      | Files:
      — `paper_ic_snapshot.py` (`process_variant`, `get_action_taken`)
      — `paper_ic_monthly_comparison.py` (`build_comparison_report` + `fmt_*` helpers)
      — `paper_3track_snapshot.py` (`_build_recovery_digest` only — other `notifier.send()` call
      sites in that file are explicitly out of scope, tracked separately, not closed by this)
      — `paper_ic_entry.py` (entry-signal notifications, ~L743/~L806)
      — `paper_ic_entry_v2.py` (entry-signal notifications, ~L663/~L725)
      | Tests: `tests/unit/strategies/ic/test_paper_ic_snapshot.py`,
      `tests/unit/strategies/ic/test_paper_ic_monthly_comparison.py`,
      `tests/unit/scripts/test_paper_3track_protection_recovery.py`,
      `tests/unit/strategies/ic/test_paper_ic_entry.py`,
      `tests/unit/strategies/ic/test_paper_ic_entry_v2.py`

- [x] **MD-4.3** (Commit: aa58f44) — Escape `TelegramGateway.send_approval_request` for unescaped dynamic values
      | Blocked by: MD-2 (independent of MD-4.1/MD-4.2 — different method, different
      `parse_mode` already on its own line, not touched by the send_notification migration)
      | **Owner: CLAUDE** | Model: Sonnet | Review: **real @code-reviewer, Opus — mandatory** —
      auth-sensitive interactive-keyboard path, requires live coordination-check against
      `telegram-approval-auth-fix` before touching; real-time judgment, not delegate-and-forget.
      **Unaffected by the MD-4.1/4.2 scope expansion** — `send_approval_request` already
      hardcodes its own `parse_mode: HTML` independently of `send_notification` and is not
      touched by those two sub-tasks.
      | Tests: TBD at implementation time (coordination-check with `telegram-approval-auth-fix`
      may dictate test shape)
- [x] **MD-6** (SHA: ce95bbd) — Add a static-scan escaping guard: a test that walks `src/`/`scripts/` for
      `notifier.send(`/`send_plain_message(` call sites and asserts every interpolated dynamic
      value passed through `escape_markdown()`/`mdcode()` somewhere upstream | Blocked by:
      MD-3, MD-4.1, MD-4.2, MD-4.3
      | Owner: Claude | Model: Sonnet | Review: code-reviewer — design judgment on what counts
      as "escaped" (AST-based vs. regex call-site detection, false-positive handling).
      **Sequencing note (corrected 2026-08-12):** an earlier session proposed sequencing this
      right after MD-2, before MD-3/MD-4. That was wrong — MD-3/MD-4 are the audit-and-fix pass
      that actually escapes the 11 currently-unescaped call sites; a guard test introduced
      before they land would immediately fail against the codebase it's supposed to protect.
      Correct position is after both audits complete, so the guard starts from a clean baseline
      and then protects every `send()` call site added afterward — including all of
      `formatting-rules/`'s and `strategy-rollout/`'s new call sites, since `backbone/` must be
      fully complete before either of those can start regardless.
- [ ] **MD-7** — Umbrella: escape gaps `MD-6`'s guard surfaced but no prior MD-*/ROLL-*
      task named | Blocked by: MD-6 | Split into MD-7.1 / MD-7.2 / MD-7.3 below (2026-08-25,
      split at Animesh's request — too many unrelated files for one session) — track completion
      on the sub-tasks, not this line; check this box only once all three are done.
      **Live-risk framing (same class as MD-2/MD-3/MD-4):** every sub-task's call sites are
      unescaped dynamic values in `.send()`/`.send_plain_message()` calls live in production
      today, not hypothetical future call sites — same DELTA_WARN failure shape (silent 400,
      swallowed by the non-fatal send contract) sitting unaddressed in currently-running code.
      **`scripts/dev/send_test_telegram.py:65` — confirmed out of scope (2026-08-25, Animesh):**
      manual dev/debug utility, invoked ad hoc by whoever's testing, not a cron or strategy event
      path. Stays a documented won't-fix in MD-6's `_BASELINE_UNESCAPED`
      (`tests/unit/notifications/test_escaping_guard.py`) — reason string updated to record the
      explicit decision, not fixed by any MD-7.x sub-task.

- [ ] **MD-7.1** — `scripts/pre_market_brief.py` — both `gateway.send_plain_message()` calls
      (~L144, ~L197) | Blocked by: MD-6
      | Owner: Antigravity | Model: n/a | Review: code-reviewer — single file, mechanical
      escaping pass, no auth/judgment
      | Tests: `tests/unit/scripts/test_pre_market_brief.py`

- [ ] **MD-7.2** — `_gate_alert` in `scripts/strategies/ic/paper_ic_entry.py` (~L255) and
      `paper_ic_entry_v2.py` (~L313) — separate path from the `send_notification()` calls MD-4.2
      already escaped in these two files | Blocked by: MD-6
      | Owner: Antigravity | Model: n/a | Review: code-reviewer — mechanical, same pattern
      MD-4.2 already applied elsewhere in both files
      | Tests: `tests/unit/strategies/ic/test_paper_ic_entry.py`,
      `tests/unit/strategies/ic/test_paper_ic_entry_v2.py`

- [ ] **MD-7.3** — `src/strategy/auto_close.py` (`auto_close_overlay` ~L235,
      `evaluate_pp_reentry_eod` ~L404, both outside MD-3's `_send_close_notification`-only scope)
      and `src/strategy/overlay_closer.py` (`close_collar_all` ~L268, `monetize_collar_put`
      ~L328/~L392) | Blocked by: MD-6
      | Owner: Claude | Model: Sonnet | Review: **real @code-reviewer, Opus — mandatory** —
      close/monetize paths for live overlay strategies, same financial-logic tier as MD-3's
      close-notification audit per root `CLAUDE.md`'s AutoTrigger table, even though this task
      is escaping-only and doesn't touch P&L computation itself
      | Tests: `tests/unit/strategy/test_auto_close.py`, `tests/unit/strategy/test_overlay_closer.py`

**All three MD-7.x sub-tasks:** same two-pass escaping treatment as MD-3/MD-4 (dynamic values
via `mdcode()`/`escape_markdown()`, static template punctuation checked too). Remove each fixed
call site's entry from MD-6's `_BASELINE_UNESCAPED` in the same commit as its fix —
`test_baseline_entries_are_still_unescaped`/`test_baseline_has_no_duplicate_or_unused_entries`
in `tests/unit/notifications/test_escaping_guard.py` will fail otherwise, per that file's
maintenance contract.

- [ ] **MD-5** — Docs close: `src/notifications/CLAUDE.md`, `DECISIONS.md`, `CONTEXT.md`,
      `TODOS.md` | Blocked by: MD-3, MD-4.1, MD-4.2, MD-4.3, MD-6, MD-7.1, MD-7.2, MD-7.3
      | Owner: Antigravity | Model: n/a | Review: none (docs only) — also document MD-6's guard
      contract and MD-7.1/MD-7.2/MD-7.3's fixes in `src/notifications/CLAUDE.md` alongside the escaping-helper rule
