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

- [x] **4. Dev paper-track snapshot** — `scripts/dev/paper_track_snapshot.py:188`
      Max-drawdown / return-on-NEE metrics + proxy-delta alert state. A few metric lines, lives
      under `scripts/dev/` (lower production stakes, still worth a consistent format). Format
      confirmed 2026-08-10 (3-line 📐/📉 emoji-labeled shape, `Action:` line dropped as
      fabricated-data, `Rule Breach:` ships verbatim pending a real data-plumbing follow-up) and
      written back as `strategy-rollout/` **ROLL-10** — see
      `scratch/2026-08-10_proxy_delta_critical_alert_format.py`. | SHA: 54f7acc

- [x] **5. System healthcheck alert** — `scripts/healthcheck.py:171-178`
      `⚠️ NiftyShield Healthcheck — {now_str} IST` + multi-line disk/process alert body (variable
      number of issue lines), sent raw via `notifier.send()`. Format confirmed 2026-08-10
      (Animesh's grouped-severity counter-proposal: `DEGRADED [HH:MM]` headline, `ACTION
      REQUIRED` issue lines, `SYSTEMS NORMAL` pass summary — supersedes an initial
      verbatim-line draft; not yet exercised via a live `--send` round-trip, this Cowork
      sandbox had no working venv) and written back as `strategy-rollout/` **ROLL-11** — see
      `scratch/2026-08-10_healthcheck_alert_format.py`. | SHA: —

- [x] **6. Position health check alert** — `scripts/position_health_check.py:129-135`
      `⚠️ NiftyShield Position Health — {date}` + overdue-position list (days overdue, net_qty
      per row) — variable-length list, closer to a table than items 1-4. Format confirmed
      2026-08-10 (three-round iteration: raw-identifier v1 rejected as "cryptic" -> resolved-
      option-label v2 -> v3's confirmed restructure — `ROLLS OVERDUE` 🚨 rows grouped/sorted by
      days-overdue descending with `[strategy] Short/Long Nx LABEL (expiry)`, `UNMAPPED ASSET`
      ⚠️ rows with a parsed token suffix instead of the raw broker key; not yet exercised via a
      live `--send` round-trip, this Cowork sandbox had no working venv) and written back as
      `strategy-rollout/` **ROLL-12** — see
      `scratch/2026-08-10_position_health_alert_format.py`. | SHA: 049d4ff

- [x] **7a. Three-track base entry bootstrap confirmation** —
      `scripts/strategies/three_track/paper_3track_entry.py:940`. Split out of the original
      item 7 (2026-08-11) once the message bodies were actually read in full — the entry-
      bootstrap and overlay-entry-bootstrap messages turned out to be two structurally
      distinct call sites, not one, so each gets its own workshop pass. Format confirmed
      2026-08-11 (per-leg 📥-prefixed kv lines, resolved human-readable instrument labels
      instead of raw broker keys, unified `Long` verb, explicit lot count on every leg,
      internal `Cycle:` tag dropped) and written back as `strategy-rollout/` **ROLL-13** — see
      `scratch/2026-08-11_3track_base_entry_format.py`. First message in this epic actually
      confirmed via a live `--send` round trip, not just print-only review — caught two real
      MarkdownV2 escaping bugs in the process (see ROLL-13's spec / `backbone/stories.md`
      MD-1 addendum). | SHA: 4e19c64

- [x] **7b. Three-track overlay-entry bootstrap confirmation** —
      `scripts/strategies/three_track/paper_3track_overlay_entry.py:1410`. Second half of the
      original item 7. Distinct message shape from 7a — covers all three overlay types
      (pp/cc/collar), genuinely mixed leg direction (put legs BUY, call legs SELL) rather than
      7a's uniform-Long shape, plus an optional trailing gate-violation line. Format confirmed
      2026-08-11 (per-leg direction-coded marker — 🟢 Long / 🔴 Short, one counter-proposal
      round from the ROLL-13-derived opening draft — resolved human-readable instrument
      labels, explicit lot count, fixed leg-role→label/right/verb mapping) and written back as
      `strategy-rollout/` **ROLL-14** — see
      `scratch/2026-08-11_3track_overlay_entry_format.py`. | SHA: —

- [x] **8. Three-track snapshot — settlement/roll command message** —
      `scripts/strategies/three_track/paper_3track_snapshot.py:487-501`
      Posts copyable settlement-close AND roll-open shell commands in one message — two distinct
      command blocks, more structurally involved than a single status line. Note: this file's
      `_build_recovery_digest` (~line 1684) IS in scope, but only for the MD-4 *escaping* audit —
      see the `paper_pnl_report.py` gap note below for how that distinction works. The
      settlement/roll command message at line 487-501 is a different message in the same file
      and isn't named in either MD-4 or any ROLL task. Workshop session opened 2026-08-11:
      Animesh decided to split this into a Telegram summary + logged commands rather than a
      pure reformat — leg-direction confirmed (`base_futures`/`base_ditm_call` never go short),
      live `--send` reviewed and approved on-device for both scenarios — written back as
      `strategy-rollout/` **ROLL-15** — see `scratch/2026-08-11_3track_settlement_roll_format.py`.
      Real implementation (message rewrite + new `logger.info` call for the commands) is a
      separate later task, per the workshop's own rule. | SHA: 9d13123

- [x] **9. Daily portfolio snapshot summary** — `scripts/portfolio/daily_snapshot.py:739`
      FD-OD/portfolio-value daily digest — the most structurally complex message in this list
      (multiple sections, multiple data sources: FD-OD capital structure + live portfolio
      value, plus the separately-appended `format_options_section` from
      `src/dhan/positions.py:287`). Not the same message as the paper-strategy EOD summary
      (`scripts/eod_summary.py`, covered by ROLL-6) — separate script, separate data source
      (live portfolio, not paper strategies).

      Workshop session run 2026-08-11: real source read
      (`_format_combined_summary`, 326 lines, two layouts — waterfall/has_deltas=True vs.
      fallback/has_deltas=False). A kv-line + dash-hierarchy redesign was drafted and iterated
      (`scratch/2026-08-11_daily_snapshot_summary_format.py`) after confirming, live on-device,
      that the current box-drawing/tree-character layout (`├ └ ▲ ▼ ─`) and 2-space indentation
      both break under MarkdownV2 plain text (leading whitespace stripped, flattening the
      Equity/Bonds child hierarchy — caught via a real send round-trip run directly on
      Animesh's machine, not just print review). A second, more compact "Performance
      Breakdown" alternative was also proposed and reviewed; rejected for reintroducing the
      day-delta-vs-cumulative ambiguity in the Derivatives section and replacing the Hedge
      block's actual MF Δ/Hedge Δ numbers with an unverifiable "Active & Protected" verdict —
      see review notes in this session's transcript.

      **Decision (confirmed with Animesh, 2026-08-11): keep the current format as-is for now
      — no ROLL-N reformat at this time.** The redesign draft and its review are kept as
      `scratch/2026-08-11_daily_snapshot_summary_format.py` for future reference only, not
      adopted. This message therefore does NOT get a new `strategy-rollout/` ROLL-N entry.
      MarkdownV2 escaping-safety for its current wording (separate from any format redesign,
      per MD-4's "escaping only" scope) remains `backbone/`'s job when that lands — re-check
      whether `backbone/`'s MD-4 file list already covers `daily_snapshot.py` /
      `src/dhan/positions.py` before assuming it's out of scope. Revisit this format decision
      later if it becomes worth reopening. | SHA: e714be2

- [x] **10. Production Proxy Delta CRITICAL alert (duplicate)** —
      `scripts/strategies/three_track/paper_3track_snapshot.py::_run`, ~line 1723 (confirmed
      exact line this session — the 1639 estimate above was off). Surfaced 2026-08-10 while
      running queue item 4 through the workshop: this is a near-identical "Proxy Delta
      CRITICAL" Telegram alert to the one item 4 covers (`scripts/dev/paper_track_snapshot.py`),
      reading the same `TrackSnapshot.proxy_delta_alert` field and firing on the same
      `"CRITICAL" in ...` check — but this one lives in the real production EOD cron path, not
      the lower-stakes dev script item 4 scoped to. Not named in `backbone/`'s MD-4 file list or
      any `ROLL-*` task. Format confirmed 2026-08-11 (reuse of `ROLL-10`'s 3-line shape,
      verbatim — no track/date line added, Animesh's call between the two options put to him)
      and written back as `strategy-rollout/` **ROLL-16** — see
      `scratch/2026-08-11_3track_proxy_delta_critical_alert_format.py`. Not yet exercised via a
      live `--send` round-trip (this Cowork sandbox's mounted `.venv` doesn't resolve inside the
      device-bash VM); print-only output matches `ROLL-10`'s already on-device-confirmed block
      byte-for-byte. | SHA: ba81291

---

## Correction (2026-08-12) — `scripts/reporting/paper_pnl_report.py` is not in scope

This file was previously described here as "half-covered" by `backbone/stories.md` MD-4 (an
escaping-only audit) while lacking a `strategy-rollout/` ROLL task for its format. That framing
was wrong: **the file has no Telegram send path at all.**

`scripts/reporting/paper_pnl_report.py` is a CLI-only tool — `build_pnl_report()` returns a
`PnLReport` dataclass, and `main()` prints it via `_report_to_json()` or `_report_to_text()` to
stdout. There is no `TelegramNotifier`, no `TelegramGateway`, no `notifier.send()` anywhere in
the file. `git log --follow` shows a single commit in its entire history (`04687f1`, SNAP-4,
2026-08-07) — it was never refactored down from a version that did send to Telegram either.
Confirmed via `grep` across `src/`, `scripts/`, `tests/`, `docs/` and cross-checked against
`TODOS.md`/`PLANNER.md`/`CONTEXT.md`/`DECISIONS.md`: no open task anywhere plans to wire this
report to Telegram. `CONTEXT.md`'s only forward-looking note for this module is that
`build_pnl_report()` is "importable by a future graphing layer" — a dashboard/graphing
consumer, not Telegram.

Both `backbone/stories.md` MD-4's file list and this epic's `README.md` confirmed-callers list
included `paper_pnl_report.py` — that inclusion has been removed from both as a documentation
correction, not a scope decision (see the `2026-08-12` notes in each file). Most likely cause:
a false positive during the original code-graph sweep, picked up alongside the genuinely
Telegram-sending `paper_ic_snapshot.py` / `paper_ic_monthly_comparison.py` it was listed next
to.

**Net effect:** no `ROLL-*` task is needed for this file, and it should not be added to the
numbered queue above. If a future session wants `paper_pnl_report.py`'s output sent to
Telegram, that is new scope (a notifier integration, not a format migration) and would need its
own story from scratch — not a correction to this epic's existing MD-4/ROLL-* task lists.

---

## Suggested next step

Do not implement any of the above from this list alone. Per this epic's own
`message-format-workshop.md` convention, each new message migration should be iterated live
(before/after via a scratch script), confirmed on-device, then written back into
`strategy-rollout/stories.md`/`tasks.md` as a new `ROLL-*` entry — the same process used for
ROLL-1 through ROLL-6. This file is the input list for that triage, not a substitute for it.
Use `missing-message-workshop-prompt.md` (this directory) to run the next queued item.
