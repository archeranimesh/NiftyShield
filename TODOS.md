# NiftyShield — TODOs

> Open work only. Completed items: [docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md) | Known defects: [docs/bugs/](docs/bugs/)
> Related: [CONTEXT.md](CONTEXT.md) | [DECISIONS.md](DECISIONS.md) | [PLANNER.md](PLANNER.md) | [BACKTEST_PLAN.md](BACKTEST_PLAN.md) | [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md)
>
> **Task tracking lives in the story folders.** Per-task state is in each story's
> `docs/plan/<slug>/tasks.md` or `docs/bugs/task.md`. The lists below are **pointers only**
> — title, path, next unchecked task, one-line why. Full rules:
> [`docs/plan/README.md`](docs/plan/README.md) §Conventions.
>
> Two separate lists: **`## Feature Backlog`** (forward spec work, `docs/plan/`) and
> **`## Open Bugs`** (defects in shipped code, `docs/bugs/`). `/work` routes to one or the
> other. When a story or bug is fully done its line here is **deleted** (moved to
> [`docs/archive/TODOS_ARCHIVE.md`](docs/archive/TODOS_ARCHIVE.md)) and its folder moved to
> `docs/archive/plan/<slug>/` — see §Conventions → *Completion → archive*.

---

## Feature Backlog — Priority Ordered

Forward spec work only — one `docs/plan/` story per line, pointer-only (title · folder ·
next unchecked task · one-line why).
Ordered **story-by-story**: finish a story's `tasks.md` in sequence before starting the next
story here; this list only decides *which story is next*.
Bugs are **not** here — see `## Open Bugs`.
Cross-references use folder names, never list positions, so renumbering can't rot them.

1. **root-doc-organization** — `docs/plan/root-doc-organization/` — next **RDO-17.1**
   (`docs/plan/` story/epic format standardization — 4 sub-tasks). RDO-16 (loop-closure)
   and RDO-11 (≥ 2026-09-03) also open.
   Root `.md` token-efficiency cleanup + doc-maintenance automation.
2. **IC yearly-expiry residual risk** — `docs/plan/ic-yearly-expiry-fix/` — next **WG-1**
   (persist per-leg Greeks for the weekly-expiry bucket).
   YE-1..YE-4 superseded / already fixed live — see DECISIONS.md BUG-015.
3. **Greeks Black-Scholes fallback** — `docs/plan/greeks-bs-fallback/` — next **GF-1**
   (read-only audit scope).
4. **Telegram Markdown migration** — `docs/plan/telegram-markdown-migration/` — next
   **ROLL-6** (`strategy-rollout/`, migrate EOD Paper Summary).
   `backbone/` + `formatting-rules/` sub-stories closed.
   Supersedes the retired `telegram-ic-comparison-formatting/` — TGFMT-1 shipped, TGFMT-2..9
   folded here; its Legs-row + Bkd/Flt inception-split asks live in `strategy-rollout/` ROLL-2.
5. **MVP: Multi-bagger Value Picks Tracker** — `docs/plan/mvp/` — next **M1.1**.
   Independent — blocks nothing.
6. **Variance gate — CSP v1 deployment gate observation** — `docs/plan/variance-gate/` —
   next **VG0** (spec reconciliation; the remaining tasks are human checkpoints, not build
   tasks).
7. **Options Income strategy** — `docs/plan/options_income/` — next **S0** (data audit).
8. **Backtest Engine** — `docs/plan/backtest-engine/` (`phase1..4/`) — next **1.3a / 1.4**
   (parallel, `phase1/`).
   Four chained phases; each phase's GATE task blocks the next dir. Gated on `variance-gate`.
   `BACKTEST_PLAN_PHASE1.md` is the canonical spec; the phase dirs are thin status pointers.
9. **backtest-eval-core** — `docs/plan/backtest-eval-core/` — next **B1.1**.
   Blocked until `backtest-engine` tasks 1.3 + 1.4 land.
10. **signals-eval-core** — `docs/plan/signals-eval-core/` — next **SE1.1**.
    Blocked until `backtest-eval-core` + `backtest-engine` 1.12.
    Covers Track A (swing) + Track B (investment), SE1–SE8.
11. **signals: multi-LLM daily signal pipeline** — `docs/plan/signals/` — next **S1.1**.
12. **risk-gamma-phase-a** — `docs/plan/risk-gamma-phase-a/` — next **B2.2**
    (chain fetch + field computation). Track A + B1 / B2.1 shipped.
13. **greeks-parity-validation** —
    `docs/plan/full-repo-review-followups/greeks-parity-validation/` — next **T1**.
    P3, council-gated: do not implement directly — needs an `options-strategist` /
    `greeks-analyst` consult first (tolerance-band decision).
14. **paper-pnl-golden-tests** —
    `docs/plan/full-repo-review-followups/paper-pnl-golden-tests/` — next **T1**
    (exact-value golden assertions for `_compute_leg_unrealized_pnl`). P3.
15. **suppression-hygiene-triage** —
    `docs/plan/full-repo-review-followups/suppression-hygiene-triage/` — next **T1**
    (REVIEW.md carve-out for self-describing `# noqa` codes). P3.
16. **Fix dead IC EOD report query** — `scripts/strategies/ic/paper_ic_snapshot.py`
    (no story folder) — the "Intraday actions" query is dead code, found in the DT-3a audit.
17. **Chain delta/decay analysis** — `docs/plan/chain-decay-analysis/` — next **CDA-1**.
    Exploratory / read-only, independent.
    Monthly bucket only (yearly excluded — see `greeks-bs-fallback` GF-1 findings).
18. **Entry event filter R4** — `docs/plan/entry-event-filter/` — next **EF-1**.
    Good-to-have, not compulsory; soft-warning only (logged, non-blocking, mirrors
    `GateViolation`). `events.yaml` needs ad-hoc upkeep.
    Revisit once entries run unattended on live capital (post `backtest-engine` Phase 2), and
    reconsider hard-block then.
19. **Broker abstraction** — `docs/plan/broker-abstraction/` — next **BA-0**
    (probe scripts + decision matrix).
    LOW priority; storage format frozen, only fetch + parse change.
    BA-14 / BA-15 blocked until `src/execution/` (`phase2-integrations` OE-1) exists.
    Do not start until the Phase 0.8 gate clears.
20. **Historical data abstraction** — `docs/plan/historical-data-abstraction/` — next
    **HD-0** (cost-bounded probe scripts). LOW priority.
    `HistoricalCandleFetcher` protocol so VIX + OHLC fetching can switch brokers without
    touching storage. HD-6 / HD-7 conditional on the HD-0 decision matrix.
    Do not start until the Phase 0.8 gate clears.
21. **Phase 2 — Research Pipelines & Integrations** — `docs/plan/phase2-integrations/` —
    next **PV-1** (P&L visualization — not gated, can be pulled forward).
    ZK-1 / OE-1 / PT-1 gated per the story file. 2027+.
    Excludes the swing / investment signal pipelines — those are `signals`.
22. **Technical Debt** — `docs/plan/technical-debt/` — DEBT-3 / 5 / 6a / 6b / 6c / 7.
    Opportunistic, **not sequential** — each item fires only when its named file / module is
    already being touched for another story's task. See `prompt.md` for the per-item trigger.

## Open Bugs

Confirmed defects in shipped code live in **[`docs/bugs/`](docs/bugs/)** — registry
`bugs.md` (status `🔴 Open` → `🟡 Fix in progress` → `✅ Fixed`), tasks `docs/bugs/task.md`.
`/work` → Bug branch reads those files directly; it does **not** read this file.
**Do not mirror bug priority or status here** — `bugs.md` is the single source of truth.

Snapshot (authoritative list: `bugs.md`) —

- **BUG-030** — `_overlay_type_groups` elif-precedence orphans the `overlay_cc` leg when
  `overlay_collar_put` is also present same-day.
  Next: **B030.1** (entry-side tagging question, blocks the grouping fix).
- **BUG-037** — `mark_trade_closed()` never wired into CSP / IC v1 / v2 close paths;
  54 stale flat legs found live.
  Next: **B037.6** (`code-reviewer` on the B037.3 / B037.4 fix).
- **BUG-038** — `OverlayCloser`'s three `self._notifier.send()` calls are unawaited
  coroutines (never actually sent).
  Next: **B038.1** (`trace_path` the three send methods).
- **BUG-019** — diagnostic-only, not actionable (awaiting a live trading day's data before a
  fix is scoped).

Feature-vs-bug priority is chosen at session start via `/work`. A bug urgent enough to
pre-empt all feature work should be raised with Animesh directly — it is not expressed by
reordering either list.

**Before build queue starts on paper-backbone-dependent stories** — verify prerequisites:
```bash
search_graph("StrategyMonitor")   # must return results
search_graph("PaperExecutor")     # must return results
search_graph("CCOverlayV1")       # must return zero results
```

---

## Animesh-only: Stockmock Calibration Backtests

Prerequisite for `backtest-engine` (`docs/plan/backtest-engine/phase1/tasks.md` task **1.1**,
which itself feeds task 1.7's `CSPConfig`). Stockmock UI — no code required.

- [ ] COVID crash (Feb–Apr 2020) — strikes hit, premium, max M2M loss, breach frequency
- [ ] IL&FS crisis (Sep–Oct 2018) — same metrics
- [ ] 2022 rate-hike selloff (Jan–Jun 2022) — same metrics
- [ ] Stable baseline (Jan–Dec 2023) — expected exit-type distribution in normal markets
- [ ] Summarise in [docs/strategies/csp_nifty_v1.md](docs/strategies/csp_nifty_v1.md) under "Calibration Backtest Results (Stockmock)"
- [ ] Commit: `docs(strategies): CSP v1 Stockmock calibration backtest results`

---

## Session Log

Full forensic log (SHAs, bug numbers, root-cause detail) moved to
[docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md) — most recently during the
2026-08-26 reorg (everything from 2026-08-01 through 2026-08-26, plus item 29's inline design
history above). Add new entries there going forward, or start a fresh dated section here if
this file's Session Log grows large again.

### 2026-08-29

- **RDO-6 + RDO-7 — `md-organize` skill + doc-staleness check (root-doc-organization).**
  4 commits, docs/tooling only. RDO-7 (`d24f15d`): `session-close/SKILL.md` Step 3e —
  report-only content-gap check (new module w/o `CONTEXT_TREE.md` row; story code touched but
  `docs/plan/README.md` status not advanced). RDO-6: `.claude/skills/md-cleanup` → `md-organize`
  with a rewritten `SKILL.md` (real 19-file root table; CONTEXT re-slim / DECISIONS roll /
  repo-wide `md-line-length` sweep / `CLAUDE.md` pointer reconcile / story-structure +
  checkbox audits / RDO-10 hook-drift check / Step 7 mirror re-sync). `.agents/skills/`
  re-synced wholesale from `.claude/skills/` (added `work/`, dropped all "Codex" refs).
  `CLAUDE.md` + `AGENTS.md` 11 long lines each wrapped; Step 5a task-line pointer added
  (RDO-13 deferred). Whole-repo `md-line-length` backlog cleared — ~700 lines across ~70
  files reflowed to semantic linefeeds via 5 parallel subagents; `--all-files` now green
  (`suggestions.md` excepted — wide table, `SKIP=md-line-length`). Epic now: RDO-11
  (≥ 2026-09-03) + RDO-16 (loop-closure) open.

### 2026-08-28

- **RDO-10 — reconcile RDO-7 / Phase 7 with the shipped doc-freshness hooks
  (root-doc-organization).** Docs + one hook edit, 1 commit. Decisions with Animesh:
  (1) RDO-7 **kept but narrowed** — `state_doc_freshness.sh` (SessionStart) +
  `doc_update_gate.sh` (PreToolUse) already own the per-file "docs behind code" signal, so the
  session-close report is re-scoped to the content gaps neither hook sees (new `src/<module>/`
  with no `CONTEXT_TREE.md` row; story code touched this session but `docs/plan/README.md`
  status not advanced). (2) `TODOS.md #4` (weekly cloud routine) **narrowed to a future
  read-only Telegram staleness digest**, out of epic scope — unattended-write cron stays
  rejected. (3) Skill name settled: **`md-organize`** (RDO-6 does the rename + ~6 by-name
  ref updates). (4) `state_doc_freshness.sh` thresholds tuned — `CONTEXT_TREE.md` /
  `DB_REGISTRY.md` / `README.md` 35-40 → 60 (all three change only on new modules / tables /
  public-surface shifts; DB_REGISTRY was the known 36/35 false positive). RDO-6 gains a step
  to verify the two hooks' hard-coded doc lists still match `CLAUDE.md` §Step 5a. `plan.md`
  Phase 7 + `tasks.md` RDO-6/7/10 + `## Epic done when` + `docs/plan/README.md` row updated.
  Open in the epic now: RDO-6, 7, 11, 16. Docs/tooling-only, no code-reviewer.

- **RDO-15 — checkbox-consistency sweep + one-box convention (root-doc-organization).**
  2 commits. `5e48451`: new `scripts/hooks/check_checkbox_consistency.py` (+ 11 tests) —
  sweeps `docs/plan/**/tasks.md` + `docs/bugs/task.md` for a checkbox inside an `## Epic done
  when` block, same-id state drift in one file, and a README `next:` marker on an already-done
  id; `--all` + path modes, runs in the `md-cleanup`/`md-organize` audit (Step 5c), not
  pre-commit. Convention (a) chosen (Animesh delegated) — `## Epic done when` blocks are now
  prose acceptance criteria, no checkboxes; working-list `tasks.md` state is the sole source,
  drift structurally impossible (same principle as RDO-13 §4). Sibling script, not an
  extension of `check_story_structure.py`. Retrofit trivial — only 2 files used the mirror
  (`root-doc-organization`, `session-entry-point`), zero pre-existing drift; `_TEMPLATE/` +
  `docs/plan/README.md` §"Checkbox consistency" updated. Id-less "loop-closure check" item
  promoted to task **RDO-16**. `code-reviewer`: 0 CRITICAL/ERROR, 4 WARNING all fixed
  (README slug regex underscore gap, `task.md` dir-glob, EXCLUDED filter style, test hints).
  `session-entry-point` epic archived to `docs/archive/plan/` in the same session (was done,
  awaiting only this worked-example use).

- **RDO-9 — `DECISIONS.md` semantic split (root-doc-organization).** 3 commits.
  9a: full-file classification (2203 lines) + `options-strategist` advisory pass +
  Animesh sign-off — scratch artifact `rdo9a_classification.md`. The file was big because
  it is append-only and verbose inside a ~4-month window, not old — so split by *kind*:
  9b `344f3a7` moved every completed-work-log entry (the chronological "fixed X, why" stream,
  `## Process`, the dated `## BUG-*` sections, the delivered NSE Bhavcopy UDiFF spec, the
  Telegram-MD sequencing narrative) → `docs/archive/DECISIONS_worklog_2026.md`; lifted 11
  still-enforced rule fragments into a new `## Risk, Delta & Entry Gates` section + existing
  sections; fixed 8 stale rule entries the 9a `options-strategist` pass caught (CSP/CC profit
  target is 30% retention not 50%, CSP delta stop 0.40 not 0.45, CC DTE_REVIEW is ACTION not
  WARN per EC-5, CC re-entry allow-list, CSP time-stop DTE guard from EC-4, Notifications
  HTML→MarkdownV2, §7.3 IC-judged-in-isolation); merged the duplicate `## Market Calendar`
  and `## Developer Tooling` headers. 9b `2fb5c5b` wrapped the file to semantic linefeeds,
  `md-line-length` green, Strategy & Research table → bulleted index. Result: 2203 → 972
  lines, ~84K → ~22K tokens, fresh full-file `Read` succeeds. **DoD deviation:** "≤ 800
  lines" conflicts with the same DoD's semantic-linefeed requirement — flagged to Animesh;
  token count is the metric that holds. Docs-only, no code-reviewer. `prompt.md` DoD +
  `docs/plan/README.md` row updated; RDO-9 + `prompt.md`-DoD-rewrite epic-done boxes ticked.

- **RDO-14 — `TODOS.md` restructure (root-doc-organization).** Design changed with Animesh:
  *not* one unified queue — two separate pointer-only lists, `## Feature Backlog` (`1..N`
  contiguous, `docs/plan/` stories) and `## Open Bugs` (non-authoritative snapshot + pointer
  to `docs/bugs/`), matching `/work`'s existing Feature/Bug fork. Dropped: completed
  `session-entry-point`, superseded `telegram-ic-comparison-formatting`, the duplicate
  "item 14", all `TGFMT-2..9` refs. Every internal `"item N"` cross-ref → story-folder name.
  Whole file reflowed to semantic linefeeds (RDO-13-deferred backlog for this file — no
  `SKIP=md-line-length` needed now). Added per Animesh: `docs/plan/README.md` §Conventions
  gains a *Completion → archive* subsection (story folder → `docs/archive/plan/`, `TODOS.md`
  line → `TODOS_ARCHIVE.md`, README row → pointer, all one commit) + `session-close` Step 5b
  "done-but-not-archived" check. `/work` branch-collapse (RDO-14 §4) explicitly declined;
  recorded in `session-entry-point/tasks.md`. Docs-only.

- **RDO-13 — docs/plan + TODOS.md convention enforcement (root-doc-organization).** 3 commits.
  13a `0712b49`: `docs/plan/README.md` §Conventions rewritten canonical + self-contained
  (archive pointer dropped), all 17 pre-existing >200-char story rows reflowed into compact
  status entries, `docs/plan/_TEMPLATE/{prompt,tasks}.md` added. 13b `a0d255d`:
  `scripts/hooks/check_story_structure.py` + 11 tests + pre-commit wiring (story-vs-epic
  detection; `--all` audit / `--staged-added` pre-commit / path modes); two empty stray
  folders removed. 13c: structure-audit + pointer-only steps in `md-cleanup` / `session-close`
  skills; this header pointer. `CLAUDE.md`/`AGENTS.md` 5a pointer deferred to RDO-6 (mirror
  long-line wrap); `TODOS.md` items 14/22/29 retrofit stays RDO-14. Committed with
  `SKIP=md-line-length` — this file carries the pre-existing backlog; the change adds none.

### 2026-08-27

- **RDO-8 — protocol-doc consistency cleanup (root-doc-organization).** 5 fixes, one
  docs/config-only commit: (1) `ANTIGRAVITY.md` step 2 docs/config-only bullet aligned to
  "skip `code-reviewer` entirely" (was: adopt persona + evaluate) — now matches `CLAUDE.md` /
  `AGENTS.md` 5c. (2) `git rm -r .codex/` (dead scaffolding from `16821d6`, only
  self-referenced); `.agents/` kept per Animesh (Antigravity autoloads it), added to RDO-6's
  re-sync scope with a note re its stale `.Codex/` refs. (3) `src/paper/` `src/nuvama/`
  `src/gamma/` rows added to the module table in `CLAUDE.md` + `AGENTS.md`; `AGENTS.md`'s
  "Also present on disk" note folded in so the two match. (4) `src/client/CLAUDE.md` heading
  + `src/client/` row in both module tables reworded "implementations (2 built + 1 variant +
  1 planned)". (5) `CLAUDE.md`'s embedded "Rules for any review" lifted to a standalone
  `## Rules for any review or handoff` section matching `AGENTS.md`; both bodies set identical.
  Next: RDO-6, RDO-7, or RDO-9.

- **RDO-5 — `md-line-length` pre-commit hook (root-doc-organization).** Added
  `scripts/hooks/check_md_line_length.py` (200-char hard cap, all line kinds;
  `<!-- lint-ignore-length -->` on the preceding line excuses one unbreakable token) + local
  `md-line-length` hook over `^([^/]+\.md|docs/(plan|bugs)/.*\.md)$` + 3 unit tests in
  `tests/unit/scripts/hooks/`. `plan.md` Phase 1's "≤100" contradiction removed, Phase 5 yaml
  block updated; semantic-linefeed + 200-cap style recorded in `docs/plan/README.md`
  §Conventions. Scoped tooling-only per Animesh — the hook enforces on staged files; the
  ~800-line pre-existing backlog (18 files) is not an RDO-5 gate, cleared opportunistically +
  by RDO-6 (`md-organize`) / RDO-9 (`DECISIONS.md`). Commit used `SKIP=md-line-length` since
  it stages the still-unwrapped `TODOS.md` / `docs/plan/README.md`. Next: RDO-6 or RDO-7.

- **RDO-4 — relocate legacy `BUGS.md` + `GLOSSARY.md` out of root (root-doc-organization).**
  `git mv BUGS.md docs/archive/BUGS_LEGACY.md` (archive banner added, only `BUG-001` still
  open) + 3-line root stub → `docs/bugs/` + archive. `git mv GLOSSARY.md docs/GLOSSARY.md`,
  no stub, `docs/GLOSSARY.md` Quick-reference row added to `CLAUDE.md` and `AGENTS.md`
  (mirror). Live inbound links repointed: `TODOS.md` header, `docs/plan/README.md` intro,
  `docs/bugs/bugs.md` relationship note. Historical mentions (`DECISIONS.md` 2026-07-02
  entry, `dev-foundation` CH-3 records, full-repo-review audit snapshots) left as accurate
  records. Docs-only. Next: RDO-5 (`md-line-length` pre-commit hook).

- **SEP-4 — end-to-end check + close (session-entry-point epic complete).** Ran both `/work`
  branches in one session. **Feature branch** demonstrated live: invoked as
  `/work on SEP-4 in session-entry-point` → Step A skip-through detection matched the story id
  → Feature branch pre-selected to `session-entry-point` (TODOS priority item 1) →
  `prompt.md` + `tasks.md` loaded → SEP-4 identified as first unchecked `- [ ]` →
  `CONTEXT.md` read → handed to `CLAUDE.md` Step 2b (council checkpoint: not warranted).
  **Bug branch** demonstrated via routing dry-run: `docs/bugs/task.md` + `bugs.md` read, open
  entries presented — BUG-038 (first unchecked B038.1, `trace_path` the two unawaited-send
  methods) and BUG-037 (first unchecked B037.6, `code-reviewer` on the B037.3/B037.4 fix);
  BUG-019 listed as diagnostic-only / not actionable. Both branches reach a loaded prompt.
  Docs-only close: SEP-4 ticked (working list + "Epic done when"), `docs/plan/README.md` row
  flipped to ✅ Done, RDO-12 ticked in `root-doc-organization/tasks.md` (both checkboxes),
  priority item 1 ticked here. `session-entry-point` epic (SEP-1..4) fully shipped.

- **SEP-3 — `AGENTS.md` mirror (session-entry-point).** Applied the SEP-2 `CLAUDE.md` Step 1
  change to `AGENTS.md` with the Antigravity adjustment: new `/work` delta bullet in the
  header deltas list; Step 1 gains a routing block stating the manual equivalent (no `/work`
  skill — take the feature target off `TODOS.md` "Priority-Ordered Open Work" first-5, or the
  bug off `docs/bugs/`, then follow the handoff protocol into Step 2b); the "new feature" +
  "specific story" load-hint lines collapsed into one manual-routing pointer; Quick-reference
  row added. RDO-6's `md-organize` re-sync scope already names `.claude/skills/work/SKILL.md`
  (RDO-12 triage) — no edit needed; RDO-6 itself still unshipped. Docs-only. Next: SEP-4
  (end-to-end check of both `/work` branches in one session + close).

- **SEP-2 — `CLAUDE.md` reconciliation (session-entry-point).** `/work` is now the documented
  start-of-task entry point in `CLAUDE.md`: leading `/work` block added to Step 1; the two
  duplicated load-hint lines ("Starting a new feature → `TODOS.md` + `PLANNER.md`", "Working a
  specific story → load ONLY that story file …") collapsed into one `/work` pointer;
  Quick-reference table gains a `/work` row. Docs-only. Next: SEP-3 (`AGENTS.md` mirror +
  `md-organize` re-sync scope).

- **RDO-15 filed (root-doc-organization).** Animesh flagged that story `tasks.md` files track
  each task id with two checkboxes — the working list and the trailing `## Epic done when`
  block (`session-entry-point/tasks.md` SEP-2 is the worked example) — plus a third state
  signal in `docs/plan/README.md`; ticking one and missing the others silently desyncs. RDO-15
  adds a checkbox-consistency sweep (extends RDO-13's `check_story_structure.py`), picks a
  one-checkbox-per-id convention, and retrofits. Docs-only.

- **`/work` priority-source fix.** `/work`'s Feature branch reads `TODOS.md` "Priority-Ordered
  Open Work", which had rotted (broken numbering `0e.`→`9.`, item 14 duplicated, `TGFMT-2..9`
  listed though superseded). Decided with Animesh: `TODOS.md` stays the canonical global
  priority file and must order **both** bugs and features. Quick fix now — prepended
  `session-entry-point` (item 1) and `root-doc-organization` (item 2), renumbered the old `0e.`
  BUG-030 entry to `3.`. Full restructure into one unified bug+feature queue filed as
  **RDO-14** in `docs/plan/root-doc-organization/tasks.md`. Docs-only.

- **Root state-doc staleness — round 2 of workflow token-optimization.** Problem: root state
  docs (`CONTEXT.md`, `TODOS.md`, `DECISIONS.md`, `PLANNER.md`, `DB_REGISTRY.md`, …) rot because
  the only thing forcing an update is `CLAUDE.md` Step 5a — a checklist line, no enforcement,
  no signal. Three levers: surface / enforce / shrink.
  - **[x] #1 — surface (done, SHA 758dd6b).** New repo hook `.claude/hooks/state_doc_freshness.sh`
    wired as `SessionStart` in `.claude/settings.json`. Counts `src/`|`scripts/` commits since
    each state doc last changed; prints a one-line flag for any doc over its threshold
    (`CONTEXT.md`/`TODOS.md` 15, `CONTEXT_TREE.md`/`DB_REGISTRY.md`/`docs/plan/README.md` 35,
    `DECISIONS.md`/`PLANNER.md`/`README.md` 40). Zero-maintenance — uses git last-touch, no
    stamp lines in the docs. Informational, always `exit 0`. Tune thresholds after a week if
    it's noisy (`DB_REGISTRY.md` currently trips at 36/35 despite a 2-day-old edit).
  - **[x] #2 — enforce (done, SHA 7dae8e3).** New repo hook `.claude/hooks/doc_update_gate.sh`,
    PreToolUse matcher `Bash`, detects `git commit`. If `git diff --cached --name-only` has
    `^(src|scripts)/.*\.py$` but none of `TODOS.md`/`CONTEXT.md`/`DECISIONS.md`/
    `docs/plan/README.md` → remind on stderr. **v1 `exit 0` (advisory)**; escape hatch
    `[skip-docs]` in the commit message → silent; `--amend`/`--dry-run` and tests-only diffs
    skipped. Flip to `exit 2` (blocking) only after a week of observing the false-positive
    rate (pure refactors, multi-commit phases). Repo. Smoke-tested: reminder fires,
    `[skip-docs]` suppresses, staged `TODOS.md` suppresses, tests-only diff silent.
  - **[x] #3 — shrink (done, SHAs 089fb91 + 7bbfaff).**
    (a) `089fb91` — `CONTEXT.md` test-count → `pytest -q | tail -1` pointer; `TODOS.md`
    session log trimmed to the two still-active threads, the four completed SHA-referenced
    entries (ROLL-4, nuvama, RDO-1, RDO-2) moved verbatim to `docs/archive/TODOS_ARCHIVE.md`.
    (b) `7bbfaff` — **scope deviation, confirmed with Animesh:** `DECISIONS.md` has *no*
    pre-2026 entries (earliest is 2026-04-01) and its 2026-04/05 entries are interleaved with
    2026-06/07/08 ones inside shared thematic sections (`## Process`, `## Strategy & Research
    Decisions`, …), so a date-cutoff archive isn't cleanly possible. Instead lifted the 5
    fully-historical, self-contained sections with no still-enforced rule
    (TradingView MCP Regime Probe, Backtest Data Source Decision, TrueData Historical Dump,
    Live Strategy Monitoring, src/ Model Placement Rule) to
    `docs/archive/DECISIONS_pre-2026-07.md` behind a one-line index; 336 KB → 330 KB,
    2302 → 2203 lines. **Follow-up:** the real DECISIONS.md shrink needs a *semantic* split
    (still-enforced rule vs completed-work log), not a date archive — filed as **RDO-9** in
    `docs/plan/root-doc-organization/tasks.md`.
  - **[ ] #4 — deferred.** `/schedule` a weekly cloud routine running the `md-cleanup` skill.
    Hold until #1–#3 have run 2 weeks — the SessionStart flag may make manual cadence enough.
    Conflicts with `root-doc-organization` Phase 7's "no unattended doc writes" — resolution
    tracked as **RDO-10**.
  - **Pending work from this session filed into `docs/plan/root-doc-organization/`:** RDO-3
    closed-partial (date-cutoff unworkable, 7bbfaff recorded); **RDO-9** (DECISIONS semantic
    split), **RDO-10** (reconcile RDO-7 with the #1/#2 hooks + #4), **RDO-11** (graduate the
    advisory hooks to blocking — review on/after 2026-09-03) added; `tasks.md` gained an
    "Epic done when" checklist including an end-to-end loop-closure test. `plan.md` + README
    refreshed.
- **Workflow-suggestion triage → new `session-entry-point` story.** Triaging a batch of
  workflow-improvement suggestions into `root-doc-organization`. #1 — unified session entry
  point — spun into its own story `docs/plan/session-entry-point/` (SEP-1..4: manual `/work`
  skill, Feature/Bug routing, Feature branch offers the first 5 of `TODOS.md` "Priority-Ordered
  Open Work", Bug branch offers open `docs/bugs/` entries) + **RDO-12** pointer row in
  `root-doc-organization/tasks.md`. Decided: manual invocation only, no SessionStart hook.
  #2 — convention enforcement — filed as **RDO-13**: `docs/plan/README.md` §Conventions made
  canonical + self-contained (drop the dead `docs/archive/plan/README.md` pointer),
  `docs/plan/_TEMPLATE/` + `check_story_structure.py` audit (into `md-organize`, not
  pre-commit), ticked `tasks.md` lines carry `| Owner | Model | SHA |`, `TODOS.md` cut to
  pointer-only items (no inline detail, no mirrored checkboxes, delete the line on story
  completion). #3 — MD line width — folded into **RDO-5** (scope edit, not a new item):
  200-char hard cap, semantic-linefeed prose style (one sentence/clause per line), check
  extended to `docs/plan/**` + `docs/bugs/**`, `.py` unchanged at ruff 100. Further
  suggestions still pending. Docs-only; commit deferred to the single end-of-triage commit.
- **SEP-1 — `/work` session entry-point skill (RDO-12).** Authored `.claude/skills/work/SKILL.md`
  — manual skill (triggers "work" / "start work" / "pick up a task" / "/work"), Step A
  skip-through (message names a story/bug/RDO id → jump to branch, else `AskUserQuestion`
  Feature/Bug), Feature branch presents the first 5 of `TODOS.md` "Priority-Ordered Open Work"
  and loads the picked story's `prompt.md` + `*_tasks.md` first unchecked task + `CONTEXT.md`,
  Bug branch lists open `docs/bugs/` entries (`🔴`/`🟡`) and loads the entry + `task.md` lines
  + first unchecked. Front-end to the existing protocol — composes with `task_protocol.sh`,
  hands to `CLAUDE.md` Step 2b. House style matched to `session-close` / `commit`. Docs +
  `.claude/` only — no code-reviewer/test-runner. SEP-2 (`CLAUDE.md` reconciliation) and
  SEP-3/4 are later sessions.
- **Workflow token-optimization** (plan: `~/.claude/plans/this-session-is-for-federated-goose.md`)
  — cut fixed per-session scaffolding cost (~5k tokens on a typical implementation session).
  Changes:
  (1) `~/.claude/hooks/cbm-code-discovery-gate` (global, not in repo) made path-aware — the
  once-per-session block now fires only for real code targets (`.py` under `src/`|`scripts/`,
  or a Grep/Glob scoped there), not for the first markdown/config Read of every session;
  (2) `.claude/hooks/guard_src_reads.sh` — full graph decision tree once per session, one-liner
  after; (3) `.claude/hooks/task_protocol.sh` — full checklist once per session, one-liner on
  later task prompts; (4) `~/.claude/hooks/cbm-session-reminder` (global) slimmed to one line
  (harness already injects the full reminder); (5) `CLAUDE.md` + `AGENTS.md` — stripped dated
  failure anecdotes, deduped the AI-Collaboration section against Step 3b/AutoTrigger; fixed
  `AGENTS.md`'s dead `md-organize` reference → `md-cleanup` Step 7 (new: re-sync AGENTS.md
  when CLAUDE.md changes). Docs/hooks only, no `.py` touched — no code-reviewer, no test-runner.

  **Next-session validation** (validated 2026-08-27, session `92c04e16` — all 5 pass):
  - [x] First action `Read CONTEXT.md` — succeeded, **no** `cbm-code-discovery-gate` block
    (gate file `cbm-code-discovery-gate-$PPID` stayed absent until the first `src/*.py` read).
  - [x] First task-shaped prompt → full `⚙️ TASK PROTOCOL` checklist injected; gate file
    written. Second-fire one-liner not observable in a single-prompt session — hook branch
    (`task_protocol.sh:42-45`) reviewed and correct.
  - [x] First `src/` `Read` → `guard_src_reads` fired once (gate `niftyshield-guard-$PPID`
    created on first attempt); retry hit the one-liner branch. Exit-0 PreToolUse stdout isn't
    surfaced to the assistant, so verification was via gate-file lifecycle + source review.
  - [x] First `Read src/__init__.py` → hard `exit 2` `BLOCKED: … codebase-memory-mcp`; retry
    (gate now written) allowed. Path-aware block fires once for real code, as intended.
  - [x] `SessionStart` reminder is a single line ("Code discovery: graph tools first — …"),
    not the old block. Confirmed against `cbm-session-reminder` source (single `echo`).
  - On failure: hooks are `~/.claude/hooks/cbm-code-discovery-gate` +
    `~/.claude/hooks/cbm-session-reminder` (global) and `.claude/hooks/guard_src_reads.sh` +
    `.claude/hooks/task_protocol.sh` (repo). Gate files `/tmp/cbm-code-discovery-gate-$PPID`,
    `/tmp/niftyshield-guard-$PPID`, `/tmp/niftyshield-task-protocol-$PPID` — `rm` to re-test
    first-fire within one session.

  **Task 5 (done 2026-08-27) — measurement + permission tooling:**
  - [x] Ran `/fewer-permission-prompts` (50 recent transcripts). Only non-auto-allowed
    read-only patterns worth listing were the four codebase-memory-mcp graph reads
    (`get_code_snippet`, `search_graph`, `search_code`, `trace_path`) — all bash usage was
    auto-allowed, mutating, or interpreter invocations. Added to `.claude/settings.json`
    `permissions.allow`. Commit `dd0da61` `chore(claude): add read-only permission allowlist`.
  - [x] Statusline: `~/.claude/statusline-command.sh` gained a `$%.2f` cost segment from
    `.cost.total_cost_usd` and a `/Nk` used-tokens suffix on the ctx segment from
    `.context_window.used_tokens` (both degrade to nothing when the field is absent — tested).
    Global file, not in-repo; noted in the TODOS-update commit body.
  - [x] `/context` snapshot (Animesh ran it manually, session `92c04e16`, ~9% used, 94.8k/1M):
    fixed scaffolding now — system prompt 3k, system tools 18.6k, memory files 10k
    (`CLAUDE.md` 8.3k + `~/.claude/CLAUDE.md` 1.6k + `MEMORY.md` 0.1k), skills 2.8k, custom
    agents 0.24k. Messages grew 60.9k→65.3k across the session. A clean cross-session
    before/after for the ~5k hook-reinjection saving isn't recoverable from one session — the
    saving is in per-turn message growth, not a static category; the once-per-session gate
    files (`task_protocol`, `guard_src_reads`, `cbm-code-discovery-gate`) were all confirmed
    single-fire above, which is the mechanism that delivers it. `logs/context.log` not
    written (`/context &> file` is client-side, redirect is inert; `logs/` is gitignored).
- Earlier 2026-08-27 entries — **ROLL-4** (`30bac70`), **nuvama empty-book crash** (`3b9b57f`),
  **RDO-1**, **RDO-2** — moved verbatim to
  [docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md) (2026-08-27 section).
  `git log --oneline` carries the sequence, each commit's `Why:` line the intent.
