
# Cross-Project Claude Template Blueprint — prompt

> Capture the 2026-09-26 discussion on abstracting NiftyShield's Python conventions, Claude-Code harness (skills/hooks/agents), and `docs/plan/` scaffolding into a tiered template other future
> projects (starting with the CardLedger statement parser and TaxCalculation) can selectively inherit, without over-transplanting live-trading-grade process onto small personal-scale projects.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing anything. One task per session. Complete it fully. Stop.

## Why this story exists

NiftyShield accumulated, over months of live use, a set of things worth reusing elsewhere: Python hygiene conventions (`Decimal` for money, frozen dataclasses, type hints, testing discipline), a
Claude-Code operating harness (`.claude/skills/*`, `.claude/agents/*`, hooks), a `docs/plan/_TEMPLATE` story-tracking scaffold, and a token-efficiency loop (`session_audit.jsonl` + `suggestions.md`).
Three concrete new projects are now in view — a credit-card statement parser / rewards optimizer ("CardLedger"), a family tax calculator ("TaxCalculation"), and potentially more — and Animesh wants to
abstract "the good parts" so each new project inherits sane defaults instead of re-deriving them, **without** forcing every project to carry NiftyShield's full weight (council protocol, AutoTrigger
multi-agent gates, graph-indexed codebase tooling) regardless of whether it needs it.

The working hypothesis from discussion, to be refined across sessions rather than assumed final:

- **Tiering is trigger-based, not time-based or size-based on a single axis.** A tier is added when a concrete condition fires (a second real architecture decision exists → add `DECISIONS.md`; a doc
  crosses a size threshold → add `md-organize`; the domain has a load-bearing hard-to-reverse decision → add the council protocol, *even in a tiny codebase* — TaxCalculation's tax-bracket logic is the
  example that shows stakes and size are different axes).
- **Distribution mechanism is a template repo (copy-once scaffold), not a git submodule and not (yet) an installable package** — same reasoning as the earlier NiftyShield-to-shared-library discussion:
  most of what's being templated (`.claude/skills/*.md`, hook scripts, `docs/plan/_TEMPLATE/`, a `CLAUDE.md` skeleton) is static harness configuration Claude Code reads at session start, not runtime
  code with a version-bump story. Genuinely reusable *code* (e.g. `setup_logging()`, a statement-parsing plugin registry) is a separate, later, installable-library question — gated on a second real
  consumer existing, per the earlier "don't extract speculatively" conclusion — and is explicitly out of this story's scope.
- A draft four-tier structure (Bootstrap / Recurring work / Correctness-critical or multi-surface / Scale) was sketched in the 2026-09-26 conversation — see `docs/archive/` once this story archives,
  or the session transcript in the interim. **This draft is not final** — that is the entire point of this story existing.

## Scope guard

No `src/`/`scripts/` code in NiftyShield changes under this story. It produces two artifacts: the design record (`plan.md`, an extra file per `docs/plan/README.md` §Conventions "Extra files") and the
template repo itself, `/Users/abhadra/myWork/myCode/AI/project-scaffold/` (its own git repo).

**Superseded 2026-09-26:** this section originally said the story was discussion-only — no template repo created, no `.claude/` files copied, the build spun off as a separate story. PTB-2 and PTB-3
wrote `tier0/`/`tier1/` straight into `project-scaffold`, and after PTB-4 Animesh set the goal explicitly: at story completion `project-scaffold` holds everything — every tier, the `python/` overlay,
a working `scaffold.sh`, and the tier/trigger guide — with no follow-on build story. PTB-5..PTB-9 are planned to that end state.

**Standing instruction (Animesh, 2026-09-26):** this is expected to run across several future sessions as pure discussion — the tier boundaries, what belongs in each tier, and the distribution
mechanism are all still open. Do not treat any task below as "ready to execute" just because the session reaches it in sequence; each still needs explicit confirmation that the design question it
covers has actually converged.

## Session-start load hints

- This conversation's own transcript (2026-09-26) is the primary source until `plan.md` exists — it contains the tier table, the scratch/tmp distinction, and the architecture-doc-trio reasoning
  (`CONTEXT.md` = mutable snapshot, `DECISIONS.md` = append-only rationale, `CONTEXT_TREE.md` = derived index) in full.
- `SCRATCH.md`, `tmp/README.md` — the actual current scratch/tmp conventions this story is generalizing from.
- `docs/plan/README.md` §Conventions — the story/epic scaffolding this story is trying to make portable.
- `.claude/skills/protocol-reference/SKILL.md` §3 — existing model/surface routing pattern (`docs/antigravity/ai_collaboration_plan.md`,
  `docs/plan/full-repo-review/findings/FR-8_practitioner-devex.md`) to generalize from, not copy verbatim.
- `docs/plan/strategy-refactor-blueprint/` — sibling discussion-only story; same pattern (planning gate before any execution, standing instruction against auto-advancing tasks).

## Task overview

- **PTB-1** — Write up the 2026-09-26 discussion (tier table, scratch/tmp distinction, architecture-doc trio, model-routing generalization) as this story's `plan.md` draft — a durable record to
  converge against, not a final answer.
- **PTB-2** — Concretize Tier 0 (Bootstrap): exact file contents/skeletons (`CLAUDE.md`, `CONTEXT.md`, `SCRATCH.md`, `tmp/README.md`, `commit` skill) a brand-new project would actually start with.
- **PTB-3** — Concretize Tier 1 (Recurring work): exact `docs/plan/_TEMPLATE` portability, `session-close` / `work` / `new-story` skill genericization, the `DECISIONS.md`-on-first-decision trigger.
- **PTB-4** — Concretize Tier 2/3 gating criteria (council, AutoTrigger agents, Rule 0 graph tooling, `md-organize`) and the generalized model-routing buckets (mechanical / design-judgment /
  independent verification).
- **PTB-5** — Record the distribution decision, and rebuild `scaffold.sh` around per-piece selection (not a numeric tier level) with merging for the shared files (`CLAUDE.md`, `.claude/settings.json`,
  `.gitignore`). Re-scoped 2026-09-26 from "hand off to a separate build story."
- **PTB-6** — Concretize the `python/` overlay (renamed from the earlier `python-addon/` concept, deferred at PTB-2): `src`/`scripts`/`tests`/`logs` structure, `pyproject.toml` + requirements files,
  pre-commit config — most future projects will actually need this, since a majority of Animesh's planned projects are Python.
- **PTB-7** — Write Tier 2 (`stakes/`, `test-runner/`, `multi-surface/`) into `project-scaffold`, genericized.
- **PTB-8** — Write Tier 3 (Rule 0 bundle, `md-organize`, `state-freshness`, `weekly-audit`) into `project-scaffold`, genericized.
- **PTB-9** — Port the tier/trigger guide into `project-scaffold/README.md`, ship a compact trigger list into every scaffolded project, validate three reference configurations end to end, archive.

Task order above is a starting guess, not a commitment — expect renumbering, merging, or new tasks as the discussion continues. `stories.md` intentionally leaves later tasks under-specified until
earlier ones converge.

## Definition of done

Done when `project-scaffold` is self-contained and usable without NiftyShield. That means every tier piece and the `python/` overlay are written; `scaffold.sh` selects pieces individually and merges
shared files; the tier/trigger guide lives in `project-scaffold/README.md`; a scaffolded project ships its own trigger list; the three reference configurations validate; and Animesh confirms it's
ready to use. (Re-defined 2026-09-26 — previously "`plan.md` written, build handed off to a follow-on story.")

## Perspectives not covered

- **Whether TaxCalculation's correctness stakes actually warrant Tier 2 (council) despite its small size** — flagged as a live example in discussion, not yet decided; needs Animesh's judgment on how
  costly a tax-calc mistake actually is versus the overhead of a council question.
- **Whether CardLedger's statement-parser and rewards-optimizer are truly one system or two** — flagged in discussion as needing confirmation; changes whether "twin projects" reasoning applies to it
  or to TaxCalculation.
- **Antigravity's actual fit for a small, single-operator project** — the handoff-antigravity pattern was designed for NiftyShield's scale; untested whether it's worth the overhead below Tier 2.
- **Hook language dependency** — several NiftyShield hooks shell out to Python helpers (`scripts/dev/hooks/*.py`), but the scaffold is meant to be language-agnostic. PTB-7/PTB-8 decide per hook;
  nobody has yet checked whether a non-Python project would ever reach Tier 3 in practice.
- **Template drift** — copy-once means `project-scaffold` improvements never reach existing projects. With per-piece selection, re-running `scaffold.sh` adds new pieces but never updates files already
  there; whether that is enough is untested until a second project exists.
