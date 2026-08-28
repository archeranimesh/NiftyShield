# `docs/plan/` — Story Index

> Each story folder is self-contained. Start from its `prompt.md`.
> Archived original files: `docs/archive/plan/`.
> Confirmed defects in shipped code (not forward spec work): [`docs/bugs/`](../bugs/) — same
> folder conventions, separate registry. See also the archived legacy registry
> [`BUGS_LEGACY.md`](../archive/BUGS_LEGACY.md) (superseded).

The **status** and **next** markers below are a *summary* of each story's `tasks.md`.
`tasks.md` is canonical; if they disagree, `tasks.md` wins and this file is stale.
Format per entry: `**\`folder/\`** · <status> · next: **<task id>**` then a short blurb.

---

## Active Epics

**`dev-foundation/`** · ✅ Shipped/Archived
Engineering-excellence epic — tooling, CI, code health (3 sub-stories).

**`full-repo-review-followups/`** · ⬜ Not started — start with the P0 folders
9 stories from the full-repo-review FR-7 synthesis (7 CRITICAL + 2 ERROR).
P0: portfolio P&L fix, DB backup cron.
P1: docs staleness, Telegram auth fix.
P2: CLAUDE.md/REVIEW.md reconcile, logging migration.
P3: Greeks/parity validation (council-gated), golden tests, suppression hygiene.
Priority + dependencies in the epic's own `README.md`.
`telegram-approval-auth-fix/` already shipped (SHA `5cafc3c`).

**`telegram-markdown-migration/`** · 🔄 In progress — `strategy-rollout/` through ROLL-3
Switch all Telegram messaging to `parse_mode=MarkdownV2` via three sequenced sub-stories:
`backbone/` (parse-mode switch + escaping audit — closed),
`formatting-rules/` (value/table spec → `FORMATTING.md` — closed),
`strategy-rollout/` (per-message-family migration — in progress).
Supersedes `telegram-ic-comparison-formatting/` TGFMT-2..9.

**`telegram-ic-comparison-formatting/`** · 🔄 TGFMT-1 shipped; rest superseded
TGFMT-1 fixed `build_comparison_report()`'s hand-counted-width alignment bug.
TGFMT-2..9 superseded 2026-08-07 by `telegram-markdown-migration/`.
The two still-open feature asks (Legs row, Bkd/Flt month-inception split) carried into
`strategy-rollout/` ROLL-2.

**`3track-consolidation/`** · ✅ Shipped/Archived 2026-08-04 → `docs/archive/plan/3track-consolidation/`
Overlay (CC/PP/Collar) retired on Futures/Proxy, live only on NiftyBees; base-leg-only daily
comparison snapshot; automated base-leg rolling; full unattended automation.

---

## Active Stories

**`eod-pt-summary/`** · ⬜ Not started · next: **PT-1** (document the 3-message spec)
Cross-strategy paper-trade EOD report (open, closed-today, strategy-wise P&L / Ann.%-on-margin)
as 3 MarkdownV2 Telegram messages.
Promotion to `src/` + cron is gated on a coordination decision vs `scripts/eod_summary.py` /
`scripts/reporting/paper_pnl_report.py`.

**`risk-gamma-phase-a/`** · 🔄 In progress · next: **B2.2** (chain fetch + field computation)
Risk delta gate (done) + Near-Expiry Gamma Buy `gamma_daily_watch.py`.

**`variance-gate/`** · ⬜ Not started · next: **VG0** (CSP v1 spec reconciliation)
CSP v1 Phase 0.8 deployment gate — spec reconciliation + gate criteria A–D.

**`root-doc-organization/`** · 🔄 In progress · next: **RDO-13** (folder conventions + `_TEMPLATE/` + audit)
Token-efficiency cleanup of the ~22 root `.md` files + doc-maintenance automation.
Docs + tooling only. RDO-1..15 + an "Epic done when" checklist in `tasks.md`.
RDO-1/2/4/5/8/12 shipped, RDO-3 closed-partial; RDO-6/7/9/10/11/13/14/15 open.

**`session-entry-point/`** · ✅ Done 2026-08-27 (SEP-1..4)
Unified manual `/work` skill — routes a task session to Feature or Bug, loads the right
prompt + first unchecked task, hands to `CLAUDE.md` Step 2b.

**`paper-backbone/`** · ✅ Shipped/Archived
Strategy Monitor daemon + pluggable strategy backbone (`src/strategy/`, `TelegramGateway`).

**`mvp/`** · ⬜ Not started · next: **M1** (models + store)
Multi-bagger Value Picks Tracker (`src/mvp/`, `scripts/mvp.py`, `scripts/mvp_watch.py`).

**`council-refactor/`** · ✅ Shipped/Archived
Remove `RapidCouncil` from the daemon approval path; fix `send_approval_request` signature
bug; add deterministic backtestable roll rules to `ExitSignalEngine`.

**`ic-nifty-v2/`** · ✅ Shipped/Archived
IronCondorV2 — 25Δ/22Δ high-delta IC with 10Δ wings, partial-roll adjustment, DTE-tiered exit.

**`paper-exit-codification/`** · ✅ Shipped/Archived 2026-08-04 → `docs/archive/plan/paper-exit-codification/`
Codify q11+q12 council rulings: TIME_STOP/DTE_REVIEW priority fix in `evaluate_cc`;
StrategyMonitor observability logs.

**`telegram-leg-labels/`** · ✅ Shipped/Archived 2026-08-07 (TL-1..5) → `docs/archive/plan/telegram-leg-labels/`
Replace raw Upstox instrument keys in Telegram prose with human-readable
`NIFTY 22000 CE 07 JUL 26` labels; CLI command lines untouched.

**`ic-yearly-expiry-fix/`** · 🔄 Partially superseded · next: **WG-1** (weekly-bucket Greeks snapshot gap)
Fix `InstrumentLookup.get_expiry_candidates()`'s `"yearly"` label resolving June instead of
December — NSE Nifty's annual contract is always December's last Tuesday.
YE-1..4 superseded 2026-07-22 (DECISIONS.md BUG-015); WG-1 open.

**`greeks-bs-fallback/`** · 🔄 Partially scoped · next: **GF-1** (audit scope)
Upstox returns all-zero `option_greeks` for far-dated NIFTY contracts despite liquid
`ltp`/`bid`/`ask`/`oi` — a data gap, not illiquidity.
Blocks delta-based IC entry for the yearly bucket.
Decision: compute Greeks ourselves (BS pricer + Newton-Raphson IV solver), not a cruder
OTM heuristic.
3 modeling decisions (risk-free rate, DTE convention, delta tolerance) still need Animesh.

**`chain-decay-analysis/`** · ⬜ Not started · next: **CDA-1** (paired-snapshot reader)
Empirical check: does intraday option premium move track delta (+ gamma/theta/vega
decomposition), or is there a persistent residual — and which moneyness bands decay faster
than theta alone predicts.
Existing 5-min intraday chain Parquet. Monthly bucket only.

**`full-repo-review/`** · ✅ Complete — see `full-repo-review-followups/`
One-time multi-model, multi-persona review of design docs, source, tests, the
AI-collaboration protocol, and per-job-type surface routing (FR-1..9).

**`ic-time-stop-dte-tiering/`** · ✅ Shipped/Archived 2026-08-05 (DT-1..4) → `docs/archive/plan/ic-time-stop-dte-tiering/`
Council-ruled fix (`docs/council/2026-08-05_...`): de-tier per-bucket
`time_stop_dte`/`dte_warn` to a uniform terminal rule; forward-only counterfactual DTE-mark
logging on `paper_exit_events`.

**`monitor-and-close-hardening/`** · ✅ Shipped/Archived 2026-08-06 → `docs/archive/plan/monitor-and-close-hardening/`
StrategyMonitor tick-loop observability + auto-close leg-resolution hardening — dedupe
`expiry_unresolved` logging, BOD-resolve replacement-leg keys, atomic close+open, shared
BOD-fallback finder (MC-1..MC-6).

**`paper-ic-daily-snapshot/`** · ✅ Shipped/Archived 2026-08-07 → `docs/archive/plan/paper-ic-daily-snapshot/`
IC daily P&L snapshot wiring (SNAP-1..5): confirmed realized/unrealized semantics, built
`scripts/reporting/paper_pnl_report.py`, fixed `paper_nav_snapshots.total_pnl` invariant +
backfilled 42 rows.

---

## Blocked / Later Stories

| Folder | Blocked by |
|--------|------------|
| `backtest-eval-core/` | Phase 1.3 (Bhavcopy) + Phase 1.4 (BacktestEngine) |
| `signals-eval-core/` | backtest-eval-core + Phase 1.12 gate |
| `signals/` | signals-eval-core |

---

## Conventions

This section is canonical and self-contained — there is no pointer to
`docs/archive/plan/README.md` (that file documents the retired one-file-per-task scheme and
is dead for convention purposes).

### Story-folder file set

A story folder is `docs/plan/<slug>/` where `<slug>` is kebab-case — no date prefix, and no
`<slug>_` prefix on the files inside it.
Copy `docs/plan/_TEMPLATE/` to start a new one.

| File | Required | Purpose |
|------|----------|---------|
| `prompt.md` | yes | Why the story exists, session-start load hints, task overview |
| `tasks.md` | yes | The working checklist — find the first unchecked `- [ ]` and do only that |
| `stories.md` | optional | Per-task implementation spec / DoD detail |
| `spec.md` / `schema.md` | optional | Data models, wire formats, gate criteria |
| `plan.md` | optional | File-by-file change plan for a large multi-phase story |

Legacy folders may still carry `<name>_tasks.md` / `<name>_stories.md` — do not mass-rename
them; new folders use the bare names above.

### Completed-task line format

When a `tasks.md` checkbox is ticked, append this tail to the task line:

```
| Owner: <Claude|Antigravity|Animesh> | Model: <model-id|n/a> | SHA: <commit-sha>
```

`Owner` records the `CLAUDE.md` Step 3b routing outcome.
`Model` is the implementing model id when `Owner=Claude` (e.g. `claude-sonnet-5`), `n/a`
otherwise.
`SHA` is the commit that closed the task.
One line per task — never mirror task state into `TODOS.md`.

### Canonical state vs derived state

`tasks.md` checkbox state is the single source of truth for task progress.
Everything else is derived and must not be hand-edited to disagree with it:

- this file's per-story status / next marker — a summary of the story's `tasks.md`
- a `stories.md` DoD checkbox — mirrors its `tasks.md` task
- a trailing `## Epic done when` block in `tasks.md` — mirrors the working list above it

### `TODOS.md` hygiene

`TODOS.md` "Priority-Ordered Open Work" items are **pointer-only**: title, the
`docs/plan/<slug>/` or `docs/bugs/` path, the next unchecked task id, and a one-line why.
No inline multi-paragraph detail, no per-task progress — that lives only in the story's
`tasks.md` / `docs/bugs/task.md`.
When a story or bug is fully done its `TODOS.md` line is **deleted** (moved to
`docs/archive/TODOS_ARCHIVE.md`), not just ticked.

### Markdown line style (RDO-5, decided 2026-08-27)

Prose uses *semantic linefeeds* — one sentence or clause per line; no fixed-width hand-wrap.
~120 chars is a soft target, not gated.
A hard 200-char ceiling applies to every line kind (prose, table rows, fenced code) and is
enforced by the `md-line-length` pre-commit hook over root `.md` + `docs/plan/**` +
`docs/bugs/**`; `<!-- lint-ignore-length -->` on the preceding line excuses an unbreakable
token.
`.py` stays at ruff's `line-length = 100` (ruff already excludes `docs/`).

### Structure audit

`scripts/hooks/check_story_structure.py` checks that every non-archived `docs/plan/*/` folder
has `prompt.md` + `tasks.md`, and flags stray or empty folders.
It runs pre-commit on newly-added folders only; the full repo-wide sweep is part of the
`md-organize` skill's periodic audit, since folders churn only ~monthly.

### Status transitions

`⬜ Not started` → `🔄 In progress` → `✅ Done`.
A `✅` story stays listed until archived; on archive, its folder content moves to
`docs/archive/plan/<slug>/` and the row keeps a one-line pointer there.
