# FR-3 — Architecture & Design-Doc Consistency Review

**Persona: Systems Architect.** Run as: **Sonnet** (model substitution — see note below), Date: 2026-07-05.

**Model substitution note:** `FR-0` recommends *keep-Fable* for FR-3, explicitly flagged low-confidence
(FR-0's tested payload was FR-1-shaped, not FR-3's cross-document-provenance-at-144-files shape). This
session ran on Sonnet, not Fable, because the driving session had no Fable subagent override available
and the task needed to proceed inline rather than via a separate cross-session run. This is a real
deviation from FR-0's (low-confidence) recommendation, not a considered downgrade decision — flagging it
per the epic's own substitution-disclosure requirement. Net effect on this review's reliability: unknown
in either direction; treat findings below as directionally sound (every claim is grounded in a specific
file/line/commit, not narrative inference) but treat the *absence* of additional findings as weaker
evidence than it would be from a Fable run, given the review corpus here (root markdown + `docs/plan/` +
`docs/council/` + two `docs/archive/` subfolders) is large enough that exhaustive cross-referencing was
not attempted — sampling followed the task's own seed issues plus targeted verification, not a full
144-file archive read.

**Scope read:** `CONTEXT.md`, `DECISIONS.md` (full, 756 lines), `docs/plan/README.md` + all 14
`docs/plan/*/` folders (listing + selected task files), `docs/council/README.md` +
`docs/council/2026-07-02_paper-delta-source-architecture.md`, `docs/archive/council/` (full directory
listing + 4 files read in full or targeted grep), `docs/archive/plan/` (full directory listing),
`BACKTEST_PLAN.md` (targeted), `BACKTEST_PLAN_PHASE1.md` (targeted), plus `git log` against `src/`
paths named in the seed issues and `find src scripts -maxdepth 2 -type d` for the naming-collision
check. Did not read `MISSION.md`, `GLOSSARY.md`, `LITERATURE.md`, `ANTIGRAVITY.md`, `REFERENCES.md`,
`TODOS.md`, `PLANNER.md`, `CONTEXT_TREE.md` line-by-line — these were available but not load-bearing
for the findings below; flagging as a gap in "Missing persona" section.

---

## 1. Dependency map — which docs claim authority over which facts

| Fact domain | Authoritative doc | Docs that restate/depend on it (drift risk) |
|---|---|---|
| Module tree / what exists | `CONTEXT.md` (summary) + `CONTEXT_TREE.md` (full) | `docs/plan/README.md` status table (independently tracks the same "what's built" fact and, per §2 below, has drifted badly) |
| Architecture decisions / council rulings | `DECISIONS.md` | Module `CLAUDE.md` files (should cite, several do); `docs/plan/*/prompt.md` files (some cite, inconsistently) |
| Instrument keys / AMFI codes | `REFERENCES.md` | Not independently re-stated elsewhere in sampled scope — no drift risk observed |
| Story status (not-started/in-progress/done) | `docs/plan/README.md` (top-level) + each story's own `*_tasks.md` (per-task truth) | These two are supposed to be kept in sync manually; §2 shows the top-level table has fallen far behind the per-story checklists and the archive itself |
| Council decision provenance | `docs/archive/council/{strategy,risk,data_architecture,misc}/` (actual files) | `docs/council/README.md`'s own stated taxonomy (`docs/council/archive/{strategy,risk,research}/`) — this is itself now a second, incorrect source of "where do decisions live" |
| Phase 0.8 gate criteria | `BACKTEST_PLAN.md` (current, revised text) | `docs/archive/council/risk/2026-05-02_variance-gate-regime-completeness.md` (origin); `DECISIONS.md → Variance Gate` (summary) — checked consistent, see §5 |

**Structural observation:** there are effectively two independent "is X built yet" ledgers —
`CONTEXT.md`'s prose description of `src/` and `docs/plan/README.md`'s status table — and only
`CONTEXT.md` is reliably updated. `docs/plan/README.md` is the one a fresh agent or human would consult
first to decide *what to work on next*, which is exactly where staleness does the most damage (see F1).

---

## 2. Stale "not implemented" / "not started" claims — spot-checked against repo state

### F1 — [CRITICAL] `docs/plan/README.md`'s "Active Stories" table is comprehensively stale; three
entries describe fully-shipped, already-archived work as "⬜ Not started"

Verified via `git log` + `docs/archive/plan/` listing:

- **`council-refactor/`** — README: "Remove `RapidCouncil` from daemon approval path... ⬜ Not started."
  Reality: this is done and *archived*. `git log --oneline --grep council-refactor` shows the folder
  was explicitly closed out (`e6b4521 chore(docs): archive council-refactor plan — all stories
  implemented`), and `DECISIONS.md` has a standing `RapidCouncil removed from paper trading approval
  path (2026-06-04, CR)` entry plus 8+ other `council-refactor, CR`-tagged shipped decisions (CSP/CC/PP/
  Collar design, `ReEntryMixin`, futures+CC block). The folder no longer even exists under `docs/plan/`
  — it lives at `docs/archive/plan/council-refactor/`. A fresh agent following the README's "Next task:
  CR0 — fix approval flow signature" would attempt to re-implement or re-diagnose a bug that was fixed
  over a month ago.
- **`paper-backbone/`** — README: "Strategy Monitor daemon + pluggable strategy backbone... ⬜ Not
  started." Reality: `DECISIONS.md` has `paper-backbone architecture shipped (2026-06-02, PB)` describing
  `PaperStrategy` protocol, `StrategyMonitor`, `PaperExecutor`, `TelegramGateway` — all currently live and
  described as existing infrastructure throughout `CONTEXT.md`. `git log` on `src/strategy/monitor.py`,
  `src/strategy/executor.py`, `src/notifications/telegram_gateway.py` shows 10+ commits of active,
  ongoing work (most recent sampled: `f737ee5 feat(strategy): wire profit-lock into
  IronCondorV2.check_signals()`). Archived at `docs/archive/plan/paper-backbone/`.
- **`ic-nifty-v2/`** — README: "IronCondorV2: 25Δ/22Δ high-delta IC... ⬜ Not started." Reality:
  `CONTEXT.md` describes `IronCondorV2` as a complete, currently-active 69 KB implementation with
  wired profit-lock, DTE-tiered exits, and full signal hierarchy; `DECISIONS.md` has two dedicated
  council-sourced entries (`Iron Condor V2 Core Design`, `IC V2 Profit-Lock Adjustment`) both marked
  shipped; `git log` shows a multi-commit implementation history culminating in
  `9aa1048 fix(strategy): add missing profit-lock Zone 2 attempt log`. Archived at
  `docs/archive/ic-nifty-v2/` (note: different archive path shape than the other two — see F5).

**Also stale, same table, one level up:** the **"Active Epics"** row for `dev-foundation/` reads
"⬜ Not started," but `docs/plan/dev-foundation/README.md` (the epic's own sub-index) states
**"Closed 2026-05-31. All 21 tasks shipped across three sub-epics."** This is not a borderline case —
the epic's own completion doc is one click away from the exact table that contradicts it.

**Impact:** four of the ten rows in the combined Epics+Stories table (dev-foundation, council-refactor,
paper-backbone, ic-nifty-v2) are wrong in the same direction — all understate progress, none overstate
it — which suggests the table was written once at project start and never revisited on story
completion, rather than drifting randomly. **This is the single highest-impact finding in this review**:
an agent or Animesh scanning this table for "what's unstarted and worth picking up" would misallocate
real planning effort against work that already shipped, and a "Next task" pointer into an archived,
non-existent folder wastes a session before the mistake is even discoverable.

**Correctly stale-free control cases** (confirms the table isn't uniformly wrong, i.e. this is real
drift, not a formatting artifact): `mvp/` — README says "Not started," and `src/mvp/`,
`scripts/mvp.py`, `scripts/mvp_watch.py` genuinely do not exist; `paper-exit-codification/` — README
says next task is "EC-1," and `docs/plan/paper-exit-codification/*tasks*.md` confirms EC-1/EC-2/EC-3
are all still `- [ ]` unchecked, consistent; `risk-gamma-phase-a/` — "In progress, next B2.2" is
accurate (`B2.1` checked, `B2.2`–`B2.5` unchecked in the story's own task file, and
`gamma_daily_watch.py`'s `_fetch_and_snapshot`/`_update_watchlist` bodies are scaffolds, not full
implementations).

### F2 — [ERROR] `CONTEXT.md` "What Does NOT Exist Yet" — `src/nuvama/CLAUDE.md` claim is stale
(seed issue, confirmed)

`CONTEXT.md` line 63 states `src/nuvama/CLAUDE.md — module context file not yet written`. The file
exists: `wc -l src/nuvama/CLAUDE.md` → 47 lines. Rated ERROR not CRITICAL because the blast radius is
narrow (one module's auto-load context, not a whole epic's status), but it is exactly the same failure
class as F1 (a "not built yet" claim that repo state has quietly outrun) and its presence in the seed
issues suggests this class of drift recurs whenever a doc's "not exists yet" section isn't pruned on
each commit that closes the gap.

---

## 3. `docs/plan/README.md` folder-convention check

Every story folder still present under `docs/plan/` (`backtest-eval-core`, `broker-abstraction`,
`dev-foundation`, `historical-data-abstraction`, `mvp`, `options_income`, `paper-exit-codification`,
`paper-store-position-granularity`, `risk-gamma-phase-a`, `signals`, `signals-eval-core`,
`telegram-leg-labels`, `variance-gate`, `full-repo-review`) matches the README's own "Conventions"
section (`prompt.md` + `*_tasks.md` + `*_stories.md`, spec/schema where applicable). **No drift found
among currently-present folders.** The drift is entirely in folders the README *still references but
that no longer exist under `docs/plan/`* — see F1 and F5.

---

## 4. `DECISIONS.md` entries a dependent doc fails to reflect

### F3 — [WARNING] `RapidCouncil`/`SignalAggregator` duplication (seed issue) is documented in
`DECISIONS.md` but not cross-referenced from either consuming plan doc

`DECISIONS.md`'s `2026-07-04` entry (`RapidCouncil status audit and re-flag criterion`) is itself the
most rigorous entry in the file — it already audited every `docs/plan/` story for live-council
candidacy and flagged the `RapidCouncil` / `SignalAggregator` (`docs/plan/signals/`, S1.3) duplication
explicitly, with a stated revival criterion. Checked whether `docs/plan/signals/` or any
`SignalAggregator`-touching story references `RapidCouncil` in a way that assumes it doesn't exist, or
vice versa: **no story file yet references the other system by name** — the duplication is currently
inert (neither doc actively contradicts the other), so this doesn't rise to CRITICAL. It is a WARNING
because the `DECISIONS.md` entry itself says "flag `RapidCouncil` for revival... check
`src/council/rapid.py` and `docs/plan/signals/` first" — that check-first instruction lives only in
`DECISIONS.md`; `docs/plan/signals/`'s own story files carry no back-reference, so a session that opens
`docs/plan/signals/` directly (per its own protocol: "load only that story file + CONTEXT.md + module
CLAUDE.md") would never see the warning that motivated this cross-check requirement in the first place.

### F4 — [INFO] `docs/council/README.md`'s "2 of 4 models" dissent framing (paper-delta-source-architecture)
is slightly imprecise but not misleading

`DECISIONS.md`'s entry says "dissent from 2 of 4 models argued for fail-closed even in paper mode."
Reading all four Stage 1 responses in `docs/council/2026-07-02_paper-delta-source-architecture.md`:
Gemini and Deepseek argued fail-closed across all three failure modes; Grok argued fail-closed only for
the chain-fetch-failure mode (partial); gpt-4.1 matched the eventual chairman synthesis. So the "2 of 4"
count is defensible as "2 full dissents" but slightly undercounts partial dissent (Grok). Rated INFO —
this is a rounding-of-nuance issue, not a paraphrase that changes the operative ruling, and the rest of
the `DECISIONS.md` entry (module boundary, signature change, fallback policy, live-vs-paper distinction)
is a faithful, non-drifted representation of the chairman's Stage 3 synthesis.

---

## 5. Provenance check — 5 `DECISIONS.md` entries vs. their cited archive source

| # | `DECISIONS.md` entry | Cited source | Verdict |
|---|---|---|---|
| 1 | Paper delta source architecture (B002.4) | `docs/council/2026-07-02_paper-delta-source-architecture.md` | **Accurate.** Module boundary (b), signature change, and fallback policy all match the chairman's Stage 3 Summary Table and Fallback Policy sections verbatim in substance. See F4 for the one minor nuance. |
| 2 | Iron Condor V2 Core Design (council q10) | `docs/archive/council/strategy/2026-06-26_ic-v2-core-design.md` | **Accurate.** Entry deltas (0.25/0.22/0.03), wing floors (monthly ₹15/weekly ₹10/5Δ floor), roll-debit cap (≤50% of credit), max 1 roll/side/cycle, and the DTE≤3 CLOSE_FULL-both-sides rule all match Decisions 1–4 in the archive file exactly, including the archive's explicit "Yes, CLOSE_FULL not challenged-side-only" answer for the profitable-side question. |
| 3 | IC V2 Profit-Lock Adjustment (council q13) | `docs/archive/council/strategy/2026-06-27_ic-v2-profit-lock-adjustment.md` | **Accurate.** Zone 1/2/3 mechanics, the `max(W,W)+D_cum+D_lock+K ≤ 0.75×C₀` (Zone 2) and `≤0.35×C₀` (Zone 3) floor formulas, the 18–20Δ wing-roll target, D3-interaction precedence rule, and the 25%-of-credit debit cap all check out against the archive's derivation section line-for-line. |
| 4 | Multi-strategy portfolio risk allocation (10 binding rules, referenced via `src/risk/` thresholds in `CONTEXT.md`) | `docs/archive/council/risk/2026-05-02_multi-strategy-portfolio-risk-allocation.md` | **Accurate.** `DECISIONS.md`'s "+1.0 lot (warning +0.75)" options-only and "+2.0 lots (warning +1.5)" combined caps match the archive's Rules 2/3 exactly, and both match the live `PortfolioDeltaTracker` constructor thresholds described in `CONTEXT.md`. Three-way consistency (archive → DECISIONS → running code) — no drift anywhere in this chain. |
| 5 | Variance Gate — Phase 0.8 Deployment Tiers | `docs/archive/council/risk/2026-05-02_variance-gate-regime-completeness.md` | **Accurate, and additionally verified propagated downstream** (see §6/F6 — `BACKTEST_PLAN.md` was actually updated with the revised A–D criteria per the council's own Implementation Sequencing instruction, with an explicit `> Council decision 2026-05-02: Gate criteria revised` annotation). This is the one sampled entry where the full provenance chain — origin council file → `DECISIONS.md` → dependent plan doc — was checked end-to-end and found clean. |

**Provenance verdict:** across the 5 sampled entries (deliberately including the ones most likely to
show drift — the newest, most complex, most cross-referenced rulings), **no paraphrase drift and no
walked-back decision was found.** This is a meaningfully different risk profile than §2's findings:
`DECISIONS.md` itself is trustworthy once you're reading it; the risk is entirely in the *index* layer
(`docs/plan/README.md`, `docs/council/README.md`) that tells you which docs are still current.

---

## 6. Forward-validity check — Blocked/Later Stories + `BACKTEST_PLAN_PHASE1.md` Phase 1+ scope

### F6 — [INFO] Blocked-story blockers still hold; no invalidation found

- `backtest-eval-core/` blocked by "Phase 1.3 (Bhavcopy) + Phase 1.4 (BacktestEngine)": confirmed both
  genuinely incomplete — `BACKTEST_PLAN_PHASE1.md` task 1.4's `src/backtest/engine.py` checkbox is
  unchecked, and the Phase 1.12 gate checklist (line 557) still requires 1.3's data-quality gate.
  Blocker accurate, not resolved, not worsened.
- `signals-eval-core/` blocked by "backtest-eval-core + Phase 1.12 gate": transitively still valid given
  the above.
- `signals/` blocked by "signals-eval-core": still valid, and additionally now has the live
  `RapidCouncil`/`SignalAggregator` duplication (F3) as a *second*, currently-undocumented dependency —
  worth adding to the blocker table once `signals-eval-core` unblocks, since whoever picks up `signals/`
  will need to consult the `DECISIONS.md` 2026-07-04 entry before choosing an implementation, and the
  blocker table doesn't currently point there.

### F7 — [WARNING] `BACKTEST_PLAN_PHASE1.md`'s own internal gate checklist has an unresolved
self-contradiction (not cross-document, but still a forward-validity risk)

`BACKTEST_PLAN_PHASE1.md` line 556: `- [x] 1.1–1.10a all [x] (including 1.3a, 1.6a, 1.9, 1.9a, 1.10,
and 1.10a).` — immediately followed by line 558: `- [ ] 1.3a complete: ... data quality gate passed`
(unchecked). Read charitably, these are different bars (task-shipped vs. gate-gate-gate re-verification
at the Phase 1.12 sign-off), but the doc does not say so explicitly, and a reader skimming for "is 1.3a
done" gets two different answers four lines apart. Low blast radius today (Phase 1.12 hasn't been
reached), but worth a one-line clarification before Phase 1 work actually reaches this gate, since it's
exactly the kind of ambiguity that produces a false "gate passed" sign-off later.

**`BACKTEST_PLAN.md`'s Phase 0.8 gate criteria specifically** (the seed issue asking whether this was
superseded without the plan doc being updated): **not stale** — confirmed clean in §5 above. This seed
issue did not pan out as a real problem on inspection, worth stating explicitly since three of the five
other seed issues did pan out.

---

## 7. Folder-naming collision check

`find src scripts -maxdepth 2 -type d | sort` (pycache dirs excluded from analysis below).

### F8 — [WARNING] `src/strategy/` vs. `scripts/strategies/` (seed pair)

Singular/plural pair, genuinely different layers (library protocol/monitor/strategy classes vs.
per-strategy CLI entrypoints). No evidence in sampled `git log` of an actual misdirected `Read`/edit
between the two — commit messages consistently scope to the correct tree (e.g., `feat(strategy): wire
profit-lock into IronCondorV2.check_signals()` targets `src/strategy/`; `feat(strategies): OPS-2 atomic
collar open/close` targets `scripts/strategies/`). The two commit-message prefixes (`strategy:` vs.
`strategies:`) already function as an informal disambiguator in practice. **Recommendation: no rename
(cost/disruption not justified); add one clarifying line to `CONTEXT_TREE.md`** stating the layer
distinction explicitly next to both entries, since the ambiguity is real for a cold reader even if it
hasn't caused a confirmed misdirection yet.

### F9 — [WARNING, escalated above the seed pair] `src/intraday/` vs. `scripts/intraday/` and
`src/council/` vs. `scripts/council/` — identical names, not just singular/plural

The seed issue's premise (singular/plural is "a thin disambiguator") undersells the actual worst case
in this repo: two pairs share the **exact same name** with no lexical cue at all.

- `src/intraday/` — 1 file (`market_store.py`, a store/model layer) vs. `scripts/intraday/` — 3 files
  (`dhan_intraday_tracker.py`, `intraday_tracker.py`, `nuvama_intraday_tracker.py`, all cron
  orchestrators). A human or agent typing `src/intraday` from memory when they meant the tracker
  scripts (or vice versa) gets no naming signal to self-correct — unlike `strategy`/`strategies`, where
  the plural is at least a visible flag. This is a **higher** ambiguity risk than the seed pair, not a
  lower one.
- `src/council/` (`models.py`, `rapid.py` — the `RapidCouncil` implementation) vs. `scripts/council/`
  (`ask_council.py` — the human-facing CLI for submitting a question to the external LLM council
  service). These are conceptually unrelated systems that happen to share a name for adjacent reasons
  (`src/council/` is an in-process automated consensus engine for strategy decisions; `scripts/council/`
  is a CLI to the separate `tools/llm-council` service used for design-doc rulings like the ones cited
  in §5) — this is the more consequential collision of the two, since confusing them could plausibly
  lead someone to believe `RapidCouncil` (dormant, F3) and the `ask_council.py` workflow (active, used
  for every archived ruling in §5) are the same subsystem, when they are unrelated.

No confirmed misdirected edit found in sampled `git log` for either pair, so rating stays WARNING not
CRITICAL for now. **Recommendation:** disambiguating note in `CONTEXT_TREE.md` for both pairs (cheap,
no code/import/CI blast radius); a rename is not warranted given the `council`/`intraday` names are
otherwise apt for what each side does — the fix is documentation, not renaming.

---

## 8. Findings summary table

| ID | Severity | Finding |
|---|---|---|
| F1 | **CRITICAL** | `docs/plan/README.md` Active Epics/Stories table stale for `dev-foundation`, `council-refactor`, `paper-backbone`, `ic-nifty-v2` — all shown "not started" despite being shipped and (for 3 of 4) already archived out of `docs/plan/` entirely |
| F2 | ERROR | `CONTEXT.md` "What Does NOT Exist Yet" — `src/nuvama/CLAUDE.md` claim stale (confirmed, seed issue) |
| F3 | WARNING | `RapidCouncil`/`SignalAggregator` duplication documented in `DECISIONS.md` but not cross-referenced from `docs/plan/signals/`'s own story files |
| F4 | INFO | Minor undercount ("2 of 4" vs. 2 full + 1 partial dissent) in the paper-delta-source provenance summary — doesn't change the operative ruling |
| F5 | (folded into F1) | `docs/council/README.md`'s stated archive taxonomy (`docs/council/archive/{strategy,risk,research}/`) is stale — actual location is `docs/archive/council/{strategy,risk,data_architecture,misc}/` (2 extra categories never documented); confirmed dead downstream link: `docs/plan/variance-gate/prompt.md:18` points to `docs/council/2026-05-02_variance-gate-regime-completeness.md`, which does not exist (real path: `docs/archive/council/risk/...`) |
| F6 | INFO | Blocked/Later Stories blockers all still hold; `signals/`'s blocker table should eventually also point at the F3 duplication |
| F7 | WARNING | `BACKTEST_PLAN_PHASE1.md` line 556 vs. 558 — internal self-contradiction on whether 1.3a is "done" (task-shipped vs. gate-verified ambiguity) |
| F8 | WARNING | `src/strategy/` vs. `scripts/strategies/` — real but not yet-exercised ambiguity; recommend `CONTEXT_TREE.md` note, no rename |
| F9 | WARNING | `src/intraday/`↔`scripts/intraday/` and `src/council/`↔`scripts/council/` — identical (not just singular/plural) names across trees, arguably higher risk than the seed pair; recommend `CONTEXT_TREE.md` notes, no rename |

**Provenance check (§5) came back clean across all 5 sampled entries** — the one negative result worth
stating plainly: this review did not find `DECISIONS.md` itself to be untrustworthy. The risk is
concentrated entirely in the index/navigation layer (`docs/plan/README.md`, `docs/council/README.md`)
that tells an agent or human where to look next — exactly the layer a "cross-document consistency"
persona is positioned to catch and a single-file code reviewer would not think to check.

---

## Closing block

State the persona you reviewed as (Systems Architect). Name at least one perspective this review did
not cover that a different persona would have caught — write "none identified" explicitly if genuinely
nothing comes to mind, do not omit this section.

**Persona reviewed as:** Systems Architect.

**Perspective not covered:** A **process/ops persona auditing why `docs/plan/README.md` goes stale
in the first place** — this review found *what* is wrong (F1) but not *why* the update step keeps
getting skipped at story-close time despite `CLAUDE.md`'s own Step 5a mandating doc updates as part of
closing a phase. That's a protocol-adherence question (closer to FR-1's Protocol Reviewer persona than
to this one), and FR-1's own pilot findings (in `FR-0`) already surfaced adjacent territory (prompt.md
drift across story eras) without specifically checking whether `docs/plan/README.md` updates are part of
any story's own closing checklist. A dedicated pass cross-referencing FR-1's findings against F1 here
would likely show the same root cause: the top-level README isn't named in any individual story's
"Step 5a — Update docs" checklist, so nothing forces it to be touched on story close. Recommend FR-9
(synthesis/roadmap) treat this as a candidate fix: add `docs/plan/README.md` to the mandatory doc-update
list alongside `CONTEXT.md`/`DECISIONS.md`/`TODOS.md` in the root protocol, since F1's four stale rows
all point to the same single missing step rather than four independent oversights.
