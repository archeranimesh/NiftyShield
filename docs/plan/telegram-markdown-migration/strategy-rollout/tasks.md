# Telegram Markdown Migration — Strategy Rollout — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task.
Each task = one commit. See `prompt.md` for why the story exists; see `stories.md` for the
per-task spec — every shipped line carries an **As-built** paragraph there (split history,
review-gate detail, phase SHAs); every open line has a full forward spec including its
confirmed message block and exact test list.

Sequenced by risk: informational messages first, live position-event notifications next,
auth-sensitive interactive messages last.

**Open: ROLL-6 (next), ROLL-7, ROLL-8, ROLL-9, ROLL-10, ROLL-11, ROLL-12, ROLL-13, ROLL-14,
ROLL-15, ROLL-16, ROLL-17, ROLL-5.**

> **Routing:** `Owner` = who implements (`Claude` = judgment-call, `Antigravity` = mechanical
> with an unambiguous spec). `Model` = model the owner runs at. `Review` = the AutoTrigger
> gate; where `stories.md` says "real `@code-reviewer`, Opus" the real subagent is mandatory,
> not a persona approximation (financial-logic close-notification / P&L-rendering paths).
>
> **Blocked by:** ROLL-1 needs `backbone/` + `formatting-rules/` fully complete (both are);
> ROLL-0 is independent. ROLL-6..ROLL-16 each depend only on `backbone/` + `formatting-rules/`,
> not on each other — **except** ROLL-15 → ROLL-16 (both touch `paper_3track_snapshot.py`,
> ROLL-15 first) and ROLL-8 / ROLL-12 (need ROLL-7's label tables). ROLL-16 also real-sequences
> after ROLL-10. Parallel sessions coordinate before claiming a ROLL-7..16 task.

## Tasks

- [x] **ROLL-0** — Capture long-leg delta + theta, compute Net Δ / Net θ in the IC EOD audit (`process_variant`) — plain-text, no parse_mode dep | Owner: Claude | Model: claude-sonnet-5 | Review:
      greeks-analyst | SHA: f9e551e
- [x] **ROLL-1** — Umbrella: IC EOD audit → bold/table MarkdownV2 + FMT-1c header, 5 variants. Split into ROLL-1a/1b/1c (2026-08-25). | SHA: f605b92
- [x] **ROLL-1a** — Promote FMT-1b: `pnl_emoji` / `alert_emoji` into `src/notifications/formatting.py` + tests | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: b05587b
- [x] **ROLL-1b** — Promote FMT-1c: `build_header()` + `_TIMEFRAME_META` / `VARIANT_META` in `paper_ic_snapshot.py` + tests | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 94dba89
- [x] **ROLL-1c** — The port: rewrite `process_variant()`'s report to bold/table MarkdownV2 using ROLL-1a/1b + FMT-2/FMT-3 | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: f605b92
- [x] **ROLL-2** — Umbrella: IC monthly comparison → one fenced row-groups table; adds Legs row, `Bkd (I)`, `Flt (M)`. Split into ROLL-2a/2b/2c (2026-08-26). | SHA: a2fbe31
- [x] **ROLL-2a** — Promote `build_compare_table` into `src/notifications/formatting.py` (widths via `max(len(...))`, display-width helper) + tests | Owner: Claude | Model: claude-sonnet-5 |
      Review: none | SHA: 3cec4e1
- [x] **ROLL-2b** — Umbrella: P&L sourcing (`Bkd (I)` + `Flt (M)`); reconciliation gate closed 2026-08-26. Split into ROLL-2b-i/2b-ii. | SHA: d2741fb
- [x] **ROLL-2b-i** — Contract: add `unrealized_this_month` to `PnLReport`, bound every snapshot read by `as_of`, record the accepted-gap decision | Owner: Claude | Model: claude-sonnet-5 |
      Review: code-reviewer | SHA: e59abb9
- [x] **ROLL-2b-ii** — Consume it: `ICMonthlyStats` += the two fields; `build_stats()` calls `build_pnl_report(...)` once, drops both local `sqlite3` helpers | Owner: Claude | Model:
      claude-sonnet-5 | Review: code-reviewer | SHA: d2741fb
- [x] **ROLL-2c** — The port: `build_comparison_report()` → one fenced table via ROLL-2a + MarkdownV2; Legs row `n/4` + `🔴`; render ROLL-2b's values | Owner: Antigravity | Model: n/a | Review:
      code-reviewer | SHA: a2fbe31
- [x] **ROLL-3** — Umbrella: migrate strategy close/roll notifications (7 classes) where it adds value. Split by family into ROLL-3.1/3.2/3.3 (2026-08-26). | SHA: 1ca5b68
- [x] **ROLL-3.1** — CSP family: migrate close/roll notifications (`csp_nifty_v1.py`) | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: 297e573
- [x] **ROLL-3.2** — IC family (`ic_nifty_v1.py`, `ic_nifty_v2.py`, kept together) — phases A `76f311a` + B `e032e28` | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: e032e28
- [x] **ROLL-3.3** — Overlay family (`cc`/`collar`/`pp`_overlay_v1 + `auto_close.py`) — phases A `12d766b` + B `da41e3d` + C `00604bc` + D `1ca5b68` | Owner: Antigravity | Model: n/a | Review:
      code-reviewer | SHA: 1ca5b68
- [x] **ROLL-4** — Migrate approval-request formatting (`TelegramGateway.send_approval_request`); coordinate with `telegram-approval-auth-fix` first | Owner: Claude | Model: claude-sonnet-5 |
      Review: code-reviewer | SHA: 30bac70
- [ ] **ROLL-6** — Migrate EOD Paper Summary (`scripts/eod_summary.py`) → `TelegramNotifier.send()` + MarkdownV2 (v2 4-bucket totals-first format, `Bkd` since-inception) | Owner: Claude | Model:
      claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **ROLL-7** — Migrate re-entry blocked/eligible notice (`ReEntryMixin._check_reentry`); refactor `blocked_reason` → `(short_reason, detail)` + new `STRATEGY_LABELS` / `LEG_ROLE_LABELS` |
      Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>
- [ ] **ROLL-8** — Migrate generic strategy WARN alert (`StrategyMonitor._route_event` WARN branch) → compact cause→effect format; reuses ROLL-7's tables, fixed `⚠️` | Owner: Antigravity | Model:
      n/a | Review: none | SHA: <—>
- [ ] **ROLL-9** — Migrate three-track base-leg roll notification (`paper_3track_roll._notify_roll`) → two leg-role layouts + closed-leg realized P&L | Owner: Claude | Model: claude-sonnet-5 |
      Review: code-reviewer | SHA: <—>
- [ ] **ROLL-10** — Migrate Proxy Delta CRITICAL alert (`paper_track_snapshot.py::main` CRITICAL branch) → 3-line emoji format; expose `TrackSnapshot.consecutive_days` | Owner: Claude | Model:
      claude-sonnet-5 | Review: none | SHA: <—>
- [ ] **ROLL-11** — Migrate System Healthcheck alert (`healthcheck.py::main`) → grouped severity-status format; refactor `run_checks()` → structured `CheckResult` | Owner: Claude | Model:
      claude-sonnet-5 | Review: none | SHA: <—>
- [ ] **ROLL-12** — Migrate Position Health check alert (`position_health_check.py::main`) → grouped-by-finding-type; refactor to `PositionFinding`, reuse ROLL-7's tables | Owner: Antigravity |
      Model: n/a | Review: none | SHA: <—>
- [ ] **ROLL-13** — Migrate 3-track base entry bootstrap notification (`paper_3track_entry.py::main`) → per-leg emoji kv with resolved instrument labels | Owner: Antigravity | Model: n/a | Review:
      code-reviewer | SHA: <—>
- [ ] **ROLL-14** — Migrate 3-track overlay entry bootstrap notification (`paper_3track_overlay_entry.py::main`) → per-leg direction-coded kv, all 3 overlay types | Owner: Antigravity | Model: n/a
      | Review: none | SHA: <—>
- [ ] **ROLL-15** — Migrate three-track base position expiry alert (`paper_3track_snapshot.py:487-501`) → compact summary; shell commands → structured `logger.info` | Owner: Antigravity | Model:
      n/a | Review: none | SHA: <—>
- [ ] **ROLL-16** — Migrate production Proxy Delta CRITICAL alert (`paper_3track_snapshot._run` ~L1723) → ROLL-10's format verbatim; reuse its builder if possible | Owner: Antigravity | Model: n/a
      | Review: none | SHA: <—>
- [ ] **ROLL-17** — IC entry confirmation shared content model (`paper_ic_entry.py` + `_v2.py`) — **DESIGN INCOMPLETE**: 6 open decisions, workshop session first; Owner/Model/Review below
      provisional | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **ROLL-5** — Docs close: synthesis across all prior ROLL tasks | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>

## Story done when

Acceptance criteria — prose, no checkboxes. Verified at story close; per-task status lives
only in the working list above.

- **ROLL-0** — `process_variant()` captures delta + theta for all four IC legs (`None` on any
  miss, never `0.0`), computes Net Δ / Net θ with the never-silently-partial rule, and prints
  the line in the current plain-text report.
- **ROLL-1** — the IC EOD audit renders in the confirmed bold/fenced-table MarkdownV2 format
  with the FMT-1c timeframe header + hashtag across all 5 active variants, using the shared
  FMT-2/FMT-3 formatters and `backbone/`'s escaping helpers.
- **ROLL-2** — the IC monthly comparison renders as one fenced row-groups table via the
  promoted `build_compare_table`, with the Legs row, `Bkd (I)` from `get_strategy_realized_pnl()`,
  and `Flt (M)` distinct from `Flt (I)`; the mandatory `Flt (M) != Flt (I)` test passes.
- **ROLL-3** — all 7 strategy close/roll notification paths render in the new format where it
  adds value (per-message judgment, not a forced table); real `@code-reviewer` ran per family.
- **ROLL-4** — the approval-request message body is formatted with the shared helpers, callback
  buttons verified unaffected, the `telegram-approval-auth-fix` coordination-check done.
- **ROLL-6** — `scripts/eod_summary.py` sends via `TelegramNotifier.send()` + MarkdownV2 in the
  confirmed 4-bucket totals-first format, `Bkd` sourced since-inception.
- **ROLL-7..ROLL-16** — each of the ten missing-message call sites renders in its confirmed
  MarkdownV2 format with a live-confirmed reference and passing tests; the shared label tables
  exist and are reused, not re-derived.
- **ROLL-17** — the IC entry confirmation design is closed via a workshop session (6 open
  decisions resolved), then implemented against a live-confirmed reference; value-level
  formatting reuses `FMT-1` / `FMT-2`.
- **ROLL-5** — the docs-close task records the final state of every migrated message family.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Update the epic
`README.md` **Stories** table status column (`strategy-rollout/` row) and add one line to
`TODOS.md` Session Log. When every box is ticked, follow `docs/plan/README.md` §Conventions
*Completion → archive* for the whole epic.
