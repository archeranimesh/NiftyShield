# NiftyShield: AI Synergy Plan (Claude + Antigravity)

NiftyShield has a highly structured, strict operating protocol (defined in `MISSION.md`, `CONTEXT.md`, and `CLAUDE.md`). By leveraging both **Claude** (acting as your local/IDE assistant via MCP) and **Antigravity** (acting as your autonomous agentic engine with direct MCP access), you can accelerate development while strictly adhering to your project's rules.

## 1. The MCP Knowledge Graph Foundation
Both Claude and Antigravity now share the same `codebase-memory-mcp` backend. This is the source of truth for your codebase structure.

* **Rule 0 Enforced:** Neither Claude nor Antigravity will blindly read source files (`src/` or `scripts/`).
* **Graph Queries:** Both AIs use `mcp__codebase-memory-mcp__search_graph` to find symbols, and `mcp__codebase-memory-mcp__trace_path` to find callers/callees. (Note the double underscores).
* **Semantic Search:** We use the graph to bridge vocabulary gaps without bloating the context window with raw text dumps.

## 2. Claude: The Architect & Local Query Engine
Claude is your immediate, synchronous assistant in the IDE. 

**Best used for:**
* **Instant Queries:** Ask Claude "Where is `OptionLeg` defined?" or "What changed recently?"
* **Specialized Agent Reviews:** Invoke your custom `.claude/agents/`:
  * `@greeks-analyst`: Review changes to your Option chain parsing or PnL logic.
  * `@options-strategist`: Discuss `finideas_ilts` vs `finrakshak` logic.
* **Council Checkpoint:** Use Claude to simulate the "Council checkpoint" (Step 2b) for standard decisions. **CRITICAL EXCEPTION:** If a decision meets all three criteria (load-bearing + costly to reverse + multi-discipline), the *real* council workflow (`docs/council/README.md`) strictly supersedes any Claude simulation.

## 3. Antigravity: The Autonomous Execution Engine
Antigravity operates asynchronously and handles multi-step, heavy-lifting tasks across the workspace.

**Best used for:**
* **Graph-Augmented Implementation:** Tell Antigravity to build a feature. I will use the MCP server to map out dependencies, edit multiple files simultaneously, and ensure the architectural boundaries hold.
* **TDD & Pipeline Execution:** Ask Antigravity to execute a phase from `BACKTEST_PLAN_PHASE1.md`. I will write the tests (Step 4), run `python -m pytest tests/unit/` locally, fix failures iteratively, and finalize the code.
* **Documentation Maintenance:** At the end of a sprint, ask Antigravity to reconcile `CONTEXT.md`, `TODOS.md`, and `DECISIONS.md`. **CRITICAL CONSTRAINT:** `CONTEXT.md` must be updated via targeted edits only (e.g., using `multi_replace_file_content`). It must *never* be completely overwritten.

**Confirmed scope limit:** Antigravity is most effective on tasks spanning **3–5 files**. If a task touches more than 5 files, Claude must decompose it into sub-phases — each with a separate handoff and commit — before handing off. Do not hand off an unbounded scope.

## 4. The Unified Workflow

**Phase A: Planning & Research (You + Claude)**
1. **Query:** Use Claude's MCP connection to trace a function or find dependencies.
2. **Review:** Ensure the planned change doesn't violate the "Protect Before You Earn" principle (`MISSION.md`).
3. **Draft Plan:** Claude drafts a quick markdown plan. If criteria are met, trigger the real Council workflow instead.

**Phase B: Heavy Lifting (You + Antigravity)**
1. **Prompt Antigravity:** Every handoff prompt from Claude must include four elements — (a) **Reading list**: explicit `view_file` paths Antigravity must read before writing any code (`CONTEXT.md` is mandatory; add `BACKTEST_PLAN.md`, `DECISIONS.md`, the relevant module `CLAUDE.md`, etc. as the task requires); (b) **Objective**: one-sentence statement of what to build; (c) **Pointers**: explicit file paths or graph queries — do not rely on Antigravity to discover scope; (d) **Boundaries**: files that must not be touched, off-limits patterns, and any financial gate reminders. Do NOT paste code. Example: *"Read: CONTEXT.md, BACKTEST_PLAN.md, src/backtest/CLAUDE.md. Objective: implement Step 2 of the bhavcopy pipeline. Pointers: src/backtest/bhavcopy_ingest.py. Boundaries: do not touch CONTEXT.md with write_to_file; stop before commit and emit CODE REVIEW GATE."*
2. **Execution & Testing:** Antigravity queries the MCP graph, writes the source code in `src/`, creates the test cases in `tests/`, and runs `pytest` in the terminal.
3. **Doc Updates:** Antigravity updates `TODOS.md` and the module-specific `CLAUDE.md`. `CONTEXT.md` is updated using strict, targeted edits.

**Phase C: Final Review & Commit (You + Claude, then Antigravity executes)**
1. **Antigravity signals the gate:** For any commit touching `.py` files, Antigravity stops and emits `CODE REVIEW GATE — awaiting @code-reviewer`. It does not proceed. Antigravity cannot spawn Claude sub-agents (Gemini engine); persona approximation of `@code-reviewer` is **not permitted for any code commit**.
2. **Claude runs the real review:** Animesh switches to Claude, runs `@code-reviewer` against `git diff HEAD`. Claude is the sole owner of this gate — not Antigravity, not Animesh manually.
3. **Resolve Findings:** Any `CRITICAL` or `ERROR` findings are resolved (by Claude or Antigravity per the finding's location) before proceeding. `WARNING` findings may be deferred with a documented reason in the commit `Why:` line.
4. **Execute Commit:** Once Claude confirms the review is clean, Animesh returns to Antigravity. Antigravity executes `git add <files> && git commit -m "<message>"` via `run_command` (blocks for UI approval), then runs `git log --oneline -1` to confirm the SHA. The commit is not complete until the SHA is confirmed.
5. **Docs-only commits** (no `.py` files): Antigravity may self-review using the `view_file: .claude/agents/code-reviewer.md` + `view_file: REVIEW.md` persona and commit directly without a Claude gate.
