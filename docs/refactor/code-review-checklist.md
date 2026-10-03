# Code-review checklist — the gaps automation doesn't close

> This is deliberately short. Everything in `python-hygiene-and-automation.md`'s defect/design-quality catalog is already enforced on every commit — by `ruff`'s default rule set and by the
> `py-code-review` pre-commit hook's AI-reviewer pass over the staged diff — so none of it is repeated here. This checklist covers only what a diff-scoped, line-level reviewer structurally cannot
> check: architecture-level judgment calls, cross-file/cross-project context, and process discipline. Re-validate this split before reusing the checklist on a different project: it's only correct as
> long as the automation it assumes (a default-config `ruff` run, an AI-reviewer pre-commit hook with the python-hygiene checklist as its instructions) is actually wired up the same way — see
> `python-hygiene-and-automation.md`'s "Automate it" section for what that wiring looks like.

## How to use this

Run through the six sections below on a pull request / review pass that a diff-scoped automated reviewer has already cleared. Each box names what to look for and which `docs/refactor/` doc has the
full reasoning if the trigger fires. This is a human (or a reviewer with repo-wide context, not just the diff) checklist — don't expect an automated pre-commit hook to tick these for you.

## 1. SOLID triggers (`design-principles.md`)

- [ ] No class gained a new method for a concern its existing methods don't already cover (SRP) — a genuinely new concern gets a new class.
- [ ] No existing decision method grew another `elif`/`case`/`switch` branch for a new variant (OCP) — a new variant is a new interface implementer, not a new branch.
- [ ] No subclass override narrows accepted inputs or returns something the base type's callers don't expect (LSP).
- [ ] No interface grew a method only some implementers actually use, forcing stub/`NotImplementedError` methods elsewhere (ISP).
- [ ] No class constructs its own external-system collaborator directly instead of receiving it via the constructor (DIP) — check this one first; it's usually the highest-leverage finding.

## 2. `Protocol`/pattern-shape choices (`design-principles.md`)

- [ ] Any new "interface" is `typing.Protocol`, not `abc.ABC`, unless there's a specific, stated reason for nominal inheritance (shared default-method bodies, `isinstance` registration).
- [ ] Any new Strategy/Factory Method/Decorator/Observer-shaped code uses the lightweight Python-native form (plain function/`Callable`, registry `dict`, `@decorator`/context manager, callback list)
  unless the class-based GoF shape is earning its weight for a stated reason (shared non-trivial state across implementations).
- [ ] EAFP (`try`/`except`) is used for genuine failure handling, not as a substitute for a plain `dict.get(key, default)`-shaped lookup with an obvious fallback.

## 3. Duplication and module-boundary discipline (`code-deduplication-and-taxonomy.md`)

- [ ] New logic that resembles something already in another project/module was actually checked against the module map / prior-art registry before being written fresh — not assumed novel.
- [ ] A module wrapping a third-party library or external service defines and raises its own exception hierarchy at the boundary, rather than letting the wrapped library's exception types leak to
  callers.
- [ ] Dependency direction in any new code points toward the abstraction/interface, not toward a concrete external-system implementation.

## 4. FCID / cross-cutting ambient-context correctness (`logging-and-correlation-id.md`)

- [ ] Any new concurrent code path (thread pool submission, `asyncio` task creation) that runs inside an FCID-bound context explicitly carries that context across the boundary
  (`contextvars.copy_context()` or equivalent) — don't assume it propagates implicitly.
- [ ] There is an actual test asserting the worker-side log line still carries the FCID for any new concurrent path, not just a reasoning claim that it should.
- [ ] No new cross-cutting concern has been threaded explicitly through every function signature where an existing ambient-context mechanism already exists for exactly that purpose (and vice versa —
  no genuine domain value has been smuggled into ambient context instead of being passed explicitly).

## 5. Before/after architecture diagrams (`architecture-diagrams.md`)

- [ ] A "before" diagram exists for any module this change claims to be converging/refactoring, generated from the actual tree at audit time — not authored from memory after the fact.
- [ ] Once the new structure lands, the "after" diagram has been regenerated the same mechanical way, with tests excluded from both.
- [ ] The before/after comparison shows a concrete, named improvement (convergence edges collapsing to one target, orchestrator decision-node count dropping, dependency direction flipping toward the
  abstraction) — not just an unverified claim that it's "cleaner."

## 6. Process discipline (`planning-protocol.md`, `process-discipline.md`)

- [ ] The plan was stated (what changes, which files, why) and an explicit go-ahead received before this work started, for anything beyond a trivial single-file tweak.
- [ ] Tests exist for new public functions (one happy-path, one edge/error-case), green before this review.
- [ ] Any durable "what exists now" project doc was updated if this change added new persistent files/modules.
- [ ] The commit (or PR) message states what changed and why; the resulting commit identifier is surfaced back to whoever is tracking the work, not left for them to look up.
