# FR-8 — Tooling Usage Guide: Claude Code vs. Cowork vs. Antigravity, by Job Type

**Persona:** Practitioner/DevEx
**Model:** Sonnet
**Date:** 2026-07-06
**Scope read:** root `CLAUDE.md` (Step 3b), `ANTIGRAVITY.md`, `docs/antigravity/ai_collaboration_plan.md`, `findings/FR-1_protocol-reviewer.md`.

This is a decision guide, not an audit. FR-1 already found the protocol ambiguities; this document
builds the practitioner-facing routing table around them and cites FR-1 findings by ID rather than
re-deriving them.

---

## 1. Step 3b, verbatim, as a decision table

Root `CLAUDE.md` Step 3b currently reads as prose. Restated as a table (no content added — this is
a literal transcription):

| Condition | Route to |
|---|---|
| Task spans 3+ files with clear, non-ambiguous spec | Antigravity |
| TDD loop needed (write tests first, iterate to green) | Antigravity |
| Phase is from `BACKTEST_PLAN.md` with a fully documented DoD | Antigravity |
| Implementation is mechanical — no real-time design decisions expected | Antigravity |
| Single file or 2-file task where inline judgment calls are likely | Claude |
| Exploratory work where the spec may change as code is written | Claude |
| Any task requiring graph queries mid-implementation to resolve ambiguity | Claude |

Per **FR-1 F-E1**, this table's applicability to ≤2-file tasks that never triggered Step 3's
go-ahead gate is unresolved in the source doc — treat "route to Claude/Antigravity" as firing
regardless of file count until that ambiguity is settled (see §5 below).

Note `docs/antigravity/ai_collaboration_plan.md`'s stated scope ceiling: Antigravity is "most
effective on tasks spanning 3–5 files"; beyond 5, Claude must decompose into sub-phases with
separate handoffs and commits before delegating. This is a real constraint the Step 3b table above
does not itself state — add it as an implicit upper bound on the "3+ files" row.

---

## 2. Second axis: Claude Code vs. Cowork

Neither `CLAUDE.md` nor `ANTIGRAVITY.md` distinguishes these two Claude surfaces — both assume "Claude"
means a single thing. In practice they differ materially for this repo:

| Property | Claude Code (CLI) | Cowork |
|---|---|---|
| Filesystem access | Direct, local, no mount translation | Sandboxed shell; bash paths differ from tool paths (mount translation) |
| Hooks (`.claude/hooks/*`) | Supported — Rule 0's PreToolUse hook fires | Not supported — no hook enforcement, Rule 0 becomes purely self-attested (compounds **FR-1 F-W1**) |
| Subagents | `.claude/agents/*` spawn natively in the same environment | Subagent model overrides (`fable`/`opus`/`sonnet`) via `Agent`; each spawn is cold, no shared session state |
| Task/todo tracking | Ad hoc (TODOS.md, story files) | Native task-list widget (`TaskCreate`/`TaskUpdate`) — visible progress UI |
| Skills | N/A (skills are a Cowork/plugin concept) | First-class — docx/xlsx/pptx/pdf output skills, nse-option-chain domain skill |
| Best for | Long, stateful sessions where Rule 0 must actually block, not just remind | Bounded audits/reviews with a concrete deliverable, or work needing a per-subagent model tier |

For Cowork, "hook-enforced" does not apply (hooks are unsupported) and "a concrete deliverable" means a review file, a spreadsheet, or a multi-persona sweep.

**Practical rule:** if the task depends on the PreToolUse hook actually firing (i.e., you are
trusting Rule 0 to be enforced rather than self-narrated), use Claude Code — Cowork cannot enforce
it, only remind. If the task is a bounded review/audit epic that produces a numbered findings file
(exactly what FR-2/FR-3/FR-6/FR-7/this document are), Cowork's per-agent model override and
task-list widget are a better fit than a single long Claude Code session.

---

## 3. Six job types — surface, model, rationale

**1. BACKTEST_PLAN Phase 0 task (e.g., a `src/paper/` or `src/risk/` implementation phase with a documented DoD).**
Surface: Antigravity (per Step 3b row 3 — DoD is fully documented, mechanical once scoped).
Model: N/A (Antigravity is a fixed Gemini engine, not a model choice).
Rationale: Matches the "Phase is from BACKTEST_PLAN.md" row exactly. Claude's role is upstream
(compose the handoff prompt per `ai_collaboration_plan.md` §4's four required elements) and
downstream (run the real `@code-reviewer` gate — **FR-1 F-C1**: this gate cannot be satisfied
in-process by Antigravity itself, so Claude Code is the surface for that half of the phase, not
Cowork, since the gate is meant to block a live commit in the same session Antigravity is running).

**2. Council-gated architecture decision (all three Step 2b criteria met: load-bearing, two
defensible approaches, multi-discipline).**
Surface: Claude (Step 2b is explicitly "Claude's responsibility... Antigravity does not trigger the
council" per root CLAUDE.md's AI Collaboration section). Claude Code, not Cowork — this needs the
live graph MCP (`codebase-memory-mcp`) wired into the same environment as the ongoing implementation
session, not a cold Cowork subagent spawn.
Model: Opus, per the pattern in FR-0/FR-1 (protocol/architecture review consistently escalated to
Opus in this repo's own review history).
Rationale: Per **FR-1 F-E2**, three docs currently describe this checkpoint three different ways
(manual self-check / `options-strategist` advisory spawn / "Claude simulates it"). Until that's
resolved, the safest practitioner default is: Claude does the manual three-condition check itself
(Step 2b body text, the most literal reading), and only spawns `options-strategist` as an advisory
second opinion, never as the sole mechanism — treat this as a judgment call, not settled doctrine.

**3. Mechanical logging-migration fix (e.g., swapping `logging.getLogger(__name__)` for the
`structlog` pattern across several `scripts/` files per `LOGGING.md`).**
Surface: Antigravity if it spans 3+ files (Step 3b row 4 — "no real-time design decisions
expected" fits a mechanical rename/pattern-migration exactly) — otherwise Claude Code for a 1-2 file
version.
Model: N/A / Sonnet for Claude's half (review only).
Rationale: This is close to the textbook "mechanical, no judgment calls" case Step 3b was written
for. The pre-commit hook `no-script-main-logger` gives Antigravity (or Claude) a hard verification
signal — good fit for autonomous execution since correctness is machine-checkable, not
judgment-based.

**4. Golden-value test authoring task (writing new tests for a domain model — Pydantic/dataclass
— per the mandatory pre-step in CLAUDE.md Step 4).**
Surface: Claude Code. This explicitly requires "graph queries mid-implementation to resolve
ambiguity" (Step 3b's third Claude-routing row) — the mandatory `get_code_snippet`/`search_graph`
pre-step before writing any `_make_*`/`build_*` helper is precisely graph-dependent, live-session
work. Cowork's cold subagent spawns are a poor fit here because the graph MCP context (index status,
prior queries in-session) doesn't carry over between spawns.
Model: Sonnet — mechanical enough once the graph query returns the field list, no architecture
judgment required.
Rationale: Matches Step 3b's "requiring graph queries mid-implementation" criterion directly; also
this is exactly the failure class CLAUDE.md documents from 2026-04-25 (`Direction.SHORT` /
`entry_date` errors from memory-written helpers) — a cold Cowork agent without the live graph
session is at higher risk of repeating it, not lower.

**5. Cron/daemon debugging session (e.g., `logs/snapshot.log` failures, `daily_snapshot.py`
misbehavior).**
Surface: Claude Code. Debugging is inherently exploratory — spec is not fixed, hypotheses form and
get discarded mid-session (Step 3b's "exploratory work where the spec may change" row). This also
touches the live DB / cron environment, which `ANTIGRAVITY.md` explicitly flags as a
"destructive target requiring approval before any write" — better handled interactively in Claude
Code where Animesh is present turn-by-turn than handed to an autonomous Antigravity run.
Model: Sonnet, escalate to Opus only if the root cause implicates a Decimal/Greeks correctness bug
(then it becomes financial logic, triggering the mandatory real `@code-reviewer` gate).
Rationale: Bash Output Discipline (Rule 1) applies here regardless of surface — `tail -20` /
`grep ERROR`, never `cat`, on `logs/snapshot.log`.

**6. Full-repo review task (an epic like this one — FR-0 through FR-9).**
Surface: Cowork. This is the one job type this repo's docs don't yet describe explicitly, but the
fit is strong: bounded scope (produces one numbered findings file per persona), benefits from the
task-list widget to track FR-0..FR-9 progress visibly, and — critically — benefits from per-agent
model overrides (Fable for FR-0's meta-validation-pilot framing, Opus for FR-1/FR-2/FR-6's
adversarial/protocol work, Sonnet for FR-8/FR-4's collation work) in a way a single Claude Code
session cannot cleanly express.
Model: Varies per FR — see each finding file's own model line; this document itself is Sonnet.
Rationale: None of `CLAUDE.md`/`ANTIGRAVITY.md` describe this job type at all (it's this epic
itself) — this entry is this document's own synthesis, not a citation.

---

## 4. Antigravity handoff mechanics

**What the structured handoff prompt must contain** (per `ai_collaboration_plan.md` §4, Phase B,
step 1 — four mandatory elements):

1. **Reading list** — explicit `view_file` paths Antigravity must read before writing any code.
   `CONTEXT.md` is mandatory in every handoff; add `BACKTEST_PLAN.md`, `DECISIONS.md`, the relevant
   module `CLAUDE.md`, etc., as the task requires.
2. **Objective** — one-sentence statement of what to build.
3. **Pointers** — explicit file paths or graph queries. Do not rely on Antigravity to discover scope
   on its own.
4. **Boundaries** — files that must not be touched, off-limits patterns, financial-gate reminders
   (e.g., "do not touch `CONTEXT.md` with `write_to_file`; stop before commit and emit
   `CODE REVIEW GATE`").

Do not paste code into the handoff prompt.

**What "Phase Completion Output" Claude must verify before closing the phase** (per
`ANTIGRAVITY.md`'s "Phase Completion Output" block):

- `files_changed` — cross-check against `git diff --name-only HEAD~1`.
- `tests_added` / `tests_passing` — cross-check against `pytest --tb=no -q` final summary line and
  `grep -c "def test_"` on the new test file(s).
- `commit_sha` — the load-bearing check: **confirm this SHA matches the tip of
  `git log --oneline -1`** before treating the phase as closed. Root `CLAUDE.md` Step 3b states this
  exact verification requirement ("Claude verifies: SHA matches `git log --oneline -1`, test count
  meets DoD").

**What to do when verification fails:** root `CLAUDE.md` Step 3b states — "Claude opens a fix
session with the failure details." Cross-checked against **FR-1's F-C1 finding**: this instruction
is still accurate as written and is not flagged stale by FR-1. However, FR-1's F-C1 does surface an
adjacent gap that a practitioner will hit immediately after a failed verification on a `.py`-file
phase: if the fix requires the `code-reviewer`/`test-runner` AutoTrigger gates, and Antigravity
cannot spawn those subagents, the "fix session" Claude opens must itself run those gates directly
(Claude Code, not a re-handoff to Antigravity) rather than assuming Antigravity's own re-attempt
will satisfy them. This is not contradicted by any doc — it is the practical consequence of F-C1
that a practitioner should know going in, not something CLAUDE.md currently spells out.

---

## 5. Judgment calls this guide had to make (not settled by existing docs — candidates for `DECISIONS.md`)

1. **Step 3b applicability below the 2-file go-ahead threshold** (§1). I assumed the routing table
   fires regardless of file count, per FR-1 F-E1's own recommended fix ("routing applies to every
   task regardless of file count"). This is FR-1's proposed resolution, not yet an actual decision
   recorded in `DECISIONS.md` — until it is, treat §1's "regardless of file count" framing as this
   document's assumption, not settled protocol.
2. **Council-checkpoint mechanism for job type #2** (§3, item 2). I picked "Claude does the manual
   check itself, `options-strategist` is advisory-only" as the safe default among three
   non-identical descriptions (FR-1 F-E2). This is my judgment call, not a resolution — FR-9 (or a
   direct `DECISIONS.md` entry) should pick one mechanism authoritatively.
3. **Claude Code vs. Cowork as a named axis at all** (§2). This distinction does not exist anywhere
   in the repo's current docs — I constructed the comparison table from first-hand knowledge of what
   each surface supports (hook enforcement, mount translation, subagent model overrides), not from a
   citation. If this guide is promoted into a doc practitioners rely on, the hook-enforcement claim
   specifically ("Cowork has no hook support, Rule 0 becomes purely self-attested there") should be
   spot-checked against actual Cowork capability, since it materially changes which surface is
   "safer" for Rule 0-dependent work.
4. **Model recommendation for job type #5 (cron debugging) escalating to Opus only on Decimal/Greeks
   involvement.** This is my own heuristic, extrapolated from the existing "financial logic commits
   require real code-reviewer" rule in root CLAUDE.md — not a documented model-selection rule for
   debugging specifically. Worth confirming as an explicit `DECISIONS.md` line if this guide is
   adopted as practitioner doctrine.

---

> State the persona you reviewed as (Practitioner/DevEx). Name at least one perspective this
> review did not cover that a different persona would have caught — write "none identified"
> explicitly if genuinely nothing comes to mind, do not omit this section.

**Persona reviewed as: Practitioner/DevEx.**

**Perspectives this review did not cover:**

1. **Execution-environment / tooling-surface auditor** (named explicitly by FR-1's own closing
   block as a gap it left for FR-8 to "partially cover"). FR-1 asked whether *every rule in
   CLAUDE.md* is physically satisfiable on *every* surface (Claude Code CLI, Cowork subagent,
   Antigravity) — a systematic per-rule audit. This document only covers the *routing guidance*
   (which surface to pick for which job), not a rule-by-rule satisfiability audit of the full
   protocol on each surface. A dedicated tooling-surface persona would take each numbered rule in
   root `CLAUDE.md` (Rule 0, Rule 1, Step 2b, Step 3b, the AutoTrigger table, the Commit Protocol)
   and test it mechanically against what Cowork/Claude Code/Antigravity can each *actually do*, the
   way FR-1's F-C1 did for one rule almost by accident. That systematic pass is still missing.
2. **Cost/latency auditor.** This guide recommends model tiers (Opus/Sonnet) per job type based on
   task-complexity heuristics, but never measures actual cost or latency tradeoffs of routing a task
   to Antigravity (async, potentially slower but unattended) vs. Claude Code (synchronous, faster
   turnaround but requires Animesh present) vs. Cowork (bounded subagent spawns, cold-start
   overhead). A dedicated persona could quantify this and turn "recommended surface" into "cheapest
   surface that meets the quality bar."
