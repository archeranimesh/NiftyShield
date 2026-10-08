
# Design Gate — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

## DG-1 — Bug-to-principle evidence matrix

**Files:** `docs/refactor/bug-principle-evidence.md` (new). **Before any code:** `grep -n '^## BUG-' docs/archive/bugs/bugs.md docs/bugs/bugs.md`, then read each body's root-cause section by `sed -n`;
never the whole file. **Implement:** one row per bug (id, root cause in one line, files touched, principle that would have prevented it or limited the blast radius). Start from the 8-principle first
cut (single seam, shared mechanism, typed collaborators, no silent failure, value types, OCP, config over constants, event-loop hygiene). Correct it where bodies disagree with titles. End with counts
per principle. The files-touched column feeds the DBL-2 hotspot overlay. **Verify:** every BUG id in both files appears once; counts sum to at least the bug count. **Commit:** `docs(refactor): add
bug-to-principle evidence matrix`

---

## DG-2 — GoF pattern applicability audit

**Files:** `docs/refactor/gof-python-applicability.md` (new); amend `docs/refactor/design-principles.md` only where a verdict contradicts it (it names 5 patterns today: Strategy, Factory Method,
Template Method, Decorator, Observer). **Before any code:** for each pattern, `search_code` / `search_graph` for its in-repo shape (registry `dict`, `Protocol`, callback list, `@decorator`,
template-method base classes) so verdicts rest on what the repo already does, not on theory. **Implement:** classify all 23 Gang of Four patterns (5 creational, 7 structural, 11 behavioural) with
exactly one verdict each: **built into Python** (Iterator via generators, Decorator via `@`, Command and Strategy as callables, Singleton as a module, Prototype via `copy`, Flyweight via interning),
**use as-is** (for example Adapter, Facade, Proxy, Composite, State), **use in Python-native form** (Factory Method and Abstract Factory as functions or a registry `dict`, Observer as a callback list,
Visitor via `functools.singledispatch`, Builder as dataclass defaults or keyword arguments), or **not applicable**. For each entry give the Python-native shape and, for any "use" verdict, a concrete
in-repo problem it solves, for example Template Method for the close sequence behind the `mark_trade_closed` bugs, Adapter for the `TelegramGateway` vs notifier mismatch (BUG-065), and the opt-in
registry in `src/payoff/`. A pattern with no concrete in-repo problem is marked "not needed here", not recommended speculatively (simplicity first). Close with a short list of the verdicts DG-4 should
carry into the decision card; the card does not reproduce all 23. **Verify:** all 23 patterns appear exactly once; every "use" verdict cites an in-repo example or bug id; `design-principles.md` and
the new doc agree. **Commit:** `docs(refactor): add GoF pattern Python applicability audit`

---

## DG-3 — Triage the remaining `docs/refactor/` docs

**Files:** `docs/refactor/README.md`, the files triaged below, the CLAUDE.md and `AGENTS.md` table rows that cite them. **Before any code:** read `python-hygiene-and-automation.md`,
`planning-protocol.md`, `process-discipline.md`, `logging-and-correlation-id.md` and `architecture-diagrams.md` by `grep -n '^#'` first, then the sections that overlap existing repo rules:
`.pre-commit-config.yaml` and ruff config, CLAUDE.md Steps 3 to 5, `LOGGING.md`, `REVIEW.md`, the nine `src/<module>/CLAUDE.md` files and `DECISIONS.md`. **Implement:** give each of the eight
`docs/refactor/` files one verdict: keep, merge into another doc, or retire. Record the reason. Reconcile the DG-4 card with the module `CLAUDE.md` invariants, `DECISIONS.md` and `REVIEW.md` so the
repo has one rule per topic. Do not edit `LOGGING.md` here: logging changes belong to the separate logging epic. **Verify:** every file has a verdict; no rule appears in two docs with different
wording; inbound links to retired files are updated. **Commit:** `docs(refactor): triage refactor docs against repo rules`

---

## DG-4 — Two-tier decision card

**Files:** `docs/refactor/decision-card.md` (new, ≤40 lines). **Implement:** consider these Python-specific candidates and keep only those that rank: functional core with an imperative shell,
composition over inheritance, parse at the boundary, Law of Demeter. Pattern guidance comes from the DG-2 verdicts, not from the full GoF list. Tier 1 baseline for all code, independent of bug
history: SOLID triggers, `Protocol` over `ABC`, EAFP, PEP 20 simplicity, small named functions, no silent failure, explicit types, `Decimal`. Tier 2 evidence-ranked from DG-1. Each entry is trigger →
action → an existing in-repo example. Fold in `code-review-checklist.md` §1–3 (SOLID triggers, `Protocol`/pattern shape, duplication and module boundary) so there is one source, not two. **Verify:**
line count ≤40; every example path exists. **Commit:** `docs(refactor): add two-tier design decision card`

---

## DG-5 — `design-check` skill and plan gate

**Files:** `.claude/skills/design-check/SKILL.md` (new), `CLAUDE.md`, `AGENTS.md`. **Implement:** the skill walks the card against a proposed change and emits a Design review block (triggers hit,
chosen seam, what is left alone). Merge the check into Step 2b/3 so it runs before the plan; the plan line gains `Design:`; widen the trigger to any change adding a branch or responsibility, or
touching more than one call site. `AGENTS.md` stays a full mirror, never a stub. **Verify:** `diff` of the changed Step text between the two files shows they match. **Commit:** `docs(protocol):
require Design clause before plan`

---

## DG-6 — Carry the gate to the other code-writing surfaces

**Files:** `.claude/skills/handoff-antigravity/SKILL.md`, `.claude/skills/plan-loop/SKILL.md`, `.claude/skills/new-story/SKILL.md`, the `protocol-reference` skill §3, `AGENTS.md` handoff text.
**Why:** the DG-5 skill and DG-8 hook only cover this Claude session. `plan-loop` workers are fresh subagents that inherit nothing, and Antigravity cannot run hooks. **Implement:** add the Design
review block to the mandatory elements of an Antigravity handoff prompt; make the `plan-loop` worker prompt require a Design clause before its first edit; make the `new-story` scaffold's Design review
section a required fill for any story that touches `src/` or `scripts/`. **Verify:** a generated handoff prompt and a generated worker prompt each contain the Design review requirement. **Commit:**
`docs(skills): require design review in handoff and plan-loop`

---

## DG-7 — Bug Design lens

**Files:** bug template under `docs/bugs/` (`prompt.md`, `task.md`) and the close checklist. **Implement:** a mandatory "Design lens" section: principle that would have helped, seam that would have
limited the blast radius, refactor follow-up (yes/no + pointer). Required only when the fix touches `src/` or `scripts/`. Enforce it with a pre-commit check in the style of
`check-checkbox-consistency`: fail when a bug entry is closed with a `src/` or `scripts/` SHA and has no Design lens section. **Verify:** a sample bug entry renders the section; the close text states
the scope rule. **Commit:** `docs(bugs): require design lens on src/scripts bugs`

---

## DG-8 — Presence hook

**Files:** `.claude/hooks/design_review_check.sh` (new), `.claude/settings.json`, the `UserPromptSubmit` reminder. **Implement:** `PreToolUse` on `Edit`/`Write` for `src/` and `scripts/`; warn when
the session transcript has no Design review block. Docs-only edits and one-line fixes may carry `Design: n/a — <reason>` instead of a full block, and the hook accepts that. A single constant flips
warn to block. Document the flip date (about one week after merge). **Verify:** run the hook against a fixture transcript with and without the block; both outcomes as expected. **Commit:**
`chore(hooks): warn on src edit without design review`

---

## DG-9 — Reviewer and checklist reconciliation

**Files:** `docs/refactor/code-review-checklist.md`, `.claude/agents/code-reviewer.md`, the CLAUDE.md and `AGENTS.md` table row that cites the checklist. **Implement:** in the checklist, keep §1–3,
make §5 (before/after diagrams) a done-criterion for refactor stories only, and remove §4 (FCID: no usage in `src/` or `scripts/`) and §6 (duplicates CLAUDE.md Steps 3–5). Remove its claim that a
`py-code-review` pre-commit hook already runs. In the agent, add a section 8 "Design" that points at the card, includes the multi-call-site duplication test, and tells the reviewer to use the graph
for repo context, since a diff alone cannot show duplication. The agent keeps its existing NiftyShield checks. **Verify:** a seeded diff (a new `elif` on a decision method; a collaborator built in
`__init__`) is flagged with the card's trigger name; the checklist has no inapplicable section. **Commit:** `docs(review): wire design card into code-reviewer`
