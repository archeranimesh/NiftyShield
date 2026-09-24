# NiftyShield — TODOs

> Open work only. Completed items: [docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md) | Known defects: [docs/bugs/](docs/bugs/) Related: [CONTEXT.md](CONTEXT.md) |
> [DECISIONS.md](DECISIONS.md) | [PLANNER.md](PLANNER.md) | [BACKTEST_PLAN.md](BACKTEST_PLAN.md) | [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md) **Task tracking lives in the story folders.**
> Per-task state is in each story's `docs/plan/<slug>/tasks.md` or `docs/bugs/task.md`. The lists below are **pointers only** — title, path, next unchecked task, one-line why. Full rules:
> [`docs/plan/README.md`](docs/plan/README.md) §Conventions. Two separate lists: **`## Feature Backlog`** (forward spec work, `docs/plan/`) and **`## Open Bugs`** (defects in shipped code,
> `docs/bugs/`). `/work` routes to one or the other. When a story or bug is fully done its line here is **deleted** (moved to [`docs/archive/TODOS_ARCHIVE.md`](docs/archive/TODOS_ARCHIVE.md)) and its
> folder moved to `docs/archive/plan/<slug>/` — see §Conventions → *Completion → archive*.

---

## Feature Backlog — Priority Ordered

Forward spec work only — one `docs/plan/` story per line, pointer-only (title · folder · next unchecked task · one-line why). Ordered **story-by-story**: finish a story's `tasks.md` in sequence before
starting the next story here; this list only decides *which story is next*. Bugs are **not** here — see `## Open Bugs`. Cross-references use folder names, never list positions, so renumbering can't
rot them.

2. **Greeks Black-Scholes fallback** — `docs/plan/greeks-bs-fallback/` — next **GF-1** (read-only audit scope).
5. **Variance gate — CSP v1 deployment gate observation** — `docs/plan/variance-gate/` — next **VG0** (spec reconciliation; the remaining tasks are human checkpoints, not build tasks).
6. **Options Income strategy** — `docs/plan/options_income/` — next **S0** (data audit).
7. **Backtest Engine** — `docs/plan/backtest-engine/` (`phase1..4/`) — next **1.3a / 1.4** (parallel, `phase1/`). Four chained phases; each phase's GATE task blocks the next dir. Gated on
   `variance-gate`. `BACKTEST_PLAN_PHASE1.md` is the canonical spec; the phase dirs are thin status pointers.
9. **backtest-eval-core** — `docs/plan/backtest-eval-core/` — next **B1.1**. Blocked until `backtest-engine` tasks 1.3 + 1.4 land.
10. **signals-eval-core** — `docs/plan/signals-eval-core/` — next **SE1.1**. Blocked until `backtest-eval-core` + `backtest-engine` 1.12. Covers Track A (swing) + Track B (investment), SE1–SE8.
11. **risk-gamma-phase-a** — `docs/plan/risk-gamma-phase-a/` — next **B2.2** (chain fetch + field computation). Track A + B1 / B2.1 shipped.
12. **greeks-parity-validation** — `docs/plan/full-repo-review-followups/greeks-parity-validation/` — next **T1**. P3, council-gated: do not implement directly — needs an `options-strategist` /
    `greeks-analyst` consult first (tolerance-band decision).
13. **paper-pnl-golden-tests** — `docs/plan/full-repo-review-followups/paper-pnl-golden-tests/` — next **T1** (exact-value golden assertions for `_compute_leg_unrealized_pnl`). P3.
14. **suppression-hygiene-triage** — `docs/plan/full-repo-review-followups/suppression-hygiene-triage/` — next **T1** (REVIEW.md carve-out for self-describing `# noqa` codes). P3.
15. **Fix dead IC EOD report query** — `scripts/strategies/ic/paper_ic_snapshot.py` (no story folder) — the "Intraday actions" query is dead code, found in the DT-3a audit.
16. **Chain delta/decay analysis** — `docs/plan/chain-decay-analysis/` — next **CDA-1**. Exploratory / read-only, independent. Monthly bucket only (yearly excluded — see `greeks-bs-fallback` GF-1
    findings).
18. **Entry event filter R4** — `docs/plan/entry-event-filter/` — next **EF-1**. Good-to-have, not compulsory; soft-warning only (logged, non-blocking, mirrors `GateViolation`). `events.yaml` needs
    ad-hoc upkeep. Revisit once entries run unattended on live capital (post `backtest-engine` Phase 2), and reconsider hard-block then.
19. **Broker abstraction** — `docs/plan/broker-abstraction/` — next **BA-0** (probe scripts + decision matrix). LOW priority; storage format frozen, only fetch + parse change. BA-14 / BA-15 blocked
    until `src/execution/` (`phase2-integrations` OE-1) exists. Do not start until the Phase 0.8 gate clears.
20. **Historical data abstraction** — `docs/plan/historical-data-abstraction/` — next **HD-0** (cost-bounded probe scripts). LOW priority. `HistoricalCandleFetcher` protocol so VIX + OHLC fetching can
    switch brokers without touching storage. HD-6 / HD-7 conditional on the HD-0 decision matrix. Do not start until the Phase 0.8 gate clears.
21. **Phase 2 — Research Pipelines & Integrations** — `docs/plan/phase2-integrations/` — next **PV-1** (P&L visualization — not gated, can be pulled forward). ZK-1 / OE-1 / PT-1 gated per the story
    file. 2027+. Excludes the swing / investment signal pipelines — those are `signals`.
21. **Technical Debt** — `docs/plan/technical-debt/` — DEBT-3 / 5 / 6a / 6b / 6c / 7. Opportunistic, **not sequential** — each item fires only when its named file / module is already being touched for
    another story's task. See `prompt.md` for the per-item trigger.
22. **IC payoff charts on Telegram** — `docs/plan/ic-payoff-charts/` — next **PC-2** (`src/strategy/payoff.py` — `ICPayoff` + `compute_ic_payoff`). Epic: `chart-core/` (expiry payoff PNG + `sendPhoto`
    plumbing + wire into entry / EOD audit / close, one chart per IC variation — no option model, ships now) → `chart-model-overlay/` (T+0 curve + ±1σ/±2σ bands + POP — blocked on
    `greeks-bs-fallback/` GF-2 + GF-3). Priority relative to items 13–21 is Animesh's call.
24. **Portfolio snapshot slimdown** — `docs/plan/portfolio-snapshot-slimdown/` — next **FD-1** (pre-delete audit). Epic, two sequenced sub-stories that both rework `_build_portfolio_summary` +
    `_format_combined_summary`: `finideas-decommission/` (FD-1..7 — full removal of `finideas_ilts` + `finrakshak`: the `src/portfolio/strategies/` provider layer, the options / hedge / ETF snapshot
    terms, and every Finideas row in `strategies` / `legs` / `trades` / `daily_snapshots` via a `scripts/dev/decommission_finideas.py` CLI — history option A, hard delete) → `dhan-holdings-removal/`
    (DHR-1..4 — remove Dhan holdings / P&L / the Dhan Options block from the snapshot; keep the Dhan login flow + client + tables wired). No `schema.md`. `/work` routes via the epic `prompt.md`.
    Requested by Animesh 2026-09-10.
## Open Bugs

Confirmed defects in shipped code live in **[`docs/bugs/`](docs/bugs/)** — registry `bugs.md` (status `🔴 Open` → `🟡 Fix in progress` → `✅ Fixed`), tasks `docs/bugs/task.md`. `/work` → Bug branch reads
those files directly; it does **not** read this file. **Do not mirror bug priority or status here** — `bugs.md` is the single source of truth.

Snapshot (authoritative list: `bugs.md`) —

- **BUG-030** — `_overlay_type_groups` elif-precedence orphans the `overlay_cc` leg when `overlay_collar_put` is also present same-day. Next: **B030.1** (entry-side tagging question, blocks the
  grouping fix).
- **BUG-037** — `mark_trade_closed()` never wired into CSP / IC v1 / v2 close paths; 54 stale flat legs found live. Next: **B037.6** (`code-reviewer` on the B037.3 / B037.4 fix).
- **BUG-038** — `OverlayCloser`'s three `self._notifier.send()` calls are unawaited coroutines (never actually sent). Next: **B038.1** (`trace_path` the three send methods).
- **BUG-019** — diagnostic-only, not actionable (awaiting a live trading day's data before a fix is scoped).

Feature-vs-bug priority is chosen at session start via `/work`. A bug urgent enough to pre-empt all feature work should be raised with Animesh directly — it is not expressed by reordering either list.

**Before build queue starts on paper-backbone-dependent stories** — verify prerequisites:
```bash
search_graph("StrategyMonitor")   # must return results
search_graph("PaperExecutor")     # must return results
search_graph("CCOverlayV1")       # must return zero results
```

---

## Animesh-only: Stockmock Calibration Backtests

Prerequisite for `backtest-engine` (`docs/plan/backtest-engine/phase1/tasks.md` task **1.1**, which itself feeds task 1.7's `CSPConfig`). Stockmock UI — no code required.

- [ ] COVID crash (Feb–Apr 2020) — strikes hit, premium, max M2M loss, breach frequency
- [ ] IL&FS crisis (Sep–Oct 2018) — same metrics
- [ ] 2022 rate-hike selloff (Jan–Jun 2022) — same metrics
- [ ] Stable baseline (Jan–Dec 2023) — expected exit-type distribution in normal markets
- [ ] Summarise in [docs/strategies/csp_nifty_v1.md](docs/strategies/csp_nifty_v1.md) under "Calibration Backtest Results (Stockmock)"
- [ ] Commit: `docs(strategies): CSP v1 Stockmock calibration backtest results`

---

## Session Log
- [2026-09-24] BUG-053 fixed — `mvp backfill --resume <pick_id>` resumes an existing PENDING pick straight into `run_backfill()`, skipping `Pick(...)`/`add_pick()` entirely (B053.1, SHA `3540577`);
  the create path now guards against a duplicate PENDING row for the same symbol+reco_date, erroring and pointing at `--resume` instead of inserting a second row (B053.2); both paths covered by new
  tests (B053.3). `@code-reviewer` clean both rounds (0 CRITICAL/ERROR). `bugs.md`/`task.md` sections archived. SHA pending (backfilled next commit).
- [2026-09-24] Bug filed — `BUG-053` (`mvp backfill` has no resume path: re-running it on an OHLCV-not-yet-bootstrapped PENDING pick inserts a duplicate row instead of completing the existing one, and
  PENDING picks have no live-price entry path via `mvp_watch` either). Found while walking through the `backfill` → `equity_bhavcopy_bootstrap` → re-`backfill` command sequence for a new pick (JK Tyre
  & Industries Ltd). `docs/bugs/bugs.md`/`task.md`, not yet fixed.
- [2026-09-24] BUG-051 fixed — `enter_backfill_pick` widened to scan forward for the first day whose close beats `reco_price`, instead of only checking `reco_date + 1` (a pick that missed day+1 stayed
  `PENDING` forever). `@code-reviewer` caught two follow-on issues in `run_backfill` in review rounds 1-2 (phantom pre-entry snapshots from the old `reco_date+1` walk-start; an unsafe fallback for the
  already-OPEN-pick resume path) — both fixed, round 3 clean. Applied to `ENGINERSIN` (`b08f6661…`): advanced `PENDING` → `OPEN`, entered ₹285.25 on 2026-09-21. SHA `61b18ee`.
- [2026-09-24] BUG-050 fixed — `write_equity_to_parquet` dedup now keys on `(symbol, trade_date)` pairs instead of `trade_date` alone, filtering only genuinely-duplicate rows rather than skipping the
  whole batch. Backfilled `ENGINERSIN`'s 9 missing trading days (2026-09-10..2026-09-23). `@code-reviewer` clean; full suite 3688/3693 (3 pre-existing failures in
  `test_escaping_guard.py`/`scripts/mvp_watch.py`, unrelated, verified via `git stash`). Both `bugs.md`/`task.md` sections archived. SHA `125032a`.
- [2026-09-24] BUG-049 fixed — `_resolve_instrument_key` now returns `(instrument_key, trading_symbol)` instead of a bare key; `_add`/`_backfill` set `Pick.symbol` from the resolved trading symbol on
  a successful match, falling back to the typed CLI string when resolution is deferred/skipped/no-match. 3 new tests added; full `tests/unit/mvp/` + `tests/unit/scripts/test_mvp.py` suite green (89
  passed). `@code-reviewer` clean (0 CRITICAL/ERROR, 4 minor WARNINGs, 2 applied). The already-filed `ENGINERSIN` (`b08f6661…`) pick's `symbol` was confirmed already correct — no DB fix needed.
  `bugs.md`/`task.md` sections archived. SHA `a874876`.
- [2026-09-24] Bugs filed — `BUG-049` (MVP `Pick.symbol` stored as raw CLI input, not the resolved NSE trading symbol; breaks `fetch_historical_closes`/bootstrap symbol filtering) and `BUG-050`
  (`write_equity_to_parquet`'s per-day dedup skips a whole day, including a genuinely-new symbol's row, if any other tracked symbol already covers that date) — found while adding an Engineers India
  (`ENGINERSIN`) MVP pick and trying to backfill its history like `UNIPARTS`. Both `docs/bugs/bugs.md`/`task.md`, not yet fixed.
- [2026-09-24] MVP M5 — docs close (`CONTEXT.md` module tree + Live Data cron note, `DECISIONS.md` MVP entry, this log). MVP watch hourly cron was already live in the crontab (`0 9-15 * * 1-5
  scripts.mvp_watch`) — no crontab change needed, just documented. M1–M9/M10–M13 ship bar now fully docs-closed.
- [2026-09-24] MVP fix — `get_category_high_low` forward-fills a pick with no day-1 snapshot into later days instead of dropping it from the day's aggregate (leftover from the M13.3 session, committed
  this session) — `0bd3c20`
- [2026-09-24] MVP M13.4 — EOD summary builders ported to `src/mvp/tracker.py` (`CategoryRollup`/`ProviderRollup`/`build_eod_table`/`format_eod_summary`) — `71bca0a`; wired into
  `scripts/mvp_watch.py`'s new `run_eod()` / `--eod` flag — `e7cdda0`. `category_short_code()` derives the Cat-column code from `Category.slug` (no schema column — Animesh's call). New cron entry (`45
  15 * * 1-5 mvp_watch.py --eod`) is code-only — not yet added to the actual crontab. M13 is now fully shipped (M13.1-M13.4).
- [2026-09-24] MVP M13.3 — `MVPStore.get_category_high_low` since-inception high-water-mark/max-drawdown return% per category — 0b63904
- [2026-09-24] MVP M13.2 — `MVPStore.get_category_day_change` invested-weighted day-over-day % rollup per category — 1a5d9dd
- [2026-09-24] MVP M12 — hourly summary rewritten as a flat `[O]`/`[P]`-badged holdings table (`format_hourly_summary`, `build_holdings_table`), OPEN+PENDING picks in one table, Invested/Current/P&L
  footer — 2b8d75d
- [2026-09-24] MVP M11 — per-category win-rate/inception P&L stats footer (`CategoryStats`, `MVPStore.get_category_stats`, wired into `_format_alert_message`) — 3c331b8
- [2026-09-24] MVP M10 — real ₹ P&L threaded into the MVP close alert (`ClosePickResult`, `_format_alert_message` redesign) — b812d82
- [2026-09-24] MVP M12 design closed out (docs only, no `src/` changes — resumed the co-investor-review session). Settled the column set within the confirmed 50-char mobile budget: measured every
  0/1/2-optional-column combination (`Svc`/`Qty`/`Avg cost`/`Chg%`/`Next`) against real fixture data in `scratch/2026-09-24_mvp_telegram_message_survey.py`; `badge`/`Sym`/`LTP`/`P&L`/`Next` (48 chars)
  was Animesh's pick over `Svc`+`Qty` (also 48 chars) since `Next` is the regression-restore column, not a nice-to-have. Confirmed rendering correctly on-device via `--send --send-only Hourly`. M10,
  M12, and M13 are now all fully signed off — next session should implement them for real (`src/mvp/tracker.py`, `scripts/mvp_watch.py`).
- [2026-09-24] MVP M9 — M-A lump-sum fill math: total_qty/deployed_capital/avg_cost/idle_cash on entry fill, realized_pnl with 25bps cost on close, CLI P&L/return% surfacing — 56f38e2
- [2026-09-23] MVP M7 — feat(mvp): add reco_price, surface deviation via CLI — d2f60d2
- [2026-09-23] MVP M6 — historical backfill primitives (`backfill_snapshots`, `fetch_historical_closes`, `mvp.py backfill`); spec rewritten against M0's Parquet layout, scoped apart from M8 —
  `499d382`
- [2026-09-23] MVP M0.4 — equity bhavcopy bootstrap CLI — d85523a
- [2026-09-22] MVP M1.1 — `src/mvp/models.py`: Provider, Category, Pick, MVPTranche, MVPSnapshot frozen Pydantic models + 7 tests — `90fa0af`.
- [2026-09-22] MVP M1.2 — `src/mvp/store.py`: `MVPStore` init_db + provider/category CRUD + 14 tests — `14700c3`.
- [2026-09-23] MVP M1.3 — `src/mvp/store.py`: `MVPStore` pick CRUD + snapshot methods + 8 tests — `44c8408`.
- [2026-09-23] MVP M2.1 — `src/mvp/tracker.py`: `MVPEvent` + `check_prices` pure logic + 9 tests — `af5ea2a`.
- [2026-09-23] MVP M2.2 — `src/mvp/tracker.py`: `format_telegram_summary` MarkdownV2 hourly watch output + 8 tests — `77e9d53`.
- [2026-09-23] MVP M3.1 — `scripts/mvp.py`: provider + category subcommands (CLI, no new tests) — `e89f205`.
- [2026-09-23] MVP M3.2 — `scripts/mvp.py`: add + update + close subcommands with instrument resolution (CLI, no new tests) — `74b84c8`.
- [2026-09-23] MVP M3.3 — `scripts/mvp.py`: list + summary subcommands (CLI, no new tests) — `731529b`.
- [2026-09-23] MVP M4.1 — `scripts/mvp_watch.py`: hourly LTP fetch + snapshot recording + auto-close (integration-only, no new tests) — `8fbe496`.
- [2026-09-23] MVP M4.2 — `scripts/mvp_watch.py`: Telegram per-alert + consolidated hourly summary (integration-only, no new tests) — `6ed6aa9`.
- [2026-09-23] MVP M0.1 — `src/mvp/store.py`: `MVPStore.get_distinct_symbols()` + 2 tests (M0 equity-ingest symbol filter, split from M0 per M0.1-M0.4) — `86bdd0b`.
- [2026-09-23] MVP open point 1 — resolved M0 NIFTY 50 index data source (NSE index-close bhavcopy, probe run twice) — `2eecd0e`.
- [2026-09-23] MVP M0.2 — `src/backtest/equity_bhavcopy_ingest.py`: `EquityBhavRecord` + download/parse/write-to-parquet (CM UDiFF, EQ-series only) + 8 tests — `5322a2d`.
- [2026-09-23] MVP M0.3 — `src/backtest/equity_bhavcopy_ingest.py`: `IndexBhavRecord` + NIFTY 50 ingest functions + 3 tests — `27ff5f8`.
- [2026-09-23] MVP M8 — backfill entry + walk-forward (`src/mvp/backfill.py`: `enter_backfill_pick`/`run_backfill`, `MVPSnapshot.benchmark_close`, `MVPStore.record_snapshot`, `scripts/mvp.py backfill`
  subcommand) — Antigravity-implemented across 4 phases, each real-`code-reviewer`-gated before commit. Uniparts acceptance run passed clean: entry ₹659.70, TARGET_HIT at ₹873.15, +3.06% dev. Three
  duplicate picks from Antigravity's earlier failed attempts were deleted from the live DB post-verification (no dedup guard on `backfill` CLI — deferred, not fixed). SHAs: `e6a6e5b`, `18602cc`,
  `3bc724e`, `cc42392`.
- [2026-09-22] `doc-format-migration/` `enforcement/` DFM-10 done (`fd50a62`) — `scripts/dev/new_plan_folder.py` (`--story`/`--epic`/`--into` CLI) scaffolds a conforming folder from
  `docs/plan/_TEMPLATE/`, stripping guidance comments and substituting slug/title placeholders; refuses an existing target or a `--into` epic that doesn't exist; `.claude/skills/new-story/SKILL.md`
  thin wrapper; `docs/plan/README.md` §Conventions now points at `/new-story` and states the format is enforced, not advisory. This closed `enforcement/` (DFM-6..10 all done) and the whole
  `doc-format-migration/` epic — archived to `docs/archive/plan/doc-format-migration/` this session, see `docs/archive/TODOS_ARCHIVE.md`.
- [2026-09-22] `doc-format-migration/` `enforcement/` DFM-9 done — `check_story_structure.py` gained `--strict` (`--all --strict` fails on any finding, warnings included, except a folder on
  `_LEGACY_ALLOWLIST` which still grandfathers — mirrors `--staged`'s per-folder treatment); new `docs-format` CI job runs all three doc hooks repo-wide (`check_md_line_length.py`,
  `check_story_structure.py --all --strict`, `check_checkbox_consistency.py --all`) and fails the build on any finding; `md-organize` SKILL.md Step 5b now says its `--all` audit is a local pre-check,
  CI is the gate. Confirmed the tree is currently clean against `--strict` (only `dev-foundation`'s grandfathered warnings survive). SHA `ade7420`.
- [2026-09-22] `doc-format-migration/` `enforcement/` DFM-8 done — added `check-checkbox-consistency` local hook to `.pre-commit-config.yaml` (`files: '^docs/(plan|bugs)/.*\.md$'`, `pass_filenames:
  true`); `check_checkbox_consistency.py` already supported path-mode invocation and `--all` was already green tree-wide post `plan-folders/` + `repo-wide-reflow/`, so no script change or new test was
  needed — existing `test_main_path_mode_checks_owning_task_file` already covers the pre-commit invocation shape. `pre-commit run --all-files` clean except two pre-existing, unrelated failures (`mypy`
  on `src/notifications/exit_message.py`, out of DFM-8 scope). SHA `d4d249d`.
- [2026-09-22] `doc-format-migration/` `enforcement/` DFM-7 done — `check_story_structure.py` gained `--staged` mode (added *or* modified `docs/plan/` folders, via `git diff --cached --name-only` with
  no `--diff-filter`), replacing `--staged-added` in `.pre-commit-config.yaml`. Added `_LEGACY_ALLOWLIST = {"dev-foundation"}` (its epic-root `prompt.md` and one sub-story's legacy `*_tasks.md` name
  are a known tier-D gap per `plan-folders/stories.md`, not yet archived) — allowlisted folders' findings all print as warnings and never fail `--staged`. `Finding` gained a `strict: bool` field: off
  the allowlist, a missing-required-file or legacy-filename warning now fails `--staged` (promoted to error-equivalent), while schema-backstop and extra-.md-checkbox warnings still pass.
  `--staged-added` and `--all` behavior unchanged. SHA `8e711f1`.
- [2026-09-22] `doc-format-migration/` `enforcement/` DFM-6 done — widened `md-line-length` + `md-reflow` `files:` to the whole repo tree (was `docs/plan|bugs/` + root only), excluding
  `docs/archive/`, `docs/plan/_TEMPLATE/`, and (new, see follow-up below) `docs/council/`. Fixed the true positives the wider net caught: `<!-- lint-ignore-length -->` markers on table/fenced-code
  lines in `src/paper/CLAUDE.md`, `docs/strategies/*.md`, `scratch/2026-09-01_*.md` (two long `--question` bash literals split into adjacent-concatenated strings to avoid corrupting the runnable
  command), and a `reflow_md.py` pass on `docs/plan/dev-foundation/` (already in scope pre-widening but never actually run). `pre-commit run --all-files` green on both hooks. SHA: `7107a56`. Next:
  DFM-7.
- **Follow-up filed:** `reflow_md.py` doesn't cleanly wrap `docs/council/*.md` (4-space-indented nested list items, some 800-1500 char single lines) — `repo-wide-reflow/` DFM-5 touched these files but
  left them non-conforming. `docs/council/` is excluded from the DFM-6 widened scope pending a fix to `reflow_md.py`'s nested-list/table handling and re-inclusion. Not yet a numbered backlog item —
  file one under `doc-format-migration/` or a standalone `reflow_md` fix when picked up.
- [2026-09-22] `doc-format-migration/` `repo-wide-reflow/` DFM-5 closed — reflowed 77 in-bounds `.md` files repo-wide (root, `docs/` non-plan, `.claude/`+`.agents/`, `src`/`scripts`/`scratch` strays)
  to fill-to-≤200 in 4 per-directory commits, then updated `docs/plan/README.md` §"Markdown line style" to drop the POC-folder carve-out. `repo-wide-reflow/` story now fully done; epic `README.md`
  Stories row flipped to ✅. SHA: `15698be`. Next: `enforcement/` (blocked until both `plan-folders/` and `repo-wide-reflow/` are green — both now are).
- [2026-09-22] `doc-format-migration/` `plan-folders/` DFM-4 closed as no-op — DFM-1's confirmed tier table classifies all 19 remaining folders as tier A or B (plus `dev-foundation/` tier D); no
  tier-C folder exists (the two examples named in `prompt.md`, `root-doc-organization/` and `telegram-markdown-migration/`, are already archived). No files changed, no commit. `plan-folders/` story is
  now fully done; epic `README.md` Stories row flipped to ✅. Next: `repo-wide-reflow/`.
- [2026-09-22] `doc-format-migration/` `plan-folders/` DFM-3 closed — restructured the last tier-B folder, `historical-data-abstraction/`: consolidated 11 `stories/HD-N.md` files into one
  `stories.md`, canonical task-line format, `Story done when` section, reflow. SHA: `906684c`. All 4 tier-B folders done (`broker-abstraction/` `525c0d2`, `phase2-integrations/` `107f58b`,
  `full-repo-review/` `caeafc7`, `historical-data-abstraction/` `906684c`, the last 3 via parallel subagents). DFM-3 ticked. Next: DFM-4 (tier-C reflow-only pass).
- [2026-09-22] `doc-format-migration/` `plan-folders/` DFM-3 — restructured `full-repo-review/` (tier B, 3 of 4, via parallel subagent): canonical task-line format, `stories.md` trimmed from 11
  forward specs to one-line digests (shipped/superseded folder), reflow. SHA: `caeafc7`.
- [2026-09-22] `doc-format-migration/` `plan-folders/` DFM-3 — restructured `phase2-integrations/` (tier B, 2 of 4, via parallel subagent): canonical task-line format + prompt.md template sections +
  reflow. No shipped tasks, no digests needed. SHA: `107f58b`.
- [2026-09-22] `doc-format-migration/` `plan-folders/` DFM-3 — restructured `broker-abstraction/` (tier B, first of 4): consolidated 16 `stories/BA-N.md` files into one `stories.md`, canonical
  task-line format, reflow. No shipped tasks, no digests needed. SHA: `525c0d2`. DFM-3 not ticked — `full-repo-review/`, `historical-data-abstraction/` remain.
- [2026-09-22] `doc-format-migration/` `plan-folders/` DFM-2 closed — converted the remaining 12 tier-A folders (`backtest-eval-core/`, `chain-decay-analysis/`, `entry-event-filter/`,
  `full-repo-review-followups/`, `greeks-bs-fallback/`, `ic-payoff-charts/`, `mvp/`, `options_income/`, `risk-gamma-phase-a/`, `signals-eval-core/`, `technical-debt/`, `variance-gate/`) via 12
  parallel subagents, one commit each (SHAs: `7fcdba2`, `8b1c5df`, `b22052a`, `4dc1ed1`, `0a2838a`, `500c290`, `8455d50`, `ddf0964`, `1f0a6cd`, `6a9c87e`, `b1bf839`, `0b8d897`);
  `portfolio-snapshot-slimdown/` needed zero changes (already canonical + reflow-clean). Notable catches beyond format: `full-repo-review-followups/` had 6 sub-story `tasks.md` files with task
  descriptions truncated mid-sentence since the original authoring commit (`149408f`), reconstructed from each sub-story's `stories.md`; `mvp/`/`options_income/`/`variance-gate/` legacy filenames
  renamed via plain `mv` (git detected the renames by content similarity anyway). All 14 tier-A folders now pass `check_story_structure.py --all` and `check_checkbox_consistency.py --all` clean;
  `reflow_md.py --check` clean repo-wide across `docs/plan/`. Added missing `docs/plan/README.md` status lines for `options_income/` and `technical-debt/` (neither had one before). DFM-2 ticked,
  DFM-1's own SHA corrected from `PENDING` to `37bf311`. Remaining tier-B folders (`broker-abstraction/`, `historical-data-abstraction/`, `phase2-integrations/`) are DFM-3's scope, not touched here.
- [2026-09-22] `doc-format-migration/` `plan-folders/` DFM-1 — enumerated and tiered all 19 non-archived `docs/plan/` folders (outside this epic + `_TEMPLATE/`) into the confirmed A/B/C/D table in
  `plan-folders/stories.md`. 15 tier A (active), 3 tier B flagged for Animesh (`broker-abstraction/`, `historical-data-abstraction/`, `phase2-integrations/` — unstarted, 0 shipped tasks, not in any
  active-work list; B is the closest fit but not a clean match), 1 tier D (`dev-foundation/` — already ✅ Shipped/Archived but its `code-health/` sub-story never moved to `docs/archive/plan/`; filed a
  follow-up `git mv`, not a conversion target). SHA `<pending>`.
- [2026-09-22] `doc-format-migration/` `plan-folders/` DFM-2 — converted tier-A folder `backtest-engine/` to canonical epic shape: added root `prompt.md` (router) + `README.md` (both missing before);
  `phase1..4/` sub-story shape was already canonical, no changes beyond reflow. `reflow_md.py` applied repo-wide across the folder; `check_story_structure.py --all` and `check_checkbox_consistency.py`
  both clean for `backtest-engine/`. Added a status line to `docs/plan/README.md` §Active Stories (the folder had none before). Proof-of-approach pass — 13 remaining tier-A folders still open. SHA
  `150fab9`.
- [2026-09-22] `root-doc-organization/` (`docs/archive/plan/root-doc-organization/`) — RDO-16 step 4 confirmed: this session's own SessionStart produced no `state_doc_freshness.sh` staleness warning,
  and a manual re-run reproduced the clean result — the flag that fired last session for `PLANNER.md`/`CONTEXT_TREE.md`/`README.md` cleared once those docs were refreshed. All four loop-closure steps
  verified end to end; RDO-16 closes, completing every task box in the story, so the story archived in the same commit per §Completion → archive. SHA `<pending>`.
- [2026-09-22] `root-doc-organization/` RDO-16 (steps 1-3 of 4) — this session's own `state_doc_freshness.sh` SessionStart flag (`PLANNER.md`/`CONTEXT_TREE.md`/`README.md` behind code) was acted on:
  all three refreshed against current `src/`/`scripts/` state (signals pipeline, paper-backbone completions, `.claude/skills/` + `hooks/` drift, stale May-June roadmap items reconciled). RDO-16 stays
  open — step 4 (flag clears at next SessionStart) can only be confirmed in a future session.
- [2026-09-22] `root-doc-organization/` RDO-11 — measured the full observation window (2026-08-27 → 2026-09-22): 84 of 116 code commits (72%) would have tripped `doc_update_gate.sh`, `[skip-docs]`
  used zero times. Kept the gate tuned-advisory (flipping to blocking would have blocked ~3 of 4 commits on an unused escape hatch); recorded in `DECISIONS.md` §Developer Tooling. SHA `<pending>`.
- [2026-09-22] `signal-outcome-profit-range/` SOP-3 (`docs/archive/plan/signal-outcome-profit-range/`) — `_format_outcome_notification` renders a "📈 High / 📉 Low" line in the executed branch only,
  using the existing `_E(...)` / `format_money(..., signed=True)` escaping pattern; omitted (no blank-line artifact) when either field is `None`. SHA `a73b6b6`. Story complete (SOP-1..3) — archived to
  `docs/archive/plan/signal-outcome-profit-range/`.
- [2026-09-22] `signal-outcome-profit-range/` SOP-2 (`docs/plan/signal-outcome-profit-range/`) — `run_record_phase` captures `trade_id` from the auto-detected live `paper_signal_entries` row and
  computes `high_pnl_per_lot`/`low_pnl_per_lot` via new `_high_low_pnl_per_lot()` off the last `paper_signal_marks` row's `mfe_pct`/`mae_pct`, scaled by `entry_premium * LOT_SIZE`. Not-executed /
  no-live-entry / no-marks leave both `None`. SHA `180ccae`. Next: SOP-3.
- [2026-09-22] `signal-outcome-profit-range/` SOP-1 (`docs/plan/signal-outcome-profit-range/`) — added `high_pnl_per_lot`/`low_pnl_per_lot: Decimal | None` to `SignalOutcome`, idempotent
  `signal_outcomes` ALTER TABLE migration, read/write in `SignalStore.record_outcome` / `_outcome_from_row`. No backfill, existing rows read back as `None`. SHA `4096c07`. Next: SOP-2.
- [2026-09-18] MVP design decisions (`docs/plan/mvp/`) — resolved the 9 open questions blocking M1 in `mvp_tasks.md` (whole-share tranche rounding + idle cash, 25bps cost per transaction, live-fetch
  benchmark_entry, N=6mo time stop, independent-per-pick portfolio mode, M-A lump-sum-first / M-B ladder phasing, no council call needed). Added `mvp_tranches` table + new `mvp_recommendations`
  columns to `mvp_schema.md`, rewrote M1.1's spec in `mvp_stories.md` for the full capital-deployment field set, and added a new M0 (equity+index bhavcopy ingest) task ahead of M6 since
  `src/backtest/bhavcopy_ingest.py` is F&O-only. SHA `cb36eaf`. Docs only, no code — next session picks up M1.1.
- [2026-09-15] BUG-047 (`docs/archive/bugs/bugs.md`) — signal_track_v1 paper entries and Telegram entry messages were never sent: `src/signals/pipeline.py`'s SPT-6 tail-call called
  `paper_store.init_db`, a method that doesn't exist on `PaperStore` (its `__init__` already creates schema), silently swallowed by the cron-boundary `except Exception` on every run since introduced.
  Confirmed via empty `paper_signal_entries` table + two days of `paper_entry_failed` warnings in `logs/morning_signal.log`. Fixed by deleting the stray call. SHA `e8d91c1`. CC/PP/Collar/IC unaffected
  — isolated to the signal-track path.
- [2026-09-15] ORD-4 (`docs/plan/telegram-message-unification/overlay-recovery-digest/`) — epic close. Updated `CONTEXT.md` (`src/notifications/` entry — fenced recovery digest + BUG-044 fix note),
  `DECISIONS.md` (epic-close + `_overlay_type_groups` grouping decision entry), `src/notifications/CLAUDE.md` (recovery digest is its own fenced block, not a renderer-lineage caller). Flipped the epic
  `README.md`'s `overlay-recovery-digest/` row to ✅ Done (SHA `8f0e8e4`) and its "Epic done when" bullet. `git mv`'d the whole `telegram-message-unification/` folder to `docs/archive/plan/`. Collapsed
  the `docs/plan/README.md` entry to a one-line pointer. Moved this Feature Backlog line to `docs/archive/TODOS_ARCHIVE.md`. Flipped BUG-044 to ✅ Fixed (SHA `7c255fd`) and moved both
  `docs/bugs/bugs.md` and `docs/bugs/task.md` entries to `docs/archive/bugs/`. Review: none (docs only). Epic complete.
- [2026-09-15] ORD-3 (`docs/plan/telegram-message-unification/overlay-recovery-digest/`) — migrated `_build_recovery_digest` off per-line `escape_markdown` onto a single MarkdownV2 fenced block
  (matches the `pre_market_brief.py` house style, fixes the BUG-042 send-path class for this caller); call site unchanged, content now literal per the fence contract. Added red/flat-day golden-string
  tests + a not-double-escaped guard. Fixed two line-number drifts in `tests/unit/notifications/test_escaping_guard.py`'s baseline (2017→2020, 2063→2066) and reworded the digest entry's rationale to
  the now-fenced shape. code-reviewer: 0 CRITICAL/ERROR, 2 WARNING (docstring wording, fixed inline; emoji header line inside the fence not yet on-device confirmed per FORMATTING.md §7 — deferred,
  non-columnar header carries no alignment risk like the rejected 🔴 case). SHA: 8f0e8e4. Next: ORD-4 (epic close).
- [2026-09-15] ORD-2 (`docs/plan/telegram-message-unification/overlay-recovery-digest/`) — fixed BUG-044 per ORD-1's heuristic (a): `_overlay_type_groups` no longer merges a standalone `overlay_cc`
  into the `collar` group; `overlay_cc` always gets its own `cc` row, `collar` only ever reflects its own legs. `_compute_overlay_pnl_snapshots` needed no change (already iterates groups generically).
  Rewrote the BUG-030 regression tests to the no-merge behavior, added an end-to-end digest test. Also fixed a line-number drift in `tests/unit/notifications/test_escaping_guard.py`'s baseline (5
  pre-existing unescaped call sites shifted by -1 line from this edit — no new unescaped sends). code-reviewer: 0 CRITICAL/ERROR, 2 WARNING (one pre-existing has_call+has_cc key-collision edge case,
  deferred — practically impossible given the entry-time dedup guard; one line-length nit, fixed). SHA: 7c255fd. Next: ORD-3.
- [2026-09-15] ORD-1 (`docs/plan/telegram-message-unification/overlay-recovery-digest/`) — investigated BUG-044: confirmed from live `paper_trades` that a standalone `overlay_cc` and a collar-put-only
  position genuinely coexist (the collar's original call leg closed 2026-08-25; every `overlay_cc` since has been an unrelated weekly `--auto-cc` re-entry on a different strike). No field in
  `paper_trades` reliably links a later `overlay_cc` back to its collar once the linked leg closes — the `Cycle N` note tag is an overlay-wide counter, not a per-collar marker. Decision: heuristic (a)
  — retire the BUG-030 `has_cc and has_put → collar` merge branch outright; always emit separate `cc` and `collar` (put-only) groups. BUG-044 updated with the finding + decision. No code change.
  SHA: 9883981. Next: ORD-2.
- [2026-09-14] UXM-7 (`docs/plan/telegram-message-unification/unified-exit-message/`) — `scripts/pre_market_brief.py` redesigned: dropped the broken `<b>` HTML (previously escaped and sent literally
  under MarkdownV2), now a fenced `Strategy | Legs | Unrealized P&L` table using `strategy_label()`; `paper_nifty_overlay` breaks into a parent row plus `├ CC / ├ Collar / └ PP` sub-rows via
  `resolve_target` leg-role filters (empty sub-group shows `—`); trailing `Total` row counts the overlay once via its parent aggregate. Added the missing `paper_signal_track_v1` entry to
  `STRATEGY_LABELS` (`strategy_label()` raises on an unmapped id — this would have crashed the brief on the day a signal-track paper position opens). SHA: 84e786b. Pre-existing, out-of-scope:
  `tests/unit/notifications/ test_escaping_guard.py` has 4 failing assertions from UXM-4/5/6's `auto_close.py` / `eod_summary.py` / `record_paper_trade.py` migrations whose escaping baseline was never
  updated — confirmed present at HEAD before this task, not touched here.
- [2026-09-14] UXM-8 (`docs/plan/telegram-message-unification/unified-exit-message/`) — sub-story docs close: `CONTEXT.md` / `src/notifications/CLAUDE.md` / `DECISIONS.md` reflect the shared exit
  renderer, `cycle_stats`, and the brief redesign; epic `README.md` Stories-table row flipped to ✅ Done (closing SHA `84e786b`, UXM-7's commit). No code change. Epic folder not archived — archives
  whole at ORD-4 (`overlay-recovery-digest/`). Next: ORD-1.
- [2026-09-13] UXM-1 (`docs/plan/telegram-message-unification/unified-exit-message/`) — gross-short-premium `short_decay_pct` (+ `short_credit_per_unit` / `short_buyback_per_unit`) added to `Cycle`;
  short leg identified by entry-trade `action == SELL`, not `leg_role` naming — stable across IC/CSP/CC/Collar, `None` for a pure-long PP. New pure `cycle_stats(trades) -> CycleStats` helper
  (win_rate, avg_win/loss, best/worst, avg_hold_days, avg_decay_pct). `resolve_target` / `LegGroup` (renamed from `_Group`) moved from `scripts/dev/cycle_pnl_report.py` into `src/paper/cycle_pnl.py`;
  CLI output unchanged. SHA 51d546c (feat), 49c9a55 (docs-close). Tests: 20/20 green (`tests/unit/paper/test_cycle_pnl.py`), full suite 3091/3091. Review: code-reviewer + greeks-analyst, both clean.
  Next: `unified-exit-message/` UXM-2 (shared `exit_message.py` renderer).
- [2026-09-14] UXM-2 (`docs/plan/telegram-message-unification/unified-exit-message/`) — new `src/notifications/exit_message.py`: `ExitKind(str, Enum)`, frozen `ExitMessage`, `format_exit_message()`;
  `CloseLegRow` + `build_close_leg_table()` added to `formatting.py`. Renderer + tests only, no callers wired yet. Cycle-line collapses into the this-exit line on a full close, omits on a partial
  close, drops the credit/buyback/decay segment for a pure-long cycle (PP); win-rate row gated at `closed_count >= 5`. `ExitMessage.__post_init__` enforces the cycle-field-group invariants (added post
  code-review — a latent `TypeError` crash if `cycle_decay_pct` were set without `cycle_short_credit`/`cycle_short_buyback`). SHA e9d830d. Tests: 13/13 green
  (`tests/unit/notifications/test_exit_message.py`), full suite 3104/3104. Review: code-reviewer, clean after the `__post_init__` fix (2 minor float-vs-Decimal WARNINGs on `CloseLegRow`/`LegRow`
  deferred — matches existing display-row precedent). Epic `README.md` `unified-exit-message/` row set to 🔄 In progress (not yet ✅ — 7 of 8 UXM tasks remain). Next: `unified-exit-message/` UXM-3
  (migrate IC v1/v2 closes).
- [2026-09-14] UXM-3 (`docs/plan/telegram-message-unification/unified-exit-message/`) — `IronCondorV1`/`IronCondorV2._send_close_notification` migrated off the hand-rolled `✅ *IC closed — …*` f-string
  onto `format_exit_message(ExitMessage(...))`. Per-leg entry/exit price now comes from the pre-close `positions` list (threaded through as a new 4th param on both methods) via
  `avg_sell_price`/`avg_cost`; per-leg P&L computed locally from `_SHORT_ROLES` sign convention; DTE via the existing `_parse_expiry` pattern; the cycle/inception/win-rate footer via
  `reconstruct_cycles`/`cycle_stats` (UXM-1) + `get_strategy_realized_pnl`. Instrument labels via `format_leg_label` against a freshly-loaded `InstrumentLookup` (falls back to the raw key on failure,
  matching the existing roll-target pattern in these files); local `_CLOSE_ROLE_LABELS` dict covers the two hedge roles `formatting.py`'s shared `LEG_ROLE_LABELS` doesn't (out of this story's file
  scope to extend). `ExitMessage` construction and `format_exit_message()` now sit in their own try/except (code-review fix — a validation/format crash there must not propagate through
  `apply_action`), separate from the `send_notification` try/except. SHA 22359bf. Tests: 108/108 green (`test_ic_nifty_v1.py` + `test_ic_nifty_v2_signals.py`, incl. new held-days and
  notify-failure-non-fatal coverage), `tests/unit/strategy/` 709/709, full suite otherwise green (4 pre-existing unrelated failures: 3 escaping-guard baseline drift from `eod_summary.py` line shifts,
  1 NSE-2025-calendar message-text mismatch — neither touched by this task). Review: code-reviewer, clean after the try/except fix. Next: `unified-exit-message/` UXM-4 (migrate CSP + recorder
  `--close`).
- [2026-09-14] UXM-4 (`docs/plan/telegram-message-unification/unified-exit-message/`) — `CSPNiftyV1`'s two close sites migrated onto `format_exit_message`: the CLOSE_AND_ROLL `_reentry_notification`
  follow-up (`ExitKind.CLOSE`) and the CLOSE_AND_WAIT `⛔ waiting` message (`ExitKind.WAITING` + `state_line="RE_ENTRY_PENDING — no new position opened."`). `_close_leg` now returns the written
  `PaperTrade | None` (was `None`) so the close price reaches the card; `_reentry_notification` gained a `close_trade` 3rd param. New shared `_send_close_card` helper mirrors IC v1's footer-calc +
  triple try/except pattern (`_send_close_card` build, `format_exit_message`, `send_notification` each logged distinctly). `scripts/record/record_paper_trade.py --notify` now also fires on a
  successful `--close` via new `_send_close_card_if_requested` (reads the just-closed cycle off `reconstruct_cycles`/`cycle_stats`, headline via `strategy_label()`, falls back to the raw strategy id
  on an unmapped one). SHA 21a8449. Tests: 66/66 green (`test_csp_nifty_v1.py` + `test_record_paper_trade.py`); escaping-guard baseline bumped for the entry-card call site's line shift (774→775) plus
  one new documented entry for the exit-card call site (845). Review: code-reviewer, clean after 2 minor WARNING fixes (narrowed a bare `except Exception` around `strategy_label()` to `except
  ValueError` + logged it; added missing `-> None` test annotations). Next: `unified-exit-message/` UXM-5 (migrate CC/PP/Collar strategy-class closes).
- [2026-09-14] UXM-5 (`docs/plan/telegram-message-unification/unified-exit-message/`) — `CCOverlayV1` / `PPOverlayV1` / `CollarOverlayV1`'s `_send_close_notification` migrated onto
  `format_exit_message`, mirroring UXM-3/UXM-4's footer pattern. Since all three share `strategy_name=STRATEGY_OVERLAY`, `cycle_stats`/`reconstruct_cycles` are pre-filtered by each strategy's own
  `leg_role`(s) (`SHORT_CALL_ROLES={"overlay_cc"}`, `LONG_PUT_ROLES={"overlay_pp"}`, `{SHORT_CALL_ROLE, LONG_PUT_ROLE}` for Collar) before reconstruction, so CC/PP/Collar cycles never blend;
  `inception_pnl` and `overlay_total_pnl` both resolve to `get_strategy_realized_pnl(store, STRATEGY_OVERLAY)` (same number in both footer rows — intentional per the epic's "store number" decision,
  flagged but accepted by greeks-analyst as spec-consistent, not a bug). PP: `MONETIZE_PP` → `ExitKind.CRASH_MONETIZE` + `state_line`; `ROLL_PP` → `ExitKind.ROLL`, no state_line. Per-leg delta/DTE
  dropped from the close card (deliberate simplification — delta is not load-bearing post-close). SHA 7e19e78. Tests: 106/106 green across the three strategy test files + escaping-guard;
  escaping-guard baseline updated for line shifts (`collar_overlay_v1.py` reentry-failure entries 607→608, 609→610) and three new documented heuristic-limitation entries (`cc_overlay_v1.py:447`,
  `pp_overlay_v1.py:470`, `collar_overlay_v1.py:863`). Full suite: 3 pre-existing unrelated failures confirmed independent of this task (`tests/unit/notifications/test_escaping_guard.py` baseline
  drift on `scripts/eod_summary.py:198/200` and `scripts/record/record_paper_trade.py: 845/846` — reproduced identically with this task's changes fully reverted; neither file is touched by UXM-5).
  Review: code-reviewer, clean after 4 unused-import WARNING fixes (`format_money`/`mdcode` left over from the removed hand-rolled f-strings); greeks-analyst clean (P&L signs verified correct for all
  three, no cross-strategy cycle blending). Next: `unified-exit-message/` UXM-6 (migrate `auto_close.py` daemon paths).
- [2026-09-14] UXM-6 (`docs/plan/telegram-message-unification/unified-exit-message/`) — `auto_close.py`'s `_send_close_notification` (Collar/CC/PP daemon paths) migrated onto `format_exit_message`,
  mirroring UXM-5's strategy-class pattern. `dte`/`held_days` — never tracked by the old hand-rolled messages — now computed in `auto_close_overlay` from `chain.expiry`/`pos.entry_date` via
  `market_today()` and threaded through (Collar uses the earliest entry date across both legs), flagged by greeks-analyst as a WARNING against a hardcoded-0 first draft and fixed before commit.
  Cycle/`cycle_stats` footer filtered per overlay type against `src/paper/cycle_pnl.py`'s `_OVERLAY_GROUPS` leg-role tuples. Per-leg delta dropped from the CRASH_MONETIZE line (consistent with UXM-5,
  not load-bearing post-close per greeks-analyst). SHA 3f812a8. Tests: 715/715 green (`tests/unit/strategy/`). Review: code-reviewer — 1 CRITICAL (missing G5 intent comment on the new footer-calc
  `except Exception`) fixed before commit; remaining WARNINGs (line-length false positives against the repo's actual 100-char limit, and a defensive `Decimal(str(leg["pnl"]))` round-trip on the
  `Any`-typed legs dict) deferred as non-blocking. Next: `unified-exit-message/` UXM-7 (`pre_market_brief.py` redesign).
- [2026-09-13] OEM-5 (`docs/plan/telegram-message-unification/overlay-entry-message/`) — sub-story docs close. `CONTEXT.md` / `src/notifications/CLAUDE.md` / `DECISIONS.md` updated to reflect the
  sign-aware net line (OEM-1) and the Collar re-entry + three-track bootstrap cards (OEM-2/OEM-4, OEM-3 merged into OEM-4). Epic `README.md` `overlay-entry-message/` row flipped to ✅ Done, closing SHA
  3982c0e. Epic folder not archived — archives whole at UXM-8. Review: none (docs only). Next: `unified-exit-message/` (UXM-1).
- [2026-09-13] OEM-3 (`docs/plan/telegram-message-unification/overlay-entry-message/`) — merged into OEM-4, no code change. Graph inspection of `CCOverlayV1.apply_action`, `PPOverlayV1.apply_action`,
  and `ReEntryMixin._check_reentry` found neither class performs an in-tick automated re-entry the way `CollarOverlayV1._reenter_collar` does (OEM-2) — `apply_action` only closes and calls
  `_check_reentry`, which writes an ELIGIBLE/BLOCKED `paper_exit_events` row and tells the operator to run a script manually; no position is reopened there. The only place a CC/PP re-entry is actually
  recorded is `auto_cc_bootstrap` / `auto_pp_bootstrap` in `paper_3track_overlay_entry.py` — OEM-4's target. `tasks.md` and `stories.md` updated to fold OEM-3's card requirement into OEM-4. Review:
  none (docs only). Epic `README.md` row stays 🔄 In progress. Next: OEM-4 (bootstrap message onto shared renderer, now covering CC/PP/Collar entry cards).
- [2026-09-13] OEM-2 (`docs/plan/telegram-message-unification/overlay-entry-message/`) — `CollarOverlayV1._reenter_collar` now sends a `✅ *Collar Entry*` card via the shared `format_entry_message`
  renderer after a successful automated two-leg re-entry, non-fatal on notifier failure. `select_and_build_collar_entry` (`src/strategy/collar_entry.py`) widened to also return the chain-fetched
  spot + each leg's delta (no second chain fetch). Two new tests (`test_reentry_sends_collar_entry_card`, `test_reentry_notify_failure_is_non_fatal`). `code-reviewer` + `greeks-analyst` clean after
  one round of fixes (try/except widened to cover message construction; deltas threaded through instead of `None`). SHA `24946d7`. Epic `README.md` row stays 🔄 In progress (OEM-3/4/5 remain). Next:
  OEM-3 (CC + PP re-entry entry cards) — see OEM-3 entry above: merged into OEM-4.
- [2026-09-13] OEM-1 (`docs/plan/telegram-message-unification/overlay-entry-message/`) — `entry_message.py::_credit_line` is sign-aware: negative `net_credit` renders `💰 *Net debit:*` (absolute
  value); positive/zero byte-identical. Two new tests (`test_net_debit_line_when_net_credit_negative`, `test_net_credit_line_unchanged_for_zero`). `code-reviewer` clean (0 CRITICAL/ERROR/WARNING). SHA
  `2832717`. Epic `README.md` row flipped to 🔄 In progress. Next: OEM-2 (`CollarOverlayV1` re-entry entry card).
- [2026-09-13] UEM-3 (`docs/plan/telegram-message-unification/unified-entry-message/`) — docs close for `unified-entry-message/` (UEM-1..3). Updated `CONTEXT.md`'s `src/notifications/` bullet
  (`ic_entry_message.py` → `entry_message.py`, shared renderer note), added the UEM-2 card note to `src/notifications/CLAUDE.md`'s `entry_message.py` entry, added a `DECISIONS.md` §P&L & Reporting
  line (renderer rename + relaxed `ivr`), flipped the epic `README.md` Stories-table row to ✅ (`889d860`), and this Session Log line. No code change. Epic folder not archived — archives whole at
  UXM-8. Next: OEM-2 (`overlay-entry-message/`).
- [2026-09-12] UEM-1 (`docs/plan/telegram-message-unification/unified-entry-message/`) — generalized `src/notifications/ic_entry_message.py` → `entry_message.py` (`EntryMessage` +
  `format_entry_message`, `headline_label` field replaces the `strategy_name` v1/v2 marker, `ivr`/`mode`/`expiry_type` made optional, `dte`/`spot`/`net_credit`/`expiry` stay required); migrated both
  IC call sites (`paper_ic_entry.py`, `paper_ic_entry_v2.py`); renamed `test_ic_entry_message.py` → `test_entry_message.py` (8 existing assertions kept, 2 new for optional-IVR behavior). IC output
  byte-identical, confirmed by `code-reviewer`. Antigravity-implemented (`08fd78c`); real `code-reviewer` run flagged 1 ERROR (stale `ic_entry_message.py` reference in `src/notifications/CLAUDE.md`,
  fixed by Claude in the same commit) and 3 cosmetic WARNINGs (deferred). 119/119 notifications tests green.
- [2026-09-13] UEM-2 (`docs/plan/telegram-message-unification/unified-entry-message/`) — added `--notify` to `scripts/record/record_paper_trade.py`: on a successful CSP/CC SELL open (not `--close`),
  derives strike/expiry/option-type from `instrument_key` (`parse_strike_from_key`/ `parse_expiry_from_key`), fetches Nifty spot, builds an `EntryMessage`/`format_entry_message` card and sends it
  non-fatally via `build_notifier()`/`TelegramNotifier`. 4 new tests (`test_record_paper_trade.py`); added a `test_escaping_guard.py` baseline entry (the guard's single-function heuristic can't see
  through `_build_entry_card` → `format_entry_message`'s internal escaping). `code-reviewer` flagged 2 WARNINGs (Decimal→float boundary at the spot value, both call site and test mock), fixed in the
  same commit. SHA `889d860`.
- [2026-09-12] SEC-3 (`docs/plan/signals-entrypoint-consolidation/`) — merged `scripts/record_signal_outcome.py`
  + `scripts/signal_report.py` into `scripts/signal_eod.py` (one 16:00 cron, one `guard_trading_day`, `--auto`/`--report-only` flags; a record-phase exception no longer blocks the report phase). Old
    scripts + tests retired. Antigravity-implemented (`928cb22` merge, `b297734` retire, `6b6177b` follow-up fix). Real `code-reviewer` run on the first pass flagged 2 CRITICAL (missing REVIEW.md G5
    intent comments on the two `except Exception` catches) and 2 ERROR (escaping-guard baseline entries left as placeholder `"temp"` reasons; two ported tests didn't mock `guard_trading_day` and
    silently relied on the real holiday calendar) — all resolved in the follow-up commit, which also restored a `send_test_telegram.py:65` baseline entry collaterally dropped during the retire commit.
    Targeted test set (`tests/unit/scripts/`, `tests/unit/signals/`, `tests/unit/notifications/test_escaping_guard.py`) green — 527 passed.
- [2026-09-12] SEC-4 (`docs/plan/signals-entrypoint-consolidation/`) — extracted `morning_signal.run()`'s pipeline body into `src/signals/pipeline.py::run_morning_signal_pipeline` (`85b4744`);
  `scripts/morning_signal.py` is now orchestration + Telegram only. `code-reviewer`: 0 CRITICAL/ERROR, 2 WARNING deferred (log-order shift, logger-name mismatch) — no data-correctness impact. Fixed a
  stale escaping-guard baseline line-number entry the extraction moved. Targeted set (`tests/unit/scripts/`, `tests/unit/signals/`, `tests/unit/strategy/`, `tests/unit/notifications/`) green — 1342
  passed.
- [2026-09-12] SEC-5 (`docs/plan/signals-entrypoint-consolidation/`) — reviewed `scripts/signal_paper_entry.py` keep-or-delete against the `morning_signal` tail-call's track record; deferred
  (`290ba3a`). The SPT-6 tail-call only landed at 19:13 on 2026-09-11, after that day's 09:30 cron had already run without it — zero live production runs, so neither the story's "failed and a re-entry
  fixed it" (keep) nor "reliable" (delete) criterion is met. Kept the script (already uses `guard_trading_day` + `is_actionable` per SEC-1/SEC-2); documented the deferral and rationale in its module
  docstring. `code-reviewer`: 0 CRITICAL/ERROR/WARNING (docstring-only diff). Revisit once the tail-call has an actual track record.
- [2026-09-12] SEC-6 (`docs/plan/signals-entrypoint-consolidation/`) — docs close: updated `CONTEXT.md`'s `src/signals/` entrypoint list + crontab to the merged two-cron state, `DECISIONS.md` §P&L &
  Reporting with the `signal_eod` merge note, collapsed `docs/plan/README.md`'s story row to the archived pointer, deleted this file's backlog pointer. Also found and fixed a live gap: the Mac host
  crontab still ran the two scripts SEC-3 retired (`record_signal_outcome`, `signal_report`), which no longer exist — tonight's 16:00/16:35 runs would have failed with `ModuleNotFoundError`. Animesh
  applied the corrected single 16:00 `scripts.signal_eod` line manually; verified via `crontab -l`. Story archived to `docs/archive/plan/signals-entrypoint-consolidation/`.
- [2026-09-12] Fixed 3 flaky `tests/unit/paper/test_overlay_entry.py` failures (`481f326`) — `_write_vix_fixture`'s `close` column was hardcoded to `rows` (252) elements while
  `pd.date_range(end=date.today(), periods=rows, freq="B")` returns fewer dates when `date.today()` falls on a non-business day (weekend runs only), raising `ValueError: All arrays must be of the same
  length`. Fixed by matching `close` to `len(dates)`. `code-reviewer`: 0 CRITICAL/ERROR/WARNING.
- [2026-09-12] Finished an incomplete `ruff` lint sweep found stashed from a prior session (`2d7890d`) — reran `ruff check --fix` + `ruff format` across scratch/, scripts/, src/portfolio/,
  src/strategy/, tests/unit/ (55 files) and manually resolved the 12 remaining lint errors ruff couldn't autofix: 5 unused locals/vars, 4 ambiguous `l` renames to `leg`
  (`test_apply_trade_positions.py`), a missing `zip(..., strict=True)`, and a blind `assertRaises(Exception)` narrowed to `FrozenInstanceError`. Full suite green (2649 passed; 3 pre-existing unrelated
  failures in `test_overlay_entry.py`, an off-by-one in a VIX fixture helper). `code-reviewer`: 0 CRITICAL/ERROR/WARNING. Separately, `tools/llm-council`'s own uncommitted WIP (5 files, OpenRouter
  model-id updates + a `max_tokens` cap fixing 402 `openrouter_key_limit` errors) was committed inside that submodule's own repo (`dbce7fe`) and the parent pointer bumped (`3a1bb5d`) — kept out of the
  lint-sweep commit per repo convention that a submodule's inner tree is a separate decision. Graph re-indexed (7370 nodes / 30025 edges).
- [2026-09-12] `docs/plan/signals-entrypoint-consolidation` **SEC-1** closed (`1ef2974`) — Added `market_calendar.guard_trading_day` and `is_market_session_now` helpers. Adopted `guard_trading_day` at
  the four signal script entrypoints, replacing duplicate inline logic. Adopted `is_market_session_now` inside `StrategyMonitor._tick` for its market-hours window. Unit tests updated and passing.
- [2026-09-11] `docs/plan/signals-paper-track` **SPT-8** closed (docs-only) — story done, archived to `docs/archive/plan/signals-paper-track/`. Updated `CONTEXT.md` (`src/strategy/` bullet +
  `SignalTrackV1`), `DECISIONS.md` (as-built follow-up note on the SPT ruling entry), `DB_REGISTRY.md` (`paper_signal_entries` / `paper_signal_marks` rows + note), `TODOS.md` (Feature Backlog item
  removed → `TODOS_ARCHIVE.md`), `docs/plan/README.md` (collapsed to the archived pointer; `signals-entrypoint-consolidation/` unblocked), and created `src/strategy/CLAUDE.md` (did not previously
  exist — also added `strategy` to root `CLAUDE.md`'s 9-module index and `protocol-reference` §5). `signals/` S5.5a marked `won't-do` in the archived `signals_tasks.md`. No code change.
- [2026-09-11] `docs/plan/signals-paper-track` **SPT-6** closed (`1f52880`) — entrypoint wiring, no new cron: `scripts/morning_signal.py` opens the paper entry via a guarded tail-call (`await
  open_signal_paper_entry(signal, snapshot, broker, paper_store)`, isolated in a `try/except` matching the existing entry-premium-capture pattern) right after `store.record_signal`;
  `scripts/monitor_daemon.py` registers `SignalTrackV1` structurally identically to the sibling strategies (its `due_interval_s=30` class attribute, set in SPT-4, drives the 30 s cadence — no
  registration-time param needed); new `scripts/signal_paper_entry.py` is a manual `--date` backfill/re-entry CLI for the rare failed-tail-call case, calling the identical `open_signal_paper_entry`
  hook. No unit tests (integration-only, matching `morning_signal.py`'s own precedent). Two `test_monitor_daemon.py` strategy-count assertions bumped +1 for the now-always-registered `SignalTrackV1`;
  one `test_escaping_guard.py` baseline line moved 282→296 (the tail-call shifted the already-safe `notifier.send(msg)` call site, not a new escaping gap). `code-reviewer`: 0 CRITICAL/ERROR/WARNING.
  Next: SPT-8 (docs close).
- [2026-09-11] `docs/plan/signals-paper-track` **SPT-5** closed (`06df9d8`) — caller-side exit wiring: on a non-HOLD `signal_exit.evaluate()` decision, `SignalTrackV1._close_position` takes the SELL
  fill at the observed mark via `PaperFillSimulator` (gap-through booked as-is, not clamped to the SL/target threshold), closes the row + writes `paper_exit_events`, and sends the new
  `build_signal_exit_message` Telegram exit message. `code-reviewer` and `greeks-analyst` independently flagged the same issue — the closing SELL leg must go through `PaperStore.record_trade`, not
  `record_signal_open_leg` (opening-leg-only, misleadingly generic) — fixed before commit. Next: SPT-6.
- [2026-09-11] `docs/plan/technical-debt` **DEBT-13** closed — `check_checkbox_consistency.py`'s `check_readme_pointers()` was blind to an epic row (`<epic>/` with `next: **ID**` pointing at a nested
  `<sub-story>/tasks.md`, no flat root `tasks.md`). Added `_resolve_pointer_task_file()`: flat file first, then a sorted glob fallback over `<epic>/**/tasks.md`. Cited ROLL-14/`strategy-rollout` repro
  was already stale (epic archived 2026-09-06) so no README correction was needed; verified via two new unit tests reconstructing the epic shape. Full `tests/unit/` green (3022 passed);
  `@code-reviewer` clean. Decision + rationale: `DECISIONS.md`.
- [2026-09-11] `docs/plan/technical-debt` **DEBT-15** closed — verified `commit_preflight.py`'s staged `ruff format --check` blocker (SWEEP-4, `2b85b84`) against `ruff-format-check-skipped-
  precommit-abort`: one post-remediation recurrence (S5.2c, `b33a43d`), none since across the dozens of sessions that followed. Like DEBT-12, the check is a real blocker and fired correctly each time
  cited (S5.2c, S5.3) — recurrence is a pre-stage-checklist cost, not hook failure. No protocol/model discussion opened. Decision + rationale: `DECISIONS.md`.
- [2026-09-11] `docs/plan/technical-debt` **DEBT-12** closed — verified `commit_preflight.py`'s staged md-line-length check (SWEEP-4, `2b85b84`) against `authored-md-prose-over-200-cap` (4
  post-remediation recurrences through 2026-09-10). Unlike DEBT-8/-9, the check is a real blocker and fired correctly each time (commits `5aa9ce6`, `b70f8fa` both aborted before landing) — recurrence
  is authoring-time cost, not hook failure. No protocol/model discussion opened; `reflow_md.py` (doc-format-migration epic) stands as the remediation. Decision + rationale: `DECISIONS.md`.
- [2026-09-11] `docs/plan/technical-debt` **DEBT-9** closed — verified `check_inline_full_suite.py` (warn-only since SWEEP-3, `e325e86`) did not stop `pytest-inlined-not-test-runner` (Count 17
  recurrences through 2026-09-11). Escalated to a protocol/model discussion per the DEBT-8/-9/ -10/-12 procedure; made the hook blocking (exit 2 + stderr), mirroring the DEBT-8 fix. Decision +
  rationale: `DECISIONS.md`.
- [2026-09-11] `docs/plan/technical-debt` **DEBT-8** closed — verified `check_repeat_read.py` (warn-only since SWEEP-2, `68683cb`) did not stop `reread-file-already-in-context` (34 recurrences through
  2026-09-11). Escalated to a protocol/model discussion per the DEBT-8/-9/ -10/-12 procedure; operator chose to make the hook blocking (exit 2 + stderr) over accepting it as model discipline.
  Decision + rationale: `DECISIONS.md`.
- [2026-09-11] Tooling: on-demand weekly feature-usage audit. `session-close` gains Step 4c — appends one JSON row per session to `session_audit.jsonl` (repo root, committed) via new
  `scripts/dev/session_audit_log.py` (`append_row`/`read_range`, frozen `SessionAuditRow` dataclass). New on-demand skill `.claude/skills/weekly-audit/SKILL.md` reads that log (never raw transcripts)
  to check for missed Claude Code features across recent sessions, drilling into a flagged session's transcript only when the aggregate is ambiguous. Deliberately on-demand, not cron/`/loop` — value
  unproven, cheapest version first. Tests: `test_session_audit_log.py` (3 cases). `code-reviewer`: 0 CRITICAL / 0 ERROR / 4 WARNING (missing JSON-parse error handling in `read_range`/CLI, no `main()`
  entry-point test, no blank-line edge-case test — deferred, all robustness/coverage gaps on a non-financial tooling path, no correctness impact on the happy path).
- [2026-09-11] signals-paper-track **SPT-3b** — new task split from SPT-5 (dependency ordering): SPT-4's spec hands `(entry, mark, now)` to `signal_exit.evaluate`, but that function was scoped to
  SPT-5 alongside the caller-side fill/close/Telegram wiring — a hard forward dependency SPT-4 couldn't satisfy standalone. Split confirmed with the operator before touching `tasks.md`/`stories.md`.
  `src/strategy/signal_exit.py` gains `SignalExitReason` (`TARGET`/`STOP_LOSS`/`TIME_EXIT`/reserved `TRAILING_STOP`), frozen `SignalExitDecision`, and pure `evaluate(entry, mark, now)` (priority:
  target > stop-loss > 15:00 IST square-off > hold; naive datetimes treated as IST, aware ones converted). SPT-5 trimmed to caller-side wiring only. Tests: `test_signal_exit.py` — 8 new cases incl.
  aware-datetime IST conversion. `code-reviewer`: 0 CRITICAL / 0 ERROR / 7 WARNING (6 line-length, 1 test-coverage gap — all fixed before commit). Full suite green (3447 passed, 2 skipped). Commit
  `c050de0`. Next: SPT-4.
- [2026-09-10] signals-paper-track **SPT-3** — entry executor. New `src/strategy/signal_exit.py` (`SL_PCT` / `TGT_PCT` / `RULESET_VERSION` / `derive_levels` — the constants half; SPT-5 adds
  `evaluate`) and `src/strategy/signal_track_v1.py` (`open_signal_paper_entry` async hook: `DailySignal` → `resolve_monthly_option` → own option-chain bid/ask fetch → `PaperFillSimulator` BUY fill →
  frozen `SignalPaperEntry` → Telegram entry message; `SignalTrackV1` `PaperStrategy` shell, tick left as a no-op for SPT-4). `PaperStore.record_signal_open_leg` added (returns the opening BUY
  `paper_trades.id`, which no existing store method exposed). `eod_pt_summary._render_table` promoted to `src/notifications/formatting.py::build_position_table` (public, `title=None` for the
  fence-embedded case) — `eod_pt_summary` repointed, behaviour-preserving. Tests: `test_signal_exit.py`, `test_signal_track_v1.py` (new); additions to `test_signal_store.py`, `test_formatting.py`,
  `test_escaping_guard.py` (L295 baseline — builder owns escaping, same shape as `morning_signal` L282). `code-reviewer`: 0 CRITICAL / 2 ERROR (both missing type hints — fixed) / 3 WARNING (deferred).
  Commit `6b0dada`. Next: SPT-4.
- [2026-09-10] Loose-ends cleanup after SPT-2. Filed **BUG-045** (`6677f13`) — `src/notifications/formatting.py` position-health helpers pass `PositionFinding` `Optional` fields into
  `date.fromisoformat` / `format_option_label` / a `sorted` key with no narrowing; latent since 2026-09-03, surfaced because the mypy pre-commit hook (`^src/(client|paper)/`) follows imports into
  `formatting.py` and SPT-2 was the first `src/paper` commit since — blocks every `src/paper`/`src/client` commit's mypy gate (SPT-2 used `SKIP=mypy`). Filed **BUG-046** (`6677f13`) — 3
  `test_escaping_guard.py` failures from `scripts/morning_signal.py` `.send()` drift (L282 new, L245 stale baseline) across the 2026-09-10 signal-cost commits. `chore` (`f8685f6`) gitignored
  `docs/council/pending/` + dropped the stale SPT-1 prompt. `docs(technical-debt)` (`06f43a5`) committed the pre-existing uncommitted DEBT-16 + `suggestions.md` session-close maintenance.
- [2026-09-10] signals-paper-track SPT-2 closed (`58e0b08`) — `SignalPaperEntry` / `SignalMark` frozen Pydantic models + `paper_signal_entries` / `paper_signal_marks` tables (non-STRICT, per
  `schema.md`) added to `PaperStore._SCHEMA`, plus `open_signal_entry` / `get_open_signal_entry` / `record_mark` / `get_marks` / `close_signal_entry` / `get_entries` / `cumulative_pnl`. Position rides
  `paper_trades` as `paper_signal_track_v1` (`STRATEGY_SIGNAL_TRACK` constant, `quantity = LOT_SIZE`). `close_signal_entry` does the state-flip + `paper_exit_events` insert in one transaction
  (code-review: no half-closed state); `cumulative_pnl` pairs closed entries to SELL rows in chronological order (safe under the one-position-at-a-time guard) with a length-mismatch raise.
  code-reviewer 3 CRITICAL + 3 ERROR → 5 fixed, STRICT-table finding rejected (`schema.md` is the DDL source and has none; siblings `paper_trades` / `paper_exit_events` are non-STRICT). 12 new tests.
  Next: SPT-3 (SPT-2a was closed as a no-op on 2026-09-10 — see below).
- [2026-09-10] Planning — signals-paper-track SPT-6/7 rewritten + follow-up story `signals-entrypoint-consolidation` created. A Plan-agent review of the entrypoint topology (asked by Animesh: too many
  overlapping signal crons, logic will diverge) concluded the paper track adds **zero** new crons — SPT-6 becomes a guarded paper-entry tail-call inside `morning_signal` (not a 09:35 cron),
  `signal_paper_entry.py` a manual backfill tool, SPT-7 a manual report. `src/strategy/signal_exit.py` becomes the single SL/target-constants + evaluator home (created in SPT-3, extended in SPT-5);
  all `65` literals → `paper.constants.LOT_SIZE`. Deferred to the new story: `DailySignal.is_actionable` predicate, `market_calendar.guard_trading_day()`, merge `record_signal_outcome` +
  `signal_report` → one 16:00 `signal_eod` (2 crons → 1). New story is blocked until `signals-paper-track/` is archived. Docs-only: `signals-paper-track/{prompt,tasks,stories}.md`,
  `signals-entrypoint-consolidation/{prompt,tasks,stories}.md`, `TODOS.md`, `docs/plan/README.md`.
- [2026-09-10] Ops fix (`a8e74f3`) — 16:00 `record_signal_outcome --auto` cron crashed with `IndexError: No item with that key` on `row["cost_usd"]`: SCT-2 (`c7efe54`, deployed 13:34) added the
  `signal_responses` cost columns via `init_db`'s idempotent ALTER loop, but `record_signal_outcome` / `signal_report` construct `SignalStore` and never call `init_db()`, so the ALTERs never hit the
  live DB (yesterday's manual `ALTER` covered only `daily_signals.entry_premium`). Fixed live DB with the three `ALTER TABLE signal_responses` columns, backfilled today's outcome + report (both
  green), and added `store.init_db()` after construction in both scripts (mirrors `morning_signal.py:205`). Today's 3 response rows keep NULL cost — this morning's run predates the code; self-heals
  2026-09-11.
- [2026-09-10] signals-cost-tracking SCT-4 closed (`b70f8fa`) — docs: added a `signal_responses` row to `DB_REGISTRY.md` (it was never registered when `signals/` shipped — an add, not the spec's
  "edit"; the sibling `signal_inputs` / `daily_signals` / `signal_outcomes` tables are still unregistered), extended the `CONTEXT.md` `src/signals/` bullet with cost capture, added the 2026-09-09
  inline-`usage.include`-over-`/generation` decision to `DECISIONS.md`. Trustworthy-from date: 2026-09-11 (first 09:30 run after SCT-2 `c7efe54` deployed 2026-09-10 13:34 IST). Story complete — `git
  mv` to `docs/archive/plan/signals-cost-tracking/`, Feature Backlog item removed, `docs/plan/README.md` collapsed to archived pointer.
- [2026-09-10] signals-cost-tracking SCT-3 closed (`1078397`) — `morning_signal.run()` sums `cost_usd` over today's priced responses and threads `(day_cost, n_priced)` into
  `_format_signal_notification`, which appends an escaped `💵 LLM cost: $X.XXXX (N calls)` line to all three variants (consensus / no-consensus / pipeline-failure). New local `_format_usd` 4dp-USD
  helper; `morning_signal.llm_cost` log line. Next: SCT-4 (docs).
- [2026-09-10] signals-cost-tracking SCT-2 closed (`c7efe54`) — `signal_responses` gains `prompt_tokens` / `completion_tokens` / `cost_usd` (nullable, idempotent ALTER loop in `init_db`);
  `record_response` persists from `response.usage`, `_response_from_row` rebuilds `SignalUsage` when `cost_usd` present. New `SignalStore.get_signal_cost(from_date, to_date)` → `{total_usd,
  call_count, by_provider}` via one grouped SQL statement. 6 new tests, full suite 3402 passed. code-reviewer CRITICAL/ERROR were on pre-existing `suggestions.md` / dirty submodule (not staged); two
  store.py WARNINGs deferred as spec-mandated. Next: SCT-3 (morning Telegram cost line).
- [2026-09-10] signals-cost-tracking SCT-1 closed (`a519714`) — new frozen `SignalUsage` model (`prompt_tokens` / `completion_tokens` / `cost_usd: Decimal`) + optional `usage` field on
  `SignalResponse`; GPT-4o / Grok / Gemini OpenRouter paths send `"usage": {"include": true}` and parse the envelope via one shared `_usage_from_envelope` helper in `providers/__init__.py` (returns
  `None` on absent/malformed/non-dict usage — never fails the signal). mock + Gemini Google-SDK path emit `usage=None`. Antigravity-implemented; code-reviewer CRITICAL (non-dict `AttributeError`) +
  ERROR (untyped param) resolved, test-runner 3396 passed. Next: SCT-2 (persist + `get_signal_cost` aggregate).
- [2026-09-10] BUG-043 logged (`abc2d60`) — "Net P&L" in strategy close notifications has no stable meaning (inception-cumulative for IC v1/v2, cycle-only for collar, absent for CSP). B043.1 closed
  (`74bf1c4`): new `src/paper/cycle_pnl.py` (`reconstruct_cycles` / `get_last_cycle_realized_pnl`) + `scripts/dev/cycle_pnl_report.py` (per-cycle P&L / exit reason / days-in-trade for IC-all / cc / pp
  / collar). 10 tests. code-reviewer CRITICAL+ERROR resolved, greeks-analyst clean. Next: B043.2 — standardise the five close paths to `Cycle P&L` + `Since inception`.
- [2026-09-10] cycle_pnl_report follow-up (`2d7412e`) — `Cycle` gains `entry_credit_per_unit` / `exit_cost_per_unit` / `decay_pct`; report shows the three as columns. code-reviewer clean, test-runner
  3382 passed.
- [2026-09-09] signals-paper-track SPT-1 closed (`636c190`) — council q17 ruled (`docs/archive/council/strategy/2026-09-09_signals-paper-track-execution-layer.md`). Docs-only: `DECISIONS.md` §"Signals
  Paper Track — Execution Layer" (module boundary A, pure `src/strategy/signal_exit.py`, fixed SL −30 % / target +50 %, Phase 1 fixed-only + `TRAILING_STOP` reserved, 30 s per-strategy cadence,
  two-tier recalibration, G1–G9 go-live gate, auto-execute 1-lot pilot); new `docs/plan/signals-paper-track/schema.md` (`paper_signal_entries` + `paper_signal_marks`, position stays on `paper_trades`
  as `paper_signal_track_v1`); `stories.md` / `tasks.md` rewritten SPT-2..SPT-8 concrete + added SPT-2a (`≤ 7-DTE` roll in `resolve_monthly_option`); `prompt.md` scope guard + task overview;
  `council-question.md` marked closed; `docs/plan/README.md` row → in progress; `git mv` the council file to `docs/archive/council/strategy/`. Deltas from our draft: cadence 30 s not 90 s, gate N≥50
  not 40, live pilot auto-execute not manual. Next: SPT-2.
- [2026-09-09] signals S6 (`566e1b0`) — story closed and archived. Docs-only: `CONTEXT.md` `src/signals/` bullet rewritten to "shipped" + crons-live, signals crons removed from "What Does NOT Exist
  Yet"; `DECISIONS.md` close bullet (story archived + `phase` column semantics); `docs/plan/README.md` entry collapsed to a `✅ Archived` pointer; `git mv docs/plan/signals/ →
  docs/archive/plan/signals/`; backlog item deleted here, appended to `TODOS_ARCHIVE.md`. The `signals/` story (S1.1–S6) is complete; next signals work is `signals-paper-track` SPT-1. Also this
  session: fixed a S5.6 deploy gap — the `entry_premium` column was added to `daily_signals` in code (`5bebf92`) but never `ALTER`-ed onto the live DB, so the 16:00 `record_signal_outcome` cron failed
  with `IndexError`; `ALTER TABLE daily_signals ADD COLUMN entry_premium TEXT` run against `data/portfolio/portfolio.sqlite`, read + write paths verified.
- [2026-09-09] signals S5.6 filed — the 09:15 "Entry band" is an LLM guess (`_consensus_entry_band`), and `record_signal_outcome --auto` books P&L against it while fetching the exit LTP on the
  *weekly* option though the strike was picked on the *monthly* chain. S5.6 (before S6): fetch + persist the real option LTP at 09:15 as the entry premium, use it for exit P&L, pin strike/entry/exit
  to one expiry (weekly vs monthly = a pre-code decision). Spec in `signals_tasks.md` / `signals_stories.md`. Docs-only.
- [2026-09-09] signals S5.5b — NSE-holiday early-exit guard added to `scripts/morning_signal.py` (`run()`) and `scripts/signal_eod.py` (`main()`): `if not is_trading_day(market_today()):
  logger.info(...); return`, mirroring `scripts/pipeline/upstox_chain_snapshot.py`. No new tests (matches existing cron pattern); `test_escaping_guard.py` baseline line numbers bumped (morning_signal
  215→218, signal_report 313→314) for the shifted `.send()` call sites. Full suite 3354 green. code-reviewer: 0 CRITICAL/ERROR, 1 WARNING (double `market_today()` call — fixed). — SHA `5466b9d`
- [2026-09-09] signals S5.5d — `scripts/signal_eod.py` now pushes the full 5-section performance report to Telegram on every run (was `print()`-only). Local `_format_report_message` wraps the body in
  a MarkdownV2 fenced block with fence-safe escaping (backslash + backtick only — `escape_markdown` renders backslashes literally inside a fence); non-fatal `_notify` mirrors
  `record_signal_outcome._notify`, sent after `print()` and downstream of the empty-window early return. 4 tests + escaping-guard baseline entry. code-reviewer: 0 CRITICAL/ERROR, 3 WARNING (1 fixed, 2
  pre-existing/not in scope). — SHA `51d3e59`
- [2026-09-09] signals S5.5a — `signal_eod.py` now posts the daily outcome to Telegram on its 16:00 run (S5.5c vertical layout): executed / not-taken (would-be P&L derived in the formatter, no
  `SignalOutcome` change) / NO_TRADE / close-only fallback. Local `_format_outcome_notification` owns MarkdownV2 escaping; `_notify` send is non-fatal (guards `build_notifier() is None` + swallows
  formatter/send errors post-write). 4 render tests + escaping-guard baseline entry. code-reviewer: 0 CRITICAL/ERROR, 2 WARNING both fixed. — SHA `ce59529`
- [2026-09-09] signals S5.5c — reformatted `morning_signal.py` 09:15 Telegram message to the agreed vertical layout (CONSENSUS / NO CONSENSUS / PIPELINE FAILED); `_format_signal_notification` now owns
  its MarkdownV2 escaping (caller sends without re-wrapping), entry band = mean of agreeing models' quoted bands. 3 formatter render tests + escaping-guard baseline entry.
- [2026-09-09] signals — restructured `signals_tasks.md` into "Remaining work — in order" (S5.5c → S5.5a → S5.5d → S5.5b → S6 + summary table) and "Completed". 4ec58c6.
- [2026-09-09] signals S5.5a design — revived (was superseded → SPT-5) as the Phase-1 interim 16:00 outcome message; `signal_eod.py` currently sends nothing. Restyled messages 6–8 in
  `scratch/2026-09-08_signal_telegram_messages.py` to the S5.5c vertical layout (executed / not-taken with would-be P&L / NO_TRADE); would-be P&L derived in the formatter, no `SignalOutcome` change.
  Docs: signals_tasks.md, signals_stories.md §S5.5a, signals-paper-track/stories.md SPT-5/SPT-8, DECISIONS.md, TODOS.md. Implementation pending.
- [2026-09-09] signals S5.5 — rollout state recorded (discussion, no code): all 3 crons already live on the Mac host, so the cron-enablement runbook was dropped; rollout phase = Phase 1
  `openrouter_only`. Telegram scope settled — 09:15 message → S5.5c, `signal_report` 16:35 digest (full report, every weekday, MarkdownV2 fenced block) → new box S5.5d. Touched signals_tasks.md,
  signals_stories.md, DECISIONS.md, TODOS.md. No SHA.
- [2026-09-08] BUG-041 B041.5/B041.6 — closed. No new code: slug/env-override and error-body capture tests landed across B041.1–B041.3. Verified at close: `pytest tests/unit/signals/` green (115),
  live `morning_signal` 16:37 run 3/3 providers respond, zero `provider_error`. `bugs.md` + `task.md` sections moved to `docs/archive/bugs/`. — SHA `4b5aed2`
- [2026-09-08] BUG-041 B041.1/B041.2 — OpenRouter model slugs made env-configurable (`SIGNAL_MODEL_{GROK,GPT4O,GEMINI}`) threaded through `factory._construct`; `model` param on grok/gemini providers.
  Confirmed grok-3/gemini-2.0-flash retired on OpenRouter; gemini 400 is the slug not `response_format`. `.env.example` gitignored — doc edit on disk only. Suite green (3331), code-reviewer clean (1
  deferred WARNING). B041.3–B041.6 remain. — SHA `f1fad55`
- [2026-09-08] BUG-041 B041.2b — provider payloads: `max_tokens` 512→2048, default `timeout` 30→60s so the reasoning models `~x-ai/grok-latest` / `~openai/gpt-latest` don't time out or return null
  content. Probe: `scratch/2026-09-08_signal_model_probe.py`. Live `morning_signal` now gets 3/3 responses. Suite green (3334), code-reviewer 0 ERROR/CRITICAL. — SHA `9a2e9d3`
- [2026-09-08] signals S5.4 — `scripts/signal_eod.py` on-demand performance report: aggregates `get_all_outcomes` over a `--from`/`--to`/`--phase` window into OVERALL (win rate, realised EV,
  deterministic md5 coin-flip baseline), per-model direction accuracy (09:10 snapshot spot as open proxy), confidence calibration, NO_TRADE move check, phase breakdown. No unit tests (per S5.4 spec).
  — SHA: <pending>
- [2026-09-08] signals S5.3 — `scripts/signal_eod.py` 03:00 PM outcome recorder: reads the day's `DailySignal`, captures entry/exit premium (manual flags or `--auto` weekly-expiry BOD lookup + live
  LTP), writes one `SignalOutcome` row; NO_TRADE / non-executed signals still logged for direction accuracy. `phase` from `SIGNAL_PHASE` env / key-set. No unit tests (per S5.3 spec). — a387349
- [2026-09-08] signals S5.2 — `scripts/morning_signal.py` 09:15 AM cron: pure wiring over `assemble_market_snapshot` → `build_providers` → `asyncio.gather` fan-out (return_exceptions) →
  `SignalAggregator.aggregate` → `SignalStore` writes (init_db/record_snapshot/response/signal via to_thread) → guarded `build_notifier` send + end-of-run structured JSON log. No unit tests
  (integration-only). SHA: e299a6b
- [2026-09-08] signals S5.2c — `src/signals/snapshot.py` `assemble_market_snapshot`: the 7 non-S5.2a MarketSnapshot fields (nifty_spot/india_vix via get_ltp, prev close/high/low via get_ohlc "1d",
  monthly_expiry via InstrumentLookup, option_chain→OptionChainSummary derivation, vix_5d_trend over get_recent_snapshots) + gift/usd_inr/fii delegated to market_inputs via asyncio.gather; no neutral
  fallbacks (DataFetchError). 4 offline tests. SHA: b33a43d
- [2026-09-08] signals S5.2b — added `BrokerClient.get_ohlc(instruments, interval="1d")` to the protocol
  + all impls (upstox_market async wrapper over get_ohlc_sync, upstox_live delegate, mock_client canned dict via set_ohlc) and `SignalStore.get_recent_snapshots(n)` (newest-first, n<=0 guard) + 6
    tests. Prereqs for the S5.2c snapshot assembler. SKIP=mypy (7 pre-existing upstox_live.py errors). SHA: e1b5a0a
- [2026-09-08] signals S5.2b split (docs-only) — the old combined S5.2b (get_ohlc/get_recent_snapshots prereqs + snapshot.py assembler) split into S5.2b (client `get_ohlc` across protocol + all 3
  impls + `SignalStore.get_recent_snapshots` + tests) and S5.2c (`snapshot.py` assemble_market_snapshot), one commit each per Animesh. Touched signals_tasks.md, signals_stories.md,
  docs/plan/README.md. No SHA.
- [2026-09-08] signals S5.2a — built src/signals/market_inputs.py: fetch_gift_nifty (GLOBAL_INDEX|SGX NIFTY LTP), fetch_usd_inr (nearest-monthly NCD_FO USDINR future via InstrumentLookup),
  fetch_fii_data (NSE fiidiiTradeReact cash-market net → FIIData); each raises DataFetchError on failure, no fallbacks + 9 offline tests. SHA: <pending>
- [2026-09-07] signals/ S5.2 split (docs-only) — S5.2 needs gift_nifty / fii / usd_inr and the repo has no fetcher; Animesh's call: probe Upstox/Dhan/Nuvama APIs rather than scrape NSE or hard-code
  defaults. Added S5.2a (persistent source-discovery spike `scratch/2026-09-07_signal_input_sources.py` + `src/signals/market_inputs.py`
  + offline tests) and S5.2b (`src/signals/snapshot.py` assemble_market_snapshot); S5.2 rewritten as wiring-only. Touched signals_tasks.md, signals_stories.md, docs/plan/README.md. No SHA (uncommitted
    at log time).
- [2026-09-07] signals/ S5.1 — added config/signals.toml (thresholds + grok/gpt4o/gemini provider sub-tables) and extended .env.example with signals pipeline block (OPENROUTER/XAI/GOOGLE_AI keys,
  SIGNAL_PROVIDERS, SIGNAL_MIN_CONFIDENCE + Phase 1/2 token checklist; .env.example local-only). SHA: 80edf53
- [2026-09-07] signals/ S4.1 — added build_providers factory: canonical-order (grok,gpt4o,gemini) env-driven selection, UPSTOX_ENV=test + empty-result fallback to MockSignalProvider, missing key →
  WARN+skip + 7 tests. SHA: 417cb5f
- [2026-09-07] signals/ S3.4 — added GeminiSignalProvider: Phase 1 OpenRouter google/gemini-2.0-flash HTTP shim, Phase 2 guarded google-generativeai SDK via asyncio.to_thread + wait_for timeout;
  failures → DataFetchError + 9 tests. SHA: 41254dc
- [2026-09-07] signals/ S3.3 — added GrokSignalProvider: use_openrouter flag picks OpenRouter x-ai/grok-3 (P1) vs xAI direct grok-3 +search (P2); reuses gpt4o POST+parse + 8 tests. SHA: 2b04546
- [2026-09-07] signals/ S3.2 — added GPT4oSignalProvider: aiohttp POST to OpenRouter chat completions, parse JSON → SignalResponse, HTTP/timeout/parse failures → DataFetchError + 7 tests. SHA: 12ba97a
- [2026-09-07] signals/ S3.1 — added MockSignalProvider: deterministic Protocol-compliant provider (fixed direction/confidence/strike_offset), never raises + 5 tests. SHA: 1d5fbbd
- [2026-09-07] signals/ S2.2 — added SignalStore read methods: get_snapshot (model_validate_json), get_responses, get_signal (rebuilds responses from signal_responses), get_outcome, get_all_outcomes
  (optional from_date/to_date/phase via parameterised WHERE) + 8 tests. SHA: fc4a8d4
- [2026-09-07] signals/ S2.1 — added SignalStore: init_db (4 tables + 2 indexes, idempotent) + write methods record_snapshot/response/signal/outcome with model→schema column mapping, Decimal→TEXT,
  INSERT OR IGNORE for responses + 9 tests. SHA: 2aa5979
- [2026-09-07] signals/ S1.3 — added SignalAggregator: strike/confidence validation, direction voting, Decimal confidence gate, modal strike with ATM tie-break + 10 tests. SHA: 4c5e7e6
- [2026-09-07] signals/ S1.2 — added SignalProvider protocol and build_prompt pure function with gpt4o, grok, and gemini suffixes + tests. SHA: 6ea9028
- [2026-09-07] signals/ S1.1 — added signals data models, Direction, MarketSnapshot, SignalResponse, DailySignal, SignalOutcome. SHA: 8d295c6
- [2026-09-07] `signals/` unblocked — moved out of `docs/plan/README.md` "Blocked / Later Stories" to an active parallel track (Feature Backlog #8, was #10). Verified zero `src/backtest/` dependency:
  self-contained `src/signals/` package, own SQLite tables, S5.4 baseline is a coin flip not shared stats. Runs alongside `backtest-engine`. `OPENROUTER_API_KEY` gates only the live S5.2 cron.
  `signals-eval-core/` stays blocked (it's mechanical-strategy backtest validation, not LLM-signal work). DECISIONS.md entry added under §Strategy & Research Decisions. Next: S1.1.
- [2026-09-07] `ic-yearly-expiry-fix/` WG-1 shipped — `IronCondorV1.check_signals` now emits `ic_nifty_v1.leg_greeks` (INFO) per short leg with tick-time delta/abs_delta/gamma/theta/vega/iv/ltp +
  warn/stop thresholds, so the Greeks behind a DELTA_WARN/DELTA_STOP decision are recoverable from `logs/` (the 2026-07-08 0.25→0.09 discrepancy had no such record). Weekly Parquet bucket — WG-1's
  primary fix — already landed in `a38e53f`. Story folder complete; removed from Feature Backlog. 2 tests.
- [2026-09-07] `eod-pt-summary/` PT-3 — docs close. CONTEXT.md (`792fa79`) / DECISIONS.md §P&L & Reporting / TODOS.md log lines already landed piecemeal with PT-1/PT-2; this pass filled the PT-2
  closing SHA (`77dc160`) into `tasks.md` + the PT-2 log line, refreshed the `docs/plan/README.md` Active-Stories row to ✅ Shipped, and marked `scratch/2026-08-13_eod_pt_summary.py` SUPERSEDED. Epic
  `eod-pt-summary/` complete (PT-1..PT-3); folder archived to `docs/archive/plan/eod-pt-summary/`. Docs-only. SHA: dac18ea
- [2026-09-07] `eod-pt-summary/` PT-2 — promoted `scratch/2026-08-13_eod_pt_summary.py` to `src/reporting/eod_pt_summary.py` (new package) + thin cron `scripts/eod_pt_summary.py`, 17 tests in
  `tests/unit/reporting/test_eod_pt_summary.py`. Function boundaries unchanged from the validated prototype; `escape_markdown` swapped to `src/notifications/markdown.py`, local `LtpProvider` Protocol
  for the broker surface, no-`LOT_SIZE` P&L regression-tested. Coordination question resolved with Animesh: runs **alongside** `scripts/eod_summary.py`, not a replacement (DECISIONS.md §P&L &
  Reporting). `code-reviewer`: 1 ERROR + 5 WARNING all fixed. Next: PT-3 (docs close). SHA: 77dc160
- [2026-09-06] `eod-pt-summary/` PT-1 — captured the confirmed 3-message Telegram-split spec (open positions / Closed Today / Strategy P&L·Ann.% on Margin) in `stories.md` as the reference for PT-2:
  full column/format derivation, CE/PE-last instrument label, the 3-Track + `STRATEGY_OVERLAY` strategy_name traps, no-`LOT_SIZE` P&L formula, MarkdownV2 fence + `_PART_EMOJI` map, non-fatal send
  contract, CLI surface. Fixed a drift in the draft spec (message 3 is open-positions-only, not "open and/or closed"). Docs-only. SHA: d1ae760
- [2026-09-06] `telegram-ic-comparison-formatting/` — archived as superseded → `docs/archive/plan/telegram-ic-comparison-formatting/`. TGFMT-1 stays shipped history (`a69d817`); TGFMT-2..9 fully
  absorbed by the now-archived `telegram-markdown-migration/` (Legs row + Bkd/Flt split landed as ROLL-2c `a2fbe31`). `docs/plan/README.md` row → pointer; detail in `TODOS_ARCHIVE.md`. Docs-only.
- [2026-09-06] ROLL-5 — docs close: `telegram-markdown-migration/` epic complete and archived → `docs/archive/plan/telegram-markdown-migration/`. All three sub-stories done: `backbone/` (`57c1c3c`),
  `formatting-rules/` (`75cc123`), `strategy-rollout/` (ROLL-0..17). CONTEXT.md / DECISIONS.md / `docs/plan/README.md` updated; Feature Backlog item removed. Docs-only. SHA: b55773d
- [2026-09-06] ROLL-17 — unify IC entry v1/v2 onto `src/notifications/ic_entry_message.py` fenced-table renderer; v2's bare `{strike}PE` label violation fixed; `ivr`/`dte`/`spot`/`net_credit` made
  required per `@code-reviewer` — 26527c2
- [2026-09-06] ROLL-17 workshop — closed all design decisions for the IC entry v1/v2 unification: fenced `build_leg_table()` renderer, `[S]`/`[B]` badge, strike+PE/CE identity, entry price on all
  legs, `IVR DTE Nifty Exp` kv row, `Net credit: X/lot x65 = Y`, `IC v1/v2 Entry` headline. Spec in `strategy-rollout/stories.md`; ref `scratch/2026-09-06_ic_entry_confirmation_format.py`. Docs +
  scratch only — implementation is a follow-on session.
- [2026-09-06] ROLL-16 — migrate production proxy delta CRITICAL alert to MarkdownV2 (shared `build_proxy_critical_alert`); guard-integrity follow-up — e5efb8f, 35c17e5
- [2026-09-06] audit finding ROLL-15 — split base-expiry Telegram alert into summary + logged commands — 3855f8f
- [2026-09-08] BUG-040 B040.2–B040.5 — signals prev-session OHLC now sourced from the Upstox v2 historical-candle day endpoint (`get_historical_candles_sync` in `upstox_market.py`, delegated from
  `upstox_live.py`); `_fetch_prev_ohlc` rewritten with a strict-before-`trade_date` guard. Antigravity handoff `50a5ce4` landed red (mangled signature, bypassed review); Claude fixup corrected it +
  cleared 2 `@code-reviewer` ERRORs. 3322 tests green. B040.6 manual `morning_signal` run blocked on live host. SHA: `680778b`
- [2026-09-08] BUG-040 follow-up — `scripts/morning_signal.py` now logs one structured line per LLM response (`morning_signal.provider_response`), a `providers_dispatched` count, and a
  `no_valid_responses` warning; new `tests/unit/scripts/test_morning_signal.py` (first tests for that script). Live `morning_signal` run on 2026-09-08 verified the BUG-040 fix end-to-end (gpt4o
  responded NEUTRAL/conf 3 → NO_TRADE; prev-OHLC sourced correctly from historical-candle). SHA: `8459604`

- [2026-09-08] BUG-041 B041.3 — all three OpenRouter signal providers now read the response body before the status check and put its text (≤500 chars) into the `DataFetchError`, so
  `morning_signal.provider_error` names the real OpenRouter reason instead of a bare `HTTP 404`/`400`; non-JSON envelope and `UnicodeDecodeError` also surface as `DataFetchError`. Per-provider tests
  for error-body capture + non-JSON envelope; `@code-reviewer` 0 CRITICAL/ERROR, WARNINGs resolved. 3340 tests green. SHA: `5bdd18c`

- [2026-09-08] BUG-041 B041.4 — `SIGNAL_MIN_CONFIDENCE` / `SIGNAL_CONSENSUS_REQUIRED` now wired through new `src/signals/factory.build_aggregator(env)` (shared `_int_env` helper, blank/invalid →
  default + warning) into `SignalAggregator`; `scripts/morning_signal.py` calls it instead of a bare `SignalAggregator()`. 3 factory tests + mock-target rename. 3343 tests green; `@code-reviewer` 0
  CRITICAL/ERROR. SHA: `1e36c32`

Full forensic log (SHAs, bug numbers, root-cause detail) moved to [docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md) — most recently during the 2026-08-26 reorg (everything from 2026-08-01
through 2026-08-26, plus item 29's inline design history above). Add new entries there going forward, or start a fresh dated section here if this file's Session Log grows large again.

- **2026-09-07** — `docs/plan/signals/` S1.1a shipped: `FIIData` redefined from index-F&O positioning (`net_futures_cr`/`net_options_cr` — unreachable per S5.2a spike) to cash-market net flows
  (`fii_cash_net_cr`/`dii_cash_net_cr`, NSE `fiidiiTradeReact`). `src/signals/models.py`
  + `prompt.py` + 8 signals test files. Split out of S5.2a per Animesh. 77 signals tests green. SHA: `<pending>`. Next: S5.2b (`snapshot.py`).
- **2026-09-06** — `docs/plan/telegram-markdown-migration/strategy-rollout/` ROLL-14 shipped: 3-track overlay entry bootstrap notification migrated to MarkdownV2 kv format. SHA: `129d54e`. Next:
  ROLL-15.
- **2026-09-06** — `docs/plan/telegram-markdown-migration/strategy-rollout/` ROLL-13 shipped: 3-track base entry notification migrated to MarkdownV2 kv format. SHA: `7adf484`. Next: ROLL-14.
- **2026-09-02** — `docs/plan/token-efficiency/fixed-overhead/` FIX-3: `session-close` now runs as a fresh `general-purpose` subagent reading the transcript by path, never a `fork` clone. Measured
  ~55% drop (116,375 → 52,523 tokens) on a matched session; fork's median cost across 9 sessions was ~254K. SHA: `03d991f`.
- **2026-09-03** — `docs/plan/token-efficiency/fixed-overhead/` FIX-4 (closes the story): `scripts/dev/graph_snippet.py` wraps `get_code_snippet` to strip the unused `fp`/`sp`/`bt` fields — ~244
  tok/call (−20%), ~730–2,200 tok/code-session. Rule 0 points at it. Upstream compact-mode issue owed (agent classifier-blocked from filing). SHA: `1b64d4a`.
- **2026-09-03** — `docs/plan/token-efficiency/suggestions-sweep/` SWEEP-1: clustered all 40 `suggestions.md` rows into 7 groups (6 rows added since story authoring folded in) with a fix / enforce /
  accept outcome each — 23 land a structural fix or hook/preflight enforce, 17 accepted with a reason. Cluster map in the SWEEP-1 As-built; ownership matches the SWEEP-2..SWEEP-7 split. Docs-only.
  SHA: `622465c`.
- **2026-09-03** — `docs/plan/token-efficiency/suggestions-sweep/` SWEEP-2: two warn-only `PreToolUse` hooks — `check_repeat_read.py` (2nd `Read` of an unedited path) and `check_wide_grep.py`
  (unscoped `grep`/`sed`/`awk` over an >800-line file / unfiltered recursive grep), 56 tests. Rule 0 + Rule 1 pointer lines in `CLAUDE.md`/`AGENTS.md`; two fix-by-text lines in `/work`. Cluster-1's 12
  rows closed. SHA: `68683cb`.
- **2026-09-03** — `docs/plan/token-efficiency/suggestions-sweep/` SWEEP-3: warn-only `PreToolUse(Bash)` hook `check_inline_full_suite.py` nudges `@test-runner` for a bare main-session `pytest
  tests/unit/` run, 12 tests. `test-runner` AutoTrigger cadence amended to "once per task before `code-reviewer` / the commit — not per-edit" in `CLAUDE.md`/`AGENTS.md`/`session-close`. Cluster-2's 2
  rows closed. SHA: `e325e86`.
- **2026-09-03** — `docs/plan/token-efficiency/suggestions-sweep/` SWEEP-4: `scripts/dev/commit_preflight.py` — CLI the `commit` skill runs (Step 1b) against the staged set: staged-index vs.
  `--expect` (warn), `ruff format --check` + md-line-length on staged files (blockers), next-marker incl. prose forms + SHA-placeholder (warn), 20 tests. `<pending>` sanctioned as the ticked-box
  interim SHA (backfilled next commit, no swap-only commit); `check_checkbox_consistency.py` + `docs/plan/README.md` §Task-line format updated to match. Cluster-3's 12 rows closed (8 enforce, 3 fix, 3
  accept). SHA: `<pending>`.
- **2026-09-03** — `docs/plan/token-efficiency/suggestions-sweep/` SWEEP-5: new **Tool-call param hygiene** section in `CLAUDE.md` + `AGENTS.md` (after AutoTrigger Rules) + a Rule 0 tool-list line —
  documents the `codebase-memory-mcp` `project=` / `index_repository` `repo_path=` first-call rule, the `AskUserQuestion` plain-array / no-`preview` rule, and the "never `ScheduleWakeup`-poll a
  spawned subagent" rule. Cluster-4's 3 rows closed (enforce-by-doc). Docs-only, no tests. SHA: `2ae951c`.
- **2026-09-03** — `docs/plan/token-efficiency/suggestions-sweep/` SWEEP-6: shell + subagent-orchestration + protocol-discipline text fixes. `CLAUDE.md` / `AGENTS.md` gain a **Shell mechanics** para
  (Rule 1), a consolidated plan-gate paragraph (Step 3), tightened `CONTEXT.md ✓` / scope wording (Step 1), and a new **Step 3c — Before writing code** (spec pre-step + parallel-subagent git rule);
  `handoff-antigravity` skill (+ `.agents/` mirror) gains a routing-settled callout; `md-organize` Step 7 gains a mirror-path grep line. Clusters 5 / 6 / 7 closed — 4 fix-by-text, 7 accept. Docs-only,
  no tests. Backfilled SWEEP-4 SHA `2b85b84` and SWEEP-5 SHA `2ae951c` on the same commit. SHA: `<pending>`.
- **2026-09-03** — `docs/plan/token-efficiency/suggestions-sweep/` SWEEP-7 (closes the story and the epic): `session-close` Step 4b gains a drain step — a `suggestions.md` slug at `Count >= 5` retires
  from the active table to a `standalone-actionable` `DEBT-*` line (remediation exists) or an "Accepted / won't-fix" section (pure judgement). Seeded DEBT-8.. DEBT-12 for the five over-threshold slugs
  (`reread-file-already-in-context` 23, `pytest-inlined-not-test-runner` 9, `wide-grep-dump-then-page` 7, `sha-recorded-via-second-commit` 6, `authored-md-prose-over-200-cap` 5); removed all five from
  `suggestions.md`. Backfilled SWEEP-6 SHA `938d929`. Docs-only. SHA: `2d896a9`.
- **2026-09-03** — `token-efficiency` epic archived → `docs/archive/plan/token-efficiency/` (all three stories shipped; closing SHA `2d896a9`). Backfilled the SWEEP-7 SHA, repointed the
  `graph_snippet.py` + `portfolio`/`client`/`notifications` `NOTES.md` references at the archive path, collapsed the `docs/plan/README.md` entry. See `docs/archive/TODOS_ARCHIVE.md` 2026-09-03. Open
  follow-ups: DEBT-8..DEBT-12.

### 2026-09-14
- **NSE 2026 holiday YAML corrected** (`c300769`). `src/market_calendar/data/nse_2026.yaml` had wrong dates (Ganesh Chaturthi listed 09-17 instead of 09-14, plus several other mismatches vs. NSE's
  published calendar) — `guard_trading_day()`'s fail-open lookup found 09-14 absent from the holiday set and let `morning_signal` fire a consensus signal on today's actual market holiday. Rebuilt the
  full list from `nseindia.com/resources/exchange-communication-holidays`; replaced `test_independence_day_is_holiday` (asserted a Saturday, already a non-trading day, was in the set — an artifact of
  the old wrong data) with `test_ganesh_chaturthi_is_holiday`. Root cause: annual-only manual refresh with no staleness alert — worth a follow-up if this recurs.

### 2026-09-10
- **SPT-2a closed as a no-op** (docs-only). Antigravity handoff surfaced that `get_expiry_candidates(preference=["monthly"])` already enforces a `dte >= 14` floor, so `resolve_monthly_option` never
  returns a `≤ 13-DTE` contract — the next-month roll SPT-2a asked for already happens at 14 DTE, consistent with `snapshot.py` / overlays / IC. A `≤ 7` hold would need a floor bypass + a
  `snapshot.py` realignment; operator (Animesh) kept the 14-DTE roll. WIP reverted, no code change. `DECISIONS.md` follow-up note added; `tasks.md` / `stories.md` / `prompt.md` / `README.md` updated.
  Next: SPT-3.

### 2026-09-11
- **Escaping-guard baseline drift fixed** (`5465c4e`). SPT-3 (`6b0dada`) added the `_BASELINE_UNESCAPED` entry for `src/strategy/signal_track_v1.py` at line 295, but the `notifier.send()` call is at
  286 — the full-suite escaping guard wasn't run before SPT-3 closed, so 3 `test_escaping_guard.py` tests failed on the next `make test`. One-line repoint 295->286; same fix class as BUG-046.
  Recurring hole: this guard only runs on the full suite, not the targeted dirs per-task sessions gate on.
- **Telegram test env-leak fixed** (`048d647`). Root cause of real Telegram messages landing during `pytest`: ~30 `scripts/*.py` modules call `load_dotenv()` unconditionally at import time, writing
  the real `.env` `TELEGRAM_BOT_TOKEN`/`CHAT_ID` into `os.environ`; `monkeypatch` can't undo that later, so once one test's import triggered it, `build_notifier()` could go live for whichever test ran
  next in the same `pytest-xdist` worker. The `clean_telegram_env` guard fixture only covered `tests/unit/test_notifications.py`; promoted to a suite-wide autouse fixture in `tests/unit/conftest.py`.
  3440 passed, 2 skipped.
- **BUG-046 fixed** (SHA `35d464d`) — 3 `test_escaping_guard.py` failures on `main`: the 2026-09-10 `morning_signal` premium/cost commits (`dc4701b`/`402db00`/`1078397`) moved the script's sole
  `notifier.send()` from line 245 → 282 without updating `_BASELINE_UNESCAPED`. Confirmed the call site is escape-safe (`_format_signal_notification()` owns the MarkdownV2 boundary). Repointed the one
  baseline key 245 → 282; no production code change. `test_escaping_guard.py` 10/10 green, full suite 3421 passed. Both sections moved to `docs/archive/bugs/`.
- **BUG-045 fixed** (SHA `aa44820`) — `src/notifications/formatting.py` position-health helpers passed `Optional` `PositionFinding` fields into non-`Optional` APIs, red-lining the mypy pre-commit hook
  for every `src/paper` / `src/client` commit. Narrowed both call sites in `_resolved_label` with explicit `ValueError` guards (REVIEW.md G6) + `days_overdue or 0` for the `overdue` sort key; 2
  regression tests. B045.1 graph trace confirmed no live wrong-output path. `@code-reviewer` 0 CRITICAL/ERROR. mypy green; suite green bar the 3 pre-existing BUG-046 `test_escaping_guard` failures.
  Both sections moved to `docs/archive/bugs/`.

### 2026-09-09
- **S5.6 completed.** Real entry premium fetch implemented and plugged into the 09:15 signal formatter and outcome P&L calculator; strike selection pinned to monthly option. (SHA `402db00`).

- **Logged BUG-042** — `721daf9`'s unconditional MarkdownV2 switch broke every unmigrated `TelegramNotifier` cron caller (CC/PP entry, paper snapshot, monitor daemon, pre-market brief); silent `400
  Bad Request` on every send since 2026-08-25. Same root cause as BUG-039 (which fixed `daily_snapshot.py` only). Full entry + fix options in `docs/bugs/bugs.md`, checklist B042.1–B042.7 in
  `docs/bugs/task.md`. Diagnostic only — CC positions still record to DB, only notifications lost. Docs-only.

### 2026-09-02

- **MEAS-1 shipped — `scripts/dev/token_audit.py` session token-attribution tool.** SHA `79effcd`. Parses a session transcript JSONL and buckets its tokens: `system_prompt` (real, first-turn
  `cache_creation_input_tokens`), `project_docs` (estimated, chars/4 over current `CLAUDE.md`+`AGENTS.md`+`MEMORY.md`), `tool_results:<tool>` (estimated, chars/4 per matched `tool_result`),
  `subagent_reports` (estimated, chars/4 over `<result>` text) and `subagent_internal` (real, `<subagent_tokens>`) kept separate, `assistant_text` (real, `usage.output_tokens`). Compact table +
  `--json`. 7 tests, fixture transcript, no network. `code-reviewer` clean (0 CRITICAL/ERROR). Next: MEAS-2 — run it on 4–5 real sessions and write the epic `README.md` Baseline section.
- **MEAS-2 shipped — token-efficiency Baseline section in the epic `README.md`.** Ran `token_audit.py` over five sessions (ROLL-7 `3dcf60ee`, TG-story `5b1c99ee`, diagnostic `d5d36b77`, RDO-17.7
  `1c878711`, RDO-17.6 `724f9ef6`). Median session ≈ 703K account-side tokens; `subagent_internal` is the largest bucket every time (median 367K, ~50%), then `assistant_text` (median 225K, inflated by
  re-derivation), then whole-file `Read` results (median 32K). Names the targets for `fixed-overhead/` (FIX-3 session-close fork, FIX-1 `CLAUDE.md` restructure) and `suggestions-sweep/`.
  `measurement/` story complete — epic router advances to `fixed-overhead/`.
- **FIX-1 shipped — resident `CLAUDE.md` reference material moved to a `protocol-reference` skill.** SHA `41ac31e`. `project_docs` bucket **12,554 → 9,556 tokens, −2,998 (−23.9%)** measured with
  `token_audit.py`. `CLAUDE.md` 409→309 lines, `AGENTS.md` 474→377, re-mirrored with its Antigravity deltas intact. Moved to the skill as five numbered sections: Council Decision Protocol, Quick
  reference, AI Collaboration, review/handoff rules, module `CLAUDE.md` index. Rule 0/1, Steps 0–5, the AutoTrigger table, Python + Logging standards stay resident. No gate dropped — verified by
  matching every path reference in the old file against (new file + skill); the one real loss found, an FR-7 citation in Step 5a, was restored. Council-trigger path fires via three routes (Step 2b
  imperative, resident "§1 is a gate" line, skill trigger phrases) — this repo's `SKILL.md` files have no YAML frontmatter, so the resident pointer is load-bearing. Skill also mirrored to
  `.agents/skills/` per `md-organize` Step 7, a scope addition FIX-1's spec had missed. The ≤200-line target set at plan time was **not** met (309) — reaching it would have meant dropping a gate; see
  the As-built. Next: FIX-2 (trim heaviest `src/*/CLAUDE.md`).
- **FIX-2 shipped — the three heaviest module `CLAUDE.md` files trimmed to invariants.** SHA `ce45719`. Auto-injected total **5,260 → 3,805 tokens, −1,455 (−28%)**: `notifications` 3,086→1,998,
  `portfolio` 1,112→930, `client` 1,062→877 (chars/4, `token_audit.py`'s own estimator — the tool excludes module `CLAUDE.md` from `project_docs` by design, so it cannot report this bucket itself).
  Measurement overruled the spec's guess: `portfolio` is second, not `paper` (980, left alone — near-pure invariants). Relocated detail to a new non-auto-loaded `NOTES.md` per module: MarkdownV2
  migration history, guard-test allowlist mechanics, full formatter/table-builder signatures, `apply_trade_positions` call sites, models/registry enumeration, implementations table, `MockBrokerClient`
  setup API. No invariant reworded and no section header dropped, so `§"Instrument Label Formatting"` (`CLAUDE.md`, `AGENTS.md`, `CONTEXT_TREE.md`) and the `FORMATTING.md` / `REVIEW.md` citations
  still resolve. Saving is per-turn once a session touches the directory, not per-session. No `.agents/` mirror needed — module docs have no `AGENTS.md` counterpart. 3074 passed, 2 skipped. Next:
  FIX-3 (`session-close` off the `fork`).

### 2026-09-01

- **`token-efficiency/` epic authored.** New 3-story epic under `docs/plan/token-efficiency/` (`measurement/` → `fixed-overhead/` → `suggestions-sweep/`, ~13 tasks). Spawned from a token audit Animesh
  asked for after the ROLL-7 session: ~740K tokens for a ~440-line task, of which the `session-close` fork alone was ~285K (a fork clones the whole conversation). Targets: skill-ify the ~400-line
  resident `CLAUDE.md`, run `session-close` as a transcript-reading subagent, strip MCP fingerprint bloat, and clear the ~35-row `suggestions.md` backlog — which is write-only today (`reread-file` at
  Count 13, `pytest-inlined` at 7, nothing ever escalates). Cross-cutting rule: every fix quotes a real before/after number from a new `token_audit.py`. Plan docs only; no code yet.

- **ROLL-7 shipped — re-entry blocked/eligible notice migrated to MarkdownV2 kv-line format.** SHA `cad8074`. `ReEntryMixin._check_reentry`'s three gates + two structural-failure paths now emit
  `(short_reason, detail)` pairs instead of one prose string (`_ivr_passes` signature widened to a 3-tuple; base + `PPOverlayV1` override + `auto_close.py` caller updated). New `STRATEGY_LABELS` /
  `LEG_ROLE_LABELS` + `strategy_label()` / `leg_role_label()` (unmapped → `ValueError`) in `src/notifications/formatting.py` — kept separate from `eod_summary.py`'s `_STRATEGY_META`; consolidation
  flagged. `notes` column flattened via `_block_notes()`. MD-6 guard baseline entry for `reentry_mixin.py` removed (now escaped in-scope). Real `@code-reviewer` run despite `Review: none` (touches
  production gate logic); full suite 3065 passed. `strategy-rollout/` next: ROLL-8.

- **ROLL-6 shipped — EOD Paper Summary migrated to MarkdownV2 bucketed table.** SHA `2471f01`. `scripts/eod_summary.py` was still emitting raw HTML `<b>` through the MarkdownV2 transport (silently
  400'ing since MD-4.1) and reading `Bkd` from `paper_nav_snapshots.realized_pnl` (zeroes on a reopen cycle). Now: `build_eod_summary_message()` renders the confirmed 4-bucket totals-first table;
  `Bkd` from `get_strategy_realized_pnl()`; figures quantized to whole rupees before summation so the table foots exactly. Promoted `build_strategy_table` / `format_summary_money` / `StrategyPnLRow`
  to `src/notifications/formatting.py` (FMT-1d §12). Real `@code-reviewer` clean (0 CRITICAL/ERROR); full suite 3051 passed. `strategy-rollout/` next: ROLL-7.

- **BUG-039 fixed — daily_snapshot Telegram P&L summary silently stopped since 2026-08-25.** Animesh reported not receiving the daily 15:45 message since 24 Aug. Root cause: `721daf9` (2026-08-24
  23:00) switched `TelegramNotifier.send()` to `parse_mode=MarkdownV2`, but `daily_snapshot.py`'s summary text (`_format_combined_summary` + `src/dhan/positions.py`'s `format_options_section`) was
  never migrated to escape its output — a known, documented gap (`test_escaping_guard.py`'s `_BASELINE_UNESCAPED` entry for that exact call site). Every unescaped `-`/`()`/`.`/`+`/`|` in the P&L
  waterfall 400'd the send on every trading day since. Fix: `escape_markdown(summary_text)` at the `notifier.send()` call site — verified no intentional MarkdownV2 entities in the message, so
  whole-string escaping is behaviorally equivalent to per-value escaping and matches `FORMATTING.md` §6's call-site boundary. Removed the stale baseline entry per its maintenance contract.
  code-reviewer clean (0 CRITICAL/ERROR/WARNING); full suite 3042 passed. SHA `2cb67ce`. Full detail: `docs/bugs/bugs.md` BUG-039.

### 2026-08-29

- **doc-format-migration epic created — answers RDO-17.8 (Owner: Animesh).** Animesh decided the legacy-folder rule: batch-convert every `docs/plan/` folder now (not on-touch), tiered A/B/C/D by
  folder state, `git log --follow` trusted for shipped SHAs, no permanent grandfathering (fully-shipped folders archive instead). Plus a scope expansion: reflow every other `.md` in the repo (not just
  `docs/plan/`) to fill-to-≤200, and make the format self-enforcing. New epic `docs/plan/doc-format-migration/` with three sub-stories: `plan-folders/` (DFM-1 tier → DFM-2 tier-A full → DFM-3 tier-B
  light → DFM-4 tier-C reflow), `repo-wide-reflow/` (DFM-5, everything outside `plan/` + `archive/` + `_TEMPLATE/`), `enforcement/` (DFM-6 widen `md-line-length` repo-wide · DFM-7
  `check_story_structure` gates modified folders · DFM-8 wire `check_checkbox_consistency` pre-commit · DFM-9 CI `docs-format` `--all` job · DFM-10 `scripts/dev/new_plan_folder.py` + `/new-story`
  skill). 11 doc files, all four doc hooks clean. RDO-17.8 left `[ ]` in `root-doc-organization/` with the decision recorded in its line + `stories.md` digest (closes in the follow-up commit per the
  two-commit convention); `docs/plan/README.md` + `TODOS.md` backlog updated (epic added at #1, list renumbered 2..23).
- **RDO-17.7 — sweep both POC folders to fill-to-≤200 + add reflow_md.py (root-doc-organization).** Scope revised with Animesh: RDO-17.7 is not just the §A guidance (shipped in `7d28d16`) — it also
  applies that style to `root-doc-organization/` and `telegram-markdown-migration/` in full, since those are the RDO-17.5/17.6 exemplars. New `scripts/dev/reflow_md.py` — reusable whitespace-only
  paragraph reflow (`--check`/in-place; code fences, tables, headings, nested list/quote structure verbatim; never leaves a wrapped line starting with a bare list marker) —
  + `tests/unit/scripts/dev/test_reflow_md.py` (10 tests). Ran over all 16 `.md` in both folders (D6 extras included): `md-line-length` clean, `git diff --word-diff` zero word changes (only interior
    blockquote `> ` markers consolidate on rewrap). Also fixed the stale "semantic linefeeds" line in `check_md_line_length.py`'s docstring; `docs/plan/README.md` §"Markdown line style" now names the
    two swept exemplars and points the rest at RDO-17.8. Commit 2: SHA + box. RDO-17.7 §B renamed to **RDO-17.8** (Owner: Animesh, still open) — the do-not-touch reusable tool now exists, so the
    decision is purely cadence / effort-ceiling / grandfathering for the other ~25 legacy folders.
- **RDO-17.6 — full-convert telegram-markdown-migration/ to canonical epic format (root-doc-organization).** Two commits, docs-only. Commit 1 (`cf46ff4`): root `README.md` → `_TEMPLATE/epic/` shape
  (Why / Scope decisions / Stories table w/ Status + Closing SHA / Cross-cutting constraints / Supersession / Epic done when); root `prompt.md` → epic router (fixed story list + Step 1–4); all 3
  sub-stories (`backbone/`, `formatting-rules/`, `strategy-rollout/`): `prompt.md` → `_TEMPLATE/story/` headers, every `tasks.md` line → one canonical `| Owner | Model | Review | SHA` line (umbrellas
  keep their checkbox w/ a bare `| SHA:` legacy tail; `Model` → `claude-*` ids), forensic detail folded into per-task `stories.md` **As-built** paragraphs (Animesh chose fold-into-section over a
  decision-log appendix, and keep-umbrella-checkbox). MD-6 + MD-4.1/4.2/4.3 gained new `stories.md` spec subsections. Deviation from RDO-17.5: the sub-story `stories.md` files already covered every
  task, so no rewrite — only As-built additions. Commit 2: tick RDO-17.6 + SHA, `stories.md` digest, `docs/plan/README.md` (both entries), this log. `md-line-length` + both structure hooks +
  `check_checkbox_consistency` clean of any `telegram-markdown-migration/` finding; 3026 unit tests green.
- **RDO-17.7 §A + RDO-17.5 — full-convert root-doc-organization/ (root-doc-organization).** Two commits, docs + tooling only. Commit 1 (`7d28d16`, RDO-17.7 §A): retired the "semantic linefeeds"
  guidance for fill-to-≤200 — `docs/plan/README.md` §"Markdown line style", both `_TEMPLATE/` sets, `md-organize/SKILL.md` + its `.agents/` mirror, and the `INSTRUCTION.md` one-liner. Commit 2
  (RDO-17.5): every `root-doc-organization/tasks.md` line collapsed to one canonical line with the `| Owner | Model | Review | SHA` tail (shipped lines keep their real SHA + `[x]`; `Review:
  code-reviewer` for RDO-5/13/15/17.2 which touched `scripts/*.py`, `none` otherwise; RDO-3 → `[x]` closed-partial; RDO-12 SHA `42eabb2`); `stories.md` rewritten to cover every task — forward spec for
  RDO-11/RDO-16, a 2–4 line as-built digest for each shipped one; `prompt.md` realigned to `_TEMPLATE/story/prompt.md`; `plan.md` kept unchanged. `docs/plan/README.md` status entry advanced (next →
  RDO-17.6). Both structure hooks `--all` clean of any `root-doc-organization/` finding; 42 hook tests green; `check_checkbox_consistency` clean.
- **RDO-17.5/17.6/17.7 filed — scope revision (root-doc-organization).** `4d5611a`, docs-only, task definitions only (no conversion executed). Animesh: RDO-17.4's partial retrofit — grandfather the
  shipped task lines — is **superseded** for the two validation folders. **RDO-17.5** fully converts `root-doc-organization/` (every `tasks.md` line to a one-liner + 4-field tail, shipped lines keep
  their real SHA; `stories.md` rewritten to cover every task — forward spec for open, 2–4 line as-built digest for shipped; `prompt.md` realigned to `_TEMPLATE/story/`). **RDO-17.6** does the same for
  the `telegram-markdown-migration/` epic (router `prompt.md`, `README.md` Stories status table, all 3 sub-stories' `prompt.md` + `tasks.md`; resolves `ROLL-1a/1b/1c` nested checkboxes vs
  one-checkbox-per-id). How cleanly the two POC conversions go calibrates whether/how the other ~25 legacy folders convert — **RDO-17.7** (Animesh) records that rule afterward. `tasks.md` RDO-17
  intro + `## Story done when` bullet + `stories.md` (17.5/17.6 specs, 17.7 placeholder) + `docs/plan/README.md` blurb updated. Both hooks `--all` green. `~/.claude/plans/woolly-honking-tarjan.md` now
  stale (grandfather framing) — Animesh owns the plan-doc update. **Follow-up (same day):** RDO-17.7 given real scope. §A (finalized, Animesh): retire RDO-5's semantic-linefeed guidance — Markdown
  prose now fills each line to the last word boundary before 200 (the `md-line-length` hook stays the only enforced rule); the mid-line ~110-char wrap was hard to read. §A executes inside RDO-17.5
  (all rewritten files authored fill-to-200; §"Markdown line style" + `_TEMPLATE/` + `md-organize` wording changed). §B (open, Animesh): the ~25-legacy-folder conversion rule, decided after 17.5/17.6.
  `tasks.md` RDO-17.5/17.7 lines + `## Story done when` + `stories.md` §RDO-17.5/§RDO-17.7 updated.
- **RDO-17.4 — retrofit the two format-validation folders (root-doc-organization).** `35d9f42` (impl) + close commit, docs-only. `root-doc-organization/` (single flat story): added `stories.md`
  covering only the open tasks (RDO-11, RDO-16, RDO-17.4 — shipped-task detail stays inline in `tasks.md` history); added the `| Owner | Model | Review | SHA` tail to the two open lines; `## Epic done
  when` → `## Story done when` + two adjacent prose fixes. `telegram-markdown-migration/` (epic): dropped untracked `.DS_Store`; `git mv` the exhausted missing-messages queue (`TODO.md` +
  `missing-message-workshop-prompt.md`, all 10 items written back as `strategy-rollout/` ROLL-7..ROLL-16) → `docs/archive/plan/telegram-markdown-migration/` with archive banners; `README.md`
  repointed + one-line completion pointer added; `message-format-workshop.md` stays live at the epic root. `check_story_structure.py --all` 14 → 12 warnings (both validation-folder findings gone),
  `check_checkbox_consistency.py --all` green, 42 hook tests green. RDO-17.1–17.4 shipped (17.4 superseded same day — see the RDO-17.5/17.6/17.7 entry above). `28d0d9c` (impl) + close commit,
  docs/skills only. `.claude/skills/work/SKILL.md` Feature branch now classifies flat-story vs epic-root: epic path reads the router `prompt.md` + `README.md`, walks the fixed story order (README
  Stories table) to the first sub-story with an unchecked `- [ ]`, loads its `prompt.md` + `stories.md` (+ `schema.md`) + first unchecked task; step 7 reports `Owner/Model/Review` and halts on owner
  mismatch. `| Review:` field added to the Step 5a task-line convention in `CLAUDE.md` + `AGENTS.md` and to the `session-close` violation check (legacy 3-field tails grandfathered); `md-organize`
  structure-audit note restated to the RDO-17 flat-story / epic-root file sets; `_TEMPLATE/epic/prompt.md` router Step 1 pins story order to the README table. `commit/SKILL.md` carries no task-line
  tail — untouched. Both structure hooks `--all` green; dry-run `/work` on `telegram-markdown-migration/` walks `backbone/` + `formatting-rules/` (all checked) → lands on `strategy-rollout/` ROLL-6.
  17.4 (retrofit the two validation folders) next.
- **RDO-17.2 — story/epic structure + checkbox hooks (root-doc-organization).** `fe280bd`, tooling + docs. `check_story_structure.py`: `Finding(level, message)`; story folders now require
  `stories.md`, epic roots require `prompt.md` + `README.md`, `schema.md` DDL backstop (warn), D6 extra-file checks; legacy shapes grandfathered — `--all` fails only on `error`, `--staged-added`
  blocks on any finding. `check_checkbox_consistency.py`: `SUMMARY_RE` gains `story done when`; canonical-tail check (Review value ∈ known gates; `SHA: —`/`<—>` iff unchecked, hex iff ticked) over
  multi-line task entries, legacy tails skipped. 40 hook tests (was 24). `docs/plan/README.md` §Checkbox-consistency wording + stale `next:` pointer (RDO-17.1 → RDO-17.2) fixed. 17.3 (`/work` epic
  descent + skill propagation) next.
- **RDO-17.1 — `docs/plan/` story/epic format spec + templates (root-doc-organization).** `7b6d05f`, docs-only. `docs/plan/README.md` §Conventions rewritten: single-story flat vs epic-with-sub-stories
  (no `stories/` layer), `stories.md` now required, `schema.md` conditional-required checklist, extra-files rule, 5-field `| Owner | Model | Review | SHA` task line. `_TEMPLATE/` split into `story/` +
  `epic/` variants. First of 4 RDO-17 sub-tasks; 17.2 (hooks) next.
- **RDO-6 + RDO-7 — `md-organize` skill + doc-staleness check (root-doc-organization).** 4 commits, docs/tooling only. RDO-7 (`d24f15d`): `session-close/SKILL.md` Step 3e — report-only content-gap
  check (new module w/o `CONTEXT_TREE.md` row; story code touched but `docs/plan/README.md` status not advanced). RDO-6: `.claude/skills/md-cleanup` → `md-organize` with a rewritten `SKILL.md` (real
  19-file root table; CONTEXT re-slim / DECISIONS roll / repo-wide `md-line-length` sweep / `CLAUDE.md` pointer reconcile / story-structure + checkbox audits / RDO-10 hook-drift check / Step 7 mirror
  re-sync). `.agents/skills/` re-synced wholesale from `.claude/skills/` (added `work/`, dropped all "Codex" refs). `CLAUDE.md` + `AGENTS.md` 11 long lines each wrapped; Step 5a task-line pointer
  added (RDO-13 deferred). Whole-repo `md-line-length` backlog cleared — ~700 lines across ~70 files reflowed to semantic linefeeds via 5 parallel subagents; `--all-files` now green (`suggestions.md`
  excepted — wide table, `SKIP=md-line-length`). Epic now: RDO-11 (≥ 2026-09-03) + RDO-16 (loop-closure) open.

### 2026-08-28

- **RDO-10 — reconcile RDO-7 / Phase 7 with the shipped doc-freshness hooks (root-doc-organization).** Docs + one hook edit, 1 commit. Decisions with Animesh: (1) RDO-7 **kept but narrowed** —
  `state_doc_freshness.sh` (SessionStart) + `doc_update_gate.sh` (PreToolUse) already own the per-file "docs behind code" signal, so the session-close report is re-scoped to the content gaps neither
  hook sees (new `src/<module>/` with no `CONTEXT_TREE.md` row; story code touched this session but `docs/plan/README.md` status not advanced). (2) `TODOS.md #4` (weekly cloud routine) **narrowed to a
  future read-only Telegram staleness digest**, out of epic scope — unattended-write cron stays rejected. (3) Skill name settled: **`md-organize`** (RDO-6 does the rename + ~6 by-name ref updates).
  (4) `state_doc_freshness.sh` thresholds tuned — `CONTEXT_TREE.md` / `DB_REGISTRY.md` / `README.md` 35-40 → 60 (all three change only on new modules / tables / public-surface shifts; DB_REGISTRY was
  the known 36/35 false positive). RDO-6 gains a step to verify the two hooks' hard-coded doc lists still match `CLAUDE.md` §Step 5a. `plan.md` Phase 7 + `tasks.md` RDO-6/7/10 + `## Epic done when` +
  `docs/plan/README.md` row updated. Open in the epic now: RDO-6, 7, 11, 16. Docs/tooling-only, no code-reviewer.

- **RDO-15 — checkbox-consistency sweep + one-box convention (root-doc-organization).** 2 commits. `5e48451`: new `scripts/hooks/check_checkbox_consistency.py` (+ 11 tests) — sweeps
  `docs/plan/**/tasks.md` + `docs/bugs/task.md` for a checkbox inside an `## Epic done when` block, same-id state drift in one file, and a README `next:` marker on an already-done id; `--all` + path
  modes, runs in the `md-cleanup`/`md-organize` audit (Step 5c), not pre-commit. Convention (a) chosen (Animesh delegated) — `## Epic done when` blocks are now prose acceptance criteria, no
  checkboxes; working-list `tasks.md` state is the sole source, drift structurally impossible (same principle as RDO-13 §4). Sibling script, not an extension of `check_story_structure.py`. Retrofit
  trivial — only 2 files used the mirror (`root-doc-organization`, `session-entry-point`), zero pre-existing drift; `_TEMPLATE/` + `docs/plan/README.md` §"Checkbox consistency" updated. Id-less
  "loop-closure check" item promoted to task **RDO-16**. `code-reviewer`: 0 CRITICAL/ERROR, 4 WARNING all fixed (README slug regex underscore gap, `task.md` dir-glob, EXCLUDED filter style, test
  hints). `session-entry-point` epic archived to `docs/archive/plan/` in the same session (was done, awaiting only this worked-example use).

- **RDO-9 — `DECISIONS.md` semantic split (root-doc-organization).** 3 commits. 9a: full-file classification (2203 lines) + `options-strategist` advisory pass + Animesh sign-off — scratch artifact
  `rdo9a_classification.md`. The file was big because it is append-only and verbose inside a ~4-month window, not old — so split by *kind*: 9b `344f3a7` moved every completed-work-log entry (the
  chronological "fixed X, why" stream, `## Process`, the dated `## BUG-*` sections, the delivered NSE Bhavcopy UDiFF spec, the Telegram-MD sequencing narrative) →
  `docs/archive/DECISIONS_worklog_2026.md`; lifted 11 still-enforced rule fragments into a new `## Risk, Delta & Entry Gates` section + existing sections; fixed 8 stale rule entries the 9a
  `options-strategist` pass caught (CSP/CC profit target is 30% retention not 50%, CSP delta stop 0.40 not 0.45, CC DTE_REVIEW is ACTION not WARN per EC-5, CC re-entry allow-list, CSP time-stop DTE
  guard from EC-4, Notifications HTML→MarkdownV2, §7.3 IC-judged-in-isolation); merged the duplicate `## Market Calendar` and `## Developer Tooling` headers. 9b `2fb5c5b` wrapped the file to semantic
  linefeeds, `md-line-length` green, Strategy & Research table → bulleted index. Result: 2203 → 972 lines, ~84K → ~22K tokens, fresh full-file `Read` succeeds. **DoD deviation:** "≤ 800 lines"
  conflicts with the same DoD's semantic-linefeed requirement — flagged to Animesh; token count is the metric that holds. Docs-only, no code-reviewer. `prompt.md` DoD + `docs/plan/README.md` row
  updated; RDO-9 + `prompt.md`-DoD-rewrite epic-done boxes ticked.

- **RDO-14 — `TODOS.md` restructure (root-doc-organization).** Design changed with Animesh: *not* one unified queue — two separate pointer-only lists, `## Feature Backlog` (`1..N` contiguous,
  `docs/plan/` stories) and `## Open Bugs` (non-authoritative snapshot + pointer to `docs/bugs/`), matching `/work`'s existing Feature/Bug fork. Dropped: completed `session-entry-point`, superseded
  `telegram-ic-comparison-formatting`, the duplicate "item 14", all `TGFMT-2..9` refs. Every internal `"item N"` cross-ref → story-folder name. Whole file reflowed to semantic linefeeds
  (RDO-13-deferred backlog for this file — no `SKIP=md-line-length` needed now). Added per Animesh: `docs/plan/README.md` §Conventions gains a *Completion → archive* subsection (story folder →
  `docs/archive/plan/`, `TODOS.md` line → `TODOS_ARCHIVE.md`, README row → pointer, all one commit) + `session-close` Step 5b "done-but-not-archived" check. `/work` branch-collapse (RDO-14 §4)
  explicitly declined; recorded in `session-entry-point/tasks.md`. Docs-only.

- **RDO-13 — docs/plan + TODOS.md convention enforcement (root-doc-organization).** 3 commits. 13a `0712b49`: `docs/plan/README.md` §Conventions rewritten canonical + self-contained (archive pointer
  dropped), all 17 pre-existing >200-char story rows reflowed into compact status entries, `docs/plan/_TEMPLATE/{prompt,tasks}.md` added. 13b `a0d255d`: `scripts/hooks/check_story_structure.py` + 11
  tests + pre-commit wiring (story-vs-epic detection; `--all` audit / `--staged-added` pre-commit / path modes); two empty stray folders removed. 13c: structure-audit + pointer-only steps in
  `md-cleanup` / `session-close` skills; this header pointer. `CLAUDE.md`/`AGENTS.md` 5a pointer deferred to RDO-6 (mirror long-line wrap); `TODOS.md` items 14/22/29 retrofit stays RDO-14. Committed
  with `SKIP=md-line-length` — this file carries the pre-existing backlog; the change adds none.

### 2026-08-27

- **RDO-8 — protocol-doc consistency cleanup (root-doc-organization).** 5 fixes, one docs/config-only commit: (1) `ANTIGRAVITY.md` step 2 docs/config-only bullet aligned to "skip `code-reviewer`
  entirely" (was: adopt persona + evaluate) — now matches `CLAUDE.md` / `AGENTS.md` 5c. (2) `git rm -r .codex/` (dead scaffolding from `16821d6`, only self-referenced); `.agents/` kept per Animesh
  (Antigravity autoloads it), added to RDO-6's re-sync scope with a note re its stale `.Codex/` refs. (3) `src/paper/` `src/nuvama/` `src/gamma/` rows added to the module table in `CLAUDE.md` +
  `AGENTS.md`; `AGENTS.md`'s "Also present on disk" note folded in so the two match. (4) `src/client/CLAUDE.md` heading
  + `src/client/` row in both module tables reworded "implementations (2 built + 1 variant + 1 planned)". (5) `CLAUDE.md`'s embedded "Rules for any review" lifted to a standalone `## Rules for any
    review or handoff` section matching `AGENTS.md`; both bodies set identical. Next: RDO-6, RDO-7, or RDO-9.

- **RDO-5 — `md-line-length` pre-commit hook (root-doc-organization).** Added `scripts/hooks/check_md_line_length.py` (200-char hard cap, all line kinds; `<!-- lint-ignore-length -->` on the preceding
  line excuses one unbreakable token) + local `md-line-length` hook over `^([^/]+\.md|docs/(plan|bugs)/.*\.md)$` + 3 unit tests in `tests/unit/scripts/hooks/`. `plan.md` Phase 1's "≤100" contradiction
  removed, Phase 5 yaml block updated; semantic-linefeed + 200-cap style recorded in `docs/plan/README.md` §Conventions. Scoped tooling-only per Animesh — the hook enforces on staged files; the
  ~800-line pre-existing backlog (18 files) is not an RDO-5 gate, cleared opportunistically + by RDO-6 (`md-organize`) / RDO-9 (`DECISIONS.md`). Commit used `SKIP=md-line-length` since it stages the
  still-unwrapped `TODOS.md` / `docs/plan/README.md`. Next: RDO-6 or RDO-7.

- **RDO-4 — relocate legacy `BUGS.md` + `GLOSSARY.md` out of root (root-doc-organization).** `git mv BUGS.md docs/archive/BUGS_LEGACY.md` (archive banner added, only `BUG-001` still open) + 3-line
  root stub → `docs/bugs/` + archive. `git mv GLOSSARY.md docs/GLOSSARY.md`, no stub, `docs/GLOSSARY.md` Quick-reference row added to `CLAUDE.md` and `AGENTS.md` (mirror). Live inbound links
  repointed: `TODOS.md` header, `docs/plan/README.md` intro, `docs/bugs/bugs.md` relationship note. Historical mentions (`DECISIONS.md` 2026-07-02 entry, `dev-foundation` CH-3 records,
  full-repo-review audit snapshots) left as accurate records. Docs-only. Next: RDO-5 (`md-line-length` pre-commit hook).

- **SEP-4 — end-to-end check + close (session-entry-point epic complete).** Ran both `/work` branches in one session. **Feature branch** demonstrated live: invoked as `/work on SEP-4 in
  session-entry-point` → Step A skip-through detection matched the story id → Feature branch pre-selected to `session-entry-point` (TODOS priority item 1) → `prompt.md` + `tasks.md` loaded → SEP-4
  identified as first unchecked `- [ ]` → `CONTEXT.md` read → handed to `CLAUDE.md` Step 2b (council checkpoint: not warranted). **Bug branch** demonstrated via routing dry-run: `docs/bugs/task.md` +
  `bugs.md` read, open entries presented — BUG-038 (first unchecked B038.1, `trace_path` the two unawaited-send methods) and BUG-037 (first unchecked B037.6, `code-reviewer` on the B037.3/B037.4 fix);
  BUG-019 listed as diagnostic-only / not actionable. Both branches reach a loaded prompt. Docs-only close: SEP-4 ticked (working list + "Epic done when"), `docs/plan/README.md` row flipped to ✅ Done,
  RDO-12 ticked in `root-doc-organization/tasks.md` (both checkboxes), priority item 1 ticked here. `session-entry-point` epic (SEP-1..4) fully shipped.

- **SEP-3 — `AGENTS.md` mirror (session-entry-point).** Applied the SEP-2 `CLAUDE.md` Step 1 change to `AGENTS.md` with the Antigravity adjustment: new `/work` delta bullet in the header deltas list;
  Step 1 gains a routing block stating the manual equivalent (no `/work` skill — take the feature target off `TODOS.md` "Priority-Ordered Open Work" first-5, or the bug off `docs/bugs/`, then follow
  the handoff protocol into Step 2b); the "new feature" + "specific story" load-hint lines collapsed into one manual-routing pointer; Quick-reference row added. RDO-6's `md-organize` re-sync scope
  already names `.claude/skills/work/SKILL.md` (RDO-12 triage) — no edit needed; RDO-6 itself still unshipped. Docs-only. Next: SEP-4 (end-to-end check of both `/work` branches in one session +
  close).

- **SEP-2 — `CLAUDE.md` reconciliation (session-entry-point).** `/work` is now the documented start-of-task entry point in `CLAUDE.md`: leading `/work` block added to Step 1; the two duplicated
  load-hint lines ("Starting a new feature → `TODOS.md` + `PLANNER.md`", "Working a specific story → load ONLY that story file …") collapsed into one `/work` pointer; Quick-reference table gains a
  `/work` row. Docs-only. Next: SEP-3 (`AGENTS.md` mirror + `md-organize` re-sync scope).

- **RDO-15 filed (root-doc-organization).** Animesh flagged that story `tasks.md` files track each task id with two checkboxes — the working list and the trailing `## Epic done when` block
  (`session-entry-point/tasks.md` SEP-2 is the worked example) — plus a third state signal in `docs/plan/README.md`; ticking one and missing the others silently desyncs. RDO-15 adds a
  checkbox-consistency sweep (extends RDO-13's `check_story_structure.py`), picks a one-checkbox-per-id convention, and retrofits. Docs-only.

- **`/work` priority-source fix.** `/work`'s Feature branch reads `TODOS.md` "Priority-Ordered Open Work", which had rotted (broken numbering `0e.`→`9.`, item 14 duplicated, `TGFMT-2..9` listed though
  superseded). Decided with Animesh: `TODOS.md` stays the canonical global priority file and must order **both** bugs and features. Quick fix now — prepended `session-entry-point` (item 1) and
  `root-doc-organization` (item 2), renumbered the old `0e.` BUG-030 entry to `3.`. Full restructure into one unified bug+feature queue filed as **RDO-14** in
  `docs/plan/root-doc-organization/tasks.md`. Docs-only.

- **Root state-doc staleness — round 2 of workflow token-optimization.** Problem: root state docs (`CONTEXT.md`, `TODOS.md`, `DECISIONS.md`, `PLANNER.md`, `DB_REGISTRY.md`, …) rot because the only
  thing forcing an update is `CLAUDE.md` Step 5a — a checklist line, no enforcement, no signal. Three levers: surface / enforce / shrink.
  - **[x] #1 — surface (done, SHA 758dd6b).** New repo hook `.claude/hooks/state_doc_freshness.sh` wired as `SessionStart` in `.claude/settings.json`. Counts `src/`|`scripts/` commits since each state
    doc last changed; prints a one-line flag for any doc over its threshold (`CONTEXT.md`/`TODOS.md` 15, `CONTEXT_TREE.md`/`DB_REGISTRY.md`/`docs/plan/README.md` 35,
    `DECISIONS.md`/`PLANNER.md`/`README.md` 40). Zero-maintenance — uses git last-touch, no stamp lines in the docs. Informational, always `exit 0`. Tune thresholds after a week if it's noisy
    (`DB_REGISTRY.md` currently trips at 36/35 despite a 2-day-old edit).
  - **[x] #2 — enforce (done, SHA 7dae8e3).** New repo hook `.claude/hooks/doc_update_gate.sh`, PreToolUse matcher `Bash`, detects `git commit`. If `git diff --cached --name-only` has
    `^(src|scripts)/.*\.py$` but none of `TODOS.md`/`CONTEXT.md`/`DECISIONS.md`/ `docs/plan/README.md` → remind on stderr. **v1 `exit 0` (advisory)**; escape hatch `[skip-docs]` in the commit message
    → silent; `--amend`/`--dry-run` and tests-only diffs skipped. Flip to `exit 2` (blocking) only after a week of observing the false-positive rate (pure refactors, multi-commit phases). Repo.
    Smoke-tested: reminder fires, `[skip-docs]` suppresses, staged `TODOS.md` suppresses, tests-only diff silent.
  - **[x] #3 — shrink (done, SHAs 089fb91 + 7bbfaff).** (a) `089fb91` — `CONTEXT.md` test-count → `pytest -q | tail -1` pointer; `TODOS.md` session log trimmed to the two still-active threads, the
    four completed SHA-referenced entries (ROLL-4, nuvama, RDO-1, RDO-2) moved verbatim to `docs/archive/TODOS_ARCHIVE.md`. (b) `7bbfaff` — **scope deviation, confirmed with Animesh:** `DECISIONS.md`
    has *no* pre-2026 entries (earliest is 2026-04-01) and its 2026-04/05 entries are interleaved with 2026-06/07/08 ones inside shared thematic sections (`## Process`, `## Strategy & Research
    Decisions`, …), so a date-cutoff archive isn't cleanly possible. Instead lifted the 5 fully-historical, self-contained sections with no still-enforced rule (TradingView MCP Regime Probe, Backtest
    Data Source Decision, TrueData Historical Dump, Live Strategy Monitoring, src/ Model Placement Rule) to `docs/archive/DECISIONS_pre-2026-07.md` behind a one-line index; 336 KB → 330 KB, 2302 →
    2203 lines. **Follow-up:** the real DECISIONS.md shrink needs a *semantic* split (still-enforced rule vs completed-work log), not a date archive — filed as **RDO-9** in
    `docs/plan/root-doc-organization/tasks.md`.
  - **[ ] #4 — deferred.** `/schedule` a weekly cloud routine running the `md-cleanup` skill. Hold until #1–#3 have run 2 weeks — the SessionStart flag may make manual cadence enough. Conflicts with
    `root-doc-organization` Phase 7's "no unattended doc writes" — resolution tracked as **RDO-10**.
  - **Pending work from this session filed into `docs/plan/root-doc-organization/`:** RDO-3 closed-partial (date-cutoff unworkable, 7bbfaff recorded); **RDO-9** (DECISIONS semantic split), **RDO-10**
    (reconcile RDO-7 with the #1/#2 hooks + #4), **RDO-11** (graduate the advisory hooks to blocking — review on/after 2026-09-03) added; `tasks.md` gained an "Epic done when" checklist including an
    end-to-end loop-closure test. `plan.md` + README refreshed.
- **Workflow-suggestion triage → new `session-entry-point` story.** Triaging a batch of workflow-improvement suggestions into `root-doc-organization`. #1 — unified session entry point — spun into its
  own story `docs/plan/session-entry-point/` (SEP-1..4: manual `/work` skill, Feature/Bug routing, Feature branch offers the first 5 of `TODOS.md` "Priority-Ordered Open Work", Bug branch offers open
  `docs/bugs/` entries) + **RDO-12** pointer row in `root-doc-organization/tasks.md`. Decided: manual invocation only, no SessionStart hook. #2 — convention enforcement — filed as **RDO-13**:
  `docs/plan/README.md` §Conventions made canonical + self-contained (drop the dead `docs/archive/plan/README.md` pointer), `docs/plan/_TEMPLATE/` + `check_story_structure.py` audit (into
  `md-organize`, not pre-commit), ticked `tasks.md` lines carry `| Owner | Model | SHA |`, `TODOS.md` cut to pointer-only items (no inline detail, no mirrored checkboxes, delete the line on story
  completion). #3 — MD line width — folded into **RDO-5** (scope edit, not a new item): 200-char hard cap, semantic-linefeed prose style (one sentence/clause per line), check extended to
  `docs/plan/**` + `docs/bugs/**`, `.py` unchanged at ruff 100. Further suggestions still pending. Docs-only; commit deferred to the single end-of-triage commit.
- **SEP-1 — `/work` session entry-point skill (RDO-12).** Authored `.claude/skills/work/SKILL.md` — manual skill (triggers "work" / "start work" / "pick up a task" / "/work"), Step A skip-through
  (message names a story/bug/RDO id → jump to branch, else `AskUserQuestion` Feature/Bug), Feature branch presents the first 5 of `TODOS.md` "Priority-Ordered Open Work" and loads the picked story's
  `prompt.md` + `*_tasks.md` first unchecked task + `CONTEXT.md`, Bug branch lists open `docs/bugs/` entries (`🔴`/`🟡`) and loads the entry + `task.md` lines
  + first unchecked. Front-end to the existing protocol — composes with `task_protocol.sh`, hands to `CLAUDE.md` Step 2b. House style matched to `session-close` / `commit`. Docs + `.claude/` only — no
    code-reviewer/test-runner. SEP-2 (`CLAUDE.md` reconciliation) and SEP-3/4 are later sessions.
- **Workflow token-optimization** (plan: `~/.claude/plans/this-session-is-for-federated-goose.md`) — cut fixed per-session scaffolding cost (~5k tokens on a typical implementation session). Changes:
  (1) `~/.claude/hooks/cbm-code-discovery-gate` (global, not in repo) made path-aware — the once-per-session block now fires only for real code targets (`.py` under `src/`|`scripts/`, or a Grep/Glob
  scoped there), not for the first markdown/config Read of every session; (2) `.claude/hooks/guard_src_reads.sh` — full graph decision tree once per session, one-liner after; (3)
  `.claude/hooks/task_protocol.sh` — full checklist once per session, one-liner on later task prompts; (4) `~/.claude/hooks/cbm-session-reminder` (global) slimmed to one line (harness already injects
  the full reminder); (5) `CLAUDE.md` + `AGENTS.md` — stripped dated failure anecdotes, deduped the AI-Collaboration section against Step 3b/AutoTrigger; fixed `AGENTS.md`'s dead `md-organize`
  reference → `md-cleanup` Step 7 (new: re-sync AGENTS.md when CLAUDE.md changes). Docs/hooks only, no `.py` touched — no code-reviewer, no test-runner.

**Next-session validation** (validated 2026-08-27, session `92c04e16` — all 5 pass):
  - [x] First action `Read CONTEXT.md` — succeeded, **no** `cbm-code-discovery-gate` block (gate file `cbm-code-discovery-gate-$PPID` stayed absent until the first `src/*.py` read).
  - [x] First task-shaped prompt → full `⚙️ TASK PROTOCOL` checklist injected; gate file written. Second-fire one-liner not observable in a single-prompt session — hook branch
    (`task_protocol.sh:42-45`) reviewed and correct.
  - [x] First `src/` `Read` → `guard_src_reads` fired once (gate `niftyshield-guard-$PPID` created on first attempt); retry hit the one-liner branch. Exit-0 PreToolUse stdout isn't surfaced to the
    assistant, so verification was via gate-file lifecycle + source review.
  - [x] First `Read src/__init__.py` → hard `exit 2` `BLOCKED: … codebase-memory-mcp`; retry (gate now written) allowed. Path-aware block fires once for real code, as intended.
  - [x] `SessionStart` reminder is a single line ("Code discovery: graph tools first — …"), not the old block. Confirmed against `cbm-session-reminder` source (single `echo`).
  - On failure: hooks are `~/.claude/hooks/cbm-code-discovery-gate` + `~/.claude/hooks/cbm-session-reminder` (global) and `.claude/hooks/guard_src_reads.sh` + `.claude/hooks/task_protocol.sh` (repo).
    Gate files `/tmp/cbm-code-discovery-gate-$PPID`, `/tmp/niftyshield-guard-$PPID`, `/tmp/niftyshield-task-protocol-$PPID` — `rm` to re-test first-fire within one session.

**Task 5 (done 2026-08-27) — measurement + permission tooling:**
  - [x] Ran `/fewer-permission-prompts` (50 recent transcripts). Only non-auto-allowed read-only patterns worth listing were the four codebase-memory-mcp graph reads (`get_code_snippet`,
    `search_graph`, `search_code`, `trace_path`) — all bash usage was auto-allowed, mutating, or interpreter invocations. Added to `.claude/settings.json` `permissions.allow`. Commit `dd0da61`
    `chore(claude): add read-only permission allowlist`.
  - [x] Statusline: `~/.claude/statusline-command.sh` gained a `$%.2f` cost segment from `.cost.total_cost_usd` and a `/Nk` used-tokens suffix on the ctx segment from `.context_window.used_tokens`
    (both degrade to nothing when the field is absent — tested). Global file, not in-repo; noted in the TODOS-update commit body.
  - [x] `/context` snapshot (Animesh ran it manually, session `92c04e16`, ~9% used, 94.8k/1M): fixed scaffolding now — system prompt 3k, system tools 18.6k, memory files 10k (`CLAUDE.md` 8.3k +
    `~/.claude/CLAUDE.md` 1.6k + `MEMORY.md` 0.1k), skills 2.8k, custom agents 0.24k. Messages grew 60.9k→65.3k across the session. A clean cross-session before/after for the ~5k hook-reinjection
    saving isn't recoverable from one session — the saving is in per-turn message growth, not a static category; the once-per-session gate files (`task_protocol`, `guard_src_reads`,
    `cbm-code-discovery-gate`) were all confirmed single-fire above, which is the mechanism that delivers it. `logs/context.log` not written (`/context &> file` is client-side, redirect is inert;
    `logs/` is gitignored).
- Earlier 2026-08-27 entries — **ROLL-4** (`30bac70`), **nuvama empty-book crash** (`3b9b57f`), **RDO-1**, **RDO-2** — moved verbatim to [docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md)
  (2026-08-27 section). `git log --oneline` carries the sequence, each commit's `Why:` line the intent.
- [2026-09-03] migrated ROLL-8 WARN event alert format (d6b6476 → 9159524 non-fatal fix → 8f3a35a fallback escape → e8fb906 test fix)
- [2026-09-03] ROLL-9 shipped (`1e270de`) — 3-track base-leg roll notification → MarkdownV2 two-layout format + closed-leg realized P&L; promoted `format_money(signed=)` + `STRATEGY_SHORT_LABELS` into
  `formatting.py`. `strategy-rollout/` next: ROLL-10.
- [2026-09-03] ROLL-10 shipped (`a94eef3`) — proxy delta CRITICAL alert (dev 3-track snapshot) → confirmed 3-line MarkdownV2 block; `escape_markdown()` over the signed delta + verbatim
  `proxy_delta_alert`; plumbed `TrackSnapshot.consecutive_days` for a future structured layout. `strategy-rollout/` next: ROLL-11.
- [2026-09-03] ROLL-11 shipped (`1336b93`) — system healthcheck alert (`healthcheck.py`) → grouped severity-status MarkdownV2 block (`NIFTYSHIELD: DEGRADED` / `🚨 ACTION REQUIRED` / `✅ SYSTEMS
  NORMAL`); refactored `run_checks()` → `list[CheckResult]` (frozen dataclass) and `_check_3track_snapshot_cron()` → `CheckResult`, dropping the pre-formatted `✅/❌/⚠️` strings;
  `build_healthcheck_alert()` colocated in `healthcheck.py`. 8 new tests, 6 updated. `strategy-rollout/` next: ROLL-12.
- [2026-09-03] ROLL-12 shipped (`b3bf77a`, `a083fba`, `ecb7d0b`) — position health check alert (`position_health_check.py`) → MarkdownV2 grouped-by-finding-type format; refactored
  `run_position_checks()` → `list[PositionFinding]` (frozen dataclass); colocated `build_position_health_message()` in `src/notifications/formatting.py`. `strategy-rollout/` next: ROLL-13.
- [2026-09-09] MVP story — reframed from price-vs-target watch to capital-deployment sim (`eaa05de`, docs only). Locked: fixed 6% tranche ladder (25% each at 0/−6/−12/−18%), tipster SL ignored,
  −30%-on-deployed-capital hard stop. Open questions (whole-share rounding, cost bps, NIFTY benchmark alpha, time stop, portfolio mode, M-A lump-sum phasing, schema council) recorded at top of
  `docs/plan/mvp/mvp_tasks.md`; M1/M2/M4 need rewrite before implementation. Not started.
- [2026-09-11] SPT-4 (`7b11e83` + `edbc135`) and SPT-7 (`71da2d5` + `bbcf596`) shipped in parallel via two isolated subagents — SPT-7 has no code dependency on SPT-4/5/6 (only SPT-2's store methods),
  so it ran concurrently with SPT-4 instead of waiting behind SPT-5/6 in task order. `signals-paper-track/` next: **SPT-5**.
- [2026-09-12] SEC-2 Phase A shipped (`0202291`) — added `DailySignal.is_actionable` and replaced inline NO_TRADE checks across entrypoint scripts and signal_track_v1.
- [2026-09-14] Fixed `scripts/eod_summary.py` `_STRATEGY_META` — daily `ValueError`/aborted EOD Telegram send since 2026-09-02 (`logs/eod_summary.log`). Root cause: S1r (2026-07-29) consolidated
  CC/PP/Collar legs under one strategy_name `paper_nifty_overlay` (`STRATEGY_OVERLAY`, `src/paper/constants.py:37`), but `_STRATEGY_META` still mapped the three stale pre-migration names
  (`paper_collar_v1`/`paper_covered_call_v1`/`paper_protective_put_v1`) and lacked the new one. Replaced the three stale keys with `"paper_nifty_overlay": ("Overlay", "Overlay")` — can't split by
  leg_role here (unlike `src/reporting/eod_pt_summary.py`) since `eod_summary.py` only sees strategy-level NAV rows.
- [2026-09-24] MVP Telegram message design session (docs only, no `src/` changes — everything prototyped in `scratch/2026-09-24_mvp_telegram_message_survey.py`). Found and added to
  `docs/plan/mvp/tasks.md`: (1) M5's scope now includes registering `scripts/mvp_watch.py`'s hourly cron, which was coded (M4.1/M4.2) but never actually added to the live crontab; (2) new **M10** —
  wire M9's real ₹ `realized_pnl`/`total_qty`/`deployed_capital` into the per-alert message (currently shows only raw price %, predates M9); (3) new **M11** (Good-to-Have, blocked on M10) — IC-style
  win-rate/inception footer, needs a new `MVPStore` aggregate query; (4) **M12** — hourly summary redesign, single flat holdings-style table with `[O]`/`[P]` badges, 🟢/🔴/⚪ net-P&L headline color,
  three-line Invested/Current/P&L footer (OPEN picks only) — design converged but discussion continues next session before real implementation. Also found: `FORMATTING.md` documents a
  `format_pct_signed()` formatter that doesn't exist in `src/notifications/formatting.py` (doc/code mismatch, not yet fixed).
- [2026-09-24] MVP M13.1 shipped (`df9001a`) — `MVPStore.get_category_stats` now accepts an optional `ltp_map` and marks a category's OPEN picks to market, combining that unrealized leg with M11's
  realized P&L into `inception_pct` (relative to total capital ever deployed in the category). Also fixed a sibling bug from a prior uncommitted session (`7cf7820`) —
  `date.fromisoformat(pick.pick_date)` crashed on datetime-format `pick_date` strings in `enter_backfill_pick`/`run_backfill`/`mvp_watch.py`'s close-alert `held_days`; sliced to `[:10]` in all three
  call sites, plus added `fetch_historical_index_closes` for M0-ingested NIFTY index Parquet. `docs/plan/mvp/` next: **M13.2**.
