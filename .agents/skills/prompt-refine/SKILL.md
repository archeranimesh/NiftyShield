# NiftyShield — Prompt Refinement Skill

> Invoke when a prompt feels vague before starting work.
> Trigger phrase: "refine this prompt", "is this prompt good enough", "help me write a prompt for..."
>
> Goal: catch underspecification early. One clarifying question now beats a wasted
> implementation pass later. A failed phase can cost more tokens than an entire clean session.

---

## Step 1 — Score the incoming prompt

Check each dimension. Mark ✅ if present, ❌ if missing:

| Dimension | Question to ask |
|---|---|
| **Task type** | Is it feat / fix / refactor / test / docs / backtest / roll / snapshot? |
| **Named files** | Does it name specific `src/` or `scripts/` files, or just a module? |
| **Phase** | Does it reference a phase from `BACKTEST_PLAN.md`, or a story from `docs/plan/`? |
| **Context files** | Does it say which context files to load (CONTEXT.md always; DECISIONS.md / REFERENCES.md / TODOS.md when relevant)? |
| **Tests required** | Does it state test expectations — offline only, happy path + edge case? |
| **Boundaries** | Does it say what NOT to touch (e.g. "do not modify BrokerClient protocol")? |
| **DoD** | Is there a clear definition of done — test count, SHA confirmation, doc update? |
| **Council check** | For a load-bearing design decision, is a council question needed first? |

---

## Step 2 — If 2 or fewer ❌, proceed

The prompt is good enough. State which dimensions are missing as assumptions, then start work.
Do not ask a clarifying question for minor gaps — fill them from CONTEXT.md and proceed.

---

## Step 3 — If 3 or more ❌, ask ONE question

Identify the single most load-bearing missing dimension and ask about it only.
Do not ask multiple questions. Pick the one that, if wrong, would require the most rework.

Priority order for which gap to ask about:
1. **Named files** — wrong file = wrong implementation entirely
2. **Phase / story** — wrong phase = violates sequencing gate
3. **DoD** — unclear success criteria means the phase never closes cleanly
4. **Boundaries** — unspecified boundaries risk protocol violations (BrokerClient, Decimal)
5. **Tests** — missing test expectations is recoverable; ask only if completely absent

---

## Step 4 — Produce the refined prompt

After scoring (and optionally asking one question), output the rewritten prompt in this format:

```
Read CONTEXT.md [+ DECISIONS.md] [+ REFERENCES.md] [+ TODOS.md + PLANNER.md] [+ BACKTEST_PLAN.md §Phase N].

Task: <one sentence, imperative mood>
Type: feat / fix / refactor / test / docs
Phase: <Phase N.M from BACKTEST_PLAN.md, or story from docs/plan/, or "none">
Files to change:
  - <src/module/file.py>: <what changes>
  - <tests/unit/module/test_file.py>: <what changes>
Boundaries:
  - Do not touch: <list any off-limits modules or files>
  - Invariants: Decimal on all monetary fields; BrokerClient via protocol only; __init__.py in every new package
Tests required: yes — offline only, no network. Happy path + one error/edge case per public function.
DoD: all tests pass (python -m pytest tests/unit/ --tb=no -q), CONTEXT.md updated, commit SHA confirmed.

Confirm scope before starting. If >2 files change, wait for go-ahead.
```

Omit sections that are genuinely not applicable (e.g. "Boundaries" for a pure docs task).
Keep the total prompt under 200 tokens — dense and precise beats verbose.

---

## Token efficiency rules

- Never repeat information already in CONTEXT.md — reference it, don't paste it.
- Graph pointers beat file reads: if the prompt needs a symbol, state `search_graph("<SymbolName>")` rather than asking to read the file.
- Phase reference beats description: `BACKTEST_PLAN.md §Phase 0.5` is 5 tokens; describing Phase 0.5 in prose is 150.
- One context file reference beats listing its contents inline.
