# NiftyShield: AI Synergy Plan (Claude + Antigravity)

NiftyShield has a highly structured, strict operating protocol (defined in `MISSION.md`, `CONTEXT.md`, and `CLAUDE.md`). By leveraging both **Claude** (acting as your local/IDE assistant via MCP) and **Antigravity** (acting as your autonomous agentic engine with direct MCP access), you can accelerate development while strictly adhering to your project's rules.

## 1. The MCP Knowledge Graph Foundation
Both Claude and Antigravity now share the same `codebase-memory-mcp` backend. This is the source of truth for your codebase structure.

* **Rule 0 Enforced:** Neither Claude nor Antigravity will blindly read source files (`src/` or `scripts/`).
* **Graph Queries:** Both AIs use `mcp_codebase-memory-mcp_search_graph` to find symbols, and `mcp_codebase-memory-mcp_trace_path` to find callers/callees. 
* **Semantic Search:** We use the graph to bridge vocabulary gaps without bloating the context window with raw text dumps.

## 2. Claude: The Architect & Local Query Engine
Claude is your immediate, synchronous assistant in the IDE. 

**Best used for:**
* **Instant Queries:** Ask Claude "Where is `OptionLeg` defined?" or "What changed recently?"
* **Specialized Agent Reviews:** Invoke your custom `.claude/agents/`:
  * `@greeks-analyst`: Review changes to your Option chain parsing or PnL logic.
  * `@options-strategist`: Discuss `finideas_ilts` vs `finrakshak` logic.
  * `@code-reviewer`: Run it against `git diff HEAD` before committing.
* **Council Decisions:** Use Claude to simulate the "Council checkpoint" (Step 2b) for load-bearing architectural decisions before any code is written.

## 3. Antigravity: The Autonomous Execution Engine
Antigravity operates asynchronously and handles multi-step, heavy-lifting tasks across the workspace.

**Best used for:**
* **Graph-Augmented Implementation:** Tell Antigravity to build a feature. I will use the MCP server to map out dependencies, edit multiple files simultaneously, and ensure the architectural boundaries hold.
* **TDD & Pipeline Execution:** Ask Antigravity to execute a phase from `BACKTEST_PLAN_PHASE1.md`. I will write the tests (Step 4), run `python -m pytest tests/unit/` locally, fix failures iteratively, and finalize the code.
* **Agent Persona Adoption:** You can tell me to read `.claude/agents/code-reviewer.md` and execute a comprehensive codebase review acting entirely as that persona.
* **Documentation Maintenance:** At the end of a sprint, ask Antigravity to reconcile `CONTEXT.md`, `TODOS.md`, and `DECISIONS.md`. I will use the graph to find what changed and update the docs systematically.

## 4. The Unified Workflow

**Phase A: Planning & Research (You + Claude)**
1. **Query:** Use Claude's MCP connection to trace a function or find dependencies.
2. **Review:** Ensure the planned change doesn't violate the "Protect Before You Earn" principle (`MISSION.md`).
3. **Draft Plan:** Claude drafts a quick markdown plan or a "Council Decision" file.

**Phase B: Heavy Lifting (You + Antigravity)**
1. **Prompt Antigravity:** Provide the Objective, Pointers (where to look), and Boundaries. Do NOT paste code. (e.g., *"Antigravity, implement Step 2 of the backtest plan. Use the MCP graph to find the `PaperStore` rollback logic."*)
2. **Execution & Testing:** Antigravity queries the MCP graph, writes the source code in `src/`, creates the test cases in `tests/`, and runs `pytest` in the terminal.
3. **Doc Updates:** Antigravity updates `TODOS.md` and the module-specific `CLAUDE.md`.

**Phase C: Final Review & Commit (You + Claude)**
1. **Code Review:** You use Claude's `@code-reviewer` agent to review Antigravity's uncommitted changes.
2. **Commit:** Once the reviewer agent gives the green light, the code is committed.
