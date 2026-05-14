# NiftyShield — Workflow Improvements Session
**Date:** 2026-05-08
**Participants:** Animesh, Claude (Cowork), Antigravity (consulted via relay)
**Purpose:** Audit existing AI tooling, identify enforcement gaps, implement improvements for token efficiency and protocol compliance.

---

## Starting Point — What Existed

### Skills (`.claude/skills/`)
- `commit/SKILL.md` — format-only template, `disable-model-invocation: true`. Never executed commits, only produced messages for the human to paste.
- `md-cleanup/SKILL.md` — manually invoked housekeeping.

### Agents (`.claude/agents/`)
- `code-reviewer.md` — Opus (outdated: `claude-opus-4-5`)
- `test-runner.md` — Haiku (outdated: `claude-haiku-4-5`)
- `greeks-analyst.md` — Sonnet (outdated: `claude-sonnet-4-5`)
- `roll-validator.md` — Opus (outdated: `claude-opus-4-5`)
- `options-strategist.md` — Opus (outdated: `claude-opus-4-5`)

### Hooks (`.claude/hooks/`)
- `guard_src_reads.sh` — PreToolUse on Read. Warns when `src/` or `scripts/` is read without querying the graph first. **Only working enforcement mechanism.**

### Core Problems Identified
1. Commit skill was a template — commits kept getting skipped or handed to the user to run manually.
2. Sub-agents never triggered automatically — had to be explicitly requested every time.
3. No prompt review mechanism — vague prompts led to wrong implementations and wasted tokens.
4. Council checkpoint (Step 2b) was memory-dependent — no enforcement.
5. All model strings were outdated.
6. No Antigravity handoff skill — handoff prompts were vague, causing Antigravity to waste 2–3 tool calls reading files it could have received inline.
7. No routing decision at plan go-ahead — Claude vs Antigravity fork was implicit and always defaulted to Claude.

---

## Antigravity Consultation (Key Findings)

Questions sent to Antigravity via Animesh as relay. Critical answers:

**Auto-loading:** Antigravity does NOT auto-load `CONTEXT.md` or `ANTIGRAVITY.md`. Must explicitly read them each session or receive content inline in the prompt.

**Code-reviewer approximation:** Antigravity reliably catches Decimal invariant, BrokerClient protocol, type hints, async correctness, and hardcoded strategy names. It **misses** `REVIEW.md` general Python hygiene rules (mutable defaults, late-binding closures, set iteration order, etc.) unless that file is loaded into context.

**Structured output:** Yes — can produce `files_changed`, `tests_added`, `tests_passing`, `commit_sha` block at phase end.

**Token cost:** 15,000–25,000 input tokens per turn for a 3-file, 150-line implementation. 2-3 mandatory file reads at session start account for ~3,000–5,000 of those tokens.

**Handoff prompt:** Can execute directly from a structured prompt (OBJECTIVE / GRAPH_POINTERS / BOUNDARIES / CONTEXT_EXTRACT / DOD / RULES_SUMMARY), but will still read `CONTEXT.md` and `BACKTEST_PLAN.md` per protocol unless that content is injected inline.

**Implication:** The handoff skill should inject content inline, not reference file paths. Each file read eliminated saves ~1,000–2,000 input tokens.

---

## What Was Built

### 1. Commit Skill — Converted to Executor
**File:** `.claude/skills/commit/SKILL.md`
**Change:** Removed `disable-model-invocation: true`. Rewrote as 5-step executable workflow:
1. Review `git diff HEAD`
2. Run `python -m pytest tests/unit/ --tb=no -q` — all must pass
3. Construct commit message in project format
4. Stage and commit via bash
5. Run `git log --oneline -1` — SHA must appear (proof of completion)

**Key rule added:** For financial logic commits (Decimal, P&L, Greeks, BrokerClient) → stop, invoke real `@code-reviewer` subagent. For non-financial → persona adoption with both `code-reviewer.md` and `REVIEW.md` in context.

### 2. Agent Model Declarations Updated
All 5 agent files updated to current model strings:
- `code-reviewer.md`: `claude-opus-4-6`
- `test-runner.md`: `claude-haiku-4-5-20251001`
- `greeks-analyst.md`: `claude-sonnet-4-6`
- `roll-validator.md`: `claude-opus-4-6`
- `options-strategist.md`: `claude-opus-4-6`

**Routing rationale:** Haiku for pass/fail test runs (no reasoning needed). Sonnet for orchestration, planning, graph queries. Opus for code review, roll validation, strategy design — decisions with financial consequence.

### 3. AutoTrigger Table Added to CLAUDE.md
Added between Step 4 and Step 5. Five agents, explicit trigger conditions, blocking vs advisory:

| Agent | Trigger | Blocking? |
|---|---|---|
| `test-runner` (Haiku) | After any code edit | Yes — before code-reviewer |
| `code-reviewer` (Opus) | Before every code commit | Yes — CRITICAL/ERROR must resolve |
| `greeks-analyst` (Sonnet) | Any `src/paper/`, option chain, or delta/gamma change | Yes |
| `roll-validator` (Opus) | Roll logic or `roll_leg.py` change | Yes |
| `options-strategist` (Opus) | Council checkpoint Step 2b (no real council warranted) | Advisory |

Financial logic commits: real `@code-reviewer` is mandatory — Antigravity's persona approximation is insufficient.

### 4. Step 3b — Implementation Routing Gate Added to CLAUDE.md
Added after Step 3 (plan go-ahead), before Step 4 (tests). Explicit fork:

**Claude implements:** Proceed to Step 4. AutoTrigger agents fire during/after. Claude commits via commit skill.

**Antigravity implements:** Invoke `handoff-antigravity` skill now. Produce structured prompt. **Stop. Do not write code.** Antigravity returns Phase Completion Output. Claude verifies SHA + test count.

**When to choose Antigravity:** 3+ files, complete spec, TDD loop needed, no real-time design decisions.
**When Claude implements:** 1–2 file task, exploratory work, graph queries needed mid-implementation.

### 5. Council-Check Hook
**File:** `.claude/hooks/council_check.sh`
**Type:** PreToolUse on Edit and Write
**Behaviour:** Warn-only (exit 0). Outputs the 3 council trigger criteria as a reminder before any file is edited.

### 6. Prompt-Refine Skill
**File:** `.claude/skills/prompt-refine/SKILL.md`
**Purpose:** Scores incoming prompts on 8 dimensions. If 2 or fewer missing, fills gaps from CONTEXT.md and proceeds. If 3 or more missing, asks ONE targeted clarifying question (priority: files → phase → DoD → boundaries → tests).
Produces rewritten prompt targeting ≤200 tokens, dense and precise.

### 7. Handoff-Antigravity Skill
**File:** `.claude/skills/handoff-antigravity/SKILL.md`
**Purpose:** Produces structured Antigravity prompt with content injected inline (not file references). Five sections:
- `OBJECTIVE` — one sentence
- `GRAPH_POINTERS` — specific `search_graph()` calls to run first
- `BOUNDARIES` — off-limits files + non-negotiable invariants
- `CONTEXT_EXTRACT` — active phase block (≤30 lines) + relevant module state (≤20 lines)
- `REVIEW_RULES` — 10 Python hygiene checks from REVIEW.md
- `DOD` — test count, CONTEXT.md update, commit SHA
- `QUALITY_GATES` — Antigravity's tooling equivalents (pytest for test-runner, persona adoption for non-financial commits)
- `STOP_CONDITIONS` — when to pause and relay to Claude (design fork), when to proceed autonomously
- `PHASE_COMPLETION_OUTPUT` — structured block with `files_changed`, `tests_added`, `tests_passing`, `commit_sha`, `ambiguities_noted`

**Token impact:** Eliminates 2–3 mandatory file reads at Antigravity session start (~3,000–5,000 tokens saved per session).

### 8. Antigravity Protocol Hardened
**File:** `ANTIGRAVITY.md`
**Changes:**
- Commit protocol Step 2 split into two tiers: financial (stop, relay to Claude for real `@code-reviewer`) vs non-financial (persona adoption with both `code-reviewer.md` + `REVIEW.md`)
- Phase Completion Output block added as mandatory end-of-phase output
- `ambiguities_noted` field added to structured output

### 9. UserPromptSubmit Hook — Task Classification
**File:** `.claude/hooks/task_protocol.sh`
**Type:** UserPromptSubmit — fires when a message is sent, before AI processes it
**Behaviour:** Classifies prompt as task vs query using keyword patterns.

**Task keywords (hook fires):** implement, fix, add, build, create, write, update, refactor, migrate, roll, backtest, record, seed, scaffold, change, modify, convert, replace, wire, extend, integrate, enable

**Query keywords (hook skips):** what, why, how does, explain, show me, list, can you, does, is, are, which, when, where, who, review what, read, check what, tell me

**Important gotcha:** "can you fix X" matches the query pattern and skips. Start task prompts with the action verb directly: "fix X", not "can you fix X".

Injects a compact 4-step checklist (prompt scoring → council check → plan + go-ahead → routing decision) only for task prompts.

### 10. Prompt Crafting Guide Added to INSTRUCTION.md
New section between "Session Start Workflow" and "Per-Task Prompt Templates". Covers:
- Two prompt types and how to phrase them
- Four completeness dimensions (files, phase, tests, DoD) with examples
- Routing directive syntax to append to any prompt
- Four copy-paste templates (minimal task, feature+phase, bug fix, query)

---

## What Still Doesn't Work

### Agent AutoTriggering — Root Cause
The AutoTrigger table in CLAUDE.md states agents are "not optional," but the only actual enforcement is documentation. The AI can still inline pytest rather than spawning the `test-runner` agent, and inline a review rather than spawning `code-reviewer`. Observed in the IVR implementation task: 11 tests ran, commit was made, SHA confirmed — but neither agent was spawned.

**Why the hook doesn't fix this:** `UserPromptSubmit` injects a checklist, but it's text the AI reads and can still override under task pressure. There's no mechanism that fires at the moment pytest is called inline and blocks it.

**Proposed fix (not yet built):** A `PostToolUse` hook on bash that checks if the command contains `pytest` or `git commit` and injects: "⚠️ test-runner / code-reviewer agent should have been spawned here per AutoTrigger rules — was this a blocking gate?" Creates friction at the right moment rather than at task start.

### Plan + Go-Ahead Step
Step 3 ("Plan: [one sentence] → touches [files] → tests in [file] → commit. Proceed?") was skipped in the IVR task. The AI went directly from structure check to implementation. No enforcement mechanism exists for this step beyond CLAUDE.md documentation.

---

## Protocol Flow (Current State)

```
User sends message
    │
    ▼
UserPromptSubmit hook (task_protocol.sh)
    ├── Query detected → SKIP, no injection
    └── Task detected → INJECT 4-step protocol checklist
            │
            ▼
        Step 1: CONTEXT.md read (mandatory)
            │
            ▼
        Step 2b: Council checkpoint
        (council_check.sh fires on first Edit/Write)
            ├── All 3 criteria hold → draft question, wait
            └── Not all hold → proceed
            │
            ▼
        Step 3: State plan → wait for go-ahead
            │
            ▼
        Step 3b: Routing decision ← KEY FORK
            │
            ├── Antigravity path:
            │       Invoke handoff-antigravity skill
            │       Produce structured prompt (content injected inline)
            │       STOP. Do not write code.
            │           │
            │           ▼
            │       Antigravity implements (autonomous)
            │           ├── QUALITY_GATES: pytest + persona review
            │           ├── STOP_CONDITIONS: relay design forks to Claude via Animesh
            │           └── PHASE_COMPLETION_OUTPUT block
            │           │
            │           ▼
            │       Claude verifies: SHA + test count vs DoD
            │
            └── Claude path:
                    Step 4: Implementation
                    AutoTrigger: test-runner (Haiku) → blocking
                    AutoTrigger: code-reviewer (Opus) → blocking
                    commit skill (5-step executor, SHA confirmation)
```

---

## Files Changed This Session

| File | Change |
|---|---|
| `.claude/agents/code-reviewer.md` | Model → `claude-opus-4-6` |
| `.claude/agents/test-runner.md` | Model → `claude-haiku-4-5-20251001` |
| `.claude/agents/greeks-analyst.md` | Model → `claude-sonnet-4-6` |
| `.claude/agents/roll-validator.md` | Model → `claude-opus-4-6` |
| `.claude/agents/options-strategist.md` | Model → `claude-opus-4-6` |
| `.claude/skills/commit/SKILL.md` | Converted from template to 5-step executor |
| `.claude/skills/prompt-refine/SKILL.md` | New — prompt scoring and rewriting |
| `.claude/skills/handoff-antigravity/SKILL.md` | New — structured Antigravity handoff with inline content |
| `.claude/hooks/task_protocol.sh` | New — UserPromptSubmit classification hook |
| `.claude/hooks/council_check.sh` | New — PreToolUse council reminder |
| `.claude/settings.json` | Added UserPromptSubmit hook + council_check hook |
| `CLAUDE.md` | Added AutoTrigger table, Step 3b routing gate |
| `ANTIGRAVITY.md` | Hardened commit gate, added Phase Completion Output |
| `INSTRUCTION.md` | Added Prompt Crafting Guide section |

---

## Commits This Session

```
3ed90fe feat(backtest): add compute_ivr() IV Rank utility  ← demo task
2203d19 chore(.claude): add UserPromptSubmit hook for task protocol injection
5d528ab docs(claude): add Step 3b implementation routing gate
66a0c67 chore(.claude): add model routing, autotrigger rules, and three new skills
```

Note: Two earlier commits (`a1c08b8` handoff-antigravity quality gates, `docs(root)` INSTRUCTION.md guide) hit a persistent `.git/HEAD.lock` from the sandbox and were staged but needed manual `rm .git/HEAD.lock` + commit from Animesh's terminal.

---

## Open Items / Next Session

- **PostToolUse bash hook** — detect inline `pytest` / `git commit` calls and warn that the AutoTrigger agent should have been spawned. This is the missing enforcement for the agent non-triggering problem.
- **Plan + go-ahead enforcement** — no mechanism currently forces Step 3 before implementation starts.
- **`src/nuvama/CLAUDE.md`** — module context file not yet written (noted in CONTEXT.md "What Does NOT Exist Yet").
- **Remaining P1-NEXT tasks** — India VIX ingestion pipeline (IVR function now done, ingestion and Parquet storage still needed), historical replay harness design doc.
