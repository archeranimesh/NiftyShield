# `docs/plan/` — Story Index

> Each story folder is self-contained. Start from its `prompt.md`. Archived original files: `docs/archive/plan/`. Confirmed defects in shipped code (not forward spec work): [`docs/bugs/`](../bugs/) —
> same folder conventions, separate registry. See also the archived legacy registry [`BUGS_LEGACY.md`](../archive/BUGS_LEGACY.md) (superseded).

The **status** and **next** markers below are a *summary* of each story's `tasks.md`. `tasks.md` is canonical; if they disagree, `tasks.md` wins and this file is stale. Format per entry:
`**\`folder/\`** · <status> · next: **<task id>**` then a short blurb.

---

## Active Epics

**`ic-payoff-charts/`** · ⬜ Not started — start with `chart-core/` **PC-2** Stockmock-style payoff diagram (one PNG per IC variation) attached to the entry, EOD-audit, and close Telegram messages. Two
sub-stories: `chart-core/` (PC-1..15 — payoff math + matplotlib expiry-payoff renderer + `sendPhoto` on `TelegramNotifier`/`TelegramGateway` + wire into `paper_ic_entry`/`_v2`, `paper_ic_snapshot`,
both `_send_close_notification`; no option model, ships now) → `chart-model-overlay/` (MO-1..9 — blue T+0 curve + ±1σ/±2σ bands
+ POP; **blocked on `greeks-bs-fallback/` GF-2 + GF-3** for the shared `src/pricing/` pricer
+ IV solver). Modeling decisions (rate / DTE convention / delta tolerance) inherited from `greeks-bs-fallback/`. No DB schema change. Requested by Animesh 2026-09-09.

**`token-efficiency/`** · ✅ Shipped/Archived 2026-09-03 → `docs/archive/plan/token-efficiency/` `measurement/` (MEAS-1..2) + `fixed-overhead/` (FIX-1..4) + `suggestions-sweep/` (SWEEP-1..7) all
shipped. `token_audit.py`, the `CLAUDE.md`/`AGENTS.md` skill-ification, `session-close` off the fork, the SWEEP `PreToolUse` hooks + `commit_preflight.py`, and the Step 4b drain path (`Count >= 5` →
`technical-debt/` DEBT-8..12) all landed. Closing SHA `2d896a9`.

**`doc-format-migration/`** · ✅ Archived → `docs/archive/plan/doc-format-migration/`.

**`dev-foundation/`** · ✅ Shipped/Archived Engineering-excellence epic — tooling, CI, code health (3 sub-stories).

**`full-repo-review-followups/`** · ⬜ Not started — start with the P0 folders 9 stories from the full-repo-review FR-7 synthesis (7 CRITICAL + 2 ERROR). P0: portfolio P&L fix, DB backup cron. P1: docs
staleness, Telegram auth fix. P2: CLAUDE.md/REVIEW.md reconcile, logging migration. P3: Greeks/parity validation (council-gated), golden tests, suppression hygiene. Priority + dependencies in the
epic's own `README.md`. `telegram-approval-auth-fix/` already shipped (SHA `5cafc3c`).

**`telegram-markdown-migration/`** · ✅ Shipped/Archived 2026-09-06 → `docs/archive/plan/telegram-markdown-migration/` All Telegram messaging switched to `parse_mode=MarkdownV2` across three sequenced
sub-stories: `backbone/` (parse-mode switch + escaping audit, `57c1c3c`), `formatting-rules/` (value/table spec → `FORMATTING.md`, `75cc123`), `strategy-rollout/` (per-message-family migration incl.
ROLL-17 IC entry unify `26527c2`; docs close ROLL-5 `b55773d`). Superseded `telegram-ic-comparison-formatting/` TGFMT-2..9.

**`telegram-ic-comparison-formatting/`** · ✅ Archived 2026-09-06 → `docs/archive/plan/telegram-ic-comparison-formatting/` TGFMT-1 shipped (`a69d817`, `build_comparison_report()` dynamic-width fix).
TGFMT-2..9 superseded by `telegram-markdown-migration/` (now itself archived) — the Legs row and Bkd/Flt month-inception split landed there as ROLL-2c.

**`3track-consolidation/`** · ✅ Shipped/Archived 2026-08-04 → `docs/archive/plan/3track-consolidation/` Overlay (CC/PP/Collar) retired on Futures/Proxy, live only on NiftyBees; base-leg-only daily
comparison snapshot; automated base-leg rolling; full unattended automation.

---

## Active Stories

**`signal-outcome-profit-range/`** · ✅ Shipped/Archived 2026-09-22 (SOP-1 `4096c07`, SOP-2 `180ccae`, SOP-3 `a73b6b6`) → `docs/archive/plan/signal-outcome-profit-range/` Shows the profit high/low
reached since entry (existing `mfe_pct`/`mae_pct` in `paper_signal_marks`) in the daily SIGNAL OUTCOME Telegram message for executed signal-track trades, persisted on `SignalOutcome`.

**`eod-pt-summary/`** · ✅ Shipped/Archived 2026-09-07 (PT-1..PT-3) → `docs/archive/plan/eod-pt-summary/` Cross-strategy paper-trade EOD digest to Telegram. PT-1 (spec `d1ae760`) + PT-2
(`src/reporting/eod_pt_summary.py`
+ `scripts/eod_pt_summary.py` + `43 15` cron, `77dc160`) + PT-3 (docs close, `dac18ea`). Runs alongside `scripts/eod_summary.py`, not a replacement (DECISIONS.md §P&L & Reporting, 2026-09-07).

**`telegram-message-unification/`** · ✅ Archived → `docs/archive/plan/telegram-message-unification/` A structured, fenced house style for every paper-strategy Telegram message; fixed BUG-044
(standalone CC overlay folded into the Collar recovery-digest figure). Closed 2026-09-15 (ORD-4).

**`portfolio-snapshot-slimdown/`** · ⬜ Not started — start with `finideas-decommission/` **FD-1** Shed two data sources from the daily portfolio snapshot. Two sequenced sub-stories (both rework
`_build_portfolio_summary` + `_format_combined_summary` — fixed order, not interleaved): `finideas-decommission/` (FD-1..7 — full removal of `finideas_ilts` + `finrakshak`: the
`src/portfolio/strategies/` provider layer, the options / FinRakshak-hedge / ETF snapshot terms, and every Finideas row in `strategies` / `legs` / `trades` / `daily_snapshots` via a
`scripts/dev/decommission_finideas.py` CLI — history option A, hard delete, no archive) → `dhan-holdings-removal/` (DHR-1..4 — remove the Dhan equity/bond holdings, their P&L, and the `📊 Dhan Options
(Intraday)` block from the snapshot; keep the Dhan login flow + `src/dhan/` client + DB tables wired). After both, the snapshot reports MF + Nuvama bonds + Nuvama options only. No `schema.md`.
Requested by Animesh 2026-09-10.

**`backtest-engine/`** · 🔄 In progress · next: **1.3a / 1.4** (`phase1/`, parallel) Four chained phases (`phase1..4/`) building the Phase 0→1+ systematic options backtest/paper-trading pipeline off
`BACKTEST_PLAN_PHASE1.md` (root, canonical spec) — CSP v1 variance-gate buildout, CSP-live/IC-paper expansion, post-gate strategy expansion, long-horizon capital allocation. Each phase gated on the
previous phase's closing GATE task; `phase1` itself gated on the Phase 0.8 variance gate (`variance-gate/`, below).

**`risk-gamma-phase-a/`** · 🔄 In progress · next: **B2.2** (chain fetch + field computation) Risk delta gate (done) + Near-Expiry Gamma Buy `gamma_daily_watch.py`.

**`variance-gate/`** · ⬜ Not started · next: **VG0** (CSP v1 spec reconciliation) CSP v1 Phase 0.8 deployment gate — spec reconciliation + gate criteria A–D.

**`root-doc-organization/`** · ✅ Archived 2026-09-22 → `docs/archive/plan/root-doc-organization/` Token-efficiency cleanup of the ~22 root `.md` files + doc-maintenance automation + `docs/plan/`
story/epic format standardization (RDO-1..17.8, all shipped). RDO-17.8's legacy-folder execution completed in `doc-format-migration/`, itself archived (above).

**`session-entry-point/`** · ✅ Archived 2026-08-28 → `docs/archive/plan/session-entry-point/` Unified manual `/work` skill (SEP-1..4) — routes a task session to Feature or Bug, loads the right
prompt + first unchecked task, hands to `CLAUDE.md` Step 2b.

**`paper-backbone/`** · ✅ Shipped/Archived Strategy Monitor daemon + pluggable strategy backbone (`src/strategy/`, `TelegramGateway`).

**`mvp/`** · 🟡 In progress · next: **M4.2** (`mvp_watch.py` Telegram alerts) Multi-bagger Value Picks Tracker (`src/mvp/`, `scripts/mvp.py`, `scripts/mvp_watch.py`).

**`options_income/`** · ⬜ Not started · next: **S0** (audit scope) Options-income overlay spec (9 tasks, S0–S8) — no code shipped yet; `src/options_income/` does not exist.

**`technical-debt/`** · 🔄 Opportunistic backlog, actively fed 10 open / 7 closed items — not a normal sequenced story, no single "next" task; each item is picked up opportunistically per its own
trigger condition in `tasks.md` (see `prompt.md`).

**`council-refactor/`** · ✅ Shipped/Archived Remove `RapidCouncil` from the daemon approval path; fix `send_approval_request` signature bug; add deterministic backtestable roll rules to
`ExitSignalEngine`.

**`ic-nifty-v2/`** · ✅ Shipped/Archived IronCondorV2 — 25Δ/22Δ high-delta IC with 10Δ wings, partial-roll adjustment, DTE-tiered exit.

**`paper-exit-codification/`** · ✅ Shipped/Archived 2026-08-04 → `docs/archive/plan/paper-exit-codification/` Codify q11+q12 council rulings: TIME_STOP/DTE_REVIEW priority fix in `evaluate_cc`;
StrategyMonitor observability logs.

**`telegram-leg-labels/`** · ✅ Shipped/Archived 2026-08-07 (TL-1..5) → `docs/archive/plan/telegram-leg-labels/` Replace raw Upstox instrument keys in Telegram prose with human-readable `NIFTY 22000 CE
07 JUL 26` labels; CLI command lines untouched.

**`ic-yearly-expiry-fix/`** · ✅ Shipped/Archived 2026-09-07 → `docs/archive/plan/ic-yearly-expiry-fix/` Fix `InstrumentLookup.get_expiry_candidates()`'s `"yearly"` label resolving June instead of
December — NSE Nifty's annual contract is always December's last Tuesday. YE-1..4 superseded 2026-07-22 (DECISIONS.md BUG-015); WG-1 shipped `761af8e` (`ic_nifty_v1.leg_greeks` INFO line; weekly
Parquet bucket already in `a38e53f`).

**`greeks-bs-fallback/`** · 🔄 Partially scoped · next: **GF-1** (audit scope) Upstox returns all-zero `option_greeks` for far-dated NIFTY contracts despite liquid `ltp`/`bid`/`ask`/`oi` — a data gap,
not illiquidity. Blocks delta-based IC entry for the yearly bucket. Decision: compute Greeks ourselves (BS pricer + Newton-Raphson IV solver), not a cruder OTM heuristic. 3 modeling decisions
(risk-free rate, DTE convention, delta tolerance) still need Animesh.

**`chain-decay-analysis/`** · ⬜ Not started · next: **CDA-1** (paired-snapshot reader) Empirical check: does intraday option premium move track delta (+ gamma/theta/vega decomposition), or is there a
persistent residual — and which moneyness bands decay faster than theta alone predicts. Existing 5-min intraday chain Parquet. Monthly bucket only.

**`signals/`** · ✅ Shipped/Archived 2026-09-09 (S1.1–S6) → `docs/archive/plan/signals/` Multi-LLM daily directional signal pipeline: market snapshot → GPT-4o / Grok / Gemini (via OpenRouter) →
`SignalAggregator` consensus → one `DailySignal` per day, scored forward-only against a `hash(trade_date) % 2` coin-flip baseline. Self-contained `src/signals/` package with its own SQLite tables — no
`backtest-engine` / `backtest-eval-core` dependency. All three crons live on the Mac host (Phase 1 `openrouter_only`): `morning_signal` 09:30, `record_signal_outcome --auto` 16:00, `signal_report`
16:35 (Mon–Fri). Follow-on execution layer → `signals-paper-track/` (archived).

**`signals-cost-tracking/`** · ✅ Archived → `docs/archive/plan/signals-cost-tracking/` (SCT-1..4, 2026-09-10) OpenRouter per-call token usage + USD cost captured via inline `usage.include`, persisted
as three nullable columns on `signal_responses`, aggregated by `SignalStore.get_signal_cost()`, and shown as today's spend on the 09:30 message. Cost trustworthy from 2026-09-11.

**`signals-paper-track/`** · ✅ Archived → `docs/archive/plan/signals-paper-track/` (SPT-1..8, 2026-09-11) Turned the `signals/` consensus into a live paper-traded strategy: `SignalTrackV1`
(`paper_signal_track_v1`) auto-enters the daily `DailySignal` as a long monthly option (near-month, rolled to next-month at 14 DTE), manages it intraday against a fixed SL −30 % / target +50 % at 30 s
cadence, exits on a hit or square off by 15:00, logs the full mark path (`paper_signal_entries` / `paper_signal_marks`), and records every entry + exit for a 6-month evaluation window that gates
go-live (SPT-7's G1–G9 report). SPT-1 ruled 2026-09-09 (council q17, `docs/archive/council/strategy/2026-09-09_signals-paper-track-execution-layer.md`): module boundary **A** — on the shared
`StrategyMonitor` / `PaperExecutor` / `PaperStore`, pure `src/strategy/signal_exit.py` evaluator, Phase 1 fixed-only (`TRAILING_STOP` reserved), two-tier recalibration. `morning_signal.py`'s guarded
tail-call opens the entry and `scripts/signal_paper_entry.py` is the manual `--date` backfill tool — **no new cron** was added. SPT-5's exit message supersedes `signals/` S5.5a's Phase-1 interim
outcome message (marked `won't-do` in the archived `signals_tasks.md`). Go-live gate + pilot unexercised — 6-month window not yet elapsed. Entrypoint-dedup cleanup now unblocked →
`signals-entrypoint-consolidation/`.

**`signals-entrypoint-consolidation/`** · ✅ Archived → `docs/archive/plan/signals-entrypoint-consolidation/` (SEC-1..6, 2026-09-12). One holiday guard (`market_calendar.guard_trading_day` +
`is_market_session_now`), one `DailySignal.is_actionable` fire-check predicate, `record_signal_outcome.py` + `signal_report.py` merged into `scripts/signal_eod.py` (2 crons → 1, byte-identical
`SignalOutcome` baseline), `morning_signal.py` reduced to orchestration + Telegram via `src/signals/pipeline.py::run_morning_signal_pipeline`, `signal_paper_entry.py` kept as a manual backfill tool
(keep-or-delete deferred pending a live track record). Live crontab confirmed matching the final two-cron state as part of SEC-6.

**`full-repo-review/`** · ✅ Complete — see `full-repo-review-followups/` One-time multi-model, multi-persona review of design docs, source, tests, the AI-collaboration protocol, and per-job-type
surface routing (FR-1..9).

**`ic-time-stop-dte-tiering/`** · ✅ Shipped/Archived 2026-08-05 (DT-1..4) → `docs/archive/plan/ic-time-stop-dte-tiering/` Council-ruled fix (`docs/council/2026-08-05_...`): de-tier per-bucket
`time_stop_dte`/`dte_warn` to a uniform terminal rule; forward-only counterfactual DTE-mark logging on `paper_exit_events`.

**`monitor-and-close-hardening/`** · ✅ Shipped/Archived 2026-08-06 → `docs/archive/plan/monitor-and-close-hardening/` StrategyMonitor tick-loop observability + auto-close leg-resolution hardening —
dedupe `expiry_unresolved` logging, BOD-resolve replacement-leg keys, atomic close+open, shared BOD-fallback finder (MC-1..MC-6).

**`paper-ic-daily-snapshot/`** · ✅ Shipped/Archived 2026-08-07 → `docs/archive/plan/paper-ic-daily-snapshot/` IC daily P&L snapshot wiring (SNAP-1..5): confirmed realized/unrealized semantics, built
`scripts/reporting/paper_pnl_report.py`, fixed `paper_nav_snapshots.total_pnl` invariant + backfilled 42 rows.

**`paper-store-position-granularity/`** · ✅ Archived → `docs/archive/plan/paper-store-position-granularity/` (PG-1..PG-4i) `PaperStore.get_positions()`/`get_position()` group by `(strategy_name,
leg_role, instrument_key)`, not `leg_role` alone, so a roll overlap no longer collapses two same-role positions into one. `ApprovedAction.legs_to_close` carries `LegClose(leg_role, instrument_key)`
pairs; `PaperExecutor.apply()` passes `instrument_key` through to `get_position()`.

---

## Blocked / Later Stories

| Folder | Blocked by |
|--------|------------|
| `backtest-eval-core/` | Phase 1.3 (Bhavcopy) + Phase 1.4 (BacktestEngine) |
| `signals-eval-core/` | backtest-eval-core + Phase 1.12 gate |

---

## Conventions

This section is canonical and self-contained — there is no pointer to `docs/archive/plan/README.md` (that file documents the retired one-file-per-task scheme and is dead for convention purposes).

### Folder shapes — size to scope

Work under `docs/plan/` takes one of two shapes.

- **Single story** — one coherent goal, however many tasks. A flat folder `docs/plan/<slug>/` (`<slug>` kebab-case — no date prefix, no `<slug>_` filename prefix). `risk-gamma-phase-a/` is the model.
  Start it with `/new-story` (or `python -m scripts.dev.new_plan_folder --story <slug>`).
- **Epic** — two or more related stories shipped together. `docs/plan/<slug>/` with a router `prompt.md` + `README.md` at the root and one sub-story folder per story **directly under it** —
  `docs/plan/<slug>/<story-slug>/`, no `stories/` layer. `telegram-markdown-migration/` is the model. Start it with `/new-story` (or `python -m scripts.dev.new_plan_folder --epic <slug>`, then
  `--story <story-slug> --into <slug>` per sub-story).

A single story that grows a second story is promoted: create `<slug>/<story-a>/` and `<slug>/<story-b>/`, move the original three files into `<story-a>/`, add the root `prompt.md` router +
`README.md`.

### Story-folder file set

Applies to a flat single-story folder and to each epic sub-story folder.

| File | Required | Purpose |
|------|----------|---------|
| `prompt.md` | yes | Session entry point — first-unchecked-box protocol, hard constraints, test gate, load hints. Loaded by `/work` on selection. |
| `tasks.md` | yes | The working checklist — first unchecked `- [ ]` is the task. One line per task (format below). |
| `stories.md` | yes | Complete per-task spec — files, "before any code" graph queries, what to implement, tests, commit message. Self-contained. |
| `schema.md` | conditional — see *When a story needs `schema.md`* | DDL + the `DB_REGISTRY.md` row, when the story changes DB schema. |
| `plan.md` / `spec.md` | optional | File-by-file plan / wire formats / gate criteria for a large story — no task checkboxes (see *Extra files*). |

Legacy folders may still carry `<name>_tasks.md` / `<name>_stories.md`, a `stories/<ID>.md` one-file-per-story layout, or `phaseN/` sub-folders — do not mass-rename; each converts to the shape above
on its next substantive touch.

### Epic-folder file set

The epic root carries **only what is common to every sub-story** — never task checkboxes.

| File | Required | Purpose |
|------|----------|---------|
| `prompt.md` | yes | The **router** — `/work` loads this, not a sub-story `prompt.md`. See *Epic router* below. |
| `README.md` | yes | The shared brief — see *Epic README* below. |

**Epic router (`prompt.md`)** — states the fixed story order; walks each sub-story's `tasks.md` for the first unchecked `- [ ]`; confirms that task line's `Owner` / `Model` / `Review`; hands to that
sub-story's own `prompt.md` + `stories.md`. One task per session, then stop.

**Epic README** — why the epic exists, the scope decisions (and with whom), the ordered story list with a status column (⬜ / 🔄 / ✅ + closing SHA) and per-story dependency, the cross-cutting
constraints every sub-story must honour, supersession / coordination notes. A fact needed by only one story belongs in that story's files.

### When a story needs `schema.md`

Decide at planning time, while writing `stories.md`. A story needs a `schema.md` iff a task:

- adds a table (`CREATE TABLE`);
- adds / renames / drops a column, or changes a column's type or constraint;
- introduces a new `*Store` class with its own `init_db()` DDL;
- adds a contract index (query-critical, not incidental);
- changes how a stored value is encoded in a way a future reader must know — a new enum value in a `TEXT` column, a units change, a new composite-key format.

It is **not** needed when the story only reads existing tables, writes rows into existing tables with no shape change, or is pure computation / formatting / notification / script-wiring.

DDL lives in `schema.md`, never inline in `stories.md` — `stories.md` points to it ("use the exact schema from `schema.md`"). `schema.md` **must** also state the `DB_REGISTRY.md` row to add.
`check_story_structure.py` warns (does not block) when a `stories.md` / `prompt.md` contains `CREATE TABLE` / `ALTER TABLE` and the folder has no `schema.md`.

### Extra files

A story or epic folder may carry additional `.md` files beyond the sets above **only** when the file is shared reference material used by more than one task — a reusable prompt, a `plan.md`, a
`spec.md`, a research note — **and** it contains no `- [ ]` / `- [x]` task checkboxes. Anything with tracked checkboxes is a task list and belongs in a story folder's `tasks.md`. OS / editor cruft
(`.DS_Store`, `*.swp`) is removed — it is already `.gitignore`d. `check_story_structure.py` flags a tracked non-`.md` file in a plan folder, and an extra `.md` that contains checkbox lines.

### Task-line format

Every `tasks.md` line is a single `- [ ]` checkbox carrying five `|`-separated fields:

```
- [ ] **<ID>** — <one-line description> | Owner: <Claude|Antigravity|Animesh> | Model: <model-id|n/a> | Review: <code-reviewer|greeks-analyst|roll-validator|none> | SHA: <—>
```

`Owner`, `Model`, and `Review` are filled **when the story is authored** — they record the `CLAUDE.md` Step 3b routing decision and which AutoTrigger sub-agent gates that task's commit. `Model` is the
implementing model id when `Owner=Claude` (e.g. `claude-sonnet-5`), `n/a` otherwise. `Review` is `none` for docs-only tasks. `SHA` is `—` until the task's commit lands; then set it to the real SHA and
tick the box. When a phase ticks its own box in the same commit, `SHA: <pending>` is the sanctioned interim — the real SHA is backfilled in the next commit's docs touch, never in a dedicated swap-only
commit (`commit` skill Step 1b; `check_checkbox_consistency.py` allows `<pending>` on a ticked line). One line per task — never mirror task state into `TODOS.md` or a `stories.md` DoD box.

### Canonical state vs derived state

`tasks.md` checkbox state is the single source of truth for task progress. Everything else is derived and must not be hand-edited to disagree with it:

- this file's per-story status / next marker — a summary of the story's `tasks.md`
- a `stories.md` DoD checkbox — mirrors its `tasks.md` task

### Checkbox consistency (RDO-15)

Every task id carries **exactly one** checkbox — the `- [ ]` / `- [x]` line in the working list. A trailing `## Epic done when` (epic) / `## Story done when` (single story) block is an
**acceptance-criteria list in prose** — bold id, one-line criterion, **no `- [ ]` checkboxes** — verified at close, not tracked incrementally. An acceptance item with no matching task id (e.g. a
whole-epic "loop-closure verified" check) is real work: give it a task id in the working list, don't leave it as a bare bullet here. Nothing mirrors task state, so nothing can drift.
`scripts/dev/hooks/check_checkbox_consistency.py` sweeps every `docs/plan/**/tasks.md` (plus legacy `*_tasks.md`) and `docs/bugs/task.md` for: a checkbox inside a summary block (`## Epic done when` /
`## Story done when` / `## Definition of done` / …), the same id with disagreeing state in one file, a README `next:` marker pointing at an already-done id, and — on any line carrying the canonical `|
Owner: … | Model: … | Review: … | SHA: …` tail — a `Review` value that is not a known gate name (`code-reviewer` / `greeks-analyst` / `roll-validator` / `none`) or a `SHA` that disagrees with the
checkbox state (`—` / `<—>` iff unchecked, a real 7–40 hex SHA — or the `<pending>` interim — iff ticked). Legacy tails (`| Owner | Model | SHA` with no `Review`, or a prose-laden `| Review:`) are
grandfathered — skipped, not flagged. It runs in the `md-organize` skill's periodic audit — not pre-commit (task files churn far faster than the audit needs to).

### `TODOS.md` hygiene

`TODOS.md` carries two separate pointer-only lists — `## Feature Backlog` (`docs/plan/` stories) and `## Open Bugs` (`docs/bugs/` defects). `/work` routes to one or the other. Each item is
**pointer-only**: title, the `docs/plan/<slug>/` or `docs/bugs/` path, the next unchecked task id, and a one-line why. No inline multi-paragraph detail, no per-task progress — that lives only in the
story's `tasks.md` / `docs/bugs/task.md`. Cross-references between items use folder names, never list positions. The `## Open Bugs` snapshot is not authoritative — `docs/bugs/bugs.md` is; never encode
bug priority or status in `TODOS.md`. On completion, a line is removed, not just ticked — see *Completion → archive*.

### Completion → archive

A story or bug is **done** when every `- [ ]` in its `tasks.md` / `docs/bugs/task.md` is ticked and its `## Epic done when` / `## Story done when` acceptance block (if present) is satisfied. As soon
as that holds, do all of the following in the same commit — never leave a done story half-archived:

1. **Story:** `git mv docs/plan/<slug>/ docs/archive/plan/<slug>/` (bug: `git mv docs/bugs/<slug>/ docs/archive/bugs/<slug>/`, or fold the `bugs.md` entry into `docs/archive/bugs/bugs.md` and mark it
   `[MOVED]` at the original location).
2. **`TODOS.md`:** delete the item's line from `## Feature Backlog` / `## Open Bugs` and append it to `docs/archive/TODOS_ARCHIVE.md` under a dated heading.
3. **This file:** collapse the story's entry under `## Active Epics` to a one-line `✅ Archived → docs/archive/plan/<slug>/` pointer.
4. **`bugs.md`:** flip the status cell to `✅ Fixed` with the closing SHA before the entry moves.

The `md-organize` skill's periodic audit and the `session-close` skill both check for done stories that were not archived; do not rely on that — archive at completion.

### Markdown line style (RDO-5; fill-to-≤200 per RDO-17.7 §A, 2026-08-29)

Prose fills each line to the last word boundary before 200 chars — do not break early at a sentence or clause end, and do not hand-wrap to a fixed narrow width. The earlier "semantic linefeeds"
guidance (one sentence or clause per line) is **retired**: the mid-line wrap near ~110 chars it produced was harder to read in source, not easier, and it made diffs noisier. Two pre-commit hooks
enforce this. `md-line-length` blocks any line over 200 chars on root `.md` + `docs/plan/**` + `docs/bugs/**` (`<!-- lint-ignore-length -->` on the immediately-preceding line excuses one unbreakable
token — a long URL, a base64 blob). `md-reflow` runs `reflow_md.py --check` on every changed `docs/plan/**` + `docs/bugs/**` `.md` (minus `_TEMPLATE/`) and blocks a commit whose markdown is not in
fill-to-≤200 style — hand-wrapping at a narrow width now fails the commit, not just an audit. A legacy narrow-wrapped file you touch must be reflowed in the same commit: `python -m
scripts.dev.reflow_md <path>`, then re-stage (this is the "converts on next substantive touch" rule, now gated). Root `.md` is not yet under `md-reflow` — that waits for
`doc-format-migration/repo-wide-reflow/`. `.py` stays at ruff's `line-length = 100` (ruff already excludes `docs/`). `scripts/dev/reflow_md.py` is the reusable engine that does the fill: `python -m
scripts.dev.reflow_md <path>` rewrites in place, `--check` reports. It only re-wraps whitespace — a `git diff --word-diff` of a reflow shows zero word changes — and leaves fenced code, tables,
headings and nested list/quote structure verbatim. The whole tree is now fill-to-≤200 — every `docs/plan/` folder (`doc-format-migration/plan-folders/`) and every other in-bounds `.md` in the repo
(`doc-format-migration/repo-wide-reflow/`) — and the `doc-format-migration/enforcement/` gate keeps it that way going forward.

### Structure audit

The format is **enforced, not advisory** (`doc-format-migration/enforcement/`, DFM-6..10). `scripts/dev/hooks/check_story_structure.py` checks every non-archived `docs/plan/*/` folder: a flat story
folder has `prompt.md` + `tasks.md` + `stories.md`; an epic root has `prompt.md` + `README.md` and at least one conforming sub-story. It also flags stray or empty folders, a missing `schema.md`
against DDL in `stories.md` / `prompt.md` (warning), and disallowed extra files (see *Extra files*). Pre-commit runs it `--staged` (added **or** modified folders) — a folder off the shrinking
`_LEGACY_ALLOWLIST` fails on a hard error or a strict warning; the CI `docs-format` job runs it `--all --strict` and fails on any non-allowlisted finding, warnings included.
`scripts/dev/hooks/check_checkbox_consistency.py` (see §"Checkbox consistency") is the companion sweep for task-state drift and task-line-tail shape; it is also wired into pre-commit and the CI
`--all` gate. `md-organize`'s periodic `--all` sweep is now a local pre-check ahead of committing, not the enforcement point. New folders start conforming via `/new-story` (or `python -m
scripts.dev.new_plan_folder`), which scaffolds from `docs/plan/_TEMPLATE/`.

### Status transitions

`⬜ Not started` → `🔄 In progress` → `✅ Done` → `✅ Archived`. A `✅ Done` story stays listed until archived; archival is not optional and not deferred — it happens in the completion commit per
*Completion → archive* above.
