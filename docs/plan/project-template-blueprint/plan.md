
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
| **1 — Recurring work** | Second real session, or a backlog exists | `docs/plan/_TEMPLATE/` + `docs/plan/README.md` §Conventions + `TODOS.md` (backlog + session log, "pointers only" convention), `work`/`new-story` skills. `DECISIONS.md` — created on the *first* real architecture decision, not before; append-only, records "why" not "what." |
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
├── tier1/                           # empty — PTB-3, now scoped to work/new-story only
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

**How a new project gets it — two viable mechanisms, either works, pick per-project:**

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
`TradeResearch/CLAUDE.md`, `TradeResearch/CONTEXT.md`, and `TradeResearch/scripts/*.py` all sit directly at root, with no `tier0/` or `python-addon/`-named subfolder anywhere inside it. This settles a
question raised in discussion: the template repo's `tier0/`/`tier1/`/`tier2/`/`tier3/` subfolders are **source-only** — a place to copy *from* — and never appear as structure *inside* a scaffolded
project. There is no "promote a file from tier1 up into tier0" step, because tiers are never merged with each other inside `project-scaffold/` itself; they are each independently overlaid onto a real
project's root, once, at scaffold time. The same flattening applies to `python-addon/` once it exists (deferred, see above) — its files land directly in the consuming project's root (`pyproject.toml`,
`.pre-commit-config.yaml`, `src/`), never inside a folder literally named `python-addon/` in the real project.

**Idea floated for the PTB-5 scaffold script, not yet built (Animesh, this session):** make the local scaffold-script option interactive and repeatable rather than a static copy — run it once against
a target path, have it ask a handful of yes/no questions (is this a Python project? does a backlog exist yet? etc.), and have it copy `tier0/*` plus whichever tier/addon deltas the answers select,
flattened directly into the target root. Repeatable means re-running it against an existing project only adds files that don't already exist — it never overwrites what's already there. This is
explicitly PTB-5 scope to design and build, not something to implement mid-PTB-2 — captured here so PTB-5 starts from it instead of re-deriving it from scratch.

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
  council question.
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

PTB-1 and PTB-2 done. Tier 0 file set confirmed and written to `/Users/abhadra/myWork/myCode/AI/project-scaffold/tier0/` (see "Tier 0 output, concretely" above) — `scratch/` subfolder-timing question
resolved (stay flat until ~50 files), `commit`/`session-close` skills written and re-scoped in from PTB-3. `project-scaffold/scaffold.sh` written and verified against tier0 (see "Validation script"
above) — run it after every tier-content change. Not yet `git init`'d in `project-scaffold/` (Animesh's call, deferred without a hard trigger stated — revisit next session). Next: PTB-3 — `work`/
`new-story` skill genericization only.
