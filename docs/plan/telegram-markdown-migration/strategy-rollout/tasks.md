# Telegram Markdown Migration — Strategy Rollout — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/telegram-markdown-migration/strategy-rollout/stories.md`.
> Sequenced by risk: informational-only messages first, live position-event notifications
> next, auth-sensitive interactive messages last.

> **Routing (added 2026-08-12, Cowork design-review session):** `Owner` is who implements —
> `Claude` for judgment-call/exploratory work, `Antigravity` for mechanical multi-file work with
> an unambiguous spec. `Model` is the model the owner should run at. `Review` is the mandatory
> gate per root `CLAUDE.md`'s Agent AutoTrigger table. Routing is a recommendation to
> re-confirm at session start, not a hard override of the AutoTrigger table.
>
> **Parallelization note:** `ROLL-7` through `ROLL-16` are each blocked only on
> "`backbone/` + `formatting-rules/` complete," not on each other, despite the linear
> find-first-unchecked-box protocol above. None of them share a touched file **except**
> `ROLL-15` and `ROLL-16`, which both touch `paper_3track_snapshot.py` and must stay sequential
> relative to each other. Everything else in that range can run as separate parallel
> sessions/agents instead of one queue — see epic improvement notes (pending).

---

- [x] **ROLL-0** (SHA: f9e551e) — Capture long-leg delta + theta and compute Net Δ/Net θ in the IC EOD audit
      (`scripts/strategies/ic/paper_ic_snapshot.py::process_variant`) — data-only, plain-text
      report line, no Markdown/parse_mode dependency | Blocked by: none
      | Owner: Claude | Model: Sonnet | Review: **greeks-analyst — mandatory** (any change to
      delta/theta/Greeks fields triggers this per AutoTrigger table regardless of change size).
      Substituted a general-purpose agent loaded with the greeks-analyst persona (same structural
      limitation as MD-7.3/BUG-037 B037.6 — this Cowork session cannot spawn `.claude/agents/*`
      directly). Verdict: PASS with one documented WARNING (Net Δ sums raw per-option delta with
      no short/long position-direction sign flip — pre-existing convention this diff extends, not
      a new defect; matches the never-partial-sum reference implementation in
      `scratch/2026-08-07_ic_eod_audit_v2_telegram_format.py` verbatim). Not fixed here — flagged
      as a fast-follow label-clarification candidate, not a blocker.
- [x] **ROLL-1** — Migrate IC EOD audit (`scripts/strategies/ic/paper_ic_snapshot.py`) to the
      new format, including the FMT-1c timeframe color/emoji/hashtag header (all 5 active
      variants: V1 weekly/monthly/leaps/yearly + V2 monthly) | Blocked by: `backbone/` +
      `formatting-rules/` complete (data sources: `ROLL-0` for Net Δ/θ, `FMT-1c` for the header —
      both soft dependencies, see `ROLL-1`'s spec for what happens if sequencing is reversed)
      | Owner: Claude | Model: Sonnet | Review: none — 5-variant header rendering across
      timeframe/version combos needs real formatting judgment, not delegation
      **Split into 3 independently-tracked/committed sub-tasks (2026-08-25) — FMT-1b/FMT-1c
      were speced in FORMATTING.md §10/§11 but never promoted to code (confirmed via git log:
      commit bb95a54 was docs-only), so ROLL-1 as originally scoped silently depended on two
      un-shipped prerequisites. Splitting makes each piece its own traceable commit instead of
      bundling the prereq promotion invisibly inside the ROLL-1 port commit.**
    - [x] **ROLL-1a** (SHA: b05587b) — Promote FMT-1b: add `pnl_emoji`/`alert_emoji` to
          `src/notifications/formatting.py` + tests in `tests/unit/notifications/test_formatting.py`
          (presence/sign-based per FORMATTING.md §10, ported from
          `scratch/2026-08-07_ic_eod_audit_v2_telegram_format.py`) | Blocked by: none (FMT-1b spec
          already final) | Owner: Claude | Model: Sonnet | Review: none
    - [x] **ROLL-1b** (SHA: 94dba89) — Promote FMT-1c: add `build_header()` + `_TIMEFRAME_META`/`VARIANT_META` to
          `scripts/strategies/ic/paper_ic_snapshot.py` (colocated with `process_variant`, per
          FORMATTING.md §11's location judgment call) + tests in
          `tests/unit/strategies/ic/test_paper_ic_snapshot.py` (one per timeframe + V1-implicit/
          V2-badge + hashtag-not-in-code-span) | Blocked by: ROLL-1a (imports nothing from it
          directly, but sequenced after so both prereqs land before the port) | Owner: Claude |
          Model: Sonnet | Review: none
    - [x] **ROLL-1c** (SHA: f605b92) — The actual ROLL-1 port: rewrite `process_variant()`'s report construction
          to the new bold/table MarkdownV2 format using `ROLL-1a`'s emoji helpers, `ROLL-1b`'s
          header, and the already-shipped `build_leg_table`/`format_money`/`format_greek`/
          `format_strike`/`format_pct` (FMT-2/FMT-3) — full spec in `stories.md` ROLL-1 | Blocked
          by: ROLL-1a, ROLL-1b | Owner: Claude | Model: Sonnet | Review: none — 5-variant header
          rendering across timeframe/version combos needs real formatting judgment, not delegation
- [x] **ROLL-2** — Migrate IC monthly comparison report
      (`scripts/strategies/ic/paper_ic_monthly_comparison.py`) to a single fenced comparison
      table; adds Legs row (`open_pos`, already available), Bkd P&L (I) (via
      `get_strategy_realized_pnl()` — NOT `paper_nav_snapshots.realized_pnl`'s raw row, which
      resets on a close/reopen cycle per `CONTEXT.md` SNAP-1), and Flt P&L (M) (genuinely new
      `_get_unrealized_pnl_month_change()`, must differ from Flt (I) — see stories.md for why).
      Hand-counted width bug already fixed (TGFMT-1, SHA `a69d817`) — not this task's job.
      | Blocked by: ROLL-1
      | Owner: Claude | Model: **Opus (design review recommended before writing code)** |
      Review: **real @code-reviewer, Opus — mandatory**. The Bkd/Flt P&L sourcing distinction
      is explicitly flagged as easy to get wrong (must differ from Flt(I)) — the one task in
      this epic worth a second opinion before implementation, not just at the commit gate.
      **Split into 3 independently-tracked/committed sub-tasks (2026-08-26, Cowork design-review
      session) — same shape as ROLL-1's split. `build_compare_table`, the row-groups fenced-table
      builder this task's confirmed layout requires, exists ONLY in
      `scratch/2026-08-07_ic_monthly_comparison_telegram_format.py` and was never promoted to
      `src/notifications/formatting.py` (confirmed via `search_graph` 2026-08-26 — FMT-3 shipped
      `build_kv_table`/`build_side_by_side_kv_table`/`build_leg_table` and used
      `build_compare_table` only as a design reference, see TODOS.md's FMT-3 entry). A
      formatting-layer addition riding invisibly inside a strategy-rollout port commit is exactly
      the ROLL-1a/1b shape. Second reason: the P&L sourcing half has real open questions (see
      `stories.md`'s 2026-08-26 design-review block) that must not gate the mechanical
      Legs-row/table plumbing.**
      **Not a must-land-together group** — unlike MD-4.1/MD-4.2, no sub-task here opens a
      live-risk window on its own: ROLL-2a adds an unreferenced new helper, ROLL-2b adds fields
      nothing renders yet, and only ROLL-2c changes what Telegram actually sends. Each may land as
      its own commit.
    - [x] **ROLL-2a** (SHA: 3cec4e1) — Promote `build_compare_table` into `src/notifications/formatting.py`
          (generic row-groups builder over `list[list[tuple[label, v1, v2]]]`, dashed rule between
          groups, every width via `max(len(...))` and never a hand-counted constant) + tests in
          `tests/unit/notifications/test_formatting.py` | Blocked by: none
          | Owner: Claude | Model: Sonnet | Review: none — but per FMT-3's standing note, do not
          delegate the width computation: this is the exact code path the TGFMT-1
          hand-counted-width bug lived in.
          **Blocking pre-check for Animesh before implementation** — the builder's width contract
          depends on whether cells may hold non-ASCII. `FORMATTING.md` §7 (FMT-1e) records `₹`
          U+20B9 inside a fence as **unverified** and lists `Δ` U+0394 as the only confirmed
          exception; ROLL-2's confirmed 2026-08-07 layout puts `₹` inside the fence, and the new
          Legs row wants a `🔴` suffix inside the fence, which no on-device confirmation covers at
          all. Needs one live `--send` check, then `FORMATTING.md` §7's table updated with the
          result. If either glyph renders double-width, `max(len(...))` is the wrong width function
          and this builder needs a display-width helper — that is a design input to ROLL-2a, not a
          post-hoc fix to it.
    - [x] **ROLL-2b** — P&L sourcing: `Bkd (I)` + `Flt (M)`. **Reconciliation gate CLOSED
          2026-08-26 (Cowork session, Animesh decided all three) — split into ROLL-2b-i /
          ROLL-2b-ii below; track completion on the sub-tasks, check this box only once both
          are done.** Decisions, binding on both sub-tasks — do not re-litigate:
          **(1) Consume, don't duplicate.** Extend `PnLReport`/`build_pnl_report`
          (`scripts/reporting/paper_pnl_report.py`) with `unrealized_this_month` and have the
          IC comparison consume one report object; delete the local `_get_monthly_realized_pnl`
          /`_get_unrealized_pnl` raw-`sqlite3` helpers. No promotion into `src/reporting/` this
          task — script-to-script import accepted.
          **(2) Uniform row selection: latest snapshot row at or before `as_of`, for every
          aggregate.** Never exact equality on the date. This is what stops `Flt (I)` and
          `Flt (M)` diverging on a holiday or a pre-15:36-cron run.
          **(3) `Bkd (M)` cycle-reset gap: knowingly accepted, recorded not fixed.** It keeps
          reading `paper_nav_snapshots.realized_pnl` while `Bkd (I)` is routed off it. Recorded
          in `paper_pnl_report.py`'s module docstring. Its own task if it is ever fixed.
          **Model re-routed Opus → Sonnet:** the five open judgment calls that justified Opus
          are closed by the decisions above; what remains is contract plumbing. The
          `@code-reviewer` gate is unchanged and still applies to both sub-tasks.
          | Blocked by: none (independent of ROLL-2a)
    - [x] **ROLL-2b-i** (SHA: e59abb9 | split docs: b566cee) — Contract change: add `unrealized_this_month` to `PnLReport`, bound
          every snapshot read by `as_of` (was `snapshots[-1]` unconditionally), record decision
          (3) in the module docstring | Blocked by: none — nothing consumes the new field yet,
          so this lands safely alone (no live-risk window)
          | Owner: Claude | Model: Sonnet | Review: **real @code-reviewer, Opus — mandatory** —
          the parent's P&L-adjacent gate travels here
          | Files: `scripts/reporting/paper_pnl_report.py`,
          `tests/unit/reporting/test_paper_pnl_report.py` (2 files → Claude per root
          `CLAUDE.md` Step 3b)
    - [x] **ROLL-2b-ii** (SHA: d2741fb) — Consume it: `ICMonthlyStats` += `inception_realized_pnl`,
          `unrealized_pnl_month_change`; `build_stats()` calls `build_pnl_report(store,
          strategy_name, as_of=today)` once and drops both local helpers | Blocked by: ROLL-2b-i
          | Owner: Claude | Model: Sonnet | Review: **real @code-reviewer, Opus — mandatory**
          | Files: `scripts/strategies/ic/paper_ic_monthly_comparison.py`,
          `tests/unit/strategies/ic/test_paper_ic_monthly_comparison.py`
          **Routing note:** 2 files → Claude by Step 3b's file-count rule, but mechanical
          against a locked contract → Antigravity by Step 3b's nature rule. The rule does not
          resolve it; routed Claude on file count (Animesh, 2026-08-26). Re-route to Antigravity
          freely if convenient — the contract is locked, nothing here is a judgment call.
          Deliberately NOT folded into ROLL-2c despite touching the same two files: that would
          put P&L sourcing back inside a port commit, which is exactly what the 2026-08-26
          review split ROLL-2 to prevent.
          **Spec drift found 2026-08-26 — RESOLVED by ROLL-2b's three decisions above; kept
          here as the record of what was wrong and why** (full detail in
          `stories.md`): (1) SNAP-4 already shipped
          `scripts/reporting/paper_pnl_report.py::build_pnl_report()` -> `PnLReport`, a pure tested
          function already computing `realized_since_inception` (= `Bkd (I)`, via
          `get_strategy_realized_pnl`), `realized_this_month` (= `Bkd (M)`) and
          `unrealized_since_inception` (= `Flt (I)`); ROLL-2's spec predates it and re-derives all
          three locally. (2) `_get_unrealized_pnl` queries `snapshot_date = today` (exact equality)
          while `_get_monthly_realized_pnl` queries `snapshot_date <= today ORDER BY DESC LIMIT 1`
          — mirroring the latter blindly makes `Flt (I)` and `Flt (M)` read different rows on any
          day with no snapshot. (3) `Bkd (M)` stays on `paper_nav_snapshots.realized_pnl`, the same
          cycle-resetting column SNAP-1 flags and ROLL-2 corrects `Bkd (I)` away from — fix it or
          record it as accepted, don't leave it silent. `get_strategy_realized_pnl(store,
          strategy_name) -> Decimal` confirmed unchanged 2026-08-26.
          Resolution: (1) -> decision (1) consume `PnLReport`; (2) -> decision (2) uniform
          latest-row-at-or-before-`as_of`; (3) -> decision (3) recorded as accepted.
    - [x] **ROLL-2c** (SHA: a2fbe31) — The port itself: `build_comparison_report()` -> one fenced row-groups table
          via ROLL-2a's builder + MarkdownV2 `parse_mode`; Legs row (`len(open_pos)` threaded
          through `build_stats()` into `ICMonthlyStats.open_leg_count`, rendered `n/4` with a `🔴`
          suffix when `n < 4` — `open_pos` confirmed still `build_stats()`'s first line,
          2026-08-26); render ROLL-2b's `Bkd (I)`/`Flt (M)`; all tests listed in `stories.md`
          | Blocked by: ROLL-2a, ROLL-2b
          | Owner: Antigravity | Model: n/a | Review: **real @code-reviewer, Opus — mandatory** —
          mechanical once 2a/2b land, but it renders P&L values, so the financial-logic gate
          applies here as well as on 2b.
- [ ] **ROLL-3** — Migrate strategy close/roll notifications (7 classes, same list as
      backbone MD-3) to the new format where it adds value | Blocked by: ROLL-2
      | Owner: Antigravity | Model: n/a | Review: **real @code-reviewer, Opus — mandatory**
      — same shape as MD-3, mechanical per-class once ROLL-2's format is locked, financial-logic
      gate still applies
- [ ] **ROLL-4** — Migrate approval-request message formatting
      (`TelegramGateway.send_approval_request`) — coordinate with
      `telegram-approval-auth-fix` first | Blocked by: ROLL-3
      | Owner: Claude | Model: Sonnet | Review: **real @code-reviewer, Opus — mandatory** —
      auth + interactive keyboard, explicit coordination-check requirement, no delegate-and-forget
- [ ] **ROLL-6** — Migrate EOD Paper Summary (`scripts/eod_summary.py`) to
      `TelegramNotifier.send()` + MarkdownV2 — not in the epic's original confirmed-callers
      list (currently sends via raw HTML, missed by `backbone/`'s audit); v2 format confirmed
      2026-08-08 on-device (4 buckets — Track/IC/Overlay/CSP, 12 strategies total —
      totals-first subtotal rows, `FMT-1d` integer-money exception + zero-as-`-`, `FMT-1e`
      ASCII-only-inside-fence rule, `Bkd` sourced from `get_strategy_realized_pnl()`
      since-inception not the resettable snapshot column, `#EOD_SUMMARY` tag after the fence)
      | Blocked by: `backbone/` + `formatting-rules/` complete (same soft deps as other ROLL
      tasks) — financial-logic commit note: `Bkd` sourcing is P&L-adjacent, real
      `@code-reviewer` required
      | Owner: Claude | Model: Sonnet | Review: **real @code-reviewer, Opus — mandatory**
      (per the task's own P&L-adjacent note)
- [ ] **ROLL-7** — Migrate re-entry blocked/eligible notice
      (`src/strategy/reentry_mixin.py::ReEntryMixin._check_reentry`) to a kv-line MarkdownV2
      format; not in the epic's original confirmed-callers list (surfaced via
      `missing-message-workshop-prompt.md`, TODO.md item 1); requires refactoring the three
      gates' `blocked_reason` construction into structured `(short_reason, detail)` pairs plus
      new `STRATEGY_LABELS`/`LEG_ROLE_LABELS` display mappings — see stories.md for why neither
      is a drop-in escaping change | Blocked by: `backbone/` + `formatting-rules/` complete
      (same soft deps as other ROLL tasks)
      | Owner: Claude | Model: Sonnet | Review: none — real refactor (blocked_reason →
      structured pairs), spec explicitly says it's not a drop-in. Parallelizable with ROLL-8
      through ROLL-16 except ROLL-15/16 (see parallelization note above); ROLL-8 depends on the
      label tables this task defines, so keep those two sequential relative to each other.
- [ ] **ROLL-8** — Migrate generic strategy WARN event alert
      (`src/strategy/monitor.py::StrategyMonitor._route_event` WARN branch) to a v2
      cause-\>effect compact MarkdownV2 format (headline + optional Leg: line + description;
      supersedes an initial kv-line draft from the same session); not in the epic's original
      confirmed-callers list (surfaced via `missing-message-workshop-prompt.md`, TODO.md item
      2); reuses `ROLL-7`'s `STRATEGY_LABELS`/`LEG_ROLE_LABELS` tables, no new formatting rule;
      severity emoji is deliberately fixed (`⚠️`, never tiered) since this code path only ever
      carries WARN-severity events | Blocked by: `backbone/` + `formatting-rules/` complete
      (same soft deps as other ROLL tasks)
      | Owner: Antigravity | Model: n/a | Review: none — mechanical reuse of ROLL-7's tables,
      fixed severity, no new design. Sequenced after ROLL-7 (real dependency on its label
      tables), otherwise parallelizable.
- [ ] **ROLL-9** — Migrate three-track base-leg roll notification
      (`scripts/strategies/three_track/paper_3track_roll.py::_notify_roll`) to two
      leg-role-specific MarkdownV2 layouts (base_futures: NIFTY FUT header + Contango/
      Backwardation spread; base_ditm_call: strike-bearing ticket line + Debit/Credit spread),
      adds closed-leg realized P&L and month labels; not in the epic's original
      confirmed-callers list (surfaced via `missing-message-workshop-prompt.md`, TODO.md item
      3) | Blocked by: `backbone/` + `formatting-rules/` complete (same soft deps as other
      ROLL tasks)
      | Owner: Claude | Model: Sonnet | Review: code-reviewer (P&L-adjacent: displays
      closed-leg realized P&L). Two distinct layouts, moderate judgment. Parallelizable.
- [ ] **ROLL-10** — Migrate Proxy Delta CRITICAL alert
      (`scripts/dev/paper_track_snapshot.py::main`, CRITICAL branch) to a 3-line emoji-labeled
      MarkdownV2 format (📐 Current / 📉 Rule Breach); not in the epic's original
      confirmed-callers list (surfaced via `missing-message-workshop-prompt.md`, TODO.md item
      4); requires a small `TrackSnapshot`/`generate_track_snapshot` data-plumbing addition
      (expose `consecutive_days`) before the `Rule Breach:` line can be split into structured
      fields — currently ships as the verbatim `proxy_delta_alert` string, see stories.md for
      why splitting now would be premature | Blocked by: `backbone/` + `formatting-rules/`
      complete (same soft deps as other ROLL tasks)
      | Owner: Claude | Model: Sonnet | Review: none — small dataclass field addition, low risk
      but touches a model, keep it out of Antigravity. Parallelizable; ROLL-16 reuses this
      task's output, so land this before ROLL-16 for the shared-builder follow-up even though
      the task list doesn't hard-block it.
- [ ] **ROLL-11** — Migrate System Healthcheck alert (`scripts/healthcheck.py::main`) to a
      grouped severity-status MarkdownV2 format (`DEGRADED [HH:MM]` headline, `ACTION REQUIRED`
      issue lines, `SYSTEMS NORMAL` pass summary); not in the epic's original confirmed-callers
      list (surfaced via `missing-message-workshop-prompt.md`, TODO.md item 5); requires
      refactoring `run_checks()` to return structured `CheckResult` objects instead of
      pre-formatted strings — see stories.md for why a drop-in re-render isn't possible | Blocked
      by: `backbone/` + `formatting-rules/` complete (same soft deps as other ROLL tasks)
      | Owner: Claude | Model: Sonnet | Review: none — real architecture change
      (`run_checks()` → structured `CheckResult`), spec flags why a drop-in isn't possible.
      Parallelizable.
- [ ] **ROLL-12** — Migrate Position Health check alert
      (`scripts/position_health_check.py::main`) to a grouped-by-finding-type MarkdownV2 format
      (`ROLLS OVERDUE` 🚨 rows sorted days-overdue descending, `UNMAPPED ASSET` ⚠️ rows); not in
      the epic's original confirmed-callers list (surfaced via
      `missing-message-workshop-prompt.md`, TODO.md item 6); requires refactoring
      `run_position_checks()` to return structured `PositionFinding` objects instead of
      pre-formatted strings, and reuses `format_option_label()` (already shipped,
      `src/instruments/lookup.py`) plus the `STRATEGY_LABELS` display-name table ROLL-7/ROLL-8
      already define — see stories.md for the full elimination trail (v1 raw-key draft ->
      v2 resolved-label draft -> v3 confirmed restructure) | Blocked by: `backbone/` +
      `formatting-rules/` complete (same soft deps as other ROLL tasks)
      | Owner: Antigravity | Model: n/a | Review: none — multi-file but fully speced (v1→v2→v3
      already resolved in workshop), reuses existing label tables — mechanical despite the
      refactor shape. Real dependency on ROLL-7's label tables; otherwise parallelizable.
- [ ] **ROLL-13** — Migrate 3-track base entry bootstrap notification
      (`scripts/strategies/three_track/paper_3track_entry.py::main`) to a per-leg emoji-
      prefixed MarkdownV2 kv format with resolved human-readable instrument labels (`NIFTY
      DEC FUT`, `NIFTY DEC 24500 CE`) instead of raw broker keys; not in the epic's original
      confirmed-callers list (surfaced via `missing-message-workshop-prompt.md`, TODO.md item
      7 — item 7's overlay-bootstrap half, `paper_3track_overlay_entry.py`, is a separate
      structurally-distinct message, still queued as TODO.md item 7's second half, not this
      task) | Blocked by: `backbone/` + `formatting-rules/` complete (same soft deps as other
      ROLL tasks)
      | Owner: Antigravity | Model: n/a | Review: code-reviewer (first-of-epic live-tested
      escaping edge cases per MD-1's addendum — keep review close even though implementation is
      mechanical). Fully speced from workshop, single file. Parallelizable.
- [ ] **ROLL-14** — Migrate 3-track overlay entry bootstrap notification
      (`scripts/strategies/three_track/paper_3track_overlay_entry.py::main`) to a per-leg
      direction-coded (🟢 Long / 🔴 Short) MarkdownV2 kv format with resolved human-readable
      instrument labels, covering all three overlay types (pp/cc/collar) and the optional
      gate-violation trailer line; not in the epic's original confirmed-callers list (surfaced
      via `missing-message-workshop-prompt.md`, TODO.md item 7 — second half; item 7's
      base-entry half is `ROLL-13`) | Blocked by: `backbone/` + `formatting-rules/` complete
      (same soft deps as other ROLL tasks)
      | Owner: Antigravity | Model: n/a | Review: none — same shape as ROLL-13, mechanical.
      Parallelizable.
- [ ] **ROLL-15** — Migrate three-track base position expiry alert
      (`scripts/strategies/three_track/paper_3track_snapshot.py:487-501`) to a compact
      Telegram summary (verb hardcoded `Long` — `base_futures`/`base_ditm_call` never go
      short by strategy design, confirmed by Animesh 2026-08-11), with the settlement-close/
      roll-open shell commands moved to a structured `logger.info` call instead of the
      message body; format CONFIRMED 2026-08-11 via live `--send` review — real
      implementation (message build + new `logger.info` call) still open; not in the epic's
      original confirmed-callers list (surfaced via `missing-message-workshop-prompt.md`,
      TODO.md item 8) | Blocked by: `backbone/` + `formatting-rules/` complete (same soft
      deps as other ROLL tasks)
      | Owner: Antigravity | Model: n/a | Review: none — message rewrite + new logger call,
      mechanical, format already confirmed. **Must stay sequential with ROLL-16** — both touch
      `paper_3track_snapshot.py`; land this one first.
- [ ] **ROLL-16** — Migrate production Proxy Delta CRITICAL alert
      (`scripts/strategies/three_track/paper_3track_snapshot.py::_run`, ~line 1723) to
      `ROLL-10`'s confirmed 3-line MarkdownV2 format, reused verbatim (no track/date line,
      confirmed by Animesh 2026-08-11); known duplicate of `ROLL-10` flagged in that task's
      spec — not in the epic's original confirmed-callers list (surfaced via
      `missing-message-workshop-prompt.md`, TODO.md item 10); once `ROLL-10` ships, check
      whether this call site can just call the same message-builder instead of duplicating it
      | Blocked by: `backbone/` + `formatting-rules/` complete (same soft deps as other ROLL
      tasks); soft-sequence after `ROLL-10` for the shared-builder follow-up
      | Owner: Antigravity | Model: n/a | Review: none — verbatim reuse of ROLL-10's builder,
      about as mechanical as this epic gets. **Must stay sequential with ROLL-15** (same file);
      also real-sequence after ROLL-10 (reuses its output).
- [ ] **ROLL-17** — IC entry confirmation (`paper_ic_entry.py` + `paper_ic_entry_v2.py`)
      shared content model — **DESIGN INCOMPLETE, not spec-locked like other ROLL tasks**;
      6 open decisions listed in `stories.md` (LegRow reuse vs. separate model, union-of-fields
      vs. per-template, `(hedge)` label mechanism, module scope, parse_mode alignment, and
      #6: field-formatter registry must call `FMT-1`/`FMT-2`'s `format_greek()`/`format_money()`
      for value-level formatting rather than re-implementing it — IC-only scope applies to the
      leg *model* only, not to number formatting, which stays epic-wide via `formatting-rules/`)
      must be closed via a `message-format-workshop.md` session before implementation starts;
      surfaced 2026-08-19 (Animesh noticed v1/v2 message drift, then asked why the story is
      IC-only rather than all strategies — answered in `stories.md` and cross-referenced into
      `ROLL-13`/`ROLL-14`'s specs: IC's hedge/wing/mode leg vocabulary doesn't generalize to
      3-track's per-track shape without guessing, but value-level formatting does and must not
      be duplicated) | Blocked by: `backbone/` + `formatting-rules/` complete (same soft deps as
      other ROLL tasks), plus its own open design decisions above (harder gate than the soft
      dep — do not start on backbone/formatting-rules completion alone)
      | Owner: TBD (design session first) | Model: TBD | Review: TBD — depends on which
      decision is picked for open decision #1; revisit routing once design closes.
- [ ] **ROLL-5** — Docs close | Blocked by: ROLL-4, ROLL-6, ROLL-7, ROLL-8, ROLL-9, ROLL-10, ROLL-11, ROLL-12, ROLL-13, ROLL-14, ROLL-15, ROLL-16, ROLL-17
      | Owner: Claude | Model: Sonnet | Review: none — synthesis/aggregation across 13 prior
      tasks needs accurate summarization, not high-stakes judgment; Opus not warranted here
