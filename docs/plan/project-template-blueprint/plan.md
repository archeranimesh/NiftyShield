
# Cross-Project Claude Template Blueprint — plan (draft, converging)

> Extra file, no task checkboxes (per `docs/plan/README.md` §Conventions "Extra files"). Written under **PTB-1** as a faithful capture of the 2026-09-26 discussion — not a final answer. Later tasks
> (PTB-2..PTB-5) concretize and converge each section below; this file is expected to keep changing.

## Why this exists

NiftyShield accumulated, over months of live use, things worth reusing elsewhere: Python hygiene conventions, a Claude-Code operating harness (`.claude/skills/*`, `.claude/agents/*`, hooks), a
`docs/plan/_TEMPLATE` story-tracking scaffold, and a token-efficiency loop (`session_audit.jsonl` + `suggestions.md`). Two concrete new projects are in view — a credit-card statement parser / rewards
optimizer ("CardLedger") and a family tax calculator ("TaxCalculation") — and the goal is to let each inherit sane defaults **without** carrying NiftyShield's full process weight (council protocol,
multi-agent AutoTrigger gates, graph-indexed codebase tooling) regardless of whether it's actually needed.

## Governing principle: trigger-based, not time-based or size-based on one axis

A tier is adopted when a concrete condition fires, not on a fixed schedule and not purely as a function of project size. Stakes and size are different axes — a tiny codebase can still warrant a "high
tier" mechanism if what it computes is load-bearing (TaxCalculation's bracket/deduction logic is the worked example: small code, real consequences if wrong).

## The four tiers (draft)

| Tier | Trigger to add it | Ships |
|---|---|---|
<!-- lint-ignore-length -->
| **0 — Bootstrap** | Every project, day one | `CONTEXT.md` (mutable current-state doc, the only mandatory design doc up front) + a `CLAUDE.md` skeleton (Step 1 read-context → Step 2 confirm scope → Step 3 plan+go-ahead → Step 4 tests mandatory → Step 5 docs→tests→commit) + `README.md`. `scratch/` (dated-filename POC folder, see below) and `tmp/` (gitignored, throwaway) from day one — both cheap enough to start with. `commit` skill. Git conventions (imperative ≤60-char subject, no amending pushed commits, stage specific files). No `DECISIONS.md`, no `TODOS.md`, no `docs/plan/` yet — don't scaffold empty structure for decisions/backlog that don't exist yet. |
<!-- lint-ignore-length -->
| **1 — Recurring work** | Second real session, or a backlog exists | `docs/plan/_TEMPLATE/` + `docs/plan/README.md` §Conventions + `TODOS.md` (backlog + session log), `work`/`new-story` skills. `DECISIONS.md` — created on the *first* real architecture decision, not before; append-only, records "why" not "what." `session-close` skill + `session_audit.jsonl`/`suggestions.md` mechanism — cheap, pays off once sessions recur; no further gating needed beyond "you're doing a second session." |
<!-- lint-ignore-length -->
| **2 — Correctness-critical or multi-surface** | The domain has a load-bearing, hard-to-reverse decision (financial/legal correctness, irreversible migration) — fires regardless of project size — **or** work genuinely spans Claude + Antigravity + subagents | `docs/council/` protocol, for decisions meeting the real three-condition test (load-bearing + two defensible approaches + spans disciplines). A generic `code-reviewer` agent, plus a domain-specific reviewer only where a specific correctness risk exists (NiftyShield's `greeks-analyst`/`roll-validator` are the pattern — e.g. a `tax-rule-reviewer` for TaxCalculation). `handoff-antigravity` + `ANTIGRAVITY.md` only if Antigravity is actually in the loop. |
<!-- lint-ignore-length -->
| **3 — Scale** | Codebase big enough that "where is X" beats "just read the file" (rough heuristic: multiple thousands of LOC across many files), or a doc keeps getting reread wholesale | Rule 0 graph-tooling (`codebase-memory-mcp` indexing + the graph-before-read hook) — resist copying this into small projects; it's dead weight below a real size threshold. `CONTEXT_TREE.md` (module-tree survey, once `CONTEXT.md`'s flat list stops being enough). `md-organize` + `docs/archive/` (doc-growth housekeeping, once a doc crosses roughly 500–1000 lines). `weekly-audit` cadence skill. |

## The `scratch/` vs `tmp/` distinction

These are not the same kind of thing, and the template must keep them separate:

- **`scratch/`** — git-tracked, curated. `YYYY-MM-DD_topic_purpose.py` naming (the date is load-bearing — it's how a later session tells "already answered" from "stale"). Purpose-subfolders once the
  flat folder passes ~50 files. A documented **convergence rule**: a repeated plumbing probe (3+ occurrences) graduates to `scratch/_lib/`; a repeated design POC (2+ occurrences) either finds an
  existing production module already solves it (stop, just call it) or graduates to `scripts/dev/`/`src/` with full discipline (tests, types, Decimal). Never extract on a single occurrence — that's
  the same speculative-abstraction trap as anywhere else.
- **`tmp/`** — gitignored, genuinely throwaway, not a project deliverable. NiftyShield's only structured use of it is council-question draft staging before submission; everything else in it is
  unrelated one-off scratch left as-is.

Open question for PTB-2: does a new project need `scratch/`'s subfolder-per-purpose convention from day one (empty buckets), or only once its own flat `scratch/` passes some file count, mirroring
NiftyShield's own ~50-file trigger? Not yet decided.

## The architecture-doc trio

Three documents, three different mutability contracts — this shape is the reusable idea, independent of NiftyShield's specific file names or content:

- **`CONTEXT.md`** — a mutable snapshot. Always edited in place, never appended to. Answers "what's true right now." The only Tier-0 design doc.
- **`DECISIONS.md`** — append-only. Answers "why did we choose this." Old entries are never rewritten, only occasionally archived wholesale once the file is too long (Tier 3's `md-organize` trigger).
  Created on the first real architecture decision (Tier 1), not before.
- **`CONTEXT_TREE.md`** — a derived index (file → one-line purpose). Exists only once `CONTEXT.md`'s inline "What Exists" listing gets too flat to navigate (Tier 3).

## Model routing (generalized, draft)

NiftyShield's `Owner | Model | Review` task-line format only earns its complexity once there's real variety of recurring task types (Tier 1+). Generalized into three buckets, to be applied instead of
copying NiftyShield's specific model names:

- **Mechanical/bulk** — well-specified, low-ambiguity work. A fast/cheap model, or Antigravity if that surface is wired in (Tier 2+).
- **Design/judgment** — anything with an open design question or domain nuance. The primary strong model for the session.
- **Independent verification** — a fresh subagent context (even the same model), used where outside review matters: code review before commit, or council for the rarer cross-discipline calls (Tier 2).

For a Tier 0/1 project, one model doing everything is correct, not a gap — don't build the routing table before Tier 2 is actually warranted. This story's own tasks already use the pattern as a worked
example: PTB-1 (discussion capture) stayed on the interactive session's model; PTB-4 (final Tier-2/3 synthesis write-up) is routed to a stronger model, mirroring `strategy-refactor-blueprint`'s own
BP-4/BP-5 convention of routing final-synthesis tasks to Opus rather than the model used for iterative back-and-forth.

## Distribution mechanism (draft, not yet decided — PTB-5)

Working conclusion from discussion, not yet finalized: a **template repo** (copy-once scaffold, e.g. a GitHub template repository or a scaffold script), not a git submodule and not an installable
package — for the same reason as the earlier conclusion about NiftyShield's own logging/db-helper code. Most of what's being templated here (`.claude/skills/*.md`, hook scripts,
`docs/plan/_TEMPLATE/`, a `CLAUDE.md` skeleton) is static harness configuration Claude Code reads at session start, not runtime code with a version-bump story. Submodules were rejected specifically
because they pin an exact commit SHA per consumer with no changelog gate and drift silently; an installable package was rejected because there's no real *runtime* code being shared here yet — that's a
separate, later question (see below), gated on a second real consumer existing.

Genuinely reusable **code** (e.g. `setup_logging()`, a statement-parsing plugin registry, a category-classification engine) is out of scope for this story. That extraction — if it happens — is gated
on a second real consumer existing to validate the boundary, per the earlier conclusion in discussion: building a shared library speculatively risks guessing the API wrong and having to break it on
the first real consumer anyway.

## Open questions (carried from `prompt.md` §"Perspectives not covered" — not resolved here)

- Whether TaxCalculation's correctness stakes actually warrant Tier 2 (council) despite its small size — needs Animesh's judgment on how costly a tax-calc mistake actually is versus the overhead of a
  council question.
- Whether CardLedger's statement-parser and rewards-optimizer are truly one system or two — changes whether "twin projects" reasoning applies to it or to TaxCalculation.
- Antigravity's actual fit for a small, single-operator project — the handoff pattern was designed for NiftyShield's scale; untested whether it's worth the overhead below Tier 2.
- `scratch/` subfolder timing for a new project (see above, under the scratch/tmp section) — open for PTB-2.
- Where the template repo itself should live, and whether it ever needs an "update flow" back into existing consumers or is genuinely copy-once — open for PTB-5.

## Status

PTB-1 (this file) done. Next: PTB-2 — concretize Tier 0's literal starting file contents, and resolve the `scratch/` subfolder-timing question above.
