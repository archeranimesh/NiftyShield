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

**`telegram-markdown-migration/`** · 🔄 In progress — `strategy-rollout/` next: **ROLL-6**
Switch all Telegram messaging to `parse_mode=MarkdownV2` via three sequenced sub-stories:
`backbone/` (parse-mode switch + escaping audit — closed, `57c1c3c`),
`formatting-rules/` (value/table spec → `FORMATTING.md` — closed, `75cc123`),
`strategy-rollout/` (per-message-family migration — in progress).
Supersedes `telegram-ic-comparison-formatting/` TGFMT-2..9.
Converted to the canonical epic format (router + Stories table, canonical task lines,
As-built digests) by `root-doc-organization/` RDO-17.6 (2026-08-29, `cf46ff4`).

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

**`root-doc-organization/`** · 🔄 In progress · next: **RDO-16** (loop-closure check — one real
session confirms the doc-freshness mechanism end to end; RDO-11 also open, date-gated ≥ 2026-09-03; RDO-17.7 §B is Owner: Animesh)
Token-efficiency cleanup of the ~22 root `.md` files + doc-maintenance automation.
Docs + tooling only. RDO-1..17 + an acceptance-criteria list in `tasks.md`.
RDO-1/2/4/5/6/7/8/9/10/12/13/14/15 + RDO-17.1..17.6 shipped, RDO-3 closed-partial;
RDO-17.7 §B, RDO-16, RDO-11 open.
RDO-17.6 (2026-08-29): full-converted `telegram-markdown-migration/` — the epic POC (after 17.5's
flat-story POC). Root `README.md` → `_TEMPLATE/epic/` shape (Stories table w/ Status + Closing SHA);
`prompt.md` → epic router; all 3 sub-stories' `tasks.md` → canonical one-liner task lines,
forensic detail folded into `stories.md` As-built paragraphs. `cf46ff4`.
RDO-17.5 (2026-08-29): full-converted `root-doc-organization/` to the canonical format — every
task line a one-liner with the 5-field tail, `stories.md` covering every task, `prompt.md`
realigned to `_TEMPLATE/story/`; folded in RDO-17.7 §A (retire semantic linefeeds for fill-to-≤200).
RDO-17 (2026-08-29): standardized the `docs/plan/` story & epic folder format —
flat single-story vs epic-with-sub-stories, required `stories.md`, conditional `schema.md`,
`| Owner | Model | Review | SHA` task line, `/work` epic descent; `_TEMPLATE/` gets
`story/` + `epic/` variants. 17.4 did a partial retrofit of the two validation folders;
17.5/17.6 supersede it with a full POC conversion (shipped task lines included) to calibrate
converting the remaining ~25 legacy folders.
RDO-6 (2026-08-29): `md-cleanup` → `md-organize` skill rewrite; `.agents/` mirror re-synced;
`CLAUDE.md`/`AGENTS.md` long-line wrap + Step 5a task-line pointer; whole-repo
`md-line-length` backlog (~700 lines / ~70 files) cleared, `--all-files` green.
RDO-7 (2026-08-29): `session-close` gains a report-only `DOC STALENESS` content-gap check.
RDO-10 (2026-08-28): reconciled RDO-7/Phase 7 with the two shipped doc-freshness hooks —
RDO-7 narrowed to content gaps only, `md-organize` name settled, `#4` → future read-only
Telegram digest, `state_doc_freshness.sh` thresholds tuned.

**`session-entry-point/`** · ✅ Archived 2026-08-28 → `docs/archive/plan/session-entry-point/`
Unified manual `/work` skill (SEP-1..4) — routes a task session to Feature or Bug, loads the
right prompt + first unchecked task, hands to `CLAUDE.md` Step 2b.

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

### Folder shapes — size to scope

Work under `docs/plan/` takes one of two shapes.

- **Single story** — one coherent goal, however many tasks.
  A flat folder `docs/plan/<slug>/` (`<slug>` kebab-case — no date prefix, no `<slug>_`
  filename prefix). `risk-gamma-phase-a/` is the model.
  Start it by copying `docs/plan/_TEMPLATE/story/`.
- **Epic** — two or more related stories shipped together.
  `docs/plan/<slug>/` with a router `prompt.md` + `README.md` at the root and one sub-story
  folder per story **directly under it** — `docs/plan/<slug>/<story-slug>/`, no `stories/`
  layer. `telegram-markdown-migration/` is the model.
  Start it by copying `docs/plan/_TEMPLATE/epic/`.

A single story that grows a second story is promoted: create `<slug>/<story-a>/` and
`<slug>/<story-b>/`, move the original three files into `<story-a>/`, add the root
`prompt.md` router + `README.md`.

### Story-folder file set

Applies to a flat single-story folder and to each epic sub-story folder.

| File | Required | Purpose |
|------|----------|---------|
| `prompt.md` | yes | Session entry point — first-unchecked-box protocol, hard constraints, test gate, load hints. Loaded by `/work` on selection. |
| `tasks.md` | yes | The working checklist — first unchecked `- [ ]` is the task. One line per task (format below). |
| `stories.md` | yes | Complete per-task spec — files, "before any code" graph queries, what to implement, tests, commit message. Self-contained. |
| `schema.md` | conditional — see *When a story needs `schema.md`* | DDL + the `DB_REGISTRY.md` row, when the story changes DB schema. |
| `plan.md` / `spec.md` | optional | File-by-file plan / wire formats / gate criteria for a large story — no task checkboxes (see *Extra files*). |

Legacy folders may still carry `<name>_tasks.md` / `<name>_stories.md`, a `stories/<ID>.md`
one-file-per-story layout, or `phaseN/` sub-folders — do not mass-rename; each converts to
the shape above on its next substantive touch.

### Epic-folder file set

The epic root carries **only what is common to every sub-story** — never task checkboxes.

| File | Required | Purpose |
|------|----------|---------|
| `prompt.md` | yes | The **router** — `/work` loads this, not a sub-story `prompt.md`. See *Epic router* below. |
| `README.md` | yes | The shared brief — see *Epic README* below. |

**Epic router (`prompt.md`)** — states the fixed story order; walks each sub-story's
`tasks.md` for the first unchecked `- [ ]`; confirms that task line's `Owner` / `Model` /
`Review`; hands to that sub-story's own `prompt.md` + `stories.md`.
One task per session, then stop.

**Epic README** — why the epic exists, the scope decisions (and with whom), the ordered
story list with a status column (⬜ / 🔄 / ✅ + closing SHA) and per-story dependency, the
cross-cutting constraints every sub-story must honour, supersession / coordination notes.
A fact needed by only one story belongs in that story's files.

### When a story needs `schema.md`

Decide at planning time, while writing `stories.md`. A story needs a `schema.md` iff a task:

- adds a table (`CREATE TABLE`);
- adds / renames / drops a column, or changes a column's type or constraint;
- introduces a new `*Store` class with its own `init_db()` DDL;
- adds a contract index (query-critical, not incidental);
- changes how a stored value is encoded in a way a future reader must know — a new enum
  value in a `TEXT` column, a units change, a new composite-key format.

It is **not** needed when the story only reads existing tables, writes rows into existing
tables with no shape change, or is pure computation / formatting / notification /
script-wiring.

DDL lives in `schema.md`, never inline in `stories.md` — `stories.md` points to it ("use
the exact schema from `schema.md`"). `schema.md` **must** also state the `DB_REGISTRY.md`
row to add. `check_story_structure.py` warns (does not block) when a `stories.md` /
`prompt.md` contains `CREATE TABLE` / `ALTER TABLE` and the folder has no `schema.md`.

### Extra files

A story or epic folder may carry additional `.md` files beyond the sets above **only** when
the file is shared reference material used by more than one task — a reusable prompt, a
`plan.md`, a `spec.md`, a research note — **and** it contains no `- [ ]` / `- [x]` task
checkboxes. Anything with tracked checkboxes is a task list and belongs in a story folder's
`tasks.md`. OS / editor cruft (`.DS_Store`, `*.swp`) is removed — it is already
`.gitignore`d. `check_story_structure.py` flags a tracked non-`.md` file in a plan folder,
and an extra `.md` that contains checkbox lines.

### Task-line format

Every `tasks.md` line is a single `- [ ]` checkbox carrying five `|`-separated fields:

```
- [ ] **<ID>** — <one-line description> | Owner: <Claude|Antigravity|Animesh> | Model: <model-id|n/a> | Review: <code-reviewer|greeks-analyst|roll-validator|none> | SHA: <—>
```

`Owner`, `Model`, and `Review` are filled **when the story is authored** — they record the
`CLAUDE.md` Step 3b routing decision and which AutoTrigger sub-agent gates that task's
commit.
`Model` is the implementing model id when `Owner=Claude` (e.g. `claude-sonnet-5`), `n/a`
otherwise.
`Review` is `none` for docs-only tasks.
`SHA` is `—` until the task's commit lands; then set it to the real SHA and tick the box.
One line per task — never mirror task state into `TODOS.md` or a `stories.md` DoD box.

### Canonical state vs derived state

`tasks.md` checkbox state is the single source of truth for task progress.
Everything else is derived and must not be hand-edited to disagree with it:

- this file's per-story status / next marker — a summary of the story's `tasks.md`
- a `stories.md` DoD checkbox — mirrors its `tasks.md` task

### Checkbox consistency (RDO-15)

Every task id carries **exactly one** checkbox — the `- [ ]` / `- [x]` line in the working
list.
A trailing `## Epic done when` (epic) / `## Story done when` (single story) block is an
**acceptance-criteria list in prose** — bold id, one-line criterion, **no `- [ ]`
checkboxes** — verified at close, not tracked incrementally.
An acceptance item with no matching task id (e.g. a whole-epic "loop-closure verified"
check) is real work: give it a task id in the working list, don't leave it as a bare bullet
here.
Nothing mirrors task state, so nothing can drift.
`scripts/dev/hooks/check_checkbox_consistency.py` sweeps every `docs/plan/**/tasks.md` (plus
legacy `*_tasks.md`) and `docs/bugs/task.md` for: a checkbox inside a summary block
(`## Epic done when` / `## Story done when` / `## Definition of done` / …), the same id with
disagreeing state in one file, a README `next:` marker pointing at an already-done id, and —
on any line carrying the canonical `| Owner: … | Model: … | Review: … | SHA: …` tail — a
`Review` value that is not a known gate name (`code-reviewer` / `greeks-analyst` /
`roll-validator` / `none`) or a `SHA` that disagrees with the checkbox state (`—` / `<—>`
iff unchecked, a real 7–40 hex SHA iff ticked). Legacy tails (`| Owner | Model | SHA` with
no `Review`, or a prose-laden `| Review:`) are grandfathered — skipped, not flagged.
It runs in the `md-organize` skill's periodic audit — not pre-commit (task files churn far
faster than the audit needs to).

### `TODOS.md` hygiene

`TODOS.md` carries two separate pointer-only lists — `## Feature Backlog` (`docs/plan/`
stories) and `## Open Bugs` (`docs/bugs/` defects). `/work` routes to one or the other.
Each item is **pointer-only**: title, the `docs/plan/<slug>/` or `docs/bugs/` path, the next
unchecked task id, and a one-line why.
No inline multi-paragraph detail, no per-task progress — that lives only in the story's
`tasks.md` / `docs/bugs/task.md`.
Cross-references between items use folder names, never list positions.
The `## Open Bugs` snapshot is not authoritative — `docs/bugs/bugs.md` is; never encode bug
priority or status in `TODOS.md`.
On completion, a line is removed, not just ticked — see *Completion → archive*.

### Completion → archive

A story or bug is **done** when every `- [ ]` in its `tasks.md` / `docs/bugs/task.md` is
ticked and its `## Epic done when` / `## Story done when` acceptance block (if present) is
satisfied.
As soon as that holds, do all of the following in the same commit — never leave a done
story half-archived:

1. **Story:** `git mv docs/plan/<slug>/ docs/archive/plan/<slug>/`
   (bug: `git mv docs/bugs/<slug>/ docs/archive/bugs/<slug>/`, or fold the `bugs.md` entry
   into `docs/archive/bugs/bugs.md` and mark it `[MOVED]` at the original location).
2. **`TODOS.md`:** delete the item's line from `## Feature Backlog` / `## Open Bugs` and
   append it to `docs/archive/TODOS_ARCHIVE.md` under a dated heading.
3. **This file:** collapse the story's entry under `## Active Epics` to a one-line
   `✅ Archived → docs/archive/plan/<slug>/` pointer.
4. **`bugs.md`:** flip the status cell to `✅ Fixed` with the closing SHA before the entry
   moves.

The `md-organize` skill's periodic audit and the `session-close` skill both check for done
stories that were not archived; do not rely on that — archive at completion.

### Markdown line style (RDO-5; fill-to-≤200 per RDO-17.7 §A, 2026-08-29)

Prose fills each line to the last word boundary before 200 chars — do not break early at a sentence or clause end, and do not hand-wrap to a fixed narrow width. The earlier "semantic
linefeeds" guidance (one sentence or clause per line) is **retired**: the mid-line wrap near ~110 chars it produced was harder to read in source, not easier, and it made diffs noisier.
The hard **200-char ceiling** is the only gated rule. It applies to every line kind (prose, table rows, fenced code) and is enforced by the `md-line-length` pre-commit hook over root
`.md` + `docs/plan/**` + `docs/bugs/**`; `<!-- lint-ignore-length -->` on the immediately-preceding line excuses one unbreakable token (a long URL, a base64 blob).
`.py` stays at ruff's `line-length = 100` (ruff already excludes `docs/`).
Existing docs reflow to fill-to-200 opportunistically when a commit next touches them — no big-bang pass (the same rule RDO-5 used to clear its own backlog).

### Structure audit

`scripts/dev/hooks/check_story_structure.py` checks every non-archived `docs/plan/*/` folder:
a flat story folder has `prompt.md` + `tasks.md` + `stories.md`; an epic root has
`prompt.md` + `README.md` and at least one conforming sub-story.
It also flags stray or empty folders, a missing `schema.md` against DDL in
`stories.md` / `prompt.md` (warning), and disallowed extra files (see *Extra files*).
It runs pre-commit on newly-added folders only — legacy shapes are grandfathered, so the
repo-wide `--all` sweep warns but does not fail; the full sweep is part of the
`md-organize` skill's periodic audit, since folders churn only ~monthly.
`scripts/dev/hooks/check_checkbox_consistency.py` (see §"Checkbox consistency") is the companion
sweep for task-state drift and task-line-tail shape; it runs alongside it in the same audit,
also not pre-commit.

### Status transitions

`⬜ Not started` → `🔄 In progress` → `✅ Done` → `✅ Archived`.
A `✅ Done` story stays listed until archived; archival is not optional and not deferred —
it happens in the completion commit per *Completion → archive* above.
