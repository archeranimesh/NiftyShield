# Code deduplication and taxonomy

> How to find and fix duplication spread across many ad hoc projects, and how to stop new duplication from re-accumulating once the shared library exists. Generalized from a real refactor that found
> the same external-API client reimplemented four times and the same five-line parsing loop reimplemented four times across unrelated projects.

## Step 1 — Audit before you design anything

Before writing a single shared module, audit the legacy tree at the **function-body level**, not just the filename level. A filename-only pass under-counts duplication badly: two files with different
names and different surrounding code can contain the identical core loop, and two files with similar names can be doing genuinely different things. Concretely:

1. List every project/folder in the legacy tree.
2. For each cross-cutting concern you suspect is duplicated (an external API client, a file-format parser, a report writer, an auth flow), grep for the *behavior*, not the name — read the actual
   function bodies, not just `grep -l theclientname`.
3. Record real evidence: which file, which function, what it does, and which other copy it matches. "We found the same N-line loader reimplemented 4 times, twice within the same project" is auditable
   evidence; "there's probably duplication" is not, and will not survive a future design review.
4. Rank by proven duplication count, not by gut feel about importance. The modules with 3+ confirmed independent copies are your first shared-library candidates; a suspected-but-unconfirmed overlap
   waits for its own audit before it gets a module.

This audit is also what gives your design-principles doc (see `design-principles.md`) its first concrete trigger — a textbook DIP violation ("every copy constructs its own client internally") or OCP
violation ("every new format is a new copy-pasted branch") is far more actionable stated against real evidence than as abstract theory.

## Step 2 — Define the shared-library module map

Produce one reference document (e.g. `docs/guides/code-module-map.md`) that states, for each shared module:

- **Responsibility** — one sentence.
- **Replaces** — the specific legacy originals it replaces, cited from the Step 1 audit (file + project), not a vague "various copies."
- **The "shared vs. specific" test** — a precise, repeatable rule for *when* logic must move to the shared library versus stay local to one project. Without this test, every future session has to
  re-litigate the boundary from scratch. A workable version: domain-*mechanism* logic (how to call the API, how to parse the format) is shared; domain-*business-rule* logic (which campaign/case this
  particular call is for) stays local to whichever project needs it.

### Design the riskiest modules' interfaces first — skeletons only

For the modules with the strongest audit evidence (highest duplicate count, clearest DIP/OCP violation), design the interface — `Protocol` by default, per `design-principles.md`'s structural-typing
rationale — **before** writing any concrete implementation: interface-only skeletons, with a conformance test proving a minimal stub satisfies the `Protocol` (`@runtime_checkable` + `isinstance`
check, where that's actually exercised at runtime rather than only by a type-checker). Defer concrete implementations and the `Protocol`s for lower-evidence modules to a follow-up, triggered the first
time a real consumer actually needs them (YAGNI) — don't build six modules' worth of production code speculatively because the module map named six candidates.

### Make dependency direction explicit

Shared-library modules must form a one-directional dependency graph with no cycles. State the rule explicitly in the module map (which modules may depend on which) and add a lightweight automated
check (walk the module graph, assert no back-edges) once a second module starts depending on a first — don't rely on manual review to catch a future cycle.

### One config-loading convention, not one per module

If multiple shared modules need configuration, standardize on a single pattern project-wide (e.g. a frozen/immutable config object loaded via a single `.load(path)`-style entry point) rather than
letting each module invent its own ad hoc environment-variable reads. A new module should reuse the existing config object if one already fits, or follow the existing shape if it needs its own.

### Wrap third-party/external exceptions at the module boundary

Each shared module that wraps a third-party library or external service should define its own small exception hierarchy (one module-specific base, narrow subclasses) and never let the wrapped
library's own exception types cross the module's public interface boundary. Callers should only ever need to catch the module's own hierarchy, never the underlying client library's exceptions directly
— this is what lets you swap the underlying library later without a cascading change to every caller's exception handling.

### Don't re-port what a sibling project already solved

Before porting legacy logic into the new shared module, check whether an independent, already-tested implementation of the same concern already exists elsewhere (a sibling repo, a published package).
If it does, wire it in as a dependency with a thin adapter instead of porting the logic a second (or fifth) time — re-porting duplicated logic recreates exactly the problem this whole exercise exists
to stop.

## Step 3 — Taxonomy: what kind of work is this, and where do its files go

A tree that grows organically ends up with structurally different kinds of work (a scheduled pipeline, an ongoing data-collection project, a one-off investigation, a reusable tool, a short-lived
experiment) all living as identical plain folders — nothing signals "this is done, archive it" versus "this is a live pipeline, treat it differently" versus "this is a throwaway probe."

Define, in one guide doc:

1. **Categories** — name the 4-6 shapes of work your tree actually contains (derived from your own audit, not a generic list), one paragraph each, with a real example from the legacy audit per
   category.
2. **Per-category folder skeleton** — the exact subfolder layout each category gets, applying two recurring anti-patterns to avoid explicitly:
   - **No double-wrap.** Don't nest a category-named folder inside itself (e.g. an "investigations" case living inside its own `investigations/` subfolder) — the exact stutter/collision this produces
     is worth naming and banning explicitly, because it recurs independently across unrelated projects once the category name is reused as a subfolder name.
   - **Campaign vs. case.** A folder that accumulates many related but distinct tickets/cases over an ongoing relationship (not one bounded investigation) is a *campaign*, and its cases should be
     flat, ID-prefixed files — not one subfolder per case, which fragments a small, related set of artifacts for no benefit.
3. **Submodule vs. plain-folder rule** — a concrete, checkable criterion (not a preference) for when a piece of work should become a real git submodule instead of a plain folder. A useful one: does
   this work have its own cadence, its own instructions, or its own release/dependency surface distinct from the parent tree? If yes, it resolves its own project root independently (e.g. its own
   root-level instructions file loads independently of the parent) — that is a concrete, checkable reason to prefer a submodule, not just a style preference.
4. **"Start new work" checklist** — a mandatory prior-art search step *before* creating a new top-level folder or writing a new script inside an existing one. This is the single highest-leverage
   anti-duplication control in the whole playbook, because the audit in Step 1 will already have shown that "thin script, import the shared library" is *not self-enforcing* on its own — every
   duplicate found during audit existed inside a project that already claimed to follow that convention. A session under time pressure will copy a sibling's script rather than research whether the
   shared library already covers it, unless the prior-art search is a mandatory, fast, low-friction step — ideally delegated to a sub-agent or lightweight tool call, not a manual "go think about it."
5. **A lightweight audit script** — list current top-level folders and flag any without a recognizable category marker, so taxonomy drift is caught mechanically, not by memory.
6. **A documented cutover procedure for any live scheduled job** (e.g. cron). Scheduler entries are frequently *not* version-controlled, so no diff/PR review ever sees an edit to them. Document a
   mandatory parallel-run-then-flip procedure for migrating any such job to the new codebase — never a same-day swap — since an undetected broken scheduled report can run silently for a full cycle
   before anyone notices.

## Step 4 — Registries that make reuse the fast path

A taxonomy and a module map only work if checking them is *faster* than writing a new duplicate from scratch. Build a generated (not hand-maintained) registry of existing scripts/modules across the
tree, and wire the "start new work" checklist's prior-art search to query it. Start the registry scoped narrowly (e.g. one throwaway/experiment folder) to prove the pattern cheaply, then generalize it
to the whole tree once the narrow version works — don't build the tree-wide version first on faith that it's needed.

## Step 5 — A durable, deduplicated knowledge/query catalog

If investigative work regularly re-derives the same facts (schema joins, query templates, field mappings), capture them in a catalog from day one, with two failure modes to avoid by construction:

- **Don't let it grow into one unreadable mega-file.** Split by topic/source as soon as a single file becomes hard to scan, not after it's already unreadable.
- **Save templates, not literal instances.** A query saved with literal IDs baked in gets re-typed with new literals next time; a query saved as a parameterized template gets reused as-is. Every
  derived fact cost real effort (schema discovery, trial and error) — that investment should never have to be re-paid because it was saved in a non-reusable shape.

## Step 6 — Harvest durable knowledge out of the legacy tree deliberately

If the legacy tree contains reusable facts (not just reusable code) — gotchas, reference mappings, domain knowledge — pull them into the new tree's own knowledge base deliberately, one source folder
at a time, rather than leaving them siloed in a read-only reference nobody re-reads. Treat this as an ongoing, appendable backlog (new entries queued each time a new source folder is next up), not a
one-off task — the legacy tree will keep aging and its content keeps being worth harvesting as long as it still exists.
