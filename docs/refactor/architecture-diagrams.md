# Before/after architecture diagrams — making the improvement visible, not just claimed

> `code-deduplication-and-taxonomy.md` covers *finding* duplication with an audit; this doc covers *drawing* what was found and what replaced it, so the improvement is something a reader can see in
> two pictures, not something they have to take on faith from a changelog.

## Why draw anything at all

A refactor's own account of itself ("we removed the duplication, it's cleaner now") is exactly the kind of claim that should come with evidence, not just assertion — the same standard this playbook
already applies to duplication claims in the audit step. A diagram generated mechanically from the actual import/call graph is harder to overstate than prose, and it gives a prior-state snapshot to
diff against once the new structure lands.

## Draw the "before" diagram at audit time, not from memory later

Generate it while the legacy code is still being read for the audit (`code-deduplication-and-taxonomy.md`'s step), not retroactively after the new structure already exists — a diagram drawn from
memory after the fact tends to quietly describe the *new* mental model, not what the old code actually did. Two diagram shapes cover most cases:

- **An internal dependency/call flowchart per legacy folder or module** — which file imports/calls which, within that one unit. This is what exposes an orchestrator that's grown decision branches
  instead of delegating to collaborators (the OCP trigger in `design-principles.md`): a flowchart with one dense node and a dozen incoming edges is visibly the same finding as "this file has too many
  responsibilities," rendered instead of stated.
- **A convergence diagram per duplicated concern** — one node per legacy copy of the same logic, each pointing at the single shared module it should converge to. This makes a duplication claim
  checkable: the diagram either names real files with a real shared-logic edge, or it doesn't, and a reviewer can tell which at a glance.

Mermaid flowcharts are a reasonable default rendering (plain text, diffable, renders inline in most doc viewers) — the format matters less than the discipline of generating diagrams from the actual
file tree, not authoring them freehand from a mental model of what the code probably does.

### Exclude tests from every diagram

A dependency/call-graph diagram is about production structure — which module depends on which collaborator — and test files are not part of that structure; they're the thing that verifies it. Mixing
test imports into the same graph adds nodes and edges that don't represent an actual runtime dependency relationship, inflates node/edge counts in a way that makes the real production coupling harder
to see, and makes a before/after comparison noisy (a growing test suite looks identical to growing production coupling if both are drawn as the same kind of edge). Scope every diagram-generation pass
to production files only — skip anything under a `tests`/`test` directory and any file matching a `test_*`/`*_test` naming convention — and state that exclusion explicitly in the diagram's own text (a
one-line caption is enough) so a reader doesn't have to infer it.

## Draw the "after" diagram once the new structure has landed

Once the target module (the shared library piece, the new orchestrator-plus-collaborators shape) actually exists and the legacy duplicates have been replaced by calls into it, generate the same two
diagram shapes again, same exclusion rule, against the new tree. Don't hand-edit the "before" diagram into an "after" one — regenerate it the same mechanical way, so both sides of the comparison were
produced by the same process and are actually comparable.

## What "improved" looks like in the diagram, concretely

Compare the pair looking for specific, visible changes — not a vague "it looks cleaner":

- **Convergence edges collapse to one target.** Where the "before" convergence diagram showed N legacy copies each duplicating the same logic, the "after" diagram should show N call-sites pointing at
  one shared module — the fan-in on that shared node is the duplication count made visible as a single number.
- **Orchestrator decision-node count drops.** A "before" flowchart with one file branching on many `elif`/`case` arms should become an "after" flowchart where that file has a small, fixed sequence of
  calls to separate collaborator nodes (the Strategy/Template Method shape from `design-principles.md`) — count the decision nodes in each; the number should go down, not just "feel" lower.
- **Dependency direction flips toward the abstraction.** A "before" diagram where a domain module's arrow points at a concrete external-system node (the DIP violation) should become an "after" diagram
  where that arrow points at an interface/`Protocol` node instead, with the concrete implementation now depending on the interface rather than the other way around.
- **No new node is denser than the worst "before" node.** A regression check, not just a positive-improvement one: if the "after" diagram's busiest node has more incoming/outgoing edges than the
  "before" diagram's busiest node, the refactor relocated complexity rather than reducing it — worth calling out explicitly rather than only reporting the wins.

## The honest limitation: nothing keeps the diagram fresh automatically

A diagram generated at one point in time starts drifting the moment the code it describes changes again — a later rename of the shared module, or a new duplicate introduced after the "after" diagram
was drawn, leaves the diagram describing a structure that no longer exists. There is no automated check tying a diagram to the code it claims to represent; treat both diagrams as a dated snapshot
("this was the shape on 2026-10-03"), not a live view, and regenerate the "after" diagram by hand whenever a structural claim about the new code needs re-checking — the same honest caveat
`process-discipline.md` applies to any other durable doc that can silently go stale.
