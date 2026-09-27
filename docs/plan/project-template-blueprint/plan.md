
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
| **0 — Bootstrap** | Every project, day one | `CONTEXT.md` (mutable current-state doc, the only mandatory design doc up front) + a `CLAUDE.md` skeleton (Step 1 read-context → Step 2 confirm scope → Step 3 plan+go-ahead → Step 4 tests mandatory → Step 5 docs→tests→commit) + `README.md`. `scratch/` (dated-filename POC folder, see below — mandatory staging ground, no throwaway code lands directly in `src`/`scripts`) and `tmp/` (gitignored, throwaway) from day one. `commit` skill. Git conventions (imperative ≤60-char subject, no amending pushed commits, stage specific files). All token-optimization techniques below marked Tier 0 (bash output discipline, `session-close` loop, `codebase-memory-mcp` indexing without its enforcement gate, keeping `CLAUDE.md` itself thin). No `DECISIONS.md`, no `TODOS.md`, no `docs/plan/` yet — don't scaffold empty structure for decisions/backlog that don't exist yet. |
<!-- lint-ignore-length -->
| **1 — Recurring work** | `TODOS.md`: the moment there's a *second* piece of work being consciously deferred rather than done now — one task in flight needs no backlog, the instant of "I'll get to that after" is the first entry. `DECISIONS.md`: the moment you're choosing between two-or-more genuinely viable approaches and the choice would need justifying to a future reader — test: "if I didn't write this down, would a future session plausibly redo this wrong or re-litigate it?"; a forced/obvious first decision doesn't count | `docs/plan/_TEMPLATE/` + `docs/plan/README.md` §Conventions + `TODOS.md` (backlog + session log, "pointers only" convention), `work`/`new-story` skills. `DECISIONS.md` — append-only, records "why" not "what." |
<!-- lint-ignore-length -->
| **2 — Correctness-critical or multi-surface** | The domain has a load-bearing, hard-to-reverse decision (financial/legal correctness, irreversible migration) — fires regardless of project size — **or** work genuinely spans Claude + Antigravity + subagents | `docs/council/` protocol, for decisions meeting the real three-condition test (load-bearing + two defensible approaches + spans disciplines). A generic `code-reviewer` agent, plus a domain-specific reviewer only where a specific correctness risk exists (NiftyShield's `greeks-analyst`/`roll-validator` are the pattern — e.g. a `tax-rule-reviewer` for TaxCalculation). `handoff-antigravity` + `ANTIGRAVITY.md` only if Antigravity is actually in the loop. |
<!-- lint-ignore-length -->
| **3 — Scale** | Codebase big enough that "where is X" beats "just read the file" (rough heuristic: multiple thousands of LOC across many files), or a doc keeps getting reread wholesale | Rule 0 graph-tooling (`codebase-memory-mcp` indexing + the graph-before-read hook) — resist copying this into small projects; it's dead weight below a real size threshold. `CONTEXT_TREE.md` (module-tree survey, once `CONTEXT.md`'s flat list stops being enough). `md-organize` + `docs/archive/` (doc-growth housekeeping, once a doc crosses roughly 500–1000 lines). `weekly-audit` cadence skill. |

Rows 2 and 3 are the original sketch. They are concretized into checklists and thresholds under "Tier 2 — gating, concretely" and "Tier 3 — gating, concretely" below (PTB-4); where the two differ,
those sections win — notably, Tier 2 is split into two independent triggers (2a stakes, 2b multi-surface).

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
  Created the moment a decision between genuinely viable approaches needs justifying to a future reader (Tier 1) — see the concrete test in the tier table above, not before.
- **`CONTEXT_TREE.md`** — a derived index (file → one-line purpose). Exists only once `CONTEXT.md`'s inline "What Exists" listing gets too flat to navigate (Tier 3).

## The enforcement lesson that shapes Tiers 2 and 3 (from NiftyShield's own history)

Source: `docs/archive/process/2026-05-08_workflow-improvements.md`. When NiftyShield first added its AutoTrigger agent table and council checkpoint, both lived only as `CLAUDE.md` text marked "not
optional." Under task pressure neither fired: the IVR task (`3ed90fe`) ran 11 tests, committed, and confirmed its SHA without ever spawning `test-runner` or `code-reviewer`. A `UserPromptSubmit`
checklist injection did not fix it either — text read at task start gets overridden by the time the action happens. What actually worked was a hook that fires **at the moment of the action**:
`council_check.sh` on the first `Edit`/`Write`, `inline_full_suite.sh` on a Bash `pytest` call, `guard_src_reads.sh` on a `Read` of `src/`/`scripts/`.

The portable rule this yields: **a Tier 2/3 gate ships together with its at-the-moment hook, or it does not ship.** A gate that exists only as protocol prose is worse than no gate — it costs resident
tokens every session and gives false assurance. Every gate below names the hook it travels with. Hooks stay warn-only (exit 0) by default, matching NiftyShield's own choice; promote one to blocking
only after it has been observed being ignored on a real task.

## Tier 2 — gating, concretely (PTB-4)

Tier 2 has two independent triggers that were fused in the draft tier table. They adopt different file sets and are evaluated separately — a project can hit one without the other.

### 2a. Stakes trigger — council protocol + review agents

**Project-level check (run once, and again whenever a new domain area is added).** Adopt 2a when you can answer yes to both:

- [ ] Can you name a specific computation whose wrong output lands **outside the code** — money moved or owed, a legal/tax filing, data destroyed or irreversibly migrated?
- [ ] Is there **no downstream check** that would catch the error before it lands (a human reviewing every output, a reconciliation against an external source, a reversible preview step)?

Project size is not an input. Worked examples, answered against the checklist:

- **TaxCalculation** — bracket/deduction/regime-choice logic → a filed return → penalty and interest if wrong; the filing *is* the output, so nothing downstream catches it. **Passes both boxes.**
  Whether Animesh actually wants to pay council overhead for it stays an open question (below) — the checklist says it qualifies, not that it must be used.
- **CardLedger statement parser** — a mis-parsed or miscategorized transaction surfaces in a report Animesh reads before acting on any rewards suggestion, and nothing irreversible happens. **Fails box
  2** as long as that stays true. It flips if CardLedger ever auto-acts (pays, files, moves money).
- **NiftyShield** — live capital, orders, P&L. Passes trivially; the reference implementation.

**Per-decision council checklist (only once 2a is adopted).** Convene a council only when every box is ticked. This is NiftyShield's Step 2b three-condition test with its first condition split in two,
because "load-bearing" and "costly to reverse" fail independently in practice:

- [ ] **Load-bearing** — being wrong changes an output someone acts on (the 2a computation, or something feeding it).
- [ ] **Costly to reverse** — undoing it after it ships takes more than one session: a data migration, re-processing history, a re-filing, or unwinding positions.
- [ ] **Two defensible approaches** — you can write the strongest one-paragraph case for each without strawmanning either. If one is obviously right, just pick it.
- [ ] **Spans ≥2 disciplines** — e.g. tax law + data modelling, options math + risk + engineering. A pure-engineering fork, however costly, is a `DECISIONS.md` entry, not a council.

Fallbacks when not every box is ticked: boxes 1–3 without 4 → write a `DECISIONS.md` entry that records both options and why one won (Tier 1 already covers this). Fewer than that → just decide and
move on.

**Ships with 2a:** `docs/council/README.md` + `_TEMPLATE`; the Step 2b block in `CLAUDE.md`; `council_check.sh` (PreToolUse `Edit|Write`, warn-only, prints the four boxes); a generic `code-reviewer`
agent (type hints, error handling, hygiene — no domain checks) plus a `REVIEW.md` skeleton for the project to fill; the AutoTrigger **table mechanism** in `CLAUDE.md` with only the generic rows
populated.

**Domain reviewer agents are per-project, never portable.** NiftyShield's `greeks-analyst`, `roll-validator`, and `options-strategist` stay behind — only the mechanism travels: one agent per named
correctness-risk surface, triggered by a path or topic, blocking. The rule for adding one is: **each ticked 2a project-level check names a computation; that computation's module gets a reviewer agent
with a path trigger.** For TaxCalculation, that would be a `tax-rule-reviewer` firing on changes to the bracket/deduction module. No surface named → no domain agent.

**`test-runner` agent — separate, context-cost trigger, not stakes.** Its value is keeping full-suite output out of the main context, not independent judgment. Adopt it (together with its
`inline_full_suite.sh` hook, which is what actually makes it fire) the first time a full `pytest -q` run's output is long enough that you trim it by hand, or you catch a session running the full suite
inline more than once per task. Before that, the Tier 0 rule "tests pass before commit" run inline is correct.

### 2b. Multi-surface trigger — cross-agent routing

Adopt only when a **second implementing surface (Antigravity or similar) has actually done at least one real task** on the project — not speculatively because it might. Ships: the Step 3b
Claude-vs-other-surface routing table; `handoff-antigravity` (content injected inline, not by path reference — the 2026-05-08 consultation measured ~3–5K tokens saved per handoff); `ANTIGRAVITY.md`;
`AGENTS.md` as a full mirror of `CLAUDE.md`, never a stub. The standing caveat from NiftyShield carries over unchanged: the second surface cannot spawn `.claude/agents/*`, so if 2a is also adopted,
every 2a review gate still runs in Claude Code, and the Phase Completion Output SHA check is Claude's job.

Hook-surface caveat: gates here only enforce where hooks fire. Per FR-8 (`docs/plan/full-repo-review/findings/FR-8_practitioner-devex.md` §2), Claude Code runs `.claude/hooks/*` and Cowork was
assessed as not — a claim FR-8 itself flagged as unverified. Until verified, run Tier 2+ gated work in Claude Code.

## Tier 3 — gating, concretely (PTB-4)

Tier 3 items are pure scale/cost optimizations — none of them affect correctness, so each has its own threshold and can be adopted one at a time. Numbers are anchored to when NiftyShield actually
needed them, not guessed.

| Item | Adopt when (first to fire wins) | Ships with it |
|---|---|---|
<!-- lint-ignore-length -->
| **Rule 0 enforcement** (graph-before-read) | **Numeric:** production code (`src/` + `scripts/` or equivalent) reaches ~10K LOC or ~70 source files — NiftyShield added `guard_src_reads.sh` at 10,247 LOC / 69 `.py` files (`a1aca07`, 2026-04-24); it is 68K / 257 now. **Behavioral (overrides the number in either direction):** over a typical session, most of your source `Read`s are to find *where* something is or *who calls* it, rather than to understand a file you already located. | `guard_src_reads.sh` + `repeat_read.sh` (PreToolUse `Read`), the `graph_snippet` fingerprint-stripping wrapper, the Rule 0 block in `CLAUDE.md`. Indexing itself is already Tier 0. |
<!-- lint-ignore-length -->
| **`CONTEXT_TREE.md`** | Same event as Rule 0 in practice — NiftyShield split it out of `CONTEXT.md` in that same `a1aca07` commit. Standalone test: `CONTEXT.md`'s "What Exists" section needs more than one line per top-level package to stay navigable. | `CONTEXT_TREE.md` skeleton; `CONTEXT.md` keeps one line per package plus a pointer. |
<!-- lint-ignore-length -->
| **`wide_grep.sh`** | Adopted with Rule 0 — an unscoped grep only becomes expensive at the same scale where the graph starts beating `Read`. | `wide_grep.sh` hook (PreToolUse `Bash`). |
<!-- lint-ignore-length -->
| **`md-organize` + `docs/archive/`** | Any root doc passes ~400 lines (the `md-organize` skill's own `CONTEXT.md ≤ 400 lines` check), or a doc gets read in full each session when only its latest section is used. | `md-organize` skill; `docs/archive/` with a dated-snapshot naming convention. |
<!-- lint-ignore-length -->
| **`state_doc_freshness.sh`** | Commit volume is high enough that state docs silently drift — the first time a session acts on a stale `CONTEXT.md`/`DECISIONS.md` claim. NiftyShield's per-doc thresholds (15–60 src commits) are a starting point to tune, not constants. | SessionStart hook + per-doc threshold list. |
<!-- lint-ignore-length -->
| **`weekly-audit`** | `session_audit.jsonl` (Tier 0) has enough rows that reading it by hand stops being quick — rough guide: a few dozen sessions. Stays on-demand, never cron, exactly as NiftyShield runs it. | `weekly-audit` skill. |

## Model routing (converged, PTB-4)

**Tier 0/1: one model for everything, and that is correct, not a gap.** The `Model:` field on task lines (free text since PTB-3) may be left `n/a`. Routing only starts paying for itself when Tier 2a
fires, because that is when an independent-verification context first earns its cost.

Once Tier 2 applies, route by **reasoning demand × cost of an error**, not by task size. NiftyShield's own 2026-05-08 rationale is the seed: Haiku for pass/fail test runs (no reasoning needed), Sonnet
for orchestration, planning and graph queries, Opus for code review, roll validation, and strategy design — the decisions with financial consequence. Generalized into three buckets:

<!-- lint-ignore-length -->
| Bucket | What goes in it | Model / surface |
|---|---|---|
<!-- lint-ignore-length -->
| **Mechanical / bulk** | Spec fully determined **and** correctness machine-checkable (tests, linters, a hook). Pass/fail test runs; pattern migrations across N files; applying an already-decided spec; doc reflow; close-out bookkeeping (SHA backfills, status rows, session-log lines). | Smallest model that follows the spec reliably — Haiku-class for pass/fail, Sonnet-class for multi-file edits — or the second surface if 2b is adopted. |
<!-- lint-ignore-length -->
| **Design / judgment** | An open question, domain nuance, or a spec that may change as it's written. Planning and story authoring; debugging; design-gate specs every downstream task depends on (NiftyShield's `FMT-1` was routed to Opus "for the spec-writing pass itself, not just a post-hoc review"); final-synthesis write-ups (this task, `strategy-refactor-blueprint` BP-4/BP-5). | Strongest available model; normally the interactive session itself. Iterative back-and-forth can run a tier lower, with the converging synthesis step escalated. |
<!-- lint-ignore-length -->
| **Independent verification** | Any check whose value comes from **not** sharing the author's context: pre-commit code review, domain reviewer agents, council. | A fresh subagent context with its checklist (`REVIEW.md`) actually loaded — the 2026-05-08 consultation found same-context persona review reliably misses the hygiene rules it wasn't given. Strong model where 2a applies (errors are consequential); the same model is acceptable otherwise, since the fresh context is the point. |

Escalation rule carried from FR-8 §3 (job type 5): a task starts in the bucket its shape suggests and **moves up** the moment it turns out to touch a 2a computation — a routine debugging session that
finds the bug is in the tax/P&L path becomes design/judgment work, and its fix goes through independent verification.

## What `tier2/` and `tier3/` will hold (built by PTB-7 and PTB-8)

Not written to `project-scaffold/` under PTB-4 — that task's scope was `plan.md` only. PTB-7 (Tier 2) and PTB-8 (Tier 3) build from this list, in the fragment shape PTB-5 defines:

- `tier2/stakes/` (2a): `docs/council/README.md` + `_TEMPLATE/`, `.claude/agents/code-reviewer.md` (generic), `REVIEW.md` skeleton, `.claude/hooks/council_check.sh`, `CLAUDE.md` Step 2b + AutoTrigger
  table fragments. `test-runner.md` + `inline_full_suite.sh` as a separately selectable piece (its trigger is context cost, not stakes).
- `tier2/multi-surface/` (2b): `.claude/skills/handoff-antigravity/`, `ANTIGRAVITY.md`, `AGENTS.md` template, `CLAUDE.md` Step 3b fragment.
- `tier3/`: `.claude/hooks/{guard_src_reads,repeat_read,wide_grep,state_doc_freshness}.sh`, the `graph_snippet` wrapper, `.claude/skills/{md-organize,weekly-audit}/`, `CONTEXT_TREE.md` skeleton,
  `CLAUDE.md` Rule 0 fragment.

**Two structural problems this list exposes for PTB-5:**

1. `scaffold.sh` overlays tiers in whole-level order (`tier0` … `tierN`), but Tier 2 is now two independently selectable halves and Tier 3 is six independently triggered items. A single numeric tier
   level can no longer express "2a yes, 2b no, Rule 0 yes, weekly-audit not yet." The interactive-question design PTB-5 already owns needs to be per-item, not per-level.
2. `.claude/settings.json` and `CLAUDE.md` are **merged**, not copied: every Tier 2/3 hook needs a registration in the same `settings.json`, and every gate adds a fragment to the same `CLAUDE.md`. The
   current overlay semantics (a higher tier's file overwrites a lower tier's) would drop earlier tiers' hook registrations. PTB-5 needs a merge step for these two files (for example, fragment files
   appended in tier order, and a JSON merge on `hooks` arrays), or it ships a broken `settings.json` the first time two tiers both register hooks.

## Distribution mechanism (draft, not yet decided — PTB-5)

Working conclusion from discussion, not yet finalized: a **template repo** (copy-once scaffold, e.g. a GitHub template repository or a scaffold script), not a git submodule and not an installable
package — for the same reason as the earlier conclusion about NiftyShield's own logging/db-helper code. Most of what's being templated here (`.claude/skills/*.md`, hook scripts,
`docs/plan/_TEMPLATE/`, a `CLAUDE.md` skeleton) is static harness configuration Claude Code reads at session start, not runtime code with a version-bump story. Submodules were rejected specifically
because they pin an exact commit SHA per consumer with no changelog gate and drift silently; an installable package was rejected because there's no real *runtime* code being shared here yet — that's a
separate, later question (see below), gated on a second real consumer existing.

Genuinely reusable **code** (e.g. `setup_logging()`, a statement-parsing plugin registry, a category-classification engine) is out of scope for this story. That extraction — if it happens — is gated
on a second real consumer existing to validate the boundary, per the earlier conclusion in discussion: building a shared library speculatively risks guessing the API wrong and having to break it on
the first real consumer anyway.

### Tier 0 output, concretely (answered ahead of PTB-5, scoped to Tier 0 only)

The output is a git repo, not a loose folder of files floating around — a small one, mostly markdown plus a few real config files, version-controlled itself so the template can be iterated on and
diffed over time.

**Canonical location (superseding the earlier `~/myWork/myCode/_templates/py-project-tier0/` sketch — decided in the PTB-2 session):** `/Users/abhadra/myWork/myCode/AI/project-scaffold/`. The root
folder name names the template project itself, not a single tier or language; each tier is a subfolder inside it (`tier0/`, `tier1/`, `tier2/`, `tier3/`), added as PTB-2/3/4 concretize each one.
`project-scaffold` is `git init`'d and has its first commit (`2e0c667`), as its own independent GitHub-project-shaped repo (see Distribution section below for the clone-once + scaffold-script model) —
tiers are never their own separate repos; only `project-scaffold` itself is one, with the tiers as plain subfolders inside it.

Current state of `project-scaffold/` (2026-09-26, PTB-2 session):

```
project-scaffold/
├── tier0/                          # populated this session (PTB-2)
│   ├── README.md
│   ├── CLAUDE.md                   # Step 1-5 skeleton, placeholder comments for deferred sections
│   ├── CONTEXT.md                  # 4-header skeleton (What Exists / Key Decisions ptr / Constraints / Protocol ptr)
│   ├── .gitignore
│   ├── session_audit.jsonl         # empty seed
│   ├── suggestions.md              # empty seed
│   ├── scratch/
│   │   ├── SCRATCH.md              # naming convention + convergence rule; subfolder-bucket list stripped (Tier 0 stays flat)
│   │   └── _lib/                   # empty, kept for the convergence rule to point to
│   ├── tmp/
│   │   └── README.md
│   └── .claude/skills/
│       ├── commit/SKILL.md          # written PTB-2 session (re-scoped from PTB-3 — Tier 0 per tier table above)
│       └── session-close/SKILL.md   # written PTB-2 session (re-scoped from PTB-3 — Tier 0 per tier table above)
├── tier1/                           # populated PTB-3 session
│   ├── docs/plan/_TEMPLATE/          # story/ + epic/ skeletons, generic-only
│   └── .claude/skills/
│       ├── work/SKILL.md            # bug branch made optional-and-detected
│       └── new-story/SKILL.md       # ported near-verbatim, already project-agnostic
├── tier2/                           # empty — PTB-4
└── tier3/                           # empty — PTB-4
```

Notably little actual Python code — Tier 0 is almost entirely markdown + config, which is exactly why "git repo to copy from" beats "installable package" here: there is no runtime code to
version-bump, just a starting shape to copy.

**`python-addon/` deferred, not built yet (decided in the PTB-2 session):** an earlier draft of this session put a `python-addon/` subfolder (with `pyproject.toml`, `.pre-commit-config.yaml`,
ruff/mypy/pytest config) directly inside `tier0/`. Animesh corrected this — Tier 0 is meant to stay universal/language-agnostic, and this repo (`project-scaffold`) isn't itself a Python project, so
building Python-specific tooling into it now is premature. Do **not** create `python-addon/` (at `tier0/python-addon/`, as a sibling of `tier0/`, or anywhere else) until a future session actually
identifies `project-scaffold` — or the tier-0-derived output — as needing Python tooling. When that trigger fires, decide then whether it lives inside `tier0/`, as a sibling at the `project-scaffold/`
root, or elsewhere; that placement question is explicitly not resolved by this note.

**Trigger fired (2026-09-26, this session):** Animesh confirmed a majority of planned projects (CardLedger, TaxCalculation, and future ones) are Python. **PTB-6** now owns concretizing this overlay —
see `tasks.md`/`stories.md` for the task spec. This note stays as the historical record of why it was deferred in the first place; do not re-derive that reasoning in PTB-6, just read it.

**Renamed to `python/` (2026-09-26, same session):** "`python-addon/`" implied a bolt-on; Animesh's framing is that a Python project's actual code structure (`src/`, `scripts/`, `tests/`, `logs/`)
belongs in this overlay too, not just tooling config — so it's the base Python project shape, not an addon. Confirmed via discussion, four concrete decisions locked in ahead of PTB-6 doing the work:
dependency management stays `requirements.txt` + `requirements-dev.txt` (matches NiftyShield, not a `pyproject.toml`-only model); `logs/` ships with a minimal `setup_logging()` stub, not just an empty
folder; `data/` is conditional on the project's actual input/output shape, not scaffolded by default; pre-commit hooks are `ruff`/`ruff-format`/`mypy`/`detect-secrets` plus a generic `pytest`
test-gate hook — the domain-agnostic five, no NiftyShield-specific local hooks.

**PTB-6a design-doc discussion (2026-09-27):** prompted by a real diagnosis — `ic_nifty_v1.py`/`ic_nifty_v2.py` both crossing 1000+ LOC — worked back from "why" to "what would have prevented it."
Generic SRP framing didn't catch it (a class accreting entry/exit/roll/sizing logic doesn't obviously violate "one reason to change" until it's already large); the concrete diagnosis is OCP: each new
roll/entry rule was added as a branch inside an existing decision method instead of a new implementer of an interface. That reframing — SOLID as concrete, checkable *triggers* tied to the exact edit
that provokes them, not a principles essay — is now the confirmed approach for `python/`'s design-principles content, superseding the earlier "not a general SOLID essay" framing in `stories.md` (that
principle still holds: `tier0/CLAUDE.md` stays thin; the change is *where* the content lives — a separate trigger-loaded `PYTHON_DESIGN.md` — and *how* it's written, as triggers). Content also folds
in: Zen of Python (PEP 20) as the governing frame; a small named pattern set (Strategy — the `EntryRule`/`ExitRule`/`RollPolicy` seam itself; Factory Method; Template Method; Decorator; Observer only
if an actual reactive need exists); and two reference links for edge cases (`testdriven.io/blog/clean-code-python`, `refactoring.guru/design-patterns/python`), framed as fallback consultation, not
required reading. Also discussed and deferred: `ruff N` (pep8-naming) enablement in the `python/` overlay's `pyproject.toml` template — confirmed necessary but must ship with a documented exception
for option-pricing math notation (`S`/`K`/`T`/`IV`), since a live check against NiftyShield's own code (`ruff check --select N`) returned 53 violations, 46 of them exactly that notation, not naming
carelessness. Explicitly scoped: no `ruff`/`pyproject.toml` change to NiftyShield itself — this is `project-scaffold`-template-only.

**`PYTHON_DESIGN.md` written (2026-09-27):** `project-scaffold/python/PYTHON_DESIGN.md` — the doc described above, written directly to `project-scaffold` (NiftyShield's own source/config untouched).

**PTB-6a closed (2026-09-27):** `project-scaffold/python/` is a root-level sibling piece (not nested inside a tier) — Python is orthogonal to the tier axis, so a Tier 0 project can be Python or not,
and later tiers don't change that. File set: `src/`/`scripts/`/`tests/` each seeded with `__init__.py` (`scripts/` includes `dev/` and `dev/hooks/` sub-packages, also seeded); `logs/setup_logging.py`
(stdlib `logging`, not structlog — this overlay stays dependency-free by default) + `logs/.gitignore` scoping the ignore to `*.log`; `pyproject.toml` (dependency-free `[project.dependencies]`,
`ruff`/`mypy`/`pytest`/`coverage` config carried over from NiftyShield's own, `ruff N` left commented as a note, not enabled — the math-notation exception only matters once a project that needs it
exists); `requirements.txt` (empty, a comment, not pre-populated) + `requirements-dev.txt`; `.pre-commit-config.yaml` with the full confirmed hook list (`ruff`, `ruff-format`, `mypy`,
`detect-secrets`, a local `pytest-gate` hook, `bandit`, `no-script-main-logger`, `no-bare-logging`, `md-line-length`/`md-reflow` — the latter two copied verbatim from
`scripts/dev/{reflow_md.py,hooks/check_md_line_length.py}`, both already generic with no NiftyShield-specific scoping, and generalized here to the whole tree rather than `docs/plan`-scoped);
`Makefile` with the confirmed generic targets, `coverage` threshold as a placeholder (`60`, not NiftyShield's `80`), `dupes`/`dead-code` left as a comment rather than commented-out targets (advisory
tools aren't installed by default, so there's nothing to wire yet); `.gitignore.fragment` (`.venv/`, caches, `*.pyc`, `logs/*.log`); `CLAUDE.fragment.md` at a new `<!-- INSERT: python -->` marker
added to `tier0/CLAUDE.md`'s existing "Python conventions" section (type hints on all public signatures, `(str, Enum)`, opt-in `Decimal`, the `setup_logging()` call convention, the `__init__.py` rule,
a pointer to `PYTHON_DESIGN.md`). `data/` stays undocumented-by-default per the conditional decision — added per-project when needed, not scaffolded. Validated in two passes: standalone
(`copy_piece_files` against a scratch destination — flat, no leftover placeholder names) then end-to-end via `scaffold.sh --piece python` (tier0 + python together — `.gitignore` and `CLAUDE.md`
fragment merges both landed correctly). Wired into `scaffold.sh`'s `PIECES` array (per-piece selection, not a numeric tier or standalone flag, per PTB-5's mechanism).

**PTB-2 closed (2026-09-26):** Animesh confirmed the final file set. Corrections made during review before sign-off: `python-addon/` removed entirely (deferred — see below, not universal Tier 0);
`.gitignore` stripped of Python-specific entries (`__pycache__/`, `*.pyc`, `.venv/`) and fixed so `tmp/README.md` isn't silently excluded by the `tmp/` ignore rule (`tmp/*` + `!tmp/README.md`);
`commit` skill's Step 2 genericized (was hardcoded to `pytest`, now command-agnostic); `commit`/`session-close` skills re-scoped in from PTB-3 and written (see tree above) since both are Tier 0, not
Tier 1, per this file's own tier table — PTB-3 narrowed to `work`/`new-story` only. `.claude/settings.json` deliberately excluded from Tier 0 — every hook/permission in NiftyShield's real file maps to
a Tier 1+ mechanism (Rule 0 enforcement, council checkpoint, doc-staleness gates), so there is no Tier-0-appropriate content to ship; add the file the moment the first such mechanism is actually
adopted. `docs/plan/` confirmed to stay Tier 1 (not pulled forward) — discussed and re-affirmed, the trigger-based principle holds even though story planning happens early in some projects, because
the final project structure is flat regardless (see `TradeResearch` example above) so there's no cost to adding it exactly when the backlog trigger fires.

**Post-close corrections, found by dogfooding (2026-09-26, same day, after PTB-2 closed):** `project-scaffold/tier0/` was copied into a throwaway test project ("BudgetBuddy") and run through a real
Claude Code session to validate the skeleton actually works standalone. Two real gaps surfaced and were fixed directly in the already-closed Tier 0 output (not re-opening the task, just correcting the
deliverable):

- **`CLAUDE.md` Step 2 didn't ask whether code was wanted at all.** Given a vague "set up the project" prompt, the first dogfood run jumped straight to implementation questions (storage backend,
  language) and scaffolded a full Python package, without first confirming whether the project was even past the design/planning stage. Fixed: Step 2 now explicitly asks that fork first — "confirm
  whether this session wants an implementation... or is still in design/planning" — before any language/storage/`src/` questions. Re-run confirmed the fix works: a second dogfood session correctly
  stayed in design/planning mode (README + CONTEXT.md only, no `src/`) until asked.
- **New markdown files were being hard-wrapped at ~80 chars instead of the intended fill-to-≤200 style.** All 8 Tier 0 markdown files were reflowed with NiftyShield's own `scripts/dev/reflow_md.py`
  (run against the external path — the tool isn't part of Tier 0 itself). A new "Markdown formatting" section was added to `CLAUDE.md` stating the ≤200-char rule as a direct instruction, since this is
  a generation-time habit no post-hoc pre-commit hook would have prevented; the automated reflow tool/hook itself stays deferred to the `python-addon` trigger, per the same "rule now, tooling only
  once Python is confirmed" split as `.pre-commit-config.yaml` above.

Separately, all "NiftyShield"-referencing wording was stripped from `tier0/`'s placeholder comments (5 occurrences — in `CLAUDE.md`'s file-thinness note, module-index note, Python-conventions note,
and markdown-reflow note, plus `scratch/SCRATCH.md`'s subfolder-timing note) — these were citing NiftyShield as the pattern's origin, which is harmless in isolation but inappropriate for a template
meant for unrelated future projects to inherit; replaced with generic wording carrying the same guidance with no attribution to the source project.

`project-scaffold` is now `git init`'d with its first commit (`2e0c667`) including all of the above.

**How a new project gets it (decided PTB-5, 2026-09-26, superseding the two-mechanism sketch below):** `project-scaffold/scaffold.sh <destination-path> [--piece <name>]...` — a local, per-piece
scaffold script, no GitHub dependency. `project-scaffold` stays local-only (no remote, not marked a GitHub template repository) until a second real consumer project actually needs `gh repo create
--template`; see `DECISIONS.md` for the full reasoning. The two-mechanism sketch that follows (naming `py-project-tier0` and a `new_project_from_tier0` script) is the pre-PTB-5 draft, kept here as the
historical record of the discussion this decision resolved — the actual script is `project-scaffold/scaffold.sh`, not either name below.

1. **GitHub template repository** — mark the repo as a template in its settings, then `gh repo create <new-project> --template <you>/py-project-tier0` creates a brand-new repo seeded with those files
   and fresh git history (not a fork, no linkage back). Clean, but assumes the new project is pushed to GitHub.
2. **A local scaffold script** — `python -m scripts.dev.new_project_from_tier0 <target-path>` copies the file set into a fresh directory and runs `git init`. Purely local, no GitHub dependency — fits
   a project that starts as a local-only folder (e.g. `/Users/abhadra/myWork/myCode/AI/TaxCalculation`) before any decision to push it anywhere is made.

**Explicit tradeoff, either mechanism:** this is copy-once, not sync-forever. Improving the Tier 0 template later does not propagate to projects already scaffolded from it — the same conclusion as the
earlier submodule rejection (a live pointer isn't worth the coupling cost for static config). The template repo becomes something deliberately revisited and selectively backported from, not something
that auto-updates.

Tier 1–3 distribution (does a project add these by editing its own copy of the same files, or is there a second template layer?) stays open for PTB-5 — this section only concretizes Tier 0.

### Flatten-at-copy-time semantics (clarified in the PTB-2 session, input for PTB-5's scaffold script)

Confirmed via `TradeResearch` (`/Users/abhadra/myWork/myCode/AI/TradeResearch/`) as a worked example: a real consuming project is **always one flat directory at its own root** —
`TradeResearch/CLAUDE.md`, `TradeResearch/CONTEXT.md`, and `TradeResearch/scripts/*.py` all sit directly at root, with no `tier0/` or `python/`-named subfolder anywhere inside it. This settles a
question raised in discussion: the template repo's `tier0/`/`tier1/`/`tier2/`/`tier3/` subfolders are **source-only** — a place to copy *from* — and never appear as structure *inside* a scaffolded
project. There is no "promote a file from tier1 up into tier0" step, because tiers are never merged with each other inside `project-scaffold/` itself; they are each independently overlaid onto a real
project's root, once, at scaffold time. The same flattening applies to `python/` once it exists (see PTB-6 above) — its files land directly in the consuming project's root (`pyproject.toml`, `src/`,
`.pre-commit-config.yaml`), never inside a folder literally named `python/` in the real project.

**Idea floated for the PTB-5 scaffold script, not yet built (Animesh, this session):** make the local scaffold-script option interactive and repeatable rather than a static copy — run it once against
a target path, have it ask a handful of yes/no questions (does a backlog exist yet? etc.), and have it copy `tier0/*` plus whichever tier deltas the answers select, flattened directly into the target
root. Repeatable means re-running it against an existing project only adds files that don't already exist — it never overwrites what's already there. This is explicitly PTB-5 scope to design and
build, not something to implement mid-PTB-2 — captured here so PTB-5 starts from it instead of re-deriving it from scratch.

**"Is this a Python project?" question re-scoped to PTB-6 (2026-09-26, this session):** the Python-specific question in the interactive scaffold script is gated on `python/` actually existing, so it
belongs to PTB-6 as a final step once the `python/` file set and placement are finalized, not to PTB-5's more general interactive-script work. PTB-6 adds the question and the conditional `python/`
overlay to `scaffold.sh`; PTB-5's own interactive-script scope narrows to the tier-selection questions (backlog exists yet, etc.) that apply regardless of language.

**Refined further (Animesh, PTB-2 session, after `project-scaffold` was `git init`'d):**

- `project-scaffold` itself is a GitHub project. A consumer clones it once locally (not a submodule, not a sync-forever link — matches the copy-once conclusion above).
- The scaffold script lives at `project-scaffold`'s own root. Invoking it asks tier-specific questions plus a project name and target path, then writes the selected tiers' files — flattened per the
  semantics above — into `<path>/<project-name>/`.
- **Script scope stops at "files written."** It does not `git init` or make any commit in the new project — that stays a deliberate, separate step the operator takes afterward. Matches the `commit`
  skill's own philosophy (a commit is explicitly executed, never done silently on the operator's behalf).

### Validation script (built ahead of PTB-5, interim non-interactive version)

`/Users/abhadra/myWork/myCode/AI/project-scaffold/scaffold.sh` exists now — a simpler, non-interactive precursor to the PTB-5 idea above (no questions asked, no project-name prompt yet; just an
explicit tier level + destination path). It overlays `tier0/` through `tierN/` (in that order, so a higher tier's files can add to or override a lower tier's) flat onto the destination root, matching
the flatten-at-copy-time semantics confirmed above. Usage: `./scaffold.sh [--force] <tier-level 0-3> <destination-path>`; refuses a non-empty destination unless `--force` is passed; does not `git
init` or commit, per the "script scope stops at files written" principle above.

**Run this after every change to `tier0/`–`tier3/` to validate the overlay still produces a clean flat tree:**

```
/Users/abhadra/myWork/myCode/AI/project-scaffold/scaffold.sh --force 0 /Users/abhadra/myWork/myCode/AI/_scratch_to_delete
```

Source: `project-scaffold/tier0/` (raise the tier-level arg as tier1+ get populated by PTB-3 onward). Destination: `/Users/abhadra/myWork/myCode/AI/_scratch_to_delete` — a disposable scratch folder
outside `project-scaffold/`, not committed anywhere, safe to `rm -rf` and re-run against. After running, `find` the destination and confirm: no `tier0/`-named subfolder appears, `.claude/skills/`
holds one flat set of skill folders, and no duplicate/stale files remain from a prior run (re-run with `--force` after `rm -rf`ing the destination first if in doubt, since the script does not prune
files a later run no longer produces).

## Open questions (carried from `prompt.md` §"Perspectives not covered" — not resolved here)

- Whether TaxCalculation's correctness stakes actually warrant Tier 2 (council) despite its small size — needs Animesh's judgment on how costly a tax-calc mistake actually is versus the overhead of a
  council question. **PTB-4 update:** against the Tier 2a project-level checklist it qualifies (output lands outside the code, nothing downstream catches it). What stays open is whether to use it.
- Whether CardLedger's statement-parser and rewards-optimizer are truly one system or two — changes whether "twin projects" reasoning applies to it or to TaxCalculation.
- Antigravity's actual fit for a small, single-operator project — the handoff pattern was designed for NiftyShield's scale; untested whether it's worth the overhead below Tier 2.
- `scratch/` subfolder timing for a new project (see above, under the scratch/tmp section) — open for PTB-2.
- Where the template repo itself should live, and whether it ever needs an "update flow" back into existing consumers or is genuinely copy-once — open for PTB-5.

## Full inventory — everything present in NiftyShield, classified by tier

Working pass at PTB-2/PTB-3/PTB-4's classification question, done as one inventory sweep rather than per-tier — enumerate first, concretize file contents per tier afterward. "Not portable" means the
item is real and good but tied to this project's domain (options trading) and shouldn't be copied; "pattern only" means the mechanism generalizes but the content must be rewritten per project, not
copied verbatim.

### Python / code hygiene (from `CLAUDE.md` + the global `~/.claude/CLAUDE.md`)

<!-- lint-ignore-length -->
| Item | Tier | Note |
|---|---|---|
| Type hints + Google-style docstrings on public functions | 0 | Portable as-is. |
| `(str, Enum)` pattern, never `StrEnum` | 0 | Portable as-is (a 3.10 compatibility choice, not project-specific). |
| Functions 10–20 lines typical, split only for clarity | 0 | Portable as-is. |
| Frozen `dataclasses` / Pydantic for API shapes | 0 | Portable as-is. |
<!-- lint-ignore-length -->
| `Decimal` for all monetary values, SQLite `TEXT` + `Decimal(row[...])` read-back | 0 | Portable *pattern* — adopt whenever a project touches money (true for CardLedger and TaxCalculation, not universal for every future project). |
<!-- lint-ignore-length -->
| `asyncio` as primary concurrency model, `ProcessPoolExecutor` for CPU-bound, explicit timeouts | not portable by default | This is NiftyShield-specific to its live 30s-cadence daemon. Adopt only if a future project is itself a long-running concurrent service — not CardLedger/TaxCalculation, which are batch scripts. |
| Testing: offline-first, one happy-path + one edge-case per public function, integration opt-in only | 0 | Portable as-is. |
| Git conventions (imperative ≤60-char subject, never amend pushed commits, stage specific files) | 0 | Portable as-is. |
<!-- lint-ignore-length -->
| No throwaway code written directly in `src/`/`scripts/` — a quick POC/exploration always starts in `scratch/` first, and only graduates via the convergence rule (see Project layout below) once it's proven | 0 | Portable as-is, and now a hard requirement, not just an available option — the discipline is "stage in `scratch/`, promote deliberately," never "write it in prod folders and clean up later." |

### `CLAUDE.md` protocol mechanics

<!-- lint-ignore-length -->
| Item | Tier | Note |
|---|---|---|
| Step 1–5 skeleton (read context → confirm scope → plan+go-ahead → tests mandatory → docs→tests→commit) | 0 | Portable pattern — the shape, not NiftyShield's specific file names. |
| Bash output discipline (aggregate/filter before it enters context) | 0 | Portable as-is — cheap, universal token hygiene. |
| Tool-call param hygiene notes (`AskUserQuestion` plain strings, don't poll `ScheduleWakeup` for subagents) | 0 | Portable as-is — these are Claude-Code-harness-level facts, not project facts. |
<!-- lint-ignore-length -->
| `codebase-memory-mcp` **indexing** (`index_repository` run once, kept fresh) | 0 | Cheap, one-shot setup with no ongoing cost — index from day one regardless of project size, so the tool is already there once it's needed. |
<!-- lint-ignore-length -->
| Rule 0's **enforcement** — mandatory graph-before-read, `search_graph`/`get_code_snippet`/`trace_path` as the required first stop over `Read` | 3 | The reminder/gate only fires once the codebase is big enough that "query the graph" actually beats "just read the file" — below that, indexing exists but isn't yet enforced. |
| Step 2b — council checkpoint (three-condition test) | 2 | Pattern generalizes; content (which council, what template) is per-project. |
| Step 3b — Claude vs. Antigravity routing table | 2 | Only relevant if a project actually splits work across two agent surfaces. |
| AutoTrigger agent table (blocking test-runner / code-reviewer) | 2 | Mechanism generalizes; NiftyShield's specific agents do not (see Agents below). |

### Skills (`.claude/skills/*`)

<!-- lint-ignore-length -->
| Skill | Tier | Note |
|---|---|---|
| `commit` | 0 | Portable pattern (message format, stage-specific-files) once stripped of NiftyShield's code-reviewer-gate specifics. |
| `work` | 1 | Portable pattern — front-door router to feature/bug trees; needs `docs/plan/`+`docs/bugs/` to exist first. |
| `new-story` | 1 | Portable as-is — thin wrapper around a scaffold script, already project-agnostic. |
| `session-close` | 0 | Promoted from Tier 1 — negligible cost, default on from day one (see token-optimization section below). |
| `md-organize` | 3 | Portable pattern, fires only once a doc crosses the size trigger. |
| `weekly-audit` | 3 | Portable pattern, only worth the cadence once there's enough surface area. |
<!-- lint-ignore-length -->
| `protocol-reference` | 1 (pattern) / 2 (most content) | The *pattern* — keep `CLAUDE.md` resident-only, push detail to a lazily-loaded skill — is Tier 1 good practice for any project whose protocol doc is growing. Its actual sections (council protocol, AI-collaboration routing) are Tier 2 content. |
| `prompt-refine` | 1 | Generic utility, optional. |
| `handoff-antigravity` | 2 | Only if Antigravity is actually in the workflow. |

### Agents (`.claude/agents/*`)

<!-- lint-ignore-length -->
| Agent | Tier | Note |
|---|---|---|
<!-- lint-ignore-length -->
| `test-runner` | 2 | The underlying rule ("tests pass before commit") is Tier 0; running it via a dedicated blocking subagent is Tier 2 overhead, worth it once sessions are long/complex enough that inline `pytest` runs bloat context. |
| `code-reviewer` | 2 | A generic version (type hints, async correctness, no domain checks) is a reasonable Tier 2 default; NiftyShield's Decimal/BrokerClient-specific checks stay behind. |
<!-- lint-ignore-length -->
| `greeks-analyst`, `roll-validator`, `options-strategist` | not portable | Entirely NiftyShield/options-domain-specific. A future project's Tier 2 would define its own equivalents (e.g. a `tax-rule-reviewer`), not reuse these. |

### Hooks (`.claude/hooks/*`, `scripts/dev/hooks/*`, pre-commit)

<!-- lint-ignore-length -->
| Hook | Tier | Note |
|---|---|---|
| `ruff` / `ruff-format` / `mypy` / `detect-secrets` (pre-commit) | 0 | Portable as-is. |
<!-- lint-ignore-length -->
| `no-script-main-logger` / `no-bare-logging` (pre-commit) | 0 | Portable *pattern* — enforce whatever the project's canonical logging entrypoint is; the specific rule (`structlog.get_logger(__name__)` banned in `scripts/`) is NiftyShield's own convention shape, reusable if a project adopts the same logging setup. |
| `task_protocol.sh` (UserPromptSubmit step gate) | 1/2 | The nudge mechanism is generalizable once a project has a `CLAUDE.md` protocol worth enforcing; its specific step list is this project's. |
| `doc_update_gate.sh` (reminds to update state docs on commit) | 1 | Portable pattern once `TODOS.md`/`DECISIONS.md`/`docs/plan/README.md` exist (Tier 1). |
| `check_story_structure.py` / `check_checkbox_consistency.py` (+ `md-line-length` / `md-reflow`) | 1 | Portable as-is — these enforce the `docs/plan/_TEMPLATE` shape itself, so they travel with it. |
| `repeat_read.sh` / `check_repeat_read.py` | 3 | Pairs with Rule 0 — a repeat-Read guard only matters once the graph is the expected first stop. |
| `guard_src_reads.sh` | 3 | Rule 0 enforcement itself. |
| `wide_grep.sh` / `check_inline_full_suite.py` | 2/3 | Bash-output-discipline enforcement; worth it once codebases/log volumes are large enough for unscoped commands to matter. |
| `state_doc_freshness.sh` | 3 | Flags docs stale relative to commit count — needs enough commit volume to be meaningful. |
| `council_check.sh` | 2 | Only relevant once the council protocol (Tier 2) exists. |

### Docs

<!-- lint-ignore-length -->
| Doc | Tier | Note |
|---|---|---|
| `CONTEXT.md` | 0 | See architecture-doc trio above. |
| `DECISIONS.md` | 1 | Created on first real decision. |
| `CONTEXT_TREE.md` | 3 | Created once `CONTEXT.md`'s flat list is unwieldy. |
| `MISSION.md` (immutable mission + grounding principles) | 0 (pattern) | A one-page "why this exists, what never changes" doc is cheap and useful for any project — content is entirely per-project. |
| `TODOS.md` (backlog + session log) | 1 | Portable pattern. |
| `docs/plan/_TEMPLATE/` + `docs/plan/README.md` §Conventions | 1 | Portable as-is (see prior conclusion). |
| `docs/bugs/` (`bugs.md`/`prompt.md`/`task.md`) | 1 | Portable pattern — parallel bug-tracking tree alongside the feature-story tree, same shape as `docs/plan/`. |
| `docs/council/` + `_TEMPLATE` | 2 | Portable pattern once council (Tier 2) is adopted. |
| `REVIEW.md` (review hygiene rules) | 2 | Pattern pairs with `code-reviewer` agent; content is NiftyShield's own review checklist. |
<!-- lint-ignore-length -->
| `LOGGING.md` | 0 (pattern) | The idea — one canonical logging standard doc every entrypoint follows — is Tier 0; NiftyShield's specific event-naming convention is a starting template to adapt, not copy verbatim. |
<!-- lint-ignore-length -->
| `PLANNER.md`, `DB_REGISTRY.md`, `REFERENCES.md`, `LITERATURE.md`, `BACKTEST_PLAN*.md`, `FORMATTING.md`, `ANTIGRAVITY.md`, `INSTRUCTION.md`, `BUGS.md` | not portable | Entirely NiftyShield-domain content (options trading, brokers, backtest phases). Each may have a generalizable *shape* worth noting later (e.g. `DB_REGISTRY.md`'s "one row per table, owner, purpose" shape is a Tier 1 pattern once a project has multiple DB tables) but none travel as content. |

### Project layout

<!-- lint-ignore-length -->
| Item | Tier | Note |
|---|---|---|
<!-- lint-ignore-length -->
| `scratch/` (dated-filename POC folder + convergence rule) | 0 | Portable pattern (see scratch/tmp section above); subfolder-per-purpose timing still open. **Mandatory, not optional** — see the no-throwaway-code-in-prod-folders rule above. |
| `tmp/` (gitignored throwaway) | 0 | Portable as-is. |
<!-- lint-ignore-length -->
| `session_audit.jsonl` + `suggestions.md` (token-efficiency loop, driven by `session-close`) | 0 | Promoted from Tier 1 — cost is negligible (one subagent call at session end) regardless of project size, so it defaults on everywhere. |
| `AGENTS.md` mirroring `CLAUDE.md` for Antigravity | 2 | Only if Antigravity is in the workflow (per existing memory note: keep it a full mirror, never a stub). |

## Token optimization techniques — consolidated

Pulled together from scattered rows above into one place, since these were being classified piecemeal. Split by whether the technique is free at any size (defaults to Tier 0) or trades
setup/maintenance cost for savings that only exceed that cost once the codebase is large enough (stays gated).

**Free at any size — Tier 0 by default:**

- Bash output discipline (aggregate/filter at the source, never dump raw result sets into context).
- The `session_audit.jsonl` + `suggestions.md` loop, driven by `session-close` — one subagent call at session end, negligible cost, no size threshold below which it stops paying off.
- `codebase-memory-mcp` **indexing** (run `index_repository` once, keep it fresh) — one-shot setup cost, no ongoing cost, so index from day one even on a tiny project.
- The deferred/lazy-loaded-reference pattern — keep `CLAUDE.md` itself thin and push bulky detail (a `protocol-reference`-style skill, a `CONTEXT_TREE.md` split out of `CONTEXT.md`) into something
  loaded only when actually needed. Free to set up from day one; the "content" that gets deferred (council protocol, full module tree) may not exist yet on a small project, but the *shape* — resident
  doc stays short, detail is one skill-invocation away — costs nothing to establish early.
- No throwaway code directly in `src`/`scripts` — always stage in `scratch/` first (see Python hygiene table above) — this is as much a token-optimization technique as a code-hygiene one: it prevents
  a half-finished exploration from bloating a session's diff/review surface before the idea is even proven.
- "Pointers only, not full detail" in the backlog doc (`TODOS.md`'s convention: title/path/next-task/one-line why, real detail lives in the story folder) and "find the first unchecked task, do only
  that task, stop" in every story's `prompt.md` — both bound what a session has to load and how far it's expected to range, before a backlog or a story even gets long. Tier 1 in practice only because
  they need `docs/plan/`/`TODOS.md` to exist first, not because of any cost concern.

**Trades setup/maintenance cost for size-dependent payoff — stays gated:**

- Rule 0's **enforcement** (`guard_src_reads.sh`, `repeat_read.sh` mandating graph-over-`Read`) — Tier 3. The index from Tier 0 sits there unused until the codebase is big enough that a graph query
  actually beats reading the file; forcing the enforcement hook on earlier just nags with no query worth making yet.
- `wide_grep.sh` scoped-grep enforcement — Tier 2/3, same reasoning: only bites once log/codebase volume makes an unscoped grep actually expensive.
- `md-organize` / doc archival — Tier 3. Zero payoff until a doc is actually large enough to be reread wholesale every session.
- `graph_snippet`'s field-stripping wrapper (drops unused `fp`/`sp`/`bt` fingerprint fields, ~244 tokens/call) — rides along with whatever tier the graph tool itself is gated at (its enforcement, not
  its indexing).

## Status

PTB-1, PTB-2, and PTB-3 done. Tier 0 file set confirmed and written to `/Users/abhadra/myWork/myCode/AI/project-scaffold/tier0/` (see "Tier 0 output, concretely" above) — `scratch/` subfolder-timing
question resolved (stay flat until ~50 files), `commit`/`session-close` skills written and re-scoped in from PTB-3. `project-scaffold/scaffold.sh` written and verified against tier0, then re-verified
against tier0+tier1 together (see "Validation script" above) — run it after every tier-content change. ~~Not yet `git init`'d in `project-scaffold/`~~ — superseded: `git init`'d with commits `2e0c667`
(Tier 0) and `ebd0e8b` (Tier 1); `scaffold.sh` itself is still untracked there (PTB-5 commits it as a baseline first).

**PTB-3 closed (2026-09-26):** `docs/plan/_TEMPLATE/` (story + epic skeletons) and the `work`/`new-story` skills written to `/Users/abhadra/myWork/myCode/AI/project-scaffold/tier1/`, generic-only.
`_TEMPLATE` was **not** copy-as-is — four NiftyShield/Tier-2/3-leaking spots were found and fixed: the mandatory graph-query step in `story/stories.md` (Rule 0 / Tier 3 tooling — made an optional,
delete-if-unused block), `story/schema.md.example`'s NiftyShield-specific `portfolio.sqlite`/`DB_REGISTRY.md` content (replaced with a bare, convention-agnostic skeleton), the fixed `Owner`/`Review`
enums in `tasks.md` naming NiftyShield's specific agents (made free text), and `epic/prompt.md`'s hardcoded agent names in the review-gate note (generalized to "whatever review gate your project
defines"). `work`'s bug branch made **optional and detected** (only offered if `docs/bugs/` exists in the target project) rather than assumed — matches the trigger-based tiering principle; a new small
project carries no bug-tracking overhead until a bug is actually worth tracking formally. `new-story` ported near-verbatim (already project-agnostic) with a fallback to a direct `cp -r` when the
target project has no scaffold script yet, so it doesn't hard-depend on `scripts/dev/new_plan_folder.py` existing elsewhere. `DECISIONS.md`/`TODOS.md` triggers sharpened from session-count language to
a single testable fact each (see tier table above) — confirmed with Animesh. Validated: `scaffold.sh --force 1 <scratch-dest>` overlays clean — no NiftyShield references, no `tier0`/`tier1`-named
subfolders in the output, `.gitignore`'s `tmp/README.md` exemption still holds. Next: PTB-4 — Tier 2/3 gating criteria + generalized model-routing buckets.

**PTB-4 closed (2026-09-26):** Tier 2 split into two independent triggers — 2a stakes (council + review agents, with a two-box project-level check and a four-box per-decision check) and 2b
multi-surface (Antigravity routing, adopted only after a real task has run there). Tier 3 thresholds anchored to NiftyShield's own adoption history (Rule 0 + `CONTEXT_TREE.md` at ~10K LOC / 69 files,
`a1aca07`). Model routing converged into three buckets routed by reasoning demand × cost of error, with Tier 0/1 explicitly single-model. The governing rule, drawn from
`docs/archive/process/2026-05-08_workflow-improvements.md`: a gate ships with its at-the-moment hook or not at all. `tier2/`/`tier3/` file lists written as PTB-5 input, not built; two scaffold
problems flagged for PTB-5 (per-item rather than per-level selection; `settings.json`/`CLAUDE.md` need merging, not overwriting). Next: PTB-5.

**Story re-planned (2026-09-26, after PTB-4):** Animesh set the end state as a self-contained `project-scaffold` — everything a consuming project needs lives there, not only in this file. PTB-5
re-scoped from "hand off to a build story" to the distribution decision plus `scaffold.sh` per-piece selection and merging (`.gitignore` added as a third merged file — `python/` needs it); PTB-7 (Tier
2 content), PTB-8 (Tier 3 content), and PTB-9 (port this guide into `project-scaffold/README.md`, ship a trigger list into scaffolded projects, three-configuration end-to-end validation, archive)
added. Order: PTB-5 → PTB-6 → PTB-7 → PTB-8 → PTB-9. `project-scaffold` commit SHAs are recorded here per task from PTB-5 on.

**PTB-5 closed (2026-09-26):** Distribution decision recorded in `DECISIONS.md` — `project-scaffold` stays a copy-once template repo, local-only (no GitHub remote) for now. `scaffold.sh` rewritten
around per-piece `--piece <name>` selection (`tier1`, `tier2/{stakes,test-runner,multi-surface}`, `tier3/{rule0,md-organize,state-freshness,weekly-audit}`); Tier 0 always applies. `tier0/CLAUDE.md`
gained named `<!-- INSERT: NAME -->` markers at Step 1 (rule0), Step 2b (stakes), Step 3 (multi-surface), Step 4 (test-runner), Step 5a (state-freshness, md-organize), Step 5c (weekly-audit).
`tier2/`/`tier3/` restructured into empty per-piece placeholder folders (`.gitkeep`), content is PTB-7/PTB-8. Merge mechanics: `CLAUDE.md` fragments at markers (idempotent, python3-checked containment
— a first attempt used `grep -F` for the idempotency check, which is wrong for multi-line patterns and was replaced); `.claude/settings.json` hook-array merge per event/matcher via `python3` (tradeoff
vs `jq`/bash recorded in `DECISIONS.md`); `.gitignore` append-with-dedup. Validated against `/Users/abhadra/myWork/myCode/AI/_scratch_to_delete`: tier0-only, tier0+tier1,
tier0+tier1+dummy-tier2+dummy-tier3 (dummy fragments built in the session scratchpad only, never committed) — valid merged JSON, both fragments landed at markers, second run zero-diff.
`project-scaffold` commits: `84357d8` (baseline `scaffold.sh` committed unchanged, per the task spec) then `d433ba0` (`feat: per-piece scaffold selection with merged shared files`). Next: PTB-6.
