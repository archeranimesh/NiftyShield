# NiftyShield — TODOs

> Open work only. Completed items: [docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md) | Known defects: [BUGS.md](BUGS.md)
> Related: [CONTEXT.md](CONTEXT.md) | [DECISIONS.md](DECISIONS.md) | [PLANNER.md](PLANNER.md) | [BACKTEST_PLAN.md](BACKTEST_PLAN.md) | [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md)

---

## Priority-Ordered Open Work

This list is ordered **story-by-story, not task-by-task**. Each story's tasks in its own
`tasks.md` are a sequence — finish a story's remaining tasks in order before starting the next
story on this list. Do not jump between stories mid-sequence; the ordering below only decides
*which story to pick up next*, once the current one is done. Completed items are in
`docs/archive/TODOS_ARCHIVE.md`.

0e. [ ] **BUG-030 — `_overlay_type_groups` elif-precedence drops `overlay_cc` leg when `overlay_collar_put` also present same-day** (found 2026-08-13, open) — the "NiftyBees vs overlays" digest's `CC No data` line and an understated `Collar` P&L figure both trace to `paper_3track_snapshot.py::_overlay_type_groups()` checking `has_put` before `has_cc` in its `elif` chain, silently orphaning the `overlay_cc` leg from every group whenever `overlay_collar_put` is also present. Orthogonal to BUG-028 (namespace fix, already closed) — this is a leg-role grouping defect BUG-028's four phases never touched. See `docs/bugs/bugs.md` BUG-030, `docs/bugs/task.md` B030.1–B030.6, starting at **B030.1** (entry-side tagging question, blocks the grouping fix).
9. [ ] **IC yearly-expiry residual risk** (2026-07-23) — `docs/plan/ic-yearly-expiry-fix/tasks.md`, starting at **WG-1** (persist per-leg Greeks for weekly expiry bucket; YE-1..YE-4 superseded/already fixed live, see DECISIONS.md BUG-015).
10. [ ] **Greeks Black-Scholes fallback** (2026-07-23) — `docs/plan/greeks-bs-fallback/tasks.md`, starting at **GF-1** (read-only audit scope).
11. [ ] **MVP: Multi-bagger Value Picks Tracker** — `docs/plan/mvp/tasks.md`, starting at **M1.1**. Independent — does not block any other story on this list.
12. [ ] **Variance gate — CSP v1 deployment gate observation** (2026-07-07) — `docs/plan/variance-gate/variance_gate_tasks.md`, starting at **VG0** (spec reconciliation; remaining tasks are human checkpoints, not build tasks).
13. [ ] **Options Income strategy** (2026-06-03) — `docs/plan/options_income/options_income_tasks.md`, starting at **S0** (data audit).
14. [ ] **Telegram IC comparison formatting** (2026-08-07) — `docs/plan/telegram-ic-comparison-formatting/tasks.md`. **TGFMT-1 closed 2026-08-07:** `build_comparison_report()`'s hand-counted fixed-width columns replaced with dynamically computed label/column widths (right-aligned values), porting the approach proven live in `scratch/2026-08-07_telegram_ic_comparison_format_repro.py`. 2 new regression tests (long-label collision, large-value width). 14/14 tests in `tests/unit/strategies/ic/test_paper_ic_monthly_comparison.py` green; wider `tests/unit/` run shows only pre-existing unrelated failures (missing `pandas`/`pyarrow`/`duckdb` in the throwaway `/tmp/pydeps` sandbox install, same class noted in TL-1/BUG-026 sessions). **TGFMT-2..9 superseded 2026-08-07 by item 29 below** — do not pick these up; TGFMT-1 stays as shipped history, its two feature asks (Legs row, Bkd/Flt month-inception split) carried forward into item 29's ROLL-2.
14. [ ] **Backtest Engine** — `docs/plan/backtest-engine/{phase1,phase2,phase3,phase4}/`. Mirrors `BACKTEST_PLAN_PHASE1.md`'s full structure (root doc is canonical; these dirs are thin status pointers). Work through phases **in order** — each phase's GATE task blocks the next phase dir entirely, so this is really 4 sub-stories chained, not 1:
    - **Phase 1** (Aug–Dec 2026 target) — `docs/plan/backtest-engine/phase1/tasks.md`. Gated on the Phase 0.8 variance gate (item 12 above). Starts at **1.3a**/**1.4** (parallel), through **1.12**. Blocks items 15/16 below.
    - **Phase 2** (CSP live + IC paper, ~6mo) — `docs/plan/backtest-engine/phase2/tasks.md`. Gated on Phase 1's **1.12**. Starts at **2.1**. Note: the Parallel Research Tracks named inside this phase in the root doc are tracked via `signals-eval-core` (item 16), not a separate task list here.
    - **Phase 3** (IC live + third strategy + portfolio construction, ~12mo) — `docs/plan/backtest-engine/phase3/tasks.md`. Gated on Phase 2's **2.7**. Starts at **3.1**.
    - **Phase 4** (basket maturity + Finideas evaluation, 2028–2030) — `docs/plan/backtest-engine/phase4/tasks.md`. Gated on Phase 3's **3.6**. Starts at **4.1** (Owner: Animesh — capital-allocation decision, not a Cowork task).
15. [ ] **backtest-eval-core: `BacktestStore` + `src/analytics/`** — `docs/plan/backtest-eval-core/tasks.md`, starting at **B1.1**. Blocked by item 14 (tasks 1.3 + 1.4) — do not start until those land.
16. [ ] **signals-eval-core: regime engine + signal generators + validation** — `docs/plan/signals-eval-core/tasks.md`, starting at **SE1.1**. Blocked by item 15 + item 14's 1.12 gate. Covers both Track A (swing) and Track B (investment) pipelines — SE1–SE8 in full.
17. [ ] **signals: multi-LLM daily signal pipeline** — `docs/plan/signals/signals_tasks.md`, starting at **S1.1**.
18. [ ] **risk-gamma-phase-a, Track B: Near-Expiry Gamma Buy strategy** — `docs/plan/risk-gamma-phase-a/risk_gamma_tasks.md`, starting at **B2.2** (Track A + B1/B2.1 already shipped).
19. [ ] **greeks-parity-validation** (P3, gated on council) — `docs/plan/full-repo-review-followups/greeks-parity-validation/tasks.md`, starting at T1. **Do not implement directly** — requires an `options-strategist`/`greeks-analyst` council consult first (tolerance-band decision).
20. [ ] **paper-pnl-golden-tests** (P3) — `docs/plan/full-repo-review-followups/paper-pnl-golden-tests/tasks.md`, starting at T1 — add exact-value golden assertions for `_compute_leg_unrealized_pnl`.
21. [ ] **suppression-hygiene-triage** (P3) — `docs/plan/full-repo-review-followups/suppression-hygiene-triage/tasks.md`, starting at T1 — REVIEW.md carve-out for self-describing `# noqa` codes.
22. [ ] **Broker abstraction** (LOW priority) — multi-broker parser/adapter layer so data fetching can migrate to Dhan or Kite without touching storage. Storage format (Parquet, SQLite, model field names) is frozen — only fetch + parse changes. Full story: `docs/plan/broker-abstraction/`. 16 tasks (BA-0 → BA-15), starting at **BA-0** (probe scripts + decision matrix). BA-14/BA-15 blocked until `src/execution/` (item 24's OE-1) exists. Do not start until Phase 0.8 gate clears.
23. [ ] **Historical data abstraction** (LOW priority) — `HistoricalCandleFetcher` protocol so VIX and OHLC fetching can switch between Upstox, Dhan, Kite, and NSE CSV without touching storage. Currently `vix_ingest.py` has Upstox URLs hardcoded with sync `requests`; `get_historical_candles` on `BrokerClient` raises `NotImplementedError`. 11 tasks HD-0→HD-10, starting at **HD-0** (cost-bounded probe scripts). HD-6 (Dhan)/HD-7 (Kite ₹2000/month) conditional on HD-0 decision matrix. Do not start until Phase 0.8 gate clears.
24. [ ] **Phase 2 — Research Pipelines & Integrations** (2027+) — `docs/plan/phase2-integrations/tasks.md`, starting at **PV-1** (P&L Visualization — not gated, can be pulled forward independently). **ZK-1**/**OE-1**/**PT-1** are gated per their own stated reasons (Kite Connect priority, static IP, defer-until-touched) — see the story file. Does not include the Swing/Investment signal pipelines — those are item 17 above.
25. [ ] **Technical Debt** (opportunistic — not sequential) — `docs/plan/technical-debt/tasks.md` (**DEBT-3/5/6a/6b/6c/7**). Do not pick these up on their own; each fires only when its named file/module is already being touched for another story's task. See `prompt.md` for the exact trigger per item and why this one breaks the "finish in sequence" rule the rest of this list follows.
26. [ ] **Fix dead IC EOD report query** (2026-08-05) — fix `scripts/strategies/ic/paper_ic_snapshot.py`'s "Intraday actions" query which was identified as dead code during the DT-3a audit.
27. [ ] **Chain delta/decay analysis** (2026-08-06) — `docs/plan/chain-decay-analysis/tasks.md`, starting at **CDA-1**. Exploratory/read-only, independent — does not block or get blocked by anything else on this list. Monthly bucket only (yearly excluded, see item 11's GF-1 findings).
28. [ ] **Entry event filter R4** (2026-07-27, bumped down 2026-08-06) — `docs/plan/entry-event-filter/tasks.md`, starting at **EF-1** (EF-0 done; ES12 dependency already shipped, SHA b86925a — no longer blocking). **Not compulsory — good-to-have.** Soft-warning only (logged, non-blocking, mirrors `GateViolation`); does not gate sizing or entry the way items 4/13 do, and event-day risk is not yet live-capital exposure at the current backtest/paper stage (item 14). `events.yaml`'s election-date leg has no natural refresh trigger and will need ad-hoc upkeep — revisit once entries run fully unattended on live capital (post item 14 Phase 2), at which point also reconsider hard-block instead of log-only.
29. [ ] **Telegram Markdown migration** (2026-08-07, in progress) — `docs/plan/telegram-markdown-migration/`. Migrates all Telegram messaging to `parse_mode=MarkdownV2` via three sequenced sub-stories: `backbone/` (parse-mode switch + escaping audit — closed), `formatting-rules/` (value/table formatting spec — closed, see `FORMATTING.md`), `strategy-rollout/` (per-message-family migration, in progress — through ROLL-3 as of 2026-08-26, next unchecked task per `strategy-rollout/tasks.md`; the former 0g–0l progress markers were archived along with the rest of this file's closed-item backlog in the 2026-08-26 reorg). **Supersedes item 14's TGFMT-2..9.** Full session-by-session design history (ROLL-0 through ROLL-17, format-workshop decisions, FMT-1 sub-rules a-f) archived to `docs/archive/TODOS_ARCHIVE.md` (2026-08-26 reorg) — the epic's own `README.md`/`stories.md`/`tasks.md` are the live spec; this line is a pointer, not the source of truth.

**Before build queue starts on paper-backbone-dependent stories** — verify prerequisites:
```bash
search_graph("StrategyMonitor")   # must return results
search_graph("PaperExecutor")     # must return results
search_graph("CCOverlayV1")       # must return zero results
```

---

## Animesh-only: Stockmock Calibration Backtests

Prerequisite for item 15 (`docs/plan/backtest-engine/phase1/tasks.md` task **1.1**, which itself
feeds task 1.7's `CSPConfig`). Stockmock UI — no code required.

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

### 2026-08-27

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
