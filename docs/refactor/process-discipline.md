# Process discipline

> The meta-layer: the recurring protocol failures a real multi-session refactor of this kind produces, and a mechanism for turning them into a visible, ranked, self-correcting backlog instead of
> repeating silently. This matters as much as the code-level design — a perfectly designed shared library built via sessions that keep skipping plan-and-wait-for-approval, or keep re-deriving context
> they already had, costs more than it should and erodes trust in the process.

## The core discipline loop

Every unit of work (a task, a story, a session) should close the same three-part loop before moving on:

1. **State the plan, wait for explicit go-ahead** — before creating, editing, or committing anything beyond a trivial single-file tweak, state what will change (which files), why, and what the
   expected result is. Wait for an explicit go-ahead before acting, every time — not just the first time in a session. Approval for one task does not carry over to the next.
2. **Do the work, with tests** — implementation plus tests (one happy-path, one edge/error-case per new public function, at minimum) — green before commit, not after.
3. **Close the loop** — update any durable project-state doc that needs it (a "what exists now" style context file), confirm tests are green, then commit with a clear message and surface the resulting
   commit identifier back to whoever is tracking the work.

A task is not complete until all three parts have happened. "I wrote the code" is not done; "I wrote the code, tests pass, docs are updated, and it's committed" is done.

## Recurring failure modes worth naming explicitly

These are the specific protocol failures that recur often enough in a real multi-session refactor to name and guard against individually, rather than relying on a generic "follow the process"
reminder:

- **Skipping the context re-read on a resumed task.** When a long task is split into many segments across time (or across sub-agent delegations), it's tempting to treat the first segment's
  context-read as covering every later segment too. It doesn't — re-read and re-acknowledge the durable context doc at the start of *each* resumed segment, not just the first.
- **Treating one approval as covering the next task.** The same logic as above, applied to the plan-and-wait step specifically: stating a plan and getting go-ahead for task N does not grant approval
  for task N+1, even in the same session, even moments later.
- **Not confirming target files before starting**, when a task is scoped loosely ("improve the X module") rather than naming specific files. Stop and confirm which files will change before creating
  new modules or tests — guessing wrong here wastes the whole task's work.
- **Forgetting to update the durable context doc** when a session adds a new persistent file — this is one of the single most common omissions in practice, because it's easy to treat "the code is
  committed" as the finish line and forget the doc that's supposed to describe current state now has a gap.
- **Re-reading the same file mid-session** when nothing about it has changed since it was last read — costs tokens/time for no new information. Reuse already-loaded context instead.
- **Using an overly broad filesystem search** (an unscoped recursive find/grep across an entire tree) when a known path or a narrower glob would answer the same question — prefer the narrower tool.
- **Dumping a whole file** when only one section is relevant — prefer a scoped read (line-range view, grep, a summary) once the target section is known.
- **Not surfacing the commit identifier** in the user-facing summary after a commit, forcing whoever's tracking the work to go look it up themselves.
- **Using a bypass flag for a routine commit** (e.g. skipping commit hooks) to save a few seconds — this defeats the exact safety net the hooks exist to provide, for essentially no benefit on a
  routine commit.
- **Destructive history rewrites for a mistake that's easy to fix forward** — reverting with a new commit rather than discarding history, amending only a genuinely still-local/unpushed commit.

## Closing the loop: a ranked, self-maintaining suggestions backlog

Rather than relying on memory or a one-off retrospective to catch these failures, maintain a durable, ranked backlog of recurring process mistakes, updated at the end of every session (or every work
unit):

1. At the close of each session, review what happened and identify any instance of a known failure mode (or a new one not yet named).
2. Record it in a single table: a short slug, a one-line actionable suggestion (not just a description of the mistake), a category, first-seen and last-seen dates, and a recurrence count.
3. If the same slug recurs in a later session, increment its count and update "last seen" rather than adding a duplicate row — the count itself is the signal for which failure mode is actually costing
   the most, cumulatively, across the whole refactor.
4. Sort by recurrence count. The top of this table is your actual priority list for "what should this project's session-start instructions emphasize harder" — not a guess, a measured ranking.

This converts an otherwise-invisible pattern ("we keep doing the thing we said we wouldn't") into a visible, data-backed artifact that can itself be acted on — e.g. promoting a chronically
high-recurrence item into a forced checkpoint (see `planning-protocol.md`'s "running a multi-story epic in one sitting" section) rather than leaving it as a reminder nobody reliably follows.

## Delegation discipline, if using sub-agents

If part of the refactor is driven by delegating units of work to separate agent sessions:

- Give each delegated unit a bounded objective and a clear stopping point — request execution of a well-scoped task, not open-ended advice.
- Trust each delegated unit's own context-extraction design (e.g. if it already knows how to read the relevant history itself) rather than pre-narrating a full summary into its prompt — a terse
  pointer (what to do, which identifiers matter) plus trust in its own extraction saves real token cost at scale.
- Don't delegate work that's genuinely small enough to finish directly in a handful of tool calls — delegation overhead (separate context, round-trip latency) only pays off for work that actually
  benefits from an isolated context window.
- Don't relaunch or nest a second delegated unit to re-check the first one's direct work "just in case" — if something is blocked, use a narrower, specific follow-up question instead of a full re-run.
