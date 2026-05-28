# Antigravity Tactical Guide for NiftyShield

Now that you have successfully connected the `codebase-memory-mcp` to Antigravity, I have direct access to your knowledge graph. Here is exactly how to interact with me to maximize efficiency, avoid context bloat, and utilize your custom agents.

## 1. How to Handle Markdown Files Without Bloating Context

You have extensive, rich documentation (`BACKTEST_PLAN.md`, `CONTEXT.md`, etc.). You **do not** need to copy-paste these into my chat window. 

**The Antigravity Approach:**
* **Lazy Loading:** Tell me exactly what I need to look for, and I will use my `grep_search` and `view_file` tools to extract only the relevant lines.
  * *Example prompt:* `"Antigravity, check the 'Current Constraints' section in CONTEXT.md and the open tasks in TODOS.md. Based on that, what should we tackle next?"*
* **Rely on the MCP Graph:** Because I have the `codebase-memory-mcp` tools, I can semantically search the codebase. If you ask me to look for the "Nuvama intraday snapshot logic", I don't need you to feed me files; I will use `mcp_codebase-memory-mcp_search_graph` to find the exact nodes and read only the necessary code snippets.
* **Artifact Distillation:** When I read large files, I will distill my findings into my own local "Artifacts" (like markdown summaries) so I remember the plan without keeping the entire raw file in my active context window.

## 2. How to Leverage Your Custom Agents and Hooks

You have custom Claude agents (e.g., `code-reviewer.md`, `greeks-analyst.md`) inside the `.claude/agents/` folder. 

**How Antigravity uses them:**
* **Persona Adoption:** I can read these markdown files and temporarily adopt the exact rules and persona of that agent.
  * *Example prompt:* `"Antigravity, read .claude/agents/code-reviewer.md and perform a review of src/portfolio/positions.py exactly as that agent would."*
* **Hook Execution:** I have full terminal access. If you have bash scripts like `.claude/hooks/guard_src_reads.sh`, I can execute them as part of my validation loop. 

## 3. What Input Should You Give Antigravity?

To get the most out of me, give me the **Objective**, the **Pointers**, and the **Boundaries**. Do not give me the code itself.

**Bad Input:**
> *"Here is the code for my client.py: [1000 lines of code] ... fix the Dhan parser."* (This bloats context and is unnecessary).

**Great Input:**
> *"Antigravity, we need to implement the Upstox chain snapshot writer.
> 1. Check `docs/archive/plan/chain-data/chain_data_stories.md` for the CD1.1 story spec.
> 2. Look at `src/backtest/vix_ingest.py` for the established Parquet write pattern.
> 3. Implement `src/backtest/chain_writer.py` and make sure `pytest tests/unit/backtest/test_chain_writer.py` passes.
> 4. Do not commit yet, just show me the diff."*

### Why this works:
1. **Objective:** I know what the end goal is.
2. **Pointers:** You told me where to look (`TODOS.md`, Upstox implementation). I will use my tools to read exactly those files.
3. **Boundaries:** You told me to run tests but *not* to commit, allowing you to review my work safely.

## Summary Checklist for your Prompts:
- [ ] **State the goal clearly.**
- [ ] **Point to the docs** (e.g., "See MISSION.md Principle IV"). Let me read it myself.
- [ ] **Define the validation** (e.g., "Run the tests in this folder").
- [ ] **Set the boundary** (e.g., "Stop and ask for review before editing the DB script").
