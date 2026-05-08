# NiftyShield: AI Synergy Plan (Claude + Antigravity)

NiftyShield has a highly structured, strict operating protocol (defined in `MISSION.md`, `CONTEXT.md`, and `CLAUDE.md`). By leveraging both **Claude** (acting as your local/IDE assistant via MCP) and **Antigravity** (acting as your autonomous agentic engine), you can accelerate development while strictly adhering to your project's rules.

Here is how to use both to their full potential:

## 1. Claude: The Architect & Query Engine
Claude is wired directly into your codebase graph via the `codebase-memory-mcp`. It excels at low-latency queries, strict adherence to local hooks, and specific knowledge retrieval.

**Best used for:**
* **Graph Queries (Rule 0):** Use Claude to ask "Where is `OptionLeg` defined?" or "Trace the callers of `compute_pnl`". Claude uses `mcp__codebase-memory-mcp__index_repository` to find things without blindly reading files.
* **Specialized Agents:** Invoke your custom `.claude/agents/` for specific tasks:
  * `@greeks-analyst`: Ask it to review changes to your Option chain parsing or PnL logic.
  * `@options-strategist`: Discuss `finideas_ilts` vs `finrakshak` logic.
  * `@code-reviewer`: Run it against `git diff HEAD` before committing (as mandated by Step 5c in `CLAUDE.md`).
* **Council Decisions:** Use Claude to simulate the "Council checkpoint" (Step 2b) for load-bearing architectural decisions before any code is written.

## 2. Antigravity: The Execution Engine
Antigravity is designed for autonomous, multi-step execution. Once Claude (or you) has determined *what* needs to be done, Antigravity can execute the *how* across the entire workspace.

**Best used for:**
* **Multi-file Implementation:** "Antigravity, implement the `PaperStore` rollback logic for collar rolls. Here are the models from Claude's graph output." Antigravity will write the logic, the tests, and update the docs.
* **TDD & Pipeline Execution:** Ask Antigravity to execute a phase from `BACKTEST_PLAN_PHASE1.md`. Antigravity can write the tests (Step 4), run `python -m pytest tests/unit/`, fix failures iteratively, and finalize the code.
* **Documentation Maintenance:** At the end of a sprint, ask Antigravity to reconcile `CONTEXT.md`, `TODOS.md`, and `DECISIONS.md`. Antigravity can grep through the project, find what changed, and update the docs systematically.
* **Environment Operations:** Antigravity can execute terminal commands, run `daily_snapshot.py`, or verify SQLite DB states (`data/portfolio/portfolio.sqlite`) directly.

## 3. The Unified Workflow

**Phase A: Planning & Research (You + Claude)**
1. **Query:** You ask Claude to trace a function or find dependencies using the MCP graph.
2. **Review:** You and Claude review `CLAUDE.md` and `MISSION.md` to ensure the planned change doesn't violate the "Protect Before You Earn" principle.
3. **Draft Plan:** Claude drafts a quick markdown plan or a "Council Decision" file.

**Phase B: Heavy Lifting (You + Antigravity)**
1. **Prompt Antigravity:** Feed the approved plan to Antigravity. (e.g., "Implement Step 2 of the backtest plan according to this design.")
2. **Execution & Testing:** Antigravity writes the source code in `src/`, creates the test cases in `tests/`, and runs `pytest`. It iterates until the tests are green.
3. **Doc Updates:** Antigravity updates `TODOS.md` and the module-specific `CLAUDE.md`.

**Phase C: Final Review & Commit (You + Claude)**
1. **Code Review:** You use Claude's `@code-reviewer` agent to review Antigravity's uncommitted changes.
2. **Commit:** Once the reviewer agent gives the green light, the code is committed.

## Summary

* **Claude** = *Radar & Strategist.* Fast context, graph navigation, strict rule enforcement, and specific persona reviews.
* **Antigravity** = *Heavy Machinery.* Multi-file editing, test-driven development loop, terminal execution, and comprehensive documentation updates.
