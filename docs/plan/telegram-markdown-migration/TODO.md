# Telegram Markdown Migration — Missing Messages

> Compiled 2026-08-08 (Cowork session). Cross-checked against `backbone/tasks.md` and
> `strategy-rollout/tasks.md` (both fully unchecked as of this writing — nothing in the epic
> has landed yet). This file lists Telegram-sending call sites that are **not** named in any
> `MD-*` or `ROLL-*` task in this epic. It is a gap list, not a task spec — promote any of
> these to a real `ROLL-*`/`MD-*` task (with `get_code_snippet`/`search_graph` pre-steps, a
> confirmed message structure via `message-format-workshop.md`, and tests) before implementing.

> **Ordering (confirmed with Animesh, 2026-08-08): simplicity-first, not risk or frequency.**
> The point of running these through `message-format-workshop.md` one at a time is to validate
> the workshop process itself as much as the message format. Starting with the simplest
> single-line/plain-text messages keeps the first few sessions fast and low-risk, and any
> friction found in the workshop steps (escaping helper availability, scratch script structure,
> `ROLL-N` write-back) gets ironed out before tackling the more structurally complex messages
> later in the list. Re-order later if a specific message becomes urgent for other reasons —
> this list is a queue, not a fixed sequence.

> **Protocol:** work top to bottom. Find the first unchecked `- [ ]` line — that is the next
> message to run through the workshop. Tick the box and append `| SHA: <sha>` once the
> workshop's docs-only commit (scratch script + `strategy-rollout/stories.md`/`tasks.md`
> write-back) has actually landed — matching the convention in `backbone/tasks.md` and
> `strategy-rollout/tasks.md`. Ticking the box records that the *format was confirmed and
> written back as a ROLL-N spec*, not that the real `src/`/`scripts/` implementation shipped —
> that's a separate, later step per the workshop's own "do not touch real code" rule.

---

## Confirmed missing — no MD-* or ROLL-* task covers these (simplicity-first order)

- [x] **1. Re-entry blocked/allowed notice** — `src/strategy/reentry_mixin.py:206-210`
      `⛔ {strategy_name} {reentry_leg_role} Re-entry BLOCKED` + notes, sent via
      `send_plain_message`. Single status line + notes — simplest message in this list, no
      table, no multi-source data. No escaping audit (MD-*) or format task (ROLL-*) names this
      file. Format confirmed 2026-08-08 (kv-line shape, not the originally-drafted single
      packed line) and written back as `strategy-rollout/` **ROLL-7** — see
      `scratch/2026-08-08_reentry_notice_format.py`. | SHA: e00326d

- [x] **2. Strategy event alerts** — `src/strategy/monitor.py:366-367`
      `text = f"[{strategy.strategy_name}] {event.event_type}: {event.description}"` →
      `self._notifier.send_plain_message(text)`. One f-string line, generic across all monitored
      event types. Distinct from `send_approval_request` (line 410, same file) which ROLL-4
      covers — this is a separate code path in the same class. Format confirmed 2026-08-08 —
      revised to a v2 cause->effect compact shape (headline + optional Leg: line +
      description) after a counter-proposal, superseding the initial kv-line draft — and
      written back as `strategy-rollout/` **ROLL-8** — see
      `scratch/2026-08-08_strategy_event_alert_format.py`. | SHA: ec008ba

- [x] **3. Three-track roll notification** —
      `scripts/strategies/three_track/paper_3track_roll.py:309-313`
      `Opened: {next_key} @ ₹{open_price}` + status line. Two lines, single position event.
      Format confirmed 2026-08-10 (two leg-role-specific layouts, not one — base_futures gets
      a NIFTY FUT header + Contango/Backwardation spread label, base_ditm_call gets a
      strike-bearing ticket line + Debit/Credit spread label; both add a new closed-leg
      realized P&L line and month labels) and written back as `strategy-rollout/` **ROLL-9** —
      see `scratch/2026-08-10_3track_roll_notification_format.py`. | SHA: 79e6314

- [ ] **4. Dev paper-track snapshot** — `scripts/dev/paper_track_snapshot.py:188`
      Max-drawdown / return-on-NEE metrics + proxy-delta alert state. A few metric lines, lives
      under `scripts/dev/` (lower production stakes, still worth a consistent format). | SHA: —

- [ ] **5. System healthcheck alert** — `scripts/healthcheck.py:171-178`
      `⚠️ NiftyShield Healthcheck — {now_str} IST` + multi-line disk/process alert body (variable
      number of issue lines), sent raw via `notifier.send()`. | SHA: —

- [ ] **6. Position health check alert** — `scripts/position_health_check.py:129-135`
      `⚠️ NiftyShield Position Health — {date}` + overdue-position list (days overdue, net_qty
      per row) — variable-length list, closer to a table than items 1-4. | SHA: —

- [ ] **7. Three-track entry / overlay-entry confirmations** —
      `scripts/strategies/three_track/paper_3track_entry.py:940`,
      `scripts/strategies/three_track/paper_3track_overlay_entry.py:1369`
      Entry-fill confirmation messages. Message bodies not yet read in full — grep only located
      the call sites (`asyncio.run(notifier.send(msg))`); pull the actual f-string and confirm
      structure before starting this session (may turn out simpler or more complex than ranked
      here — re-rank if so). | SHA: —

- [ ] **8. Three-track snapshot — settlement/roll command message** —
      `scripts/strategies/three_track/paper_3track_snapshot.py:497-503`
      Posts copyable settlement-close AND roll-open shell commands in one message — two distinct
      command blocks, more structurally involved than a single status line. Note: this file's
      `_build_recovery_digest` (~line 1684) IS in scope, but only for the MD-4 *escaping* audit —
      see the `paper_pnl_report.py` gap note below for how that distinction works. The
      settlement/roll command message at line 497-503 is a different message in the same file
      and isn't named in either MD-4 or any ROLL task. | SHA: —

- [ ] **9. Daily portfolio snapshot summary** — `scripts/portfolio/daily_snapshot.py:739`
      FD-OD/portfolio-value daily digest — the most structurally complex message in this list
      (multiple sections, multiple data sources: FD-OD capital structure + live portfolio
      value). Not the same message as the paper-strategy EOD summary
      (`scripts/eod_summary.py`, covered by ROLL-6) — separate script, separate data source
      (live portfolio, not paper strategies). | SHA: —

---

## Gap explanation — `scripts/reporting/paper_pnl_report.py`

This file is **half-covered**, and it's easy to misread the epic docs and assume it's fully
in scope. Two separate things are true at once:

- **It IS named in `backbone/stories.md` MD-4** (`## MD-4 — Audit + Fix: Reporting Scripts +
  Approval Requests`), alongside `paper_ic_snapshot.py`, `paper_ic_monthly_comparison.py`,
  `paper_3track_snapshot.py::_build_recovery_digest`, and `send_approval_request`. MD-4's job
  is narrow: **escaping safety only** — wrap dynamic values (and reserved static punctuation)
  so the message doesn't 400 once `TelegramNotifier.send()` switches to MarkdownV2 parse_mode.
  MD-4 explicitly states: *"Do NOT change the message's overall wording/structure in this
  task — that's `strategy-rollout/`'s job."*

- **It is NOT named in any `strategy-rollout/` ROLL task.** `strategy-rollout/stories.md`
  covers IC EOD Audit (ROLL-1), IC Monthly Comparison (ROLL-2), the 7 strategy close/roll
  notifications (ROLL-3), approval requests (ROLL-4), and EOD Paper Summary (ROLL-6). There is
  no `ROLL-*` entry for `paper_pnl_report.py` anywhere in `tasks.md` or `stories.md`.

**Net effect:** once `backbone/` ships, `paper_pnl_report.py`'s message will survive the
MarkdownV2 transport switch without silently breaking on an underscore or asterisk — but it
will keep its current plain/HTML-era wording and layout forever, because no task actually owns
migrating its *format* to the new bold/table style the rest of the epic is standardizing on.
This is a real gap, not a "someone will get to it eventually" — nothing in `docs/plan/README.md`
or this epic's own `README.md` schedules it. If `paper_pnl_report.py`'s message should get the
same bold-header/table treatment as its siblings (IC EOD audit, IC comparison), it needs a new
`ROLL-*`-style task added to `strategy-rollout/stories.md` + `tasks.md` explicitly — not added
to the numbered queue above since it's a coverage gap in the epic's task list itself, not a
message the workshop should pick up next by default.

**Before writing that task:** read the actual message-building function in
`paper_pnl_report.py` (not yet done in this pass) to confirm what it currently sends and
whether it even benefits from a table/bold-header format, per `ROLL-3`'s "match the format to
what the message actually needs" judgment call — don't assume it needs the same treatment as
the IC messages just because it's in the same reporting family.

---

## Suggested next step

Do not implement any of the above from this list alone. Per this epic's own
`message-format-workshop.md` convention, each new message migration should be iterated live
(before/after via a scratch script), confirmed on-device, then written back into
`strategy-rollout/stories.md`/`tasks.md` as a new `ROLL-*` entry — the same process used for
ROLL-1 through ROLL-6. This file is the input list for that triage, not a substitute for it.
Use `missing-message-workshop-prompt.md` (this directory) to run the next queued item.
