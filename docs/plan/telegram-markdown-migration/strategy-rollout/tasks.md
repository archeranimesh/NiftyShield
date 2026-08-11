# Telegram Markdown Migration — Strategy Rollout — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/telegram-markdown-migration/strategy-rollout/stories.md`.
> Sequenced by risk: informational-only messages first, live position-event notifications
> next, auth-sensitive interactive messages last.

---

- [ ] **ROLL-0** — Capture long-leg delta + theta and compute Net Δ/Net θ in the IC EOD audit
      (`scripts/strategies/ic/paper_ic_snapshot.py::process_variant`) — data-only, plain-text
      report line, no Markdown/parse_mode dependency | Blocked by: none
- [ ] **ROLL-1** — Migrate IC EOD audit (`scripts/strategies/ic/paper_ic_snapshot.py`) to the
      new format, including the FMT-1c timeframe color/emoji/hashtag header (all 5 active
      variants: V1 weekly/monthly/leaps/yearly + V2 monthly) | Blocked by: `backbone/` +
      `formatting-rules/` complete (data sources: `ROLL-0` for Net Δ/θ, `FMT-1c` for the header —
      both soft dependencies, see `ROLL-1`'s spec for what happens if sequencing is reversed)
- [ ] **ROLL-2** — Migrate IC monthly comparison report
      (`scripts/strategies/ic/paper_ic_monthly_comparison.py`) to a single fenced comparison
      table; adds Legs row (`open_pos`, already available), Bkd P&L (I) (via
      `get_strategy_realized_pnl()` — NOT `paper_nav_snapshots.realized_pnl`'s raw row, which
      resets on a close/reopen cycle per `CONTEXT.md` SNAP-1), and Flt P&L (M) (genuinely new
      `_get_unrealized_pnl_month_change()`, must differ from Flt (I) — see stories.md for why).
      Hand-counted width bug already fixed (TGFMT-1, SHA `a69d817`) — not this task's job.
      | Blocked by: ROLL-1
- [ ] **ROLL-3** — Migrate strategy close/roll notifications (7 classes, same list as
      backbone MD-3) to the new format where it adds value | Blocked by: ROLL-2
- [ ] **ROLL-4** — Migrate approval-request message formatting
      (`TelegramGateway.send_approval_request`) — coordinate with
      `telegram-approval-auth-fix` first | Blocked by: ROLL-3
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
- [ ] **ROLL-7** — Migrate re-entry blocked/eligible notice
      (`src/strategy/reentry_mixin.py::ReEntryMixin._check_reentry`) to a kv-line MarkdownV2
      format; not in the epic's original confirmed-callers list (surfaced via
      `missing-message-workshop-prompt.md`, TODO.md item 1); requires refactoring the three
      gates' `blocked_reason` construction into structured `(short_reason, detail)` pairs plus
      new `STRATEGY_LABELS`/`LEG_ROLE_LABELS` display mappings — see stories.md for why neither
      is a drop-in escaping change | Blocked by: `backbone/` + `formatting-rules/` complete
      (same soft deps as other ROLL tasks)
- [ ] **ROLL-8** — Migrate generic strategy WARN event alert
      (`src/strategy/monitor.py::StrategyMonitor._route_event` WARN branch) to a v2
      cause-\>effect compact MarkdownV2 format (headline + optional Leg: line + description;
      supersedes an initial kv-line draft from the same session); not in the epic's original
      confirmed-callers list (surfaced via `missing-message-workshop-prompt.md`, TODO.md item
      2); reuses `ROLL-7`'s `STRATEGY_LABELS`/`LEG_ROLE_LABELS` tables, no new formatting rule;
      severity emoji is deliberately fixed (`⚠️`, never tiered) since this code path only ever
      carries WARN-severity events | Blocked by: `backbone/` + `formatting-rules/` complete
      (same soft deps as other ROLL tasks)
- [ ] **ROLL-9** — Migrate three-track base-leg roll notification
      (`scripts/strategies/three_track/paper_3track_roll.py::_notify_roll`) to two
      leg-role-specific MarkdownV2 layouts (base_futures: NIFTY FUT header + Contango/
      Backwardation spread; base_ditm_call: strike-bearing ticket line + Debit/Credit spread),
      adds closed-leg realized P&L and month labels; not in the epic's original
      confirmed-callers list (surfaced via `missing-message-workshop-prompt.md`, TODO.md item
      3) | Blocked by: `backbone/` + `formatting-rules/` complete (same soft deps as other
      ROLL tasks)
- [ ] **ROLL-10** — Migrate Proxy Delta CRITICAL alert
      (`scripts/dev/paper_track_snapshot.py::main`, CRITICAL branch) to a 3-line emoji-labeled
      MarkdownV2 format (📐 Current / 📉 Rule Breach); not in the epic's original
      confirmed-callers list (surfaced via `missing-message-workshop-prompt.md`, TODO.md item
      4); requires a small `TrackSnapshot`/`generate_track_snapshot` data-plumbing addition
      (expose `consecutive_days`) before the `Rule Breach:` line can be split into structured
      fields — currently ships as the verbatim `proxy_delta_alert` string, see stories.md for
      why splitting now would be premature | Blocked by: `backbone/` + `formatting-rules/`
      complete (same soft deps as other ROLL tasks)
- [ ] **ROLL-11** — Migrate System Healthcheck alert (`scripts/healthcheck.py::main`) to a
      grouped severity-status MarkdownV2 format (`DEGRADED [HH:MM]` headline, `ACTION REQUIRED`
      issue lines, `SYSTEMS NORMAL` pass summary); not in the epic's original confirmed-callers
      list (surfaced via `missing-message-workshop-prompt.md`, TODO.md item 5); requires
      refactoring `run_checks()` to return structured `CheckResult` objects instead of
      pre-formatted strings — see stories.md for why a drop-in re-render isn't possible | Blocked
      by: `backbone/` + `formatting-rules/` complete (same soft deps as other ROLL tasks)
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
- [ ] **ROLL-13** — Migrate 3-track base entry bootstrap notification
      (`scripts/strategies/three_track/paper_3track_entry.py::main`) to a per-leg emoji-
      prefixed MarkdownV2 kv format with resolved human-readable instrument labels (`NIFTY
      DEC FUT`, `NIFTY DEC 24500 CE`) instead of raw broker keys; not in the epic's original
      confirmed-callers list (surfaced via `missing-message-workshop-prompt.md`, TODO.md item
      7 — item 7's overlay-bootstrap half, `paper_3track_overlay_entry.py`, is a separate
      structurally-distinct message, still queued as TODO.md item 7's second half, not this
      task) | Blocked by: `backbone/` + `formatting-rules/` complete (same soft deps as other
      ROLL tasks)
- [ ] **ROLL-5** — Docs close | Blocked by: ROLL-4, ROLL-6, ROLL-7, ROLL-8, ROLL-9, ROLL-10, ROLL-11, ROLL-12, ROLL-13
