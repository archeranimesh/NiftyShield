# NiftyShield — Antigravity Handoff Skill

> Invoke at the end of planning phase, before handing implementation to Antigravity.
> Trigger phrase: "prepare antigravity handoff", "write the antigravity prompt", "hand off to antigravity"
>
> Goal: eliminate Antigravity's mandatory file-read tool calls at session start by injecting
> the relevant content inline. Each file read Antigravity skips saves ~1,000–2,000 input tokens.

---

## Step 1 — Gather the five content blocks

Read and extract (do not paste in full — extract only what's relevant to the task):

**A. Active phase block** — from `BACKTEST_PLAN.md`, extract only the active phase section
   (e.g. `§Phase 0.5`): its objective, DoD checklist, and any sequencing constraints.
   Skip completed phases, future phases, and narrative context. Target: ≤ 30 lines.

**B. Module context block** — from `CONTEXT.md`, extract only the module entries relevant
   to the task (e.g. `src/paper/` description + invariants). Skip unrelated modules.
   Target: ≤ 20 lines.

**C. Graph pointers** — run `search_graph` or `get_code_snippet` for the key symbols
   the task touches. Record the qualified names and their file locations so Antigravity
   can query the graph directly without discovery overhead. Format as a list of
   `search_graph("<SymbolName>")` calls Antigravity should run first.

**D. ANTIGRAVITY.md rules summary** — the 6 non-negotiable constraints (extract verbatim,
   no paraphrase):
   - Decimal invariant (monetary fields → Decimal, TEXT in SQLite)
   - BrokerClient protocol (no concrete imports outside factory.py)
   - `__init__.py` required in every new package directory
   - `UPSTOX_ENV=test` default; never auto-run on live DB
   - No `SELECT *` in any run_command query
   - State-mutating commands (git commit, DB writes) require UI approval

**E. REVIEW.md hygiene rules** — extract the 10 general Python hygiene checks
   (mutable defaults, late-binding closures, bare except, generator exhaustion,
   dict mutation during iteration, `__eq__` without `__hash__`, None sentinel,
   set iteration order, zip without strict=True, copy vs deepcopy).
   Include in every handoff — Antigravity misses these without it.

---

## Step 2 — Compose the handoff prompt

Output this block in full, ready to paste to Antigravity:

```
Read CONTEXT.md and ANTIGRAVITY.md. Then execute this handoff.

OBJECTIVE
<one sentence, imperative mood — what gets built this phase>

GRAPH_POINTERS
Run these graph queries first before reading any source file:
- search_graph("<PrimaryClass>")
- get_code_snippet("<Module.method>")
- trace_path("<function_with_dependencies>")
[list the specific queries from Step 1C]

BOUNDARIES
Do not touch:
- <list specific files or modules that are off-limits>
Invariants (non-negotiable):
- Decimal on all monetary fields; never float; SQLite stores as TEXT
- No imports of UpstoxLiveClient / MockBrokerClient outside src/client/factory.py
- __init__.py required in every new package directory
- UPSTOX_ENV=test for all run_command executions
- No SELECT * in any DB query

CONTEXT_EXTRACT
Active phase (BACKTEST_PLAN.md §Phase N.M):
[paste Step 1A block here]

Relevant module state (CONTEXT.md):
[paste Step 1B block here]

REVIEW_RULES
Before committing, check the diff against these Python hygiene rules:
- Mutable default arguments: def f(x=[]) or def f(x={}) — always use None + guard
- Late-binding closures: lambdas inside loops capturing loop variable
- Bare except: except: or except Exception: pass without logging
- Generator exhaustion: generator passed to two consumers
- Dict/set/list mutation during iteration
- __eq__ without __hash__ on any class defining __eq__
- None as sentinel when None is a valid domain value — use _MISSING = object()
- Set iteration order assumptions: list(some_set)[0]
- zip without strict=True on mismatched-length sequences
- copy.copy() on nested mutables — use copy.deepcopy()
For financial logic commits (Decimal, P&L, BrokerClient): stop and ask Animesh to
run the real @code-reviewer via Claude. Do not approximate with persona adoption.

DOD
- [ ] Tests pass: python -m pytest tests/unit/ --tb=no -q (all green)
- [ ] New public functions have happy-path + error/edge-case tests (offline, no network)
- [ ] CONTEXT.md updated (module tree) if new files added
- [ ] TODOS.md updated (session log entry, completed items marked)
- [ ] Commit executed (not drafted) — SHA confirmed via git log --oneline -1

QUALITY_GATES
Antigravity runs these gates using its own tooling — not Claude's sub-agents.

Test gate (replaces Claude's test-runner agent):
  run_command: python -m pytest tests/unit/ --tb=no -q
  All tests must pass before proceeding to review. If failures exist, fix them first.

Review gate (replaces Claude's code-reviewer agent) — two tiers:
  NON-FINANCIAL code (tooling, config, scripts with no monetary logic):
    view_file: .claude/agents/code-reviewer.md
    view_file: REVIEW.md
    Adopt both as persona. Evaluate git diff HEAD against all rules in both files.
    Resolve CRITICAL/ERROR before committing. WARNING may be deferred with a note.

  FINANCIAL logic (any change touching Decimal fields, P&L, Greeks, BrokerClient,
    src/paper/, src/portfolio/, src/mf/, src/client/):
    STOP. Do not commit. Tell Animesh: "This commit touches financial logic.
    Please ask Claude to run the real @code-reviewer agent against git diff HEAD
    before I proceed." Wait for Claude's verdict before continuing.

STOP_CONDITIONS
Stop mid-implementation and surface to Animesh (who relays to Claude) when:
  - A design decision arises that isn't resolved by CONTEXT.md, DECISIONS.md, or the graph
    (e.g. two valid approaches with different P&L or architectural consequences)
  - A required symbol or model field is missing from the codebase and needs a new design decision
  - A test is failing for a reason that suggests the spec is wrong, not the implementation

Do NOT stop for: implementation style choices, naming decisions, minor refactors.
When stopping, include in the relay message: what the ambiguity is, the two options
you considered, and which you would pick if forced. Claude resolves it and you continue.

PHASE_COMPLETION_OUTPUT
At end of phase, produce this block:
PHASE COMPLETE
files_changed: [list]
tests_added: N
tests_passing: N of M
commit_sha: <7-char SHA>
ambiguities_noted: [list any stop-condition items that arose, or "none"]
```

---

## Step 3 — Token budget check

Before sending, count approximate tokens (rough guide: 1 token ≈ 4 chars).
Target: handoff prompt ≤ 2,000 tokens total.

If over budget, trim in this order:
1. CONTEXT_EXTRACT — cut to 10 lines, most critical invariants only
2. GRAPH_POINTERS — keep only the 2–3 most load-bearing symbols
3. REVIEW_RULES — keep only if the task touches non-trivial Python logic;
   drop for pure doc or config tasks

Never trim BOUNDARIES or DOD — these are the correctness gates.
