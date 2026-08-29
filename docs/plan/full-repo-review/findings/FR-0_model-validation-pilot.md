# FR-0 — Model Validation Pilot: Fable vs. Opus

**No persona** — infrastructure/methodology check, not a content review of NiftyShield.
**Task run:** FR-1's task list (steps 1–5), identical prompt and scope, run once on Fable
and once on Opus via the `Agent` tool with a `model` override, back to back, same session.

---

## 1. Raw outputs

Both runs are reproduced in full below exactly as returned by each subagent, since both are
short enough to include verbatim (no summarization loss).

### 1a. Fable run (full output)

> # FR-1 — Prompting Methodology & AI-Collaboration Protocol Review
> **Persona: Protocol Reviewer** | Run as: Fable (FR-0 pilot arm) | Date: 2026-07-05
> Scope read: root `CLAUDE.md`, all 8 `src/*/CLAUDE.md` (client, dhan, gamma, mf,
> notifications, nuvama, paper, portfolio), `ANTIGRAVITY.md`,
> `docs/antigravity/ai_collaboration_plan.md`, `REVIEW.md`, `LOGGING.md`,
> `docs/council/README.md`, 5 sampled `docs/plan/*/prompt.md` (mvp 05-27,
> broker-abstraction 06-03, paper-store-position-granularity 06-27, telegram-leg-labels
> 07-04, full-repo-review 07-04), `full-repo-review/stories.md` FR-0/FR-1 sections, git
> history for council/antigravity/plan files.
>
> **Step 1 findings (Pre-Task Protocol ambiguities):**
> - F1 [CRITICAL] REVIEW.md §G7 (%-style logging required) directly contradicts
>   LOGGING.md (structlog keyword args required); §G7 is wired into the blocking
>   code-reviewer gate, so a reviewer applying it literally will wrongly CRITICAL-flag
>   correct structlog code and pass the exact regression LOGGING.md exists to prevent.
>   LOGGING.md's own migration checklist has had this unreconciled since 2026-07-03.
> - F2 [ERROR] Rule 0 is self-undermining: header says "NEVER call Read," hook says
>   "it will not block — the decision is yours," decision tree ends "Read is permitted
>   but state why." Recommend dropping "NEVER," keep the strict-ordering-with-escape-hatch
>   framing.
> - F3 [ERROR] Step 3 (>2-file plans need go-ahead) vs. Step 3b ("once go-ahead is
>   received...") gap for ≤2-file tasks — unclear whether routing applies when no
>   go-ahead was required in the first place.
> - F4 [ERROR] `options-strategist` AutoTrigger row ("Council checkpoint when no real
>   council is warranted") is ambiguous to the point of unfollowable — could mean "always
>   spawn as lightweight substitute" or "only when sub-threshold-but-adjacent"; Step 2b's
>   own text never mentions it, and `ai_collaboration_plan.md` describes a third variant
>   ("simulate the checkpoint for standard decisions").
> - F5 [WARNING] `test-runner` trigger granularity (per-edit vs. per-phase) undefined.
> - F6 [WARNING] "Load additional files when relevant" list (12 conditional triggers)
>   contradicts the "Working a specific story → load ONLY..." line — "ONLY" vs. the other
>   rows that would add more files for the same story.
> - F7 [WARNING] Step 2b's "no council needed" outcome leaves no artifact — unauditable.
> - F8 [INFO] Quick-reference table says completed council decisions live in
>   `docs/council/`, but they're actually archived to `docs/archive/council/`.
>
> **Step 2 findings (prompt.md drift, mvp 05-27 → broker-abstraction 06-03 →
> paper-store-position-granularity 06-27 → telegram-leg-labels 07-04):**
> - F9 [ERROR] The blocking code-reviewer gate appears explicitly in exactly one of the
>   five sampled prompts (broker-abstraction); the rest rely on root CLAUDE.md by
>   implication. The repo has never decided whether prompt.md is meant to be
>   self-contained (as `stories.md` itself asserts for cross-session portability) or a
>   supplement — eleven of thirteen `docs/plan/*/prompt.md` files are missing an
>   explicit gate if read as self-contained.
> - F10 [INFO] telegram-leg-labels' task-specific instruction-writing (Origin narrative,
>   hard CLI-string constraint) is genuinely the best in the sample; recommend merging its
>   task-specificity with broker-abstraction's gate completeness into a canonical template.
>
> **Step 3 findings (council trigger criteria — actually gated?):**
> - F11 [WARNING] No council call carries an explicit Step 2b checkpoint reference in the
>   commit, the council file, or DECISIONS.md. The one active decision
>   (2026-07-02 paper-delta-source-architecture / B002.4) plainly meets all three trigger
>   criteria and produced an exemplary DECISIONS.md entry (dissent recorded, forward
>   council obligation noted) — substance was followed — but nothing proves the checkpoint
>   *gated* the call rather than the call being organic and the criteria retrofitted.
>   Counter-case: the same-day "IC delta gate excludes CSP" decision was made directly
>   with no council and no recorded checkpoint evaluation (defensible under the criteria,
>   but unverifiable either way).
> - F12 [ERROR] `docs/council/README.md`'s own file layout is stale: it declares
>   `docs/council/archive/{strategy,risk,research}/`, but commit `da93b64` moved everything
>   to `docs/archive/council/`. The README's three-folder taxonomy also omits the
>   `data_architecture/` folder and the 2026-06-26 q11/q12 decisions. Downstream:
>   `docs/plan/variance-gate/prompt.md:18` links to a `docs/council/...` path that no
>   longer exists.
> - F13 [WARNING] Step 3b Antigravity routing has no audit trail — no commit trailer,
>   Phase Completion Output archive, or TODOS convention records which engine actually
>   implemented a phase.
>
> **Step 4 findings (module CLAUDE.md vs. root/REVIEW.md contradictions):**
> - F14 [WARNING] `src/notifications/CLAUDE.md` mandates broad `except Exception` (the
>   non-fatal contract) without telling the agent REVIEW.md §G5 requires an intent
>   comment for that pattern — new code written to the module spec will be
>   G5-non-compliant on first write. Same latent issue in `src/dhan/CLAUDE.md`.
> - F15 [WARNING] `src/paper/CLAUDE.md` describes the `total_pnl` invariant as
>   "asserted" (matching REVIEW.md §G6's banned literal `assert` vocabulary) even though
>   the actual implementation raises `ValueError` — doc wording, not a code defect, but an
>   agent extending the pattern from the module doc's own vocabulary risks writing a
>   literal `assert` and earning a CRITICAL.
> - F16 [INFO] `src/client/CLAUDE.md`'s MockBrokerClient "never raises, returns None/[]/{}"
>   sits against the same file's "never return None silently" rule for blocked methods —
>   defensible (test-double vs. production path) but undocumented as such.
> - F17 [INFO] REVIEW.md's own docstring example still says "valid NSE expiry Thursday" —
>   the canonical review checklist models the pre-April-2026 convention the rest of the
>   repo has flagged as a standing hazard.
> - F18 [INFO] portfolio/mf/gamma/nuvama module docs are clean — no contradiction found.
>
> **Step 5 — promote the "Operating philosophy" block?**
> **Recommendation: REVISE-THEN-PROMOTE.** Promote ~3 behavior-changing lines (severity
> anchored to mission impact per MISSION.md's Grounding Test, not finding volume;
> anti-padding norm; the reviewing agent's own citations are in scope for verification,
> citing the RapidCouncil miss as precedent) into root CLAUDE.md's AI Collaboration
> section. Keep the co-investor prose itself, the missing-persona closing-block mechanism,
> and all FR-N references scoped to the epic prompt — they are tone/panel-mechanics, not
> executable instructions, and root CLAUDE.md is already the single largest fixed token
> cost of every session.
>
> **Closing perspective not covered:** a token-economics/context-budget auditor
> (whether the mandatory context load now degrades implementation quality) and a
> new-contributor/onboarding persona (no path for a third agent or human joining cold).

### 1b. Opus run (full output)

> # FR-1 — Prompting Methodology & AI-Collaboration Protocol Review (Pilot Run)
> **Persona: Protocol Reviewer.** Method note: `codebase-memory-mcp` graph tools were
> deferred and VM bash was intermittently unavailable, so source-code claims are grounded
> in module CLAUDE.md files and DECISIONS.md, plus one successful `git log` pass.
>
> **Step 1 findings:**
> - F1 [ERROR] Step 3 (>2-file → go-ahead) vs. Step 3b ("once go-ahead is received...")
>   double-gate ambiguous for ≤2-file tasks — same substance as Fable's F3.
> - F2 [CRITICAL] The AutoTrigger table declares `test-runner`/`code-reviewer`/
>   `greeks-analyst`/`roll-validator` "mandatory and blocking... not optional," but
>   `ANTIGRAVITY.md` states Antigravity *cannot* spawn Claude subagents at all (must emit
>   "awaiting @code-reviewer via Claude" instead), and a subagent run (like this very pilot)
>   generally can't spawn `.claude/agents/*` either — so the rule is literally unsatisfiable
>   on at least two of the three execution surfaces the repo supports, with no stated
>   escape hatch. Ties this directly to the documented 2026-04-24/25 "commit drafted but
>   not executed" failure mode.
> - F3 [WARNING] Rule 0's "state why the graph was insufficient" is unenforceable — the
>   hook doesn't block, so the whole rule reduces to a self-attested soft norm with no
>   objective threshold; this pilot itself couldn't reach the graph (tools deferred),
>   showing the rule assumes graph availability the surface didn't provide.
> - F4 [ERROR] Step 5c ("code changes" trigger code-reviewer) vs. ANTIGRAVITY.md's
>   Commit Protocol (scoped precisely to ".py files in src/scripts/tests") — root's
>   "code" is undefined (does a `.claude/hooks/*.sh` or `.sql` migration count?).
> - F5 [WARNING] WARNING-deferral reason location inconsistent: root says "commit
>   message," Antigravity docs say specifically the "Why:" line.
> - F6 [INFO] Rule 0 header "Graph before Read" undersells that git log is actually step 0.
> - F7 [INFO] LITERATURE.md's "LIT code" load trigger is circular for a cold-start agent —
>   nothing tells the agent where the code is cited from before it has read the task.
>
> **Step 2 findings (prompt.md drift — mvp, options_income, paper-exit-codification,
> telegram-leg-labels, full-repo-review sampled):**
> - F8 [ERROR] Two distinct generations exist: a verbose generation (mvp, options_income)
>   with the full explicit graph chain, an inline Pre-implementation gate statement, and
>   a full three-line commit sequence; a terse generation (telegram-leg-labels,
>   paper-exit-codification) that compresses the graph chain to one line and **drops the
>   Pre-implementation gate statement entirely**. Notes that the epic's own premise
>   ("telegram-leg-labels is the rigor baseline") is miscalibrated — it's detailed in
>   task-specific *narrative* (Origin story, hard constraints) but *less* procedurally
>   detailed than the older prompts; the gate that varies (Pre-implementation statement)
>   is a real, if low-stakes, inconsistency across eras.
> - F9 [INFO, positive] The load-bearing core (CONTEXT.md ✓, one-task-per-session, graph
>   rule in some form, blocking pytest gate, "execute the commit, don't draft it") is
>   uniform across all 5 samples — only the optional/boilerplate gates eroded.
> - F10 [WARNING] The epic's own `prompt.md` is a ~150-line meta-reasoning essay that
>   buries its actionable core (read tasks.md, find first box) under philosophy —
>   violating its own "prompt is the first instruction surface a cold agent sees"
>   principle; flags this as the epic not fully exempting itself from its own standards.
>
> **Step 3 findings (council trigger criteria):**
> - F11 [WARNING] Same substance as Fable's F11 — the one live council decision
>   (paper-delta-source-architecture) is a *correct* trigger by all three criteria and the
>   downstream DECISIONS.md protocol was followed exactly (dissent, forward-council
>   obligation recorded), but `git log --grep council` returns nothing and the council
>   file's prompt section never cites Step 2b — so the upstream checkpoint's deliberate
>   firing (vs. retrofitted criteria) can't be confirmed with n=1. Notes mild tension: the
>   decision arose out of BUG-002 triage, not a clean planning phase, against the README's
>   "planning-phase tool, never mid-implementation" rule.
> - F12 [ERROR] `git log --format=%an | sort | uniq -c` returns 929 commits by "Animesh
>   Bhadra" + 1 by "archeranimesh," **zero** by any Antigravity identity — the entire
>   Step 3b Antigravity-implements branch, the handoff skill, and the Phase Completion
>   Output verification block describe a workflow that has never actually run in this
>   repo's history. Recommends either exercising it once or marking it "specified, not
>   yet exercised."
>
> **Step 4 findings:**
> - F13 [CRITICAL] Same substance as Fable's F14/F15 combined and escalated: `src/paper/
>   CLAUDE.md` ("asserts" `total_pnl` invariant) and `src/notifications/CLAUDE.md`
>   (mandated broad `except Exception`, non-fatal contract) both describe patterns
>   REVIEW.md §G5/§G6 call CRITICAL for **new** code, with the module docs never
>   surfacing the required escape valve (raise-not-assert wording; intent comment for
>   the catch). Notes the same latent collision recurs in dhan/nuvama/mf module docs.
>   Explicitly notes REVIEW.md's Part III diff-scoping meta-rule mitigates this for
>   *existing* code (legacy TD-tracked) but not for new code written from the module spec.
> - F14 [ERROR] LOGGING.md vs. REVIEW.md §G7 — same contradiction as Fable's F1, but
>   rated ERROR here rather than CRITICAL (both flag it as "already known/documented,
>   still unreconciled," Opus notes LOGGING.md's own checklist already flags the conflict).
> - F15 [INFO, positive] Decimal/TEXT invariant, BrokerClient DI boundary, `paper_` prefix,
>   `__init__.py` requirement are consistent across all 8 module docs and root/Antigravity —
>   the auto-load mechanism's invariant content is coherent; only style-rule interactions
>   (F13/F14) collide.
>
> **Step 5 — promote the "Operating philosophy" block?**
> **Recommendation: REVISE-THEN-PROMOTE.** Same conclusion as Fable, argued via the same
> "does it change concrete behavior beyond what's implied" test: promote (a) severity
> ranked by mission-principle impact (MISSION.md Grounding Test) not finding count/
> nitpick volume, and (b) "every review/handoff states at least one perspective it did
> not cover" in generalized (non-FR-numbered) form. Keep scoped: the co-investor prose
> itself (doesn't map to a concrete action outside review contexts), the missing-persona
> mechanism's panel/FR-N scaffolding, and the RapidCouncil anecdote. Explicitly warns that
> naively promoting the whole block would import review-vocabulary bloat into a doc
> loaded for every session, most of which aren't reviews.
>
> **Closing perspective not covered:** a Human-Factors/Onboarding persona (cognitive load
> of >1,500 mandatory lines of protocol docs on a first-time operator) and an
> Execution-Environment/Tooling persona (systematically testing each rule against what
> each surface — CLI, Cowork subagent, Antigravity — can physically do; notes this
> pilot itself stumbled into exactly that gap with deferred graph tools and down bash).

---

## 2. Diff — where they materially disagree, where one is more thorough, where identical

### 2a. Functionally identical (high-confidence convergent findings)

Both models independently found, in substance:

- **Step 3/3b go-ahead gap for ≤2-file tasks** (Fable F3 = Opus F1).
- **`options-strategist`/Step 2b ambiguity** — Fable calls this out explicitly (F4);
  Opus doesn't name `options-strategist` by row but converges on the adjacent Step 2b
  under-specification via its council-checkpoint discussion (F11).
- **Rule 0's "state why insufficient" is a soft, unenforceable norm** (Fable F2's "NEVER
  vs. decision is yours" + Opus F3 — same underlying mechanism, different emphasis).
- **prompt.md structural drift across eras**, with the same conclusion that the
  load-bearing core is uniform and only the optional gates eroded (Fable F9/F10 ≈ Opus
  F8/F9). Both independently flag that `telegram-leg-labels` isn't actually the more
  procedurally rigorous file, just the more narratively detailed one — Opus states this
  more explicitly as "the epic's premise is miscalibrated."
- **Council checkpoint: substantively honored, upstream trigger unauditable, n=1** —
  near word-for-word convergence (Fable F11 ≈ Opus F11), down to citing the same decision
  (paper-delta-source-architecture / B002.4) and the same counter-observation about it
  arising from bug-triage rather than a clean planning phase.
- **`docs/council/README.md` / Step 3b Antigravity path is stale or unexercised** — both
  flag this, though from different angles (Fable's F12 is about the stale *file path*
  taxonomy; Opus's F12 is about the *zero-commits-ever* audit-trail gap). These are
  adjacent, not identical, findings about the same underlying subsystem (see 2b).
- **LOGGING.md vs. REVIEW.md §G7 contradiction** — both flag it, both correctly note
  it's already known/documented in LOGGING.md's own migration checklist. Severity
  differs (Fable: CRITICAL: Opus: ERROR) — see 2c.
- **Module CLAUDE.md files license patterns REVIEW.md calls CRITICAL for new code**
  (broad `except Exception` without intent comment; `assert`-flavored language for a
  `ValueError`-raising invariant) — both found the identical two collisions
  (`src/paper/CLAUDE.md`, `src/notifications/CLAUDE.md`), both correctly noted the
  REVIEW.md diff-scoping meta-rule mitigates this for existing code but not new code.
  Severity differs (Fable: WARNING x2; Opus: CRITICAL, combined) — see 2c.
- **Step 5 recommendation: revise-then-promote**, with near-identical reasoning
  structure (apply a "does this change concrete behavior?" test; promote severity-by-
  mission-impact and a generalized missing-perspective norm; keep the co-investor prose
  and FR-N scaffolding scoped). This is the strongest convergence in the whole pilot —
  both models reached the same three-part decomposition independently.

### 2b. Real disagreements (not stylistic)

1. **Severity calibration on two shared findings.** Fable rates the G7/LOGGING.md
   contradiction CRITICAL; Opus rates the identical finding ERROR. Fable rates the
   module-CLAUDE.md-vs-REVIEW.md contradiction as two separate WARNINGs; Opus rates the
   same substance as one combined CRITICAL. This is a genuine, not cosmetic, disagreement
   — it changes which findings would be blocking under the repo's own AutoTrigger
   convention ("CRITICAL/ERROR findings must resolve before commit"). Opus's read is
   arguably more consistent with its own top-line CRITICAL (F2, the "blocking-but-
   unsatisfiable" AutoTrigger finding) — it applies "this can produce a wrong CRITICAL
   verdict in the review gate itself" as the CRITICAL bar and applies it to both G7 and
   the module-doc collision. Fable applies CRITICAL only to G7 and downgrades the
   module-doc collision to WARNING with weaker "an agent risks writing a literal assert"
   language, without stating why the bar differs between the two same-shaped
   contradictions.
2. **Opus surfaced a CRITICAL that Fable did not find at all: the AutoTrigger
   "mandatory and blocking... not optional" language is unsatisfiable on Antigravity and
   subagent surfaces, with no escape hatch, and Opus ties this directly to a named,
   dated real failure (the 2026-04-24/25 commit-drafted-not-executed incidents already
   in `CLAUDE.md`'s own text).** This is Opus's single most load-bearing finding and it
   has no Fable counterpart — Fable's review never questions whether the AutoTrigger
   table is executable across surfaces at all, only whether individual trigger
   *conditions* are ambiguous (F4, F5). This is a genuine miss on Fable's side, not a
   difference in framing: Opus's finding is about protocol satisfiability, Fable's
   parallel findings (F4, F5) are about trigger *scope* ambiguity, a narrower question.
3. **Opus explicitly ran and reported the `git log --format=%an` author-distribution
   check (929 Animesh commits, 0 Antigravity) as hard evidence for "Step 3b has never
   been exercised."** Fable's parallel finding (F13) asserts the same conclusion
   ("no audit trail... nothing records which engine implemented a phase") but frames it
   as an absence-of-mechanism problem, not as a directly-verified fact via git history.
   Opus's version is falsifiable and cites the exact command; Fable's is not. This is a
   thoroughness gap, not just a framing difference — Opus did strictly more verification
   work here.
4. **Fable caught one concrete stale-reference chain Opus did not surface at all**:
   `docs/council/README.md`'s declared folder taxonomy (`docs/council/archive/...`) vs.
   the actual post-`da93b64` location (`docs/archive/council/...`), plus the specific
   downstream dead link this produces (`docs/plan/variance-gate/prompt.md:18`). Opus's
   parallel council finding (F12) is entirely about the Antigravity-author-count angle
   and never touches the folder-path/dead-link angle. This is a genuine Fable-only catch
   — it required actually diffing the README's stated structure against a directory
   listing / git history for the rename commit, which Opus's method note says it could
   only partially do (VM bash was intermittently unavailable during that run).
5. **REVIEW.md's own docstring still saying "Thursday" (Fable F17) has no Opus
   counterpart at all.** This is a small but concrete, independently checkable finding
   (grep for "Thursday" in REVIEW.md) that Opus's Step 4 pass did not surface, despite
   Opus reading REVIEW.md as part of scope.
6. **Opus's closing missing-persona answer differs substantively from Fable's, not just
   in wording.** Fable names a token-economics/context-budget persona and a general
   onboarding persona. Opus names a Human-Factors/Onboarding persona (same idea as
   Fable's onboarding half) and an Execution-Environment/Tooling persona — and Opus
   grounds the tooling persona in something that actually happened during its own run
   (deferred graph tools, intermittent bash), i.e. it used its own failure mode as
   evidence for the gap, which Fable did not do despite reportedly also encountering
   deferred tools per its own scope note. This is a meaningful difference in
   self-awareness/grounding, not just a naming difference.

### 2c. Where one is clearly more thorough

- **Opus is more thorough on protocol-satisfiability and verification rigor**: its two
  strongest findings (F2 on AutoTrigger cross-surface unsatisfiability, F12 on the
  git-author-count check) both involved either tying a finding to a concrete prior
  documented incident or running and citing an exact reproducible command. Fable's
  findings are, on the whole, well-argued but more textual/comparative (diffing wording
  across documents) than empirically verified against git/repo state.
- **Fable is more thorough on cross-document reference-chain checking**: the stale
  `docs/council/README.md` taxonomy + specific dead downstream link (2b.4), and the
  REVIEW.md "Thursday" docstring staleness (2b.5), are both findings that required
  tracing a claim through to a second or third document and confirming the chain breaks
  — exactly FR-3's Systems Architect job description, arguably outside strict FR-1 scope,
  but genuinely useful and something Opus's run did not produce.
- **Neither is more thorough on Step 2 (prompt.md drift) or Step 5 (promote/keep-scoped)**
  — these two sections are close to word-for-word equivalent in substance, sample
  selection, and conclusion between the two runs.

---

## 3. Cost-premium verdict

Per Anthropic's published pricing, Fable carries roughly a 5x per-token premium over
Opus (Fable is a larger/slower-horizon model positioned for long-context synthesis;
Opus is priced below it). Token usage in this run: Fable consumed ~96.8K tokens across
28 tool calls in ~246s; Opus consumed ~126.7K tokens across 31 tool calls in ~239s —
Opus was *not* cheaper on token count here (it read more, partly because it ran the
`git log --format=%an` full-history check and additional verification passes Fable did
not attempt), but at even a conservative 5x per-token multiplier, Fable's run would cost
roughly 5x more than Opus's *despite Opus doing measurably more verification work and
producing the single highest-value finding of the pilot (F2, cross-surface AutoTrigger
unsatisfiability)*.

**Verdict for this specific task shape (protocol/prompt-methodology review over ~15
markdown/doc files, moderate cross-referencing, no deep single-formula derivation): the
Fable cost premium is not justified by this diff.** Fable did produce two findings Opus
missed (the stale council folder taxonomy/dead-link chain, the REVIEW.md "Thursday"
docstring) that have genuine standalone value, and the two runs' convergence on ~10 of
~15 substantive findings plus an identical Step 5 recommendation is itself informative
(cross-model agreement is a legitimate signal). But Opus's run was not shallower in any
dimension that showed up in the diff — it was more empirically grounded, tied findings
to concrete verifiable commands and to a real documented incident, and it caught the
single most consequential finding in the entire pilot. If the goal is "the best possible
protocol review at the lowest defensible cost," Opus is the better buy for this specific
task shape; if the goal is "maximize total distinct findings surfaced regardless of
cost," running both (as this pilot did) beats either alone, but that is not the same
claim as "Fable alone justifies its premium over Opus alone."

---

## 4. Per-task recommendation table

Per-task recommendation, each as a task shape, a recommendation, and the reasoning tied to this diff.

### **FR-1** (Protocol Reviewer)

**Task shape:** Same shape as this pilot's payload, verbatim

**Recommendation:** **Downgrade to Opus.**

**Reasoning tied to this diff:** This *is* the FR-1 task.
The diff directly shows Opus produced the most consequential single finding (F2)
and did more empirical verification (git-author-count check) at comparable or lower cost, while Fable's unique catches (council folder taxonomy, Thursday docstring) are real
but narrower in blast radius than F2. Extrapolation confidence: **high** — this is a direct test, not an analogy.

### **FR-3** (Systems Architect — cross-document architecture/provenance synthesis over `docs/archive/`, ~144 files, DECISIONS.md-to-council-source tracing)

**Task shape:** Different cognitive demand:
much larger document corpus (144 archive files vs. ~15 here), deeper provenance-tracing (does a current decision still match its cited archived source) rather than internal-consistency-of-current-docs

**Recommendation:** **Keep Fable — do not extrapolate from this pilot with high confidence.**

**Reasoning tied to this diff:** This pilot's payload was ~15 files with light cross-referencing;
FR-3 explicitly must hold a much larger document graph in mind at once and trace provenance across an order of magnitude more files.
Fable's *only* two unique catches in this pilot (2b.4, 2b.5) were both exactly this genre of cross-document reference-chain tracing,
which is weak evidence *in Fable's favor* for FR-3's specific demand, but the sample size (2 findings, one document graph) is too thin to be confident.
State explicitly: **cannot extrapolate confidently from an FR-1-shaped test to FR-3's provenance-and-scale demand** — this is a genuine limitation of this pilot, not a hedge.
Default to keeping Fable per the epic's own stated fallback ("if FR-0 can't extrapolate confidently, treat default-to-Fable as the safer choice").

### **FR-7** (Chairman — synthesis-of-synthesis over FR-1..FR-6's six findings documents plus their closing missing-persona blocks)

**Task shape:** Different cognitive demand again: not reviewing the repo, reviewing *other reviews* —
cross-referencing six documents' worth of findings for convergence/duplication, and weighing closing-block self-reports

**Recommendation:** **Keep Fable — do not extrapolate from this pilot with high confidence.**

**Reasoning tied to this diff:** Same limitation as FR-3, arguably stronger: this pilot never tested a model reading *another model's output* and synthesizing across it —
it tested two models independently reading the *same primary-source* repo.
FR-7's actual demand (read six findings docs, deduplicate,
weigh self-reported gaps) is structurally closer to FR-1/FR-3's long-horizon-synthesis profile than to Opus's demonstrated strength in this pilot (empirical verification against primary repo state —
there is no "primary repo state" to verify in FR-7, only other models' prose).
Flagging explicitly, per the epic's own instruction: FR-0's recommendation for FR-7 is **low-confidence** and defaults to keeping Fable rather than downgrading on thin evidence.


---

## 5. Limitations of this pilot (read before applying the table above)

- **n=1 comparison, one task shape.** This pilot ran exactly one prompt once per model.
  It is direct, strong evidence for FR-1 (identical task) and weak, non-extrapolable
  evidence for FR-3 and FR-7 (different cognitive demands), as stated above. Do not treat
  the FR-3/FR-7 "keep Fable" recommendation as validated — it is a default applied under
  uncertainty, not a tested conclusion.
- **Tool availability asymmetry.** The Opus run's own method note states its
  `codebase-memory-mcp` graph tools were deferred and VM bash was intermittently
  unavailable during part of its run; the Fable run did not report the same disruption.
  This may partly explain why Opus leaned more heavily on `git log`/author-count style
  verification (available) versus deeper graph-based cross-referencing (unavailable) —
  i.e., the diff may partly reflect which tools happened to be reachable in each run
  rather than a pure model-capability difference. This is a genuine confound; a repeat
  run with identical tool availability would strengthen the FR-1 recommendation further
  and is worth doing if the FR-1 downgrade decision is ever revisited.
- **No blind grading.** Both outputs were read and diffed by the same orchestrating
  session that requested them, with knowledge of which output came from which model.
  This introduces a risk of confirmation bias in what counts as "more thorough" — the
  diff above tries to ground every thoroughness claim in a specific, checkable action
  (a command run, a cited incident, a second-document trace) rather than a subjective
  quality judgment, but this is a mitigation, not a full blind-review control.

---

**This is a one-time validation.** Do not re-run this pilot for every subsequent
Fable-assigned task in this epic. FR-1 reads this file and downgrades to Opus per the
table above. FR-3 and FR-7 each read this file once and keep Fable per the table above,
noting FR-0's explicit low-confidence flag for their task shape.
