Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/csp-collateral-leg/tasks.md` and find the first unchecked box. That is your **only
task** for this session. Do not look at any other unchecked item. One task. Complete it fully.
Stop.

**CL-0 is already checked off** — this directory's creation satisfies the original TODOS.md
DoD ("story dir + back-fill command documented"). The next unchecked box (CL-1) is genuinely
new design/implementation work.

**CL-4 needs an explicit operator decision before implementation** — "annual reset" is
underspecified in the source TODOS.md item; ask before building anything, don't guess the
semantics.

**Graph-before-Read rule:** Never call `Read` on `src/` without first using the graph. Order:
`git log` → graph query → `search_code` → `sed -n` → `Read` (state why).

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` first.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing.

**Financial logic note:** this whole story touches Decimal quantity/collateral calculations
tied to real formula math — the real `@code-reviewer` gate is mandatory per project protocol
once code lands (CL-1 onward), even if this surface can't spawn it (state the substitution
used).

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.
