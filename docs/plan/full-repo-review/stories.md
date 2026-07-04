# Full Repo Review — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Each task below is designed to be run as an independent session/subagent, possibly by a
> human operator manually selecting a different model per task in the Claude app. Follow
> the "Model" and "Folder/files to attach" lines exactly — they are not interchangeable
> (see `prompt.md` for why).
>
> **Every task's prompt ends with the same closing block** (reproduced in each task below,
> not just referenced) — this is deliberate: it must survive being copy-pasted into a fresh
> session with no other context from this file.
>
> **Ordering note:** FR-1 (Protocol Review) runs first, ahead of the financial/code review
> tasks, even though it would conventionally be numbered last as a meta-task. Reason: it has
> no dependency on any other task's output, and it judges — among other things — whether
> this very epic's own protocol (including the "Operating philosophy" in `prompt.md`) is
> sound before the other six tasks spend real model budget executing under it. Same logic
> as `CLAUDE.md`'s own Step 2b council checkpoint: verify the process before running it, not
> after.

---

## FR-1 — Prompting Methodology & AI-Collaboration Protocol Review

**Persona:** Protocol Reviewer — this is the meta-task: reviewing not the code but the
instructions that govern how AI assistants (Claude, Antigravity, and any future model) work
in this repo, including this review epic's own instructions. Origin of this whole epic was
a **prompting** conversation; it would be inconsistent to review everything except the
prompts themselves, and inconsistent to let this task run last when it gates the rest.

**Model:** Fable. This requires holding `CLAUDE.md`, every module `CLAUDE.md`,
`ANTIGRAVITY.md`, `docs/antigravity/ai_collaboration_plan.md`, and a sample of
`docs/plan/*/prompt.md` files in mind simultaneously to judge whether the protocol is
internally consistent and whether it's actually being followed in practice (not just
whether it reads well in isolation).

**Folder/files to attach:** root `CLAUDE.md`, every `src/*/CLAUDE.md`, `ANTIGRAVITY.md`,
`docs/antigravity/`, `REVIEW.md`, `LOGGING.md`, `docs/council/README.md`, every
`docs/plan/*/prompt.md` (not the full stories/tasks files — just the prompts, which is the
actual instruction surface an agent sees first), and this epic's own
`docs/plan/full-repo-review/prompt.md` + `stories.md`.

**Known seed issues — start here, then go wider:**
- This very story's own `prompt.md` and `stories.md` are in scope — do not exempt this
  review epic from its own review. Check whether the model/persona assignments made here
  are actually justified or whether they're arbitrary-sounding despite the stated reasoning.
- Compare 3-4 `docs/plan/*/prompt.md` files against each other — is the "one task per
  session, find first unchecked box, stop" discipline actually uniform, or have later
  stories drifted in structure/tone from earlier ones (`telegram-leg-labels/prompt.md` is a
  recent, detailed example — use it as the baseline for comparison)?
- `CLAUDE.md`'s Step 2b "Council checkpoint" — check whether any story in `docs/plan/`
  contains a decision that should have triggered a council call per
  `docs/council/README.md#when-to-trigger-the-council` but didn't (i.e., the checkpoint is
  written down but verify it's actually been applied, not just documented).
- Whether the Antigravity/Claude implementation-routing logic (Step 3b) has ever actually
  been exercised — check `git log` for any commit authored via the Antigravity path vs.
  whether every commit so far has gone through the Claude-implements branch regardless of
  what the routing criteria would have selected.

**Task:**
1. Read `CLAUDE.md`'s full Pre-Task Protocol top to bottom as if seeing it for the first
   time — flag any instruction that is ambiguous enough that two reasonable agents would
   follow it differently.
2. Sample 3 `docs/plan/*/prompt.md` files from different months (check folder mtimes or
   `git log` for creation dates) and diff their structure/tone/rigor.
3. Check whether `docs/council/README.md`'s trigger criteria have actually gated any real
   decision, or whether council calls (where they exist in `docs/council/`) were made
   without an explicit checkpoint reference beforehand.
4. Evaluate whether the module `CLAUDE.md` auto-load mechanism creates any contradiction
   between a module's local rules and the root `CLAUDE.md` (e.g. does any module file
   permit something Part III of `REVIEW.md` forbids?).
5. **Decide whether the "Operating philosophy" block in this epic's own `prompt.md`**
   (co-investor framing, mutual blind-spot catching, findings rated by mission impact not
   nitpick volume) **should be promoted into root `CLAUDE.md`'s "AI Collaboration" section**
   so it governs every session rather than only this one review epic. Weigh: does it change
   any concrete behavior beyond what's already implied by the existing protocol (Rule 0's
   "state why the graph was insufficient," the mandatory missing-persona closing block
   pattern itself), or is it framing/tone that doesn't survive being generalized outside a
   review context? State a clear recommendation (promote / keep scoped / revise-then-promote)
   with reasoning — this is a decision FR-9 will act on, not a rhetorical question.
6. Rate each finding CRITICAL (protocol ambiguity that has already caused or will cause
   incorrect agent behavior) / ERROR (drift/inconsistency, not yet harmful) / WARNING /
   INFO.

**Output:** `docs/plan/full-repo-review/findings/FR-1_protocol-reviewer.md`.

**Closing block (include verbatim at the end of your own output file):**
> State the persona you reviewed as (Protocol Reviewer). Name at least one perspective this
> review did not cover that a different persona would have caught — write "none identified"
> explicitly if genuinely nothing comes to mind, do not omit this section.

---

## FR-2 — Financial Modeling & Greeks Correctness Review

**Persona:** Quant Reviewer — options pricing, Greeks, P&L accounting, Decimal/float
boundary discipline. Adversarial toward the codebase: assume every formula is wrong until
checked against a reference value, not until it "looks right."

**Model:** Opus. This is single-pass deep judgment on load-bearing math, the same class of
work `greeks-analyst`/`roll-validator` already gate per-commit — a full-repo pass needs the
same rigor applied broadly, not a cheaper model skimming for style issues.

**Folder/files to attach:** `src/risk/`, `src/paper/`, `src/strategy/` (all files, esp.
`exit_signals.py`, `profit_lock_engine.py`, `delta_tracker.py`), `src/backtest/ivr.py`,
`src/models/options.py`, `REFERENCES.md`, `DECISIONS.md`. Do not attach `scripts/` or
`docs/plan/` — this task is about the math living in `src/`, not the automation around it.

**Known seed issues — start here, then go wider:**
- No golden/reference-value test exists anywhere in `tests/` that checks a Greeks
  calculation against an independently computed value (e.g. Black-Scholes delta at a fixed
  spot/strike/IV/DTE via `py_vollib` or hand calculation). Existing property tests
  (`test_delta_hypothesis.py`, `test_ivr_hypothesis.py`, `test_pnl_hypothesis.py`) check
  internal consistency (bounds, monotonicity), not correctness against ground truth — a
  systematically wrong but internally consistent formula would pass all of them.
- `PortfolioDeltaTracker.aggregate_delta`'s fallback approximation (CE=`net_qty/lot_size`,
  PE=`-net_qty/lot_size` when no chain-derived delta is supplied) — verify the sign
  convention and whether the WARNING-logged fallback path has ever been exercised against a
  real mispriced scenario in backtests.
- `ProfitLockEngine`'s floor formula `max(W,W)+D_cum+D_lock+K ≤ 0.75×C₀` — confirm the
  `max(W,W)` isn't a typo for two different wing-width variables collapsed to the same one.
- Verify put-call parity holds across `src/client/upstox_market.py`'s
  `parse_upstox_option_chain` output for any sampled chain in `tests/fixtures/responses/`.

**Task:**
1. `search_graph`/`get_code_snippet` every public function touching Greeks, delta, premium,
   or P&L math in the attached scope. Do not `Read` whole files first — Rule 0 applies here
   too even though this is a review, not an implementation session.
2. For each, write down the formula as you understand it, then independently derive or look
   up the correct formula and compare.
3. Flag every place `Decimal` is not used for a monetary field, and every float comparison
   using `==`.
4. Check `git log --oneline -10` on the 3-4 riskiest files for recent unexplained changes to
   thresholds or formulas without a corresponding `DECISIONS.md` entry.
5. Rate each finding CRITICAL (wrong result, real-money impact) / ERROR (wrong in an edge
   case) / WARNING (correct today, fragile) / INFO (stylistic).

**Output:** `docs/plan/full-repo-review/findings/FR-2_quant-reviewer.md` — one section per
finding, formula shown, correct derivation shown, severity, file:line.

**Closing block (include verbatim at the end of your own output file):**
> State the persona you reviewed as (Quant Reviewer). Name at least one perspective this
> review did not cover that a different persona would have caught — write "none identified"
> explicitly if genuinely nothing comes to mind, do not omit this section.

---

## FR-3 — Architecture & Design-Doc Consistency Review

**Persona:** Systems Architect — cross-document consistency, whether decisions recorded in
one doc are honored in the docs that depend on it, whether the story-file/epic structure
itself is internally coherent over its ~6-month history.

**Model:** Fable. This task requires holding the full document graph in mind at once —
`CONTEXT.md` ↔ `DECISIONS.md` ↔ `CONTEXT_TREE.md` ↔ `BACKTEST_PLAN.md`/`_PHASE1.md` ↔
`docs/plan/*` ↔ `docs/council/*` — and synthesizing across all of it in one pass, which is
exactly the long-horizon multi-file synthesis Fable is positioned for.

**Folder/files to attach:** full repo root markdown files (`CONTEXT.md`, `CONTEXT_TREE.md`,
`DECISIONS.md`, `REFERENCES.md`, `TODOS.md`, `PLANNER.md`, `BACKTEST_PLAN.md`,
`BACKTEST_PLAN_PHASE1.md`, `MISSION.md`, `GLOSSARY.md`, `LITERATURE.md`, `ANTIGRAVITY.md`),
plus `docs/plan/` and `docs/council/` in full, plus `docs/bugs/bugs.md`. Do not attach
`src/` or `tests/` — this task is documents-only; FR-2/FR-4/FR-5 cover code.

**Known seed issues — start here, then go wider:**
- `CONTEXT.md` "What Does NOT Exist Yet" claims `src/nuvama/CLAUDE.md` is unwritten; it
  exists (47 lines, confirmed 2026-07-04).
- `DECISIONS.md` (2026-07-04 entry) already documents `RapidCouncil` and `SignalAggregator`
  as unreconciled duplicate consensus mechanisms — confirm whether any story in `docs/plan/`
  references either in a way that assumes the other doesn't exist.
- `docs/plan/README.md`'s status table — spot-check 3 "Not started" entries against
  `git log` for the relevant `src/` paths; a story marked not-started with commits already
  landed against its scope is a stale-status bug, same class as the nuvama one above.
- Whether `BACKTEST_PLAN.md` (Phase 0) and `BACKTEST_PLAN_PHASE1.md` still describe a gate
  criterion (Phase 0.8) that has since been superseded by a later council ruling without the
  plan doc being updated to match.

**Task:**
1. Build a dependency map of which docs claim authority over which facts (e.g. "instrument
   keys live in REFERENCES.md" — do any other docs restate instrument keys that could drift?).
2. For every claim of the form "X does not exist yet" / "X is not implemented" / "status:
   not started", spot-check against the actual repo state (file existence, `git log`).
3. Check whether every "Active Story" in `docs/plan/README.md` has a folder that actually
   matches its declared `prompt.md`/`tasks.md`/`stories.md` convention (per the README's own
   "Conventions" section) — flag any structural drift.
4. Identify any decision recorded in `DECISIONS.md` that a *dependent* doc (a story file, a
   module `CLAUDE.md`) contradicts or fails to reflect.
5. Rate each finding CRITICAL (actively misleading, will cause wrong work) / ERROR (stale
   but low-blast-radius) / WARNING (drifting, not yet wrong) / INFO.

**Output:** `docs/plan/full-repo-review/findings/FR-3_systems-architect.md`.

**Closing block (include verbatim at the end of your own output file):**
> State the persona you reviewed as (Systems Architect). Name at least one perspective this
> review did not cover that a different persona would have caught — write "none identified"
> explicitly if genuinely nothing comes to mind, do not omit this section.

---

## FR-4 — Code Quality & Coding-Standard Compliance Sweep

**Persona:** Standards Auditor — mechanical, wide, cheap coverage against the rules already
written down in `REVIEW.md` and `LOGGING.md`. Not a judgment task; a counting task.

**Model:** Sonnet. This is grep-shaped work — enumerate every violation of an already-stated
rule across many files. It doesn't need Opus-level judgment or Fable-level long-horizon
synthesis, and running it on either would be paying for capability this task doesn't use.

**Folder/files to attach:** `src/`, `scripts/`, `REVIEW.md`, `LOGGING.md`. Do not attach
`docs/plan/` or `docs/council/` — those are FR-1's and FR-3's scope.

**Known seed issues — confirm current counts, do not assume these are still accurate:**
- 20 files using bare `logging.getLogger(__name__)` instead of
  `structlog.stdlib.get_logger(...)` (as of 2026-07-04 spot check).
- 22 scripts with an `if __name__ == "__main__":` entrypoint that never call
  `setup_logging()`.
- `REVIEW.md` §G7 ("logger calls must use `%`-style formatting") contradicts `LOGGING.md`'s
  keyword-argument rule for structlog calls — confirm this is still unreconciled and note
  every file where a correct structlog keyword-arg call would be wrongly flagged CRITICAL
  by a reviewer applying G7 literally.
- `print()` usage in `scripts/strategies/`, `scripts/portfolio/`, `scripts/lookup/`,
  `scripts/record/` (excluding `src/auth/*`, which may be legitimate interactive-CLI prompts
  — verify this exclusion is actually correct rather than assuming it).

**Task:**
1. Re-run the greps that produced the seed numbers above; report exact current counts (they
   may have changed since 2026-07-04) — do not report the seed numbers as current fact.
2. Check every Part III (G1–G8) rule in `REVIEW.md` against new-code diffs from the last 20
   commits (`git log --oneline -20`, then diff each) — Part III applies at diff level, not
   retroactively, so scope the check accordingly.
3. Grep for `# type: ignore` and `# noqa` — confirm each has an explanatory comment per
   `REVIEW.md`'s meta-rule.
4. Grep for `assert` outside `tests/` (G6 violation) and unjustified `except Exception`
   without an intent comment (G5 violation).
5. Rate each finding CRITICAL/ERROR/WARNING/INFO per the severities `REVIEW.md`'s own rules
   assign (G1, G5, G6, G7 are explicitly CRITICAL; G8 is ERROR).

**Output:** `docs/plan/full-repo-review/findings/FR-4_standards-auditor.md` — grouped by
rule ID, with exact file:line and current count, not the seed estimate.

**Closing block (include verbatim at the end of your own output file):**
> State the persona you reviewed as (Standards Auditor). Name at least one perspective this
> review did not cover that a different persona would have caught — write "none identified"
> explicitly if genuinely nothing comes to mind, do not omit this section.

---

## FR-5 — Test Adequacy & Ground-Truth Coverage Review

**Persona:** Test Auditor — not "do tests pass" but "what's untested that matters," with
particular focus on the gap between property tests (internal consistency) and golden tests
(correctness against an independent reference).

**Model:** Sonnet for the coverage sweep (mechanical: which public functions have zero
tests, which have only happy-path tests, which error/edge cases from `CLAUDE.md`'s mandatory
"one happy-path + one error/edge-case" rule are missing). **Escalate to Opus** for any
finding that touches Greeks/P&L/Decimal correctness specifically — Sonnet should flag the
gap, but whether a proposed golden test's expected value is actually correct is a quant
judgment call, not a coverage-counting one.

**Folder/files to attach:** `tests/`, `src/` (for cross-reference), `CLAUDE.md` (for the
"every public function needs one happy-path + one error/edge-case test" rule).

**Known seed issues — start here, then go wider:**
- No golden-value test exists for any Greeks calculation (see FR-2 seed #1 — this is the
  same gap from the test-coverage angle rather than the correctness angle; both tasks
  should cross-reference each other's findings in FR-7).
- No put-call parity check exists on the option chain parser.
- 3 hypothesis property-test files exist (`test_delta_hypothesis.py`,
  `test_ivr_hypothesis.py`, `test_pnl_hypothesis.py`) — confirm whether any *other* module
  with equally load-bearing math (e.g. `ProfitLockEngine`, `ExitSignalEngine`'s CSP/CC/PP
  thresholds) lacks an equivalent property-test suite despite comparable complexity.
- `pyproject.toml`'s coverage gate is `fail_under=80` — identify which specific
  under-80%-covered modules (if any currently sit below the line) are financial-logic
  modules vs. plumbing, since an 80% aggregate can hide a 40%-covered `src/risk/` file
  behind a 95%-covered `scripts/seed/`.

**Task:**
1. Run `python -m pytest tests/unit/ --cov=src --cov-report=term-missing --tb=no -q`
   (Rule 1 applies — do not dump full output; extract per-module coverage percentages only).
2. Cross-reference every public function in `src/risk/`, `src/paper/`, `src/strategy/`
   against its test file — is there a test that would fail if the *sign* of a calculation
   were flipped? (Property tests checking bounds often would not catch this; a golden test
   would.)
3. For every finding requiring a judgment call on whether a proposed reference value is
   correct, write the finding but flag it `NEEDS-OPUS-REVIEW` rather than asserting a
   golden value yourself if you are not confident in the derivation.
4. Rate each finding CRITICAL (financial logic with zero correctness-checking test) / ERROR
   (financial logic with property tests but no golden test) / WARNING (non-financial gap) /
   INFO.

**Output:** `docs/plan/full-repo-review/findings/FR-5_test-auditor.md`.

**Closing block (include verbatim at the end of your own output file):**
> State the persona you reviewed as (Test Auditor). Name at least one perspective this
> review did not cover that a different persona would have caught — write "none identified"
> explicitly if genuinely nothing comes to mind, do not omit this section.

---

## FR-6 — Security & Operational-Risk Review

**Persona:** Red-Team Reviewer — assume adversarial conditions: a leaked token, a malformed
API response, a network partition mid-order, a config error in prod vs. sandbox. Where does
this system fail unsafely rather than fail loudly?

**Model:** Opus. Security/operational-risk judgment on a system with real order-execution
paths (even if currently blocked pending static IP) warrants the same rigor as the financial
logic review, not a lighter pass.

**Folder/files to attach:** `src/client/` (all 4 `BrokerClient` implementations +
`exceptions.py` + `factory.py`), `src/auth/`, `src/config.py`, `.env.example`,
`.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `src/notifications/telegram_gateway.py`.

**Known seed issues — start here, then go wider:**
- Confirm no `.env` file is tracked in git (`git ls-files | grep .env`) and that
  `detect-secrets` pre-commit hook is actually active, not just configured.
- Confirm `factory.py` is genuinely the sole composition root — grep for any direct import
  of `UpstoxLiveClient` or `MockBrokerClient` outside `factory.py` and outside `tests/`.
- Confirm the `BrokerError` exception hierarchy's retryable/terminal split
  (`RateLimitError`/`DataFetchError` vs. `OrderRejectedError`/`InstrumentNotFoundError`) is
  actually respected everywhere a broker call is retried — a retry loop that retries a
  terminal exception is a real-money bug (duplicate order submission risk), not just a
  style issue.
- `TelegramGateway`'s chat-ID allowlist enforcement — verify it's checked on every inbound
  callback path, not just the initial approval request.
- CI (`ci.yml`) forces `UPSTOX_ENV=test` — confirm no code path can accidentally hit the
  live Upstox API during CI regardless of env misconfiguration (defense in depth, not just
  "the env var is set correctly").

**Task:**
1. Trace every retryable-exception catch site (`search_code`/`trace_path` on
   `RateLimitError`, `DataFetchError`) and confirm the retry logic can't loop on a terminal
   exception subclassing the same catch.
2. Check `src/config.py`'s `Settings` singleton for any field that logs its own value
   (token/secret fields must never appear in structured log output — cross-check against
   `LOGGING.md`'s "the actual values involved in the decision" guidance, which could
   conflict with secret-safety if applied carelessly to an auth module).
3. Verify `MockBrokerClient` is genuinely incapable of hitting a live endpoint under any
   input, including malformed config.
4. Check whether any `NotImplementedError`-raising blocked method (order execution) has a
   code path that could silently no-op instead of raising, if a future refactor changes
   the exception handling around it.
5. Rate each finding CRITICAL (exploitable or real-money-risk) / ERROR (defense-in-depth
   gap) / WARNING / INFO.

**Output:** `docs/plan/full-repo-review/findings/FR-6_red-team-reviewer.md`.

**Closing block (include verbatim at the end of your own output file):**
> State the persona you reviewed as (Red-Team Reviewer). Name at least one perspective this
> review did not cover that a different persona would have caught — write "none identified"
> explicitly if genuinely nothing comes to mind, do not omit this section.

---

## FR-7 — Missing-Persona / Blind-Spot Synthesis

**Persona:** Chairman — same role as `RapidCouncil`'s chairman-synthesis stage (see
`src/council/rapid.py`, currently unwired but structurally the right model for this step):
read all Stage-1 outputs, do not re-derive their findings, synthesize and rank.

**Model:** Fable. This step requires reading six full findings documents plus this repo's
existing council-output conventions and holding all of it in context to judge what's
missing — the same long-horizon synthesis role as FR-1/FR-3, applied to the panel's own
output rather than the repo directly.

**Folder/files to attach:** `docs/plan/full-repo-review/findings/` (all six FR-1..FR-6
outputs, which must exist before this task can start — do not run FR-7 out of order),
`docs/council/README.md`, one existing `docs/archive/council/strategy/*.md` file as a
formatting reference for Stage 3 synthesis style.

**Task:**
1. Read each of `FR-1` through `FR-6`'s findings files in full.
2. Read each file's closing "missing perspective" block specifically — this is the primary
   input for this task, not an afterthought. Where multiple reviewers named the same gap
   independently, that is a high-confidence signal a 7th persona is genuinely missing (e.g.
   if both Quant Reviewer and Test Auditor separately flag "no one is checking regulatory/
   SEBI-compliance implications of the April 2026 Tuesday-expiry change on any of this
   logic," that's not a coincidence to ignore).
3. Cross-reference findings across documents — does FR-2's Greeks-formula finding and FR-5's
   test-coverage finding describe the same underlying gap from two angles? Merge, don't
   duplicate.
4. Produce a Summary Table in the same style as `docs/archive/council/strategy/*.md`'s
   Stage 3 output: one row per distinct finding, columns for severity, source task(s),
   one-line description, recommended action.
5. Produce an explicit "Personas Not Represented" section: list every gap named across all
   six closing blocks, deduplicated, and state whether each is (a) worth a follow-up review
   pass with an 8th persona, (b) already covered by an existing role this panel just didn't
   invoke correctly, or (c) not worth pursuing and why.

**Output:** `docs/plan/full-repo-review/findings/FR-7_synthesis.md`.

**Closing block (include verbatim at the end of your own output file):**
> State the persona you reviewed as (Chairman). Name at least one perspective this review
> did not cover that a different persona would have caught — write "none identified"
> explicitly if genuinely nothing comes to mind, do not omit this section. (Yes, this
> applies to the Chairman step too — a synthesis pass can itself have blind spots, e.g.
> over-weighting the most articulate reviewer's findings rather than the most correct ones.)

---

## FR-8 — Tooling Usage Guide: Claude Code vs. Cowork vs. Antigravity Handoff, by Job Type

**Persona:** Practitioner/DevEx — not "is the protocol internally consistent" (that's
FR-1), but "if I am a developer starting a task right now, which surface do I open, and
why." This is the piece that was actually missing from the review as originally scoped:
every other task audits whether existing docs are correct; this one produces a decision
guide that doesn't fully exist yet in one place.

**Model:** Sonnet. This is synthesis of already-known, already-documented criteria (Step 3b
in root `CLAUDE.md`, `ANTIGRAVITY.md`, `docs/antigravity/ai_collaboration_plan.md`) plus
general knowledge of what each surface (Claude Code CLI, Cowork, Antigravity) is actually
built for — it's a collation-and-clarification task, not a deep judgment call. Read
`findings/FR-1_protocol-reviewer.md` first (must exist before this task starts) — do not
re-derive protocol ambiguities FR-1 already found; build the guide around them.

**Folder/files to attach:** root `CLAUDE.md` (Step 3b specifically), `ANTIGRAVITY.md`,
`docs/antigravity/ai_collaboration_plan.md`, `docs/plan/full-repo-review/findings/FR-1_protocol-reviewer.md`.

**Task:**
1. Extract the current Step 3b routing criteria verbatim (when Claude implements vs. when
   Antigravity implements) and restate them as a decision table, not prose.
2. Add a second axis this repo's docs don't currently cover explicitly: Claude Code (CLI,
   local terminal, hooks, direct filesystem) vs. Cowork (sandboxed shell, skills, subagent
   model overrides including `fable`/`opus`/`sonnet`, task-list widget, no local hook
   support) — when is one surface clearly better suited than the other for this repo's kind
   of work (e.g. a quick single-file fix at your desk vs. a multi-hour audit like this very
   epic vs. a job needing a specific model override like FR-2/FR-3/FR-6/FR-7 here).
3. For at least 6 concrete job types drawn from this repo's actual history (a BACKTEST_PLAN
   Phase 0 task, a council-gated architecture decision, a mechanical logging-migration
   fix, a golden-value test authoring task, a cron/daemon debugging session, a full-repo
   review task like this epic), state: recommended surface, recommended model (if
   choosable), and why — cite the FR-1 finding if it flagged ambiguity relevant to that job
   type.
4. Explicitly cover the Antigravity handoff mechanics: what the structured handoff prompt
   must contain (per Step 3b), what "Phase Completion Output" Claude must verify (SHA match,
   test count) before closing the phase, and what to do when verification fails (per
   existing CLAUDE.md instruction: open a fix session with failure details — confirm this
   is still accurate or flag if FR-1 found it stale).
5. Flag anywhere this guide has to make a judgment call the existing docs don't actually
   settle — those are candidates for a `DECISIONS.md` entry, not something to guess at
   silently.

**Output:** `docs/plan/full-repo-review/findings/FR-8_practitioner-devex.md`.

**Closing block (include verbatim at the end of your own output file):**
> State the persona you reviewed as (Practitioner/DevEx). Name at least one perspective this
> review did not cover that a different persona would have caught — write "none identified"
> explicitly if genuinely nothing comes to mind, do not omit this section.

---

## FR-9 — Build Implementation Roadmap Folder + DECISIONS.md Update

**No model assignment — this is mechanical synthesis, not review.** Whoever runs this (any
model, or the human operator directly) is assembling already-produced findings into an
actionable structure, not generating new judgment.

**Folder/files to attach:** `docs/plan/full-repo-review/findings/` (all eight files),
`docs/plan/README.md`, `DECISIONS.md`.

**Task:**
1. For every CRITICAL/ERROR finding in `FR-7_synthesis.md`'s Summary Table that maps to a
   concrete code or doc change, create a new story stub under `docs/plan/` following the
   existing `prompt.md`/`tasks.md`/`stories.md` convention (see `docs/plan/README.md`
   "Conventions" section) — one new story folder per coherent group of related findings,
   not one giant undifferentiated backlog. Name folders descriptively
   (`logging-migration-completion/`, `greeks-golden-tests/`, `docs-consistency-cleanup/`,
   etc. — actual names depend on what FR-7 found).
2. Fold `FR-8_practitioner-devex.md`'s tooling guide into a durable location — either a new
   section in root `CLAUDE.md` (if FR-8 found the current Step 3b guidance genuinely
   incomplete) or a pointer row added to `CONTEXT.md`/`CLAUDE.md` referencing where the
   guide lives, following the same "targeted `Edit`, never `Write`-over" rule as every other
   doc update in this repo. Do not leave the guide stranded only inside `findings/` where
   nothing points to it.
3. Read FR-1's recommendation on whether the "Operating philosophy" (co-investor framing)
   block should be promoted into root `CLAUDE.md`'s "AI Collaboration" section. If FR-1
   recommended promote or revise-then-promote, add it there (targeted `Edit`, scoped to
   what FR-1 actually recommended — do not paste the full epic-specific block verbatim if
   FR-1 flagged parts of it as review-context-specific). If FR-1 recommended keep-scoped,
   leave `docs/plan/full-repo-review/prompt.md` as the sole location and note the decision
   + reasoning in this task's own commit message so it isn't silently dropped.
4. Add a row to `docs/plan/README.md`'s "Active Stories" table for each new story folder
   created, status `⬜ Not started`.
5. Update `DECISIONS.md` per the existing Council Decision Protocol (root `CLAUDE.md`):
   add one entry citing this review epic as the source, dated, with the Summary Table
   findings and any "Noted, deferred" items from FR-7's "Personas Not Represented" section
   logged as dissenting/deferred notes.
6. Do **not** implement any fix in this task — new story folders contain only specs, no
   code changes. This task's own commit is docs-only.

**Verify:**
- `docs/plan/full-repo-review/findings/` contains 8 files (FR-1 through FR-8).
- At least one new story folder exists under `docs/plan/` for each CRITICAL finding.
- `docs/plan/README.md` lists every new folder.
- Root `CLAUDE.md` or `CONTEXT.md` points to where the FR-8 tooling guide lives.
- `DECISIONS.md` has a new dated entry referencing this epic.

**Commit:** `docs(plan): full-repo-review synthesis + implementation roadmap`

**Docs close:** add one line to `TODOS.md` marking `full-repo-review` FR-1..FR-9 complete,
with a pointer to the new story folders it spawned.
