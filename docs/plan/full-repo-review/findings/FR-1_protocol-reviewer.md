# FR-1 — Prompting Methodology & AI-Collaboration Protocol Review

**Persona:** Protocol Reviewer
**Model:** Opus (downgraded from Fable per `findings/FR-0_model-validation-pilot.md`'s FR-1
recommendation — "Downgrade to Opus," extrapolation confidence: high, because FR-0's payload
*is* the FR-1 task. Substitution is expected, not an error.)
**Date:** 2026-07-05
**Scope read in full:** root `CLAUDE.md`, all 8 `src/*/CLAUDE.md` (client, dhan, gamma, mf,
notifications, nuvama, paper, portfolio), `ANTIGRAVITY.md`,
`docs/antigravity/ai_collaboration_plan.md`, `REVIEW.md`, `LOGGING.md`,
`docs/council/README.md`, 5 sampled `docs/plan/*/prompt.md` (mvp, options_income,
paper-exit-codification, telegram-leg-labels, full-repo-review), plus this epic's own
`prompt.md` + `stories.md`. Git history for author distribution, council/Step-2b commits, and
the two dead-link chains was re-run independently (see "Verification" below).

---

## Verification of prior-pass facts (spot-checked, not trusted blind)

Per the epic's own philosophy ("do not accept a citation as live without checking"), I
independently re-ran three of the handed-down facts before building on them:

1. **Author distribution** — `git log --format=%an | sort | uniq -c` → **931 "Animesh Bhadra"
   + 1 "archeranimesh", zero Antigravity.** Confirmed. (Prior pass said 929; the delta is
   commits landed since that pass — the *conclusion* is unchanged and strengthened.)
2. **variance-gate dead link** — `docs/council/2026-05-02_variance-gate-regime-completeness.md`
   does **not** exist; the file is at `docs/archive/council/risk/2026-05-02_...`. Confirmed dead.
3. **Council archive taxonomy** — actual: `docs/archive/council/{strategy,risk,research,data_architecture,misc}/`
   (5 subfolders). `docs/council/README.md` declares `docs/council/archive/{strategy,risk,research}/`
   (3 subfolders, wrong path prefix). Confirmed stale on both axes.

I also independently confirmed a **second, previously-flagged-but-worth-restating** dead-link
instance in `DECISIONS.md` (F12b below) and the ANTIGRAVITY "cannot spawn Claude agents"
constraint that drives the CRITICAL below (F-C1).

---

## Step 1 — CLAUDE.md Pre-Task Protocol ambiguities (two-agents-diverge test)

### F-C1 [CRITICAL] — The AutoTrigger table is unsatisfiable on the Antigravity surface, with no reconciling escape hatch stated in root CLAUDE.md

Root `CLAUDE.md`'s "Agent AutoTrigger Rules" table says `test-runner` and `code-reviewer` are
**"Blocking? Yes"** and "Spawning the correct sub-agent is not optional." But `ANTIGRAVITY.md`
lines 88–92 state the opposite for the Antigravity execution path: *"you are a Gemini engine and
**cannot spawn Claude agents**"* — Antigravity must instead emit `CODE REVIEW GATE — awaiting
@code-reviewer via Claude` and hand control back to a human. So the same rule that root CLAUDE.md
frames as an absolute, self-executing block is, on one of the three execution surfaces this repo
explicitly supports (Claude Code / Cowork subagent / Antigravity), *literally impossible to
satisfy in-process*. The reconciliation exists — but only inside `ANTIGRAVITY.md`, not in the
root doc that states the absolute rule.

**Why CRITICAL, not ERROR:** this is not cosmetic drift — it is directly tied to root CLAUDE.md's
*own documented* 2026-04-24/25 failure mode ("commit drafted but not executed"). An agent reading
only root CLAUDE.md's "blocking, not optional" language, running on a surface that can't spawn the
agent, has two documented-in-the-repo failure exits: (a) draft the commit and stop (the exact
recurring failure Step 5c warns against), or (b) proceed without the gate (the exact thing the
gate exists to prevent). The rule as written in the authoritative doc has no branch for "you are on
a surface that cannot spawn subagents." **Fix:** add one line to the AutoTrigger table's "Blocking"
note — "On surfaces that cannot spawn `.claude/agents/*` (Antigravity, some subagent contexts),
emit the await-signal per `ANTIGRAVITY.md` and treat the gate as human-completed, not skipped."

### F-C2 [CRITICAL] — Module CLAUDE.md files license patterns REVIEW.md Part III flags CRITICAL for new code, without surfacing the required escape valve

The module auto-load mechanism silently sets up a collision between two docs an agent holds in
context simultaneously:

- `src/notifications/CLAUDE.md` mandates the non-fatal contract: *"`send()` catches all
  `Exception` broadly."* `src/dhan/CLAUDE.md` ("Non-fatal in cron — Dhan block wrapped in
  try/except"), `src/nuvama/CLAUDE.md` (broad `InvalidOperation`/parse catches), and `src/mf/`
  (missing AMFI codes "logged as WARNING, not raised") describe the same broad-catch pattern as a
  *design requirement*. But `REVIEW.md` §G5 rates `except Exception` **without an inline intent
  comment** a **CRITICAL** finding for all new code.
- `src/paper/CLAUDE.md` describes the `total_pnl` invariant twice as *"asserts `total_pnl ==
  unrealized_pnl + realized_pnl`"* and *"Asserts `total_pnl` invariant before writing."* The actual
  code raises `ValueError` (correct), but the module doc's own vocabulary is `assert` — and
  `REVIEW.md` §G6 rates any literal `assert` outside `tests/` a **CRITICAL** finding.

An agent writing *new* code to the module spec — following the module CLAUDE.md faithfully — will
produce code that a `code-reviewer` applying REVIEW.md §G5/§G6 literally would block as CRITICAL.
Neither module doc tells the agent the required escape valve (add the `# Intentional: isolate ...`
comment for G5; raise `ValueError`, never `assert`, for G6). REVIEW.md's Part III diff-scoping
meta-rule protects *existing* code (it's TD-tracked), but explicitly not new code — which is
exactly what an agent extending a module writes. **Fix:** each broad-catch module doc should state
the G5 intent-comment requirement inline; `src/paper/CLAUDE.md` should change "asserts" →
"raises `ValueError` on mismatch (never literal `assert` — §G6)."

### F-E1 [ERROR] — Step 3 vs. Step 3b routing gap for ≤2-file tasks

Step 3 requires explicit go-ahead only "if plan touches more than 2 files." Step 3b ("Implementation
routing — mandatory after go-ahead") reads *"Once go-ahead is received, decide who implements."* For
a ≤2-file task where no go-ahead was required, it is genuinely unclear whether the mandatory routing
fork (Claude-implements vs. Antigravity-implements) still applies, or is skipped along with the
go-ahead. Two reasonable agents diverge: one treats routing as always-mandatory; the other reads
"after go-ahead" as a precondition that a ≤2-file task never triggers. **Fix:** state that routing
applies to every task regardless of file count; the go-ahead gate and the routing fork are
independent.

### F-E2 [ERROR] — options-strategist / Step 2b: three docs describe the same mechanism, none authoritative

The `options-strategist` AutoTrigger row (CLAUDE.md ~line 179) says: *"Council checkpoint (Step 2b)
when no real council is warranted | Advisory."* But:
- Step 2b's own body text in CLAUDE.md **never names `options-strategist`** — it describes a manual
  three-condition check, then "if no: proceed to Step 3." No agent is mentioned.
- `docs/antigravity/ai_collaboration_plan.md` line 20 gives a *third* framing: *"Use Claude to
  simulate the 'Council checkpoint' (Step 2b) for standard decisions."*

So an agent hitting Step 2b has three non-identical instructions for the same checkpoint: (a) do a
manual three-condition self-check (Step 2b body), (b) spawn `options-strategist` advisorily
(AutoTrigger row), (c) "use Claude to simulate" it (Antigravity doc). None cross-references the
others. Two agents will follow this differently; one may spawn an agent the other never invokes.
**Fix:** pick one mechanism, define it in Step 2b's body, and make the AutoTrigger row + Antigravity
doc point to that definition rather than restating it divergently.

### F-E3 [ERROR] — "code" is undefined at the code-reviewer trigger boundary

Step 5c triggers `code-reviewer` for "code changes" / "commits touching code"; `ANTIGRAVITY.md`'s
Commit Protocol scopes the same gate precisely to *"`.py` files in `src/scripts/tests`."* Root
CLAUDE.md's looser "code" leaves undefined whether a `.sql` migration, a `.claude/hooks/*.sh`
script, or a `pyproject.toml` change counts. The Antigravity doc is more precise than the
authoritative root doc it's supposed to be subordinate to. **Fix:** adopt ANTIGRAVITY.md's precise
scope in root CLAUDE.md's Step 5c.

### F-W1 [WARNING] — Rule 0 "NEVER... but the decision is yours" is a self-attested soft norm

Rule 0's header says **"NEVER call `Read` on `src/` or `scripts/` without first trying the graph"**
while the same block says *"It will not block — the decision is yours"* and the tree ends "Read is
permitted — but state why." This is a strict-sounding prohibition with a self-attested escape hatch
and no objective threshold for "insufficient." It functions, not as a NEVER, but as "prefer the
graph and narrate your reasoning." Low harm (it biases correctly), but the "NEVER" vocabulary
overstates enforceability — and, notably, this very review ran on a surface where graph tools were
deferred, i.e. the rule assumes an availability the surface doesn't always provide. **Fix:** soften
"NEVER" to "Default to the graph; `Read` source only after the graph can't answer, and state why."

### F-W2 [WARNING] — "Load ONLY that story file" contradicts the 12-row conditional-load list

CLAUDE.md's "Load additional files when relevant" list has a row *"Working a specific story → load
ONLY that story file + `CONTEXT.md` + module `CLAUDE.md`"* — but the same list has ~11 other rows
that would each *add* files (REFERENCES.md for expiry work, LOGGING.md for logger edits, etc.) for
that same story. "ONLY" and "also load X" collide whenever a specific-story task also touches
expiry/logging/etc. **Fix:** reword "ONLY" to "at minimum" or list the conditional-add rows as
explicit exceptions to it.

### F-I1 [INFO] — Quick-reference table points completed council decisions at the wrong tree

The Quick-reference table row "Completed council decisions | `docs/council/YYYY-MM-DD_<topic>.md`"
is the *active/unresolved* location; completed ones are archived to `docs/archive/council/...`. Same
staleness family as F12a/F12b. Low harm (an agent would still find the active ones), but it will
mislead anyone looking for an *absorbed* decision.

---

## Step 2 — prompt.md drift across eras (mvp → options_income → paper-exit-codification → telegram-leg-labels)

Sampled across the two real generations by first-commit date: **May 27–Jun 3** (mvp 27 lines,
options_income 31 lines) vs. **Jun 27–Jul 4** (paper-exit-codification 21 lines, telegram-leg-labels
41 lines, full-repo-review 156 lines).

**Conclusion: the load-bearing core is uniform; the procedural scaffolding has eroded, and it is
NOT monotonic — the epic's own premise is miscalibrated.**

- **Uniform across all samples (the discipline holds):** `CONTEXT.md ✓` first; "first unchecked
  box, one task, stop"; a graph-before-Read rule *in some form*; a blocking `pytest --tb=no -q`
  gate; "execute the commit — do not draft it"; tick tasks.md + append SHA + one TODOS.md line.
  The core one-task-per-session discipline is genuinely consistent. **F-I2 [INFO, positive].**

- **F-E4 [ERROR] — the "Pre-implementation gate" statement was silently dropped.** The older
  generation (mvp, options_income) carries an explicit *"Pre-implementation gate: State in one
  sentence which task, which files, which test file. Do not write any code until this plan is
  stated."* The newer generation (paper-exit-codification, telegram-leg-labels) **omits this
  entirely.** This is the one procedurally-load-bearing element that varies across eras — and it's
  the plan-before-code gate, not boilerplate. Also compressed: the graph-before-Read rule shrinks
  from a full explicit chain (`git log → search_graph → trace_path → search_code → sed → Read`) in
  the old generation to a one-line `git log → graph → search_code → sed → Read` in the new one.

- **F-E5 [ERROR] — the epic's stated "rigor baseline" is wrong.** Both `stories.md` (FR-1 seed
  issues) and `prompt.md` call `telegram-leg-labels` "a recent, detailed example — use it as the
  baseline for comparison." It is the most *narratively* detailed (Origin story, a genuinely
  excellent hard CLI-string constraint) but is **procedurally thinner** than the older mvp/
  options_income prompts — it has *no* Pre-implementation gate statement and a compressed graph
  chain. Using it as the rigor baseline anchors the comparison on the wrong axis (task-specificity,
  not procedural completeness) and would lead FR-9 to codify a template that's actually a regression
  on the gate that matters. **Fix:** the canonical prompt template should merge telegram-leg-labels'
  task-specificity *with* the older generation's Pre-implementation gate + full graph chain — take
  the best of both eras, not the most recent one.

- **F-W3 [WARNING] — the epic's own prompt.md violates its own "first instruction surface"
  principle.** This epic's `prompt.md` is 156 lines — ~5.7× the median older prompt (27) and ~3.8×
  telegram-leg-labels (41). It front-loads a ~30-line "Operating philosophy" essay before its
  actionable core ("read tasks.md, find first box, stop"), which is exactly what `prompt.md` itself
  argues *against* elsewhere (the prompt is the first thing a cold agent sees; bury the action and a
  cold agent misexecutes). The epic does not fully exempt itself from its own standard. Low harm
  here because the audience is a deliberate reviewer, not a cold task-executor — but it's a real
  self-inconsistency worth noting for FR-9's template work.

---

## Step 3 — Has the council trigger criteria actually gated a real decision?

**Conclusion: the criteria are substantively sound and were correctly *applied* at least once, but
there is no evidence the Step 2b checkpoint ever *gated* a call upstream — every observable council
decision is consistent with the criteria being applied organically (or in retrospect), not with the
checkpoint firing as a planning gate. n=1, unverifiable direction of causation.**

- The one live, well-formed council decision — **paper-delta-source-architecture, 2026-07-02,
  commit `62ed6ef`** — plainly meets all three trigger criteria (load-bearing: the delta-source
  layering; two defensible approaches: inject I/O into `delta_tracker` vs. caller-resolved map;
  multi-discipline: Greeks + architecture + test-invariant preservation). Its `DECISIONS.md` entry
  (line 16) is *exemplary* — it records the unanimous verdict, the rejected alternatives (a) and
  (c), the 2-of-4 dissent on fail-closed, the chairman's overrule, **and** a forward-council
  obligation ("before this fallback gates live money, a fresh council pass is required"). The
  *substance* of the protocol was followed exactly.

- **F-W4 [WARNING] — but the checkpoint's firing is unverifiable.** `git log --grep=council -i`
  and `--grep="Step 2b" -i` surface only the doc-authoring commits (`b212573 docs(council): add
  trigger criteria and planning-gate checkpoint`; `e4a3b0a`) — **not one implementation commit
  references Step 2b as the gate that triggered the call.** The 2026-07-02 decision also arose out
  of **BUG-002 triage**, not a clean planning phase — mild tension with the README's own
  "planning-phase tool, never mid-implementation" rule. So: criteria correct, one decision correctly
  matches them, but nothing proves the *checkpoint* gated it versus the criteria applying in
  retrospect. This is a documentation/auditability gap, not a substance failure — the checkpoint is
  written down (F-W4) but there is no artifact proving it has ever fired as designed.

- **F-E6 [ERROR] — `docs/council/README.md`'s folder taxonomy is stale on two axes.** README
  declares `docs/council/archive/{strategy,risk,research}/` (3 subfolders under `docs/council/`).
  Reality (after commit `da93b64` "consolidate council archive into docs/archive/council/") is
  `docs/archive/council/{strategy,risk,research,data_architecture,misc}/` — a **different path
  prefix** and **5 subfolders**, not 3. The README's own "Archived Decisions" tables still list only
  the 3 old subfolders and omit the `data_architecture/` (q12 strategy-monitor) and 2026-06-26
  q11/q12 decisions entirely. Downstream breakage this produces:

  - **F12a:** `docs/plan/variance-gate/prompt.md:18` links to
    `docs/council/2026-05-02_variance-gate-regime-completeness.md` → **dead** (now at
    `docs/archive/council/risk/...`).
  - **F12b [ERROR]:** `DECISIONS.md` lines 397–407 cite `docs/council/2026-05-28_paper-trade-exit-philosophy.md`
    as the source for ~9 CSP/CC/PP/collar exit rules → **dead** (now split across
    `docs/archive/council/strategy/2026-05-28_...` **and** a revised
    `docs/archive/council/strategy/2026-06-26_...`). This is a **second independent instance** of
    the same staleness pattern, on a decision that is load-bearing (it's the source of the paper
    exit-signal thresholds), and worse than the variance-gate one because the content was *also
    revised* on 2026-06-26 — a reader following the dead 05-28 link, if they find it, might read the
    superseded version. Note the newer `paper-exit-codification/prompt.md` correctly points at the
    `docs/archive/council/.../2026-06-26_...` paths — so the repo *knows* the new location; only the
    older citations in the README and DECISIONS.md weren't updated when `da93b64` moved the tree.

  These are ERROR (drift/broken-reference, not yet actively causing wrong trading logic) trending
  toward CRITICAL for F12b specifically, because a dead link to the *source of record* for live exit
  thresholds is exactly the provenance break FR-3 exists to catch — flag it there too.

---

## Step 4 — Module CLAUDE.md auto-load contradictions with root / REVIEW.md

Covered as **F-C2** above (the load-bearing collision: broad-catch and `assert`-vocabulary module
docs vs. REVIEW.md §G5/§G6 CRITICAL-for-new-code). Additional lower-severity notes:

- **F-I3 [INFO] — REVIEW.md's own canonical docstring example is stale on expiry convention.**
  `REVIEW.md:562` still reads *"expiry: Option expiry date. Must be a valid NSE expiry Thursday."*
  `REFERENCES.md` documents the SEBI change of Nifty weekly expiry Thursday→Tuesday, effective April
  2026. The review checklist that every reviewer reads still models the pre-change convention. Harm
  is low (it's a docstring illustration, not executable), but it's the *canonical example doc* — a
  fresh agent could copy the "Thursday" convention forward. **Fix:** change to "Tuesday" per
  REFERENCES.md.

- **F-I4 [INFO] — MockBrokerClient's "never raises, returns None/[]/{}" vs. the same file's "never
  return None silently — fail loudly."** `src/client/CLAUDE.md` says blocked live methods must fail
  loudly and never return None, while the Mock "returns `None`/`[]`/`{}`, never raises." This is
  defensible (test-double vs. production path) but the file never states *why* the two rules
  coexist, so an agent could mistakenly propagate the Mock's silence into a production method. Add a
  one-line note distinguishing the two.

- **F-I5 [INFO, positive] — the invariant *content* is coherent.** The Decimal-as-TEXT round-trip
  rule, the BrokerClient DI/factory boundary, the `paper_` prefix guard, the `__init__.py`
  requirement, and the ledger-vs-mutate models are stated consistently across all 8 module docs and
  root/ANTIGRAVITY. Only the *style-rule interactions* (F-C2) collide; the domain invariants do not.

---

## Step 5 — Should the "Operating philosophy" block be promoted into root CLAUDE.md's "AI Collaboration" section?

**Recommendation: REVISE-THEN-PROMOTE.** (Gates FR-9's step 4.)

The right test is `prompt.md`'s own: *does the block change concrete behavior beyond what the
existing protocol already implies?* Applying it line by line, the ~30-line block splits cleanly:

**Promote (behavior-changing, generalizes cleanly), in generalized non-FR-numbered form:**

1. **Severity is rated by mission impact, not by finding volume.** *"Rate severity by actual
   business impact (does this expose capital, does this cost a real decision-quality point per
   MISSION.md's Grounding Test) — not by how many findings make the review look thorough. A padded
   list of INFO-level nitpicks is as useless to a co-investor as a review that rubber-stamps
   everything."* This is a *new, concrete constraint* on the existing `code-reviewer`/`review`
   gates — nothing in current CLAUDE.md or REVIEW.md tells a reviewer not to pad, or ties severity
   to MISSION.md's Grounding Test. It changes behavior and applies to every review session, not just
   this epic.
2. **The reviewing agent's own citations/claims are in scope for verification.** *"Neither treats
   the other party's blind spots as worth surfacing... citing a file as 'live' without checking
   DECISIONS.md first."* This generalizes into a real rule that already has repo precedent (the
   RapidCouncil miss) and that this very review exercised (I re-ran the git log and the dead-link
   checks rather than trusting the prior pass). It's the same spirit as Rule 0's "state why the
   graph was insufficient," but broader: *verify your own citations before asserting them.* Worth
   promoting as a one-liner.
3. **The "name at least one perspective this review did not cover / write 'none identified'
   explicitly" closing-block pattern** — generalize it to "every review or handoff states at least
   one perspective it did not cover." This is already a proven mechanism (it's why FR-7 exists) and
   costs nothing to apply to ordinary `code-reviewer` runs.

**Keep scoped to the epic (framing/tone that doesn't survive generalization, or is review-panel
mechanics):**

- The full "co-investor, not client/vendor, not grader/gradee" prose. It's good framing but does not
  map to a *concrete action* outside a review context — and root CLAUDE.md is the single largest
  fixed token cost loaded into *every* session, most of which are implementation, not review.
  Importing ~25 lines of review-panel philosophy into that doc taxes every non-review session for
  no behavioral gain.
- All FR-N references, the multi-model/multi-persona panel rationale, and the FR-7-synthesis
  scaffolding — these are epic-specific machinery.

**Why not "promote whole":** naively promoting the entire block imports review-vocabulary bloat into
the highest-frequency doc in the repo and (per F-W3) that doc is *already* over-long relative to its
own stated principle. **Why not "keep scoped":** items 1–3 above are genuinely behavior-changing and
apply far beyond this one epic — leaving them stranded in an epic prompt that fires once means every
ordinary review keeps padding findings and skipping self-verification. Revise-then-promote captures
the ~3 executable lines and leaves the prose where it belongs. FR-9 should `Edit` (never
`Write`-over) exactly those 3 items into root CLAUDE.md's "AI Collaboration — Antigravity" section,
retitled to cover Claude-to-human review too.

---

## Step 6 — Severity roll-up

| ID | Severity | Finding | Fix owner |
|---|---|---|---|
| F-C1 | **CRITICAL** | AutoTrigger "blocking, not optional" is unsatisfiable on the Antigravity surface; no escape hatch in root CLAUDE.md; tied to the documented commit-not-executed failure mode | root CLAUDE.md |
| F-C2 | **CRITICAL** | Module CLAUDE.md docs (notifications/dhan/nuvama/mf broad-catch; paper "asserts") license patterns REVIEW.md §G5/§G6 flag CRITICAL for new code, without stating the escape valve | module CLAUDE.md ×5 |
| F-E1 | ERROR | Step 3 vs. Step 3b routing gap for ≤2-file tasks | root CLAUDE.md |
| F-E2 | ERROR | options-strategist / Step 2b described three non-identical ways across three docs, none authoritative | root CLAUDE.md + Antigravity doc |
| F-E3 | ERROR | "code" undefined at code-reviewer trigger boundary (root looser than ANTIGRAVITY.md) | root CLAUDE.md |
| F-E4 | ERROR | Pre-implementation gate statement silently dropped in newer prompt.md generation | prompt template / FR-9 |
| F-E5 | ERROR | Epic's stated "telegram-leg-labels is the rigor baseline" is miscalibrated (narratively rich, procedurally thinner) | this epic's docs / FR-9 |
| F-E6 | ERROR | council/README.md folder taxonomy stale (wrong prefix + 3 vs. 5 subfolders); breaks F12a/F12b | docs/council/README.md |
| F12b | ERROR | DECISIONS.md 397–407 cite dead `docs/council/2026-05-28_...` (source of live exit thresholds; also revised 06-26) — 2nd instance of the staleness pattern | DECISIONS.md (FR-3/FR-9) |
| F-W1 | WARNING | Rule 0 "NEVER... decision is yours" is a self-attested soft norm, not a NEVER | root CLAUDE.md |
| F-W2 | WARNING | "Load ONLY that story file" contradicts the 12-row conditional-add list | root CLAUDE.md |
| F-W3 | WARNING | Epic's own prompt.md (156 lines) violates its own "first instruction surface" principle | this epic's prompt.md |
| F-W4 | WARNING | No artifact proves the Step 2b checkpoint ever *gated* a council call (n=1, direction of causation unverifiable) | audit-trail convention |
| F-I1 | INFO | Quick-ref table points completed council decisions at the active (wrong) tree | root CLAUDE.md |
| F-I3 | INFO | REVIEW.md:562 docstring example still says "Thursday" (pre-April-2026 convention) | REVIEW.md |
| F-I4 | INFO | MockBrokerClient "returns None" vs. same file's "never return None" — undocumented distinction | src/client/CLAUDE.md |
| F-I2/F-I5 | INFO (positive) | One-task-per-session core discipline + domain invariants are consistent across all samples | — |

**CRITICAL count = 2 (F-C1, F-C2).** Both are protocol ambiguities that *will* cause incorrect
agent behavior on a real execution surface (F-C1) or on first-write new code (F-C2), not merely
stylistic drift. Per FR-9's CRITICAL-verification gate, both are independently re-derived above
(the ANTIGRAVITY.md line references and the module-doc/REVIEW.md line references are cited exactly)
and should survive re-confirmation.

---

> State the persona you reviewed as (Protocol Reviewer). Name at least one perspective this
> review did not cover that a different persona would have caught — write "none identified"
> explicitly if genuinely nothing comes to mind, do not omit this section.

**Persona reviewed as: Protocol Reviewer.**

**Perspectives this review did not cover** (a different persona would have caught):

1. **Token-economics / context-budget auditor.** This review flagged that root CLAUDE.md and the
   epic prompt.md are over-long (F-W3) and that promoting the whole philosophy block would tax every
   session (Step 5) — but it did not actually *measure* the cumulative mandatory-load cost. Nobody in
   this panel is checking whether the >1,500 lines of always-loaded protocol (root CLAUDE.md + 8
   auto-loaded module docs + CONTEXT.md) has crossed the point where it degrades implementation
   quality rather than improving it. That is a distinct, quantifiable discipline (measure the load,
   correlate against failure modes) I only touched qualitatively.

2. **Cold-start / new-contributor (human or third AI) onboarding persona.** Every finding here
   assumes a reader who already holds the repo's conventions in mind. A genuinely cold operator — a
   new human contributor, or a *third* AI engine beyond Claude/Antigravity — would surface a
   different class of gap: e.g. the LITERATURE.md "LIT code" load-trigger is circular for someone who
   hasn't read the task yet, and there is no single "start here if you've never seen this repo"
   entrypoint. I reviewed the protocol for *internal consistency*, not for *first-contact
   navigability*, and those are different tests.

3. **Execution-environment / tooling-surface persona.** F-C1 stumbled into this (a rule that can't
   run on Antigravity) but did not do it systematically — nobody in this panel took each rule in
   CLAUDE.md and tested it against what each surface (Claude Code CLI, Cowork subagent, Antigravity)
   can *physically* do. This review itself ran on a surface where graph tools were deferred, which is
   direct evidence the gap is real; FR-8 (Practitioner/DevEx) partially covers the *guidance* side of
   this, but not the *"is every rule satisfiable on every surface"* audit.
