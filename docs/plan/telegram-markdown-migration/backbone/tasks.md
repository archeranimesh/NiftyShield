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

- [ ] **MD-1** — Add `escape_markdown()` / `mdcode()` helpers to `src/notifications/` + tests
      | Owner: Claude | Model: Sonnet | Review: code-reviewer (not financial-logic tier) —
      foundational correctness (Unicode/empty-string edge cases) warrants inline judgment over
      pure mechanical delegation
- [ ] **MD-2** — Switch `TelegramNotifier.send()` to Markdown parse_mode; update/replace the two
      HTML-specific tests; add an entity-parse regression test | Blocked by: MD-1
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
- [ ] **MD-3** — Audit + fix strategy close/roll notifications (7 classes) for unescaped dynamic
      values | Blocked by: MD-2
      | Owner: Antigravity | Model: n/a | Review: **real @code-reviewer, Opus — mandatory**
      (financial-logic close-notification paths per AutoTrigger table). Mechanical per-class
      audit-and-fix with a fully unambiguous spec — good Antigravity fit — but the Opus gate
      applies regardless of implementer.
- [ ] **MD-4** — Audit + fix reporting scripts + `send_approval_request` for unescaped dynamic
      values | Blocked by: MD-2
      | **Split by risk:**
      — `paper_ic_snapshot.py`, `paper_ic_monthly_comparison.py`, `_build_recovery_digest`:
      Owner: Antigravity | Model: n/a | Review: code-reviewer — mechanical escaping pass, no
      auth/judgment
      — `TelegramGateway.send_approval_request`: Owner: Claude | Model: Sonnet | Review:
      **real @code-reviewer, Opus — mandatory** — auth-sensitive interactive-keyboard path,
      requires live coordination-check against `telegram-approval-auth-fix` before touching;
      real-time judgment, not delegate-and-forget
- [ ] **MD-6** — Add a static-scan escaping guard: a test that walks `src/`/`scripts/` for
      `notifier.send(`/`send_plain_message(` call sites and asserts every interpolated dynamic
      value passed through `escape_markdown()`/`mdcode()` somewhere upstream | Blocked by:
      MD-3, MD-4
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
- [ ] **MD-5** — Docs close: `src/notifications/CLAUDE.md`, `DECISIONS.md`, `CONTEXT.md`,
      `TODOS.md` | Blocked by: MD-3, MD-4, MD-6
      | Owner: Antigravity | Model: n/a | Review: none (docs only) — also document MD-6's guard
      contract in `src/notifications/CLAUDE.md` alongside the escaping-helper rule
