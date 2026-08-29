# FR-7 — Chairman Synthesis (Synthesis-of-Synthesis)

**Persona:** Chairman
**Model:** Fable (kept per FR-0's explicit low-confidence caveat on its FR-7 recommendation — no substitution)
**Date:** 2026-07-06
**Inputs read in full:** FR-1 (Protocol Reviewer), FR-2 (Quant Reviewer), FR-3 (Systems Architect),
FR-3.1 (Folder Structure Auditor — treated as part of FR-3's findings), FR-4 (Standards Auditor),
FR-5 (Test Auditor), FR-6 (Red-Team Reviewer). Background only: `docs/council/README.md`,
`docs/archive/council/strategy/2026-05-02_iron-condor-v1-core-design.md` (formatting reference).

**Role note:** this document does not re-review the repo. Findings are taken as given from the six
reviewer passes; the work here is merging, deduplicating, ranking, and reconciling severity across
them — the same role RapidCouncil's chairman-synthesis stage plays.

---

## How to read this document

- The **Summary Table** is one row per *distinct underlying issue*. Where multiple reviewers hit the
  same gap from different angles, the row merges them and the "Source" column lists all of them.
- Severity in the table is the **chairman's synthesized rating**, not necessarily any single
  reviewer's. Where reviewers disagreed, the disagreement is preserved in the "Severity divergences"
  section below the table rather than silently collapsed — per FR-5's own explicit request that FR-7
  "preserve both framings rather than collapsing to one severity label."
- Rows are ordered by synthesized severity, then by capital-proximity (real-money paths before
  paper/docs paths).

---

## Stage 3 — Summary Table

The rows of the synthesized summary follow, each as **# — Severity — Source**, then the one-line finding and the recommended action.

### 1 — **CRITICAL** — FR-2 (F1, F2)

**Finding:** `src/portfolio/store.py::get_position()` returns `entry_price = 0` for short-first legs, AND `apply_trade_positions` silently drops all realized P&L for closed legs —
both confirmed live against the real `finideas_ilts` position (₹52,318.50 of booked profit invisible; open short PE P&L wrong in sign and magnitude)

**Action:** Fix `get_position()` to use weighted SELL price when `buy_qty == 0`;
add a realized-P&L path to `PortfolioTracker` mirroring `src/paper/tracker.py`'s reference implementation; add regression tests for short-first and round-tripped legs.
Highest-priority code fix in the epic — real capital, wrong today.

### 2 — **CRITICAL** — FR-6 (S-4)

**Finding:** No backup mechanism of any kind exists for `data/portfolio/portfolio.sqlite` —
the single store of record for all trade history, paper P&L, approvals, and risk state, sitting on a FUSE-artifact-littered mount

**Action:** Add a daily cron using SQLite's `.backup` API (not raw file copy — WAL torn-copy risk) to a separate directory/drive with 30-daily/12-monthly retention.
5-line change on existing cron surface.

### 3 — **CRITICAL** — FR-3 (F1)

**Finding:** `docs/plan/README.md` status table shows 4 of 10 epics/stories (`dev-foundation`, `council-refactor`, `paper-backbone`, `ic-nifty-v2`) as "Not started" when all are shipped
and mostly archived — the first doc consulted to pick up work, misdirecting whole sessions

**Action:** Rewrite the status table rows against `docs/archive/plan/` + `DECISIONS.md`; adopt FR-3's root-cause fix (row 15).

### 4 — **CRITICAL** — FR-1 (F-C1)

**Finding:** Root CLAUDE.md's AutoTrigger table ("blocking, not optional") is literally unsatisfiable on the Antigravity surface, which cannot spawn Claude agents;
the escape hatch exists only in ANTIGRAVITY.md — directly feeds the documented commit-drafted-not-executed failure mode

**Action:** Add one line to the AutoTrigger "Blocking" note: on surfaces that cannot spawn agents, emit the await-signal per ANTIGRAVITY.md and treat the gate as human-completed, not skipped.

### 5 — **CRITICAL** — FR-1 (F-C2), FR-4 (G7 §1)

**Finding:** The repo's own standards contradict each other:
module CLAUDE.md files mandate broad-catch / "assert" patterns REVIEW.md §G5/§G6 rates CRITICAL for new code, and REVIEW.md G7 (%-style logging) contradicts LOGGING.md's structlog keyword-arg rule —
a compliant agent gets blocked by a compliant reviewer either way

**Action:** One reconciliation pass: add G5 intent-comment guidance inline to the 4 broad-catch module docs;
fix `src/paper/CLAUDE.md` "asserts" → "raises ValueError"; add a G7 carve-out ("%-style for stdlib logging, kwargs for structlog") to REVIEW.md; log in DECISIONS.md.

### 6 — **CRITICAL** (contested — see divergence D1) — FR-5 (GREEKS-1, PARITY-1), FR-2 (F7)

**Finding:** No independent correctness check exists anywhere for Greeks or option-chain data:
no Black-Scholes reference test (Upstox's own feed is the uninspected ground truth) and zero put-call-parity checks repo-wide —
the confirmed reason findings 1/2 above went undetected until manual DB reconciliation

**Action:** Both tagged NEEDS-OPUS-REVIEW by FR-5:
a quant (options-strategist / greeks-analyst) decides tolerance bands
and reference-model assumptions, then implement a parity check (cheap, fixture-arithmetic-only) first and a BS reference test second.

### 7 — **CRITICAL** — FR-4 (§1)

**Finding:** Logging standard mass non-compliance: 21 `src/` files use bare `logging.getLogger(__name__)`, 22 of 53 script entrypoints never call `setup_logging()` —
LOGGING.md's mandatory rules, elevated to canonical by CLAUDE.md, exactly the BUG-010 failure class

**Action:** Mechanical batch fix (good Antigravity handoff shape: many files, zero ambiguity); pre-commit hook extension to catch bare `getLogger` in `src/` too.

### 8 — **ERROR** — FR-1 (F-E6, F12a, F12b), FR-3 (F5), FR-3.1 (F10)

**Finding:** Council/archive index layer is stale in one connected cluster:
`docs/council/README.md` declares a nonexistent path taxonomy (`docs/council/archive/`, 3 subfolders vs. actual `docs/archive/council/`, 5);
two confirmed dead links downstream, including DECISIONS.md's citation of the *source of record for live paper exit thresholds* (content also revised 06-26 —
a follower could read the superseded version)

**Action:** Fix README taxonomy + both dead links in one docs commit; FR-1 flags the DECISIONS.md link (F12b) as trending CRITICAL — do that one first.
FR-3's provenance check confirms DECISIONS.md *content* is trustworthy; the rot is entirely in the index/navigation layer.

### 9 — **ERROR** — FR-6 (S-2)

**Finding:** Telegram callback auth guard is OR where it should be AND — any member of a group chat the bot is ever added to could approve/reject real trading decisions;
currently masked only by 1:1-DM topology living in the deployer's head

**Action:** Change guard to `sender_id != self._chat_id` alone (identity of the button-presser is what matters). One-line fix + one test.

### 10 — **ERROR** — FR-4 (§3, §4)

**Finding:** Suppression hygiene: 26/26 `# type: ignore` and 80/89 `# noqa` lack the explanatory comment REVIEW.md's meta-rule mandates;
2 literal `assert`s in `src/` (G6); 183 `except Exception` sites only partially audited (10+ confirmed bare)

**Action:** Triage rather than blanket-fix:
carve out self-describing codes (E402/F401) in REVIEW.md, TD-ticket the 2 asserts, and scope the 183-broad-catch instance audit as its own follow-up (see row 20 / personas §b).

### 11 — **ERROR** — FR-1 (F-E1, F-E2, F-E3)

**Finding:** Protocol ambiguity cluster in root CLAUDE.md: Step 3b routing undefined for ≤2-file tasks;
Step 2b described three non-identical ways across three docs; "code" undefined at the code-reviewer trigger boundary (ANTIGRAVITY.md is more precise than the root doc it's subordinate to)

**Action:** Single CLAUDE.md editing pass: routing applies regardless of file count; one authoritative Step 2b mechanism; adopt ANTIGRAVITY.md's `.py` in `src/scripts/tests` scope.

### 12 — **ERROR** — FR-1 (F-E4, F-E5)

**Finding:** Prompt-template regression:
the "Pre-implementation gate" statement was silently dropped in the newer prompt.md generation, and the epic's own declared rigor baseline (telegram-leg-labels) is the procedurally *thinner* era —
FR-9 would codify a regression

**Action:** FR-9's canonical template must merge telegram-leg-labels' task-specificity with the older generation's Pre-implementation gate + full graph chain.

### 13 — **ERROR** — FR-5 (PNL-1)

**Finding:** `_compute_leg_unrealized_pnl`'s targeted property-test file has no golden (exact-value) assertion;
magnitude-preserving bugs pass — mitigated by golden tests one layer up in `test_tracker.py`

**Action:** Add 1–2 exact-value assertions directly into `test_pnl_hypothesis.py` so the unit closest to the math is self-verifying.

### 14 — **ERROR** — FR-3 (F2), FR-3.1 (F10)

**Finding:** Stale "does not exist yet" claims: CONTEXT.md still says `src/nuvama/CLAUDE.md` isn't written (it is, 47 lines); no doc anywhere describes 11 of `docs/archive/`'s 12 top-level entries

**Action:** Prune the CONTEXT.md line; write a short `docs/archive/README.md` (or narrow the council README's implied scope).

### 15 — **WARNING** — FR-3 (closing block), FR-3 (F1 root cause)

**Finding:** Root cause of rows 3/8/14: `docs/plan/README.md` is not named in Step 5a's mandatory doc-update list, so nothing forces it to be touched at story close —
four stale rows are one missing protocol step, not four oversights

**Action:** FR-9: add `docs/plan/README.md` to Step 5a's mandatory list alongside CONTEXT.md/DECISIONS.md/TODOS.md.

### 16 — **WARNING** — FR-3 (F8, F9), FR-3.1 (F10a)

**Finding:** Four `src/`↔`scripts/` name collisions (`council`, `intraday`, `portfolio` — exact-name;
`strategy`/`strategies`) with no lexical disambiguator; `portfolio` pair is on the live P&L critical path; sweep is exhaustive, no fifth pair exists

**Action:** One `CONTEXT_TREE.md` section listing all four pairs together (single taxonomy pattern, not four one-offs). No renames — cost not justified, commit-prefix convention has held.

### 17 — **WARNING** — FR-6 (S-5)

**Finding:** Token files written without `chmod 600` (world-readable `.env` with live broker tokens under default umask); OAuth callback lacks CSRF `state` param

**Action:** Mechanical follow-up story: `os.chmod(0o600)` after each of 3 token writes; `secrets.token_urlsafe()` state round-trip in `login.py`.

### 18 — **WARNING** — FR-6 (S-1 + closing block)

**Finding:** Retryable/terminal exception split is pure documentation — no retry mechanism exists;
safe today (orders hard-blocked) but load-bearing the day static-IP unblocks, and the *absence* of retry may itself cause silently-skipped risk gates (FR-6's own named blind spot)

**Action:** DECISIONS.md/TODOS.md note: retry semantics must be designed before the static-IP constraint is lifted; the missed-gate side needs an options-strategist judgment (personas §b).

### 19 — **WARNING** — FR-2 (F6), FR-1 (F-I3)

**Finding:** Tuesday-expiry migration consistent everywhere load-bearing,
but `src/instruments/lookup.py:341` lacks the pre/post-April-2026 cutoff guard its two siblings have, and REVIEW.md's canonical docstring example still says "Thursday"

**Action:** Add cutoff guard (or an explicit current-instruments-only comment) to lookup.py; one-word REVIEW.md fix.

### 20 — **WARNING** — FR-3.1 (F16 + closing), FR-4 (closing)

**Finding:** `scratch/` is git-tracked (including committed `diff.patch`/`git_diff.diff`) while identical-purpose `tmp/` is ignored;
contents never security-checked; separately, auth-path broad catches/suppressions never assessed for credential-leak masking

**Action:** One narrow security pass (FR-6's persona, scope extension): read the 8 tracked scratch files + `src/auth/` broad catches; then gitignore `scratch/` or document the distinction.

### 21 — **WARNING** — FR-5 (§7)

**Finding:** Coverage gate (`fail_under=80`) unverified for the two financially critical modules (`src/paper/`, `src/strategy/`) — sandbox couldn't install pandas;
`src/risk/` measured at 100% could be masking lower numbers in aggregate

**Action:** Next session with a working `.venv`: run targeted `--cov=src/paper --cov=src/strategy` before treating the 80% gate as verified.

### 22 — **WARNING** — FR-2 (F5)

**Finding:** `PortfolioDeltaTracker` fallback sign convention for short-PE could not be fully closed out without graph tooling (deferred in that session); no golden test pins the fallback's sign

**Action:** Follow-up with graph tools: verify `net_qty` sign at population site; add golden test `net_qty=-65, lot_size=65 → delta_lots == Decimal("1.00")`.

### 23 — **WARNING** — FR-3 (F3, F7), FR-3.1 (F11, F14, F15)

**Finding:** Lower-grade doc-drift cluster: RapidCouncil/SignalAggregator duplication warning lives only in DECISIONS.md (signals/ story files carry no back-reference);
BACKTEST_PLAN_PHASE1 internal 1.3a contradiction; 4-folder pre-convention archive pattern; `data/` + `config/`/`docs/instructions/`/`docs/viz/` undocumented

**Action:** Batch docs commit; none individually urgent, all the same discoverability failure mode.

### 24 — **WARNING** — FR-1 (F-W1–F-W4), FR-4 (§1 print)

**Finding:** Soft-norm residue: Rule 0's "NEVER…decision is yours" overstates enforceability; "load ONLY" contradicts the conditional-add list;
Step 2b has never verifiably fired as a gate; 23 script files use `print()` pending legitimate-CLI-output vs. structured-log triage

**Action:** Wording fixes in CLAUDE.md; print() triage needs a persona judgment call (FR-4 explicitly declined to blanket-rate it).

### 25 — **INFO** — FR-6 (S-6)

**Finding:** `requests`+`to_thread` in `UpstoxMarketClient` contradicts CLAUDE.md's aiohttp-only standard — works correctly, but is exactly the BUG-010-style doc/code drift pattern

**Action:** DECISIONS.md entry either accepting the pattern for sync SDK wrappers or scoping a migration.

### 26 — **INFO (positive)** — FR-3 (§5), FR-5 (§1), FR-6 (S-3), FR-1 (F-I2/I5), FR-4 (§2)

**Finding:** Explicitly-verified sound areas, so FR-9 doesn't mistake unexamined for unsound: DECISIONS.md provenance clean across 5 sampled entries;
`src/risk/` at 100% measured coverage with golden+property sign tests (the reference example); CI/prod boundary has genuine defense in depth;
core one-task discipline and domain invariants uniform; zero Part-III violations in the only recent code commit

**Action:** No action. Cite `src/risk/`'s test suite and `factory.py`'s single-chokepoint design as the patterns other modules should copy.


### Severity divergences preserved (not collapsed)

- **D1 — Greeks/parity absence (row 6):** FR-5 rates CRITICAL ("is the correctness test missing for
  financial logic" axis); FR-2 rates the same absence WARNING ("absence of a test is not itself a
  wrong result" axis) while rating the *consequences* (rows 1) CRITICAL. Both are right on their own
  axes. Chairman keeps CRITICAL in the table because the epic's evidence base itself proves the
  consequence: the absence demonstrably allowed two live CRITICAL accounting errors to survive.
- **D2 — Suppression-comment violations (row 10):** FR-4 rates CRITICAL "per the letter of the rule"
  while itself noting most bare E402/F401 codes are self-describing and the rule likely needs a
  carve-out. Chairman downgrades to ERROR: the load-bearing fix is the REVIEW.md policy carve-out,
  not 100+ mechanical comment additions.
- **D3 — FR-3.1 vs FR-3 framing:** FR-3.1 sharpened three FR-3 findings (F10 > F5; F11 pattern-of-4
  vs one-off; F12 split 2-of-9 documented vs 7 undocumented) without changing any severity. Rows 8,
  14, 23 use FR-3.1's sharper framing.

---

## Personas Not Represented

Every gap named across the seven closing blocks, deduplicated, classified:

**(a) Worth a follow-up review pass**

1. **Dedicated `src/portfolio/` quant/test pass** (FR-2 closing). Highest-confidence follow-up in
   this epic: no FR task had `src/portfolio/` as a primary judgment-level target, yet it produced the
   epic's two most consequential CRITICALs *by accident* (via a reconciliation side-instruction). It
   is the one module tracking real capital. Scope: `store.py`, `tracker.py`, `models/portfolio.py`,
   plus the regression tests for rows 1/13/22.
2. **Market-Data Adversarial Reviewer** (FR-5 closing). Genuinely new persona no other reviewer
   approximates: every fixture in `tests/fixtures/responses/option_chain/` was recorded on a calm
   day; parser behavior under circuit-breaker halts, crossed bid/ask, expiry-day degenerate chains
   is unverified. Pairs naturally with row 6's parity work — same fixtures, same session.
3. **Token-economics / context-budget auditor** (FR-1 closing). Cheap, quantifiable, and independently
   corroborated by FR-1's F-W3 (the epic violating its own prompt-length principle): measure the
   >1,500 lines of always-loaded protocol and check whether the mandatory load has crossed the point
   of degrading implementation quality. One session.
4. **Execution-environment / tooling-surface auditor** (FR-1 closing). Test every CLAUDE.md rule
   against what each surface (Claude Code CLI, Cowork subagent, Antigravity) can physically do. Row 4
   (F-C1) plus the fact that *three of six reviews* ran with graph tools deferred or a broken venv
   (FR-1, FR-2, FR-5 all disclosed this) is direct evidence the gap is real and recurring. Partially
   FR-8's territory per FR-1 — fold in there rather than a new pass if FR-8 runs.

**(b) Already covered by an existing role the panel didn't invoke correctly (scope fix, not new persona)**

5. **Security pass over `scratch/` tracked contents + `src/auth/` broad catches** (FR-3.1 closing +
   FR-4 closing, independently converging). This is FR-6's Red-Team persona — the gap is that FR-6's
   attached scope didn't include `scratch/` or the instance-level audit of auth-path suppressions.
   Two reviewers independently naming it is the high-confidence signal, but the fix is a scope
   extension for the existing persona (row 20), not a 7th chair.
6. **Options-strategist weighing absence-of-retry missed-gate risk** (FR-6 closing). The repo already
   defines `options-strategist` and `greeks-analyst` agents; FR-6 correctly identified the question
   as outside its own competence. Route row 18's design note through the existing agent when the
   static-IP constraint is revisited — no new persona needed.
7. **Process/ops root-cause auditor for why docs/plan/README.md goes stale** (FR-3 closing). FR-3
   itself notes this is FR-1's Protocol Reviewer territory, and the root cause is already identified
   (row 15: the file isn't in Step 5a's checklist). Resolved by the fix, not by another pass.

**(c) Not worth pursuing (or defer), and why**

8. **Regulatory/Compliance persona (margin, STT, tax)** (FR-2 §Regulatory flag). Correctly identified
   as covered by nobody — but it becomes load-bearing only when real orders are placed, which is
   hard-blocked today (static IP; `_raise_order_blocked()`). Defer with a trigger condition: mandatory
   before the order-execution block is lifted, waste before then. Log the trigger in DECISIONS.md so
   it isn't rediscovered in production.
9. **Cold-start / new-contributor onboarding persona** (FR-1 closing). Real but low-yield for a
   single-operator repo with two established AI collaborators: the failure it catches (a third party
   can't navigate in) has no current victim, and the highest-value slice (a "start here" entrypoint)
   is a one-paragraph README fix FR-9 can just do, not a review pass.

**Verdict on a genuinely missing 7th persona:** the strongest convergent signal is not a persona but
a **scope hole** — `src/portfolio/` (item 1), named once but backed by the epic's two worst findings.
Among true personas, only the **Market-Data Adversarial Reviewer** (item 2) is both genuinely new
(no existing role approximates it) and attached to a confirmed CRITICAL-severity gap (row 6). If FR-9
funds exactly one new pass, it should be item 1; if it funds a new *persona*, item 2.

---

## Implementation Sequencing (for FR-9)

1. Rows 1–2 first (real capital: portfolio P&L fix + DB backup) — code, tests, code-reviewer gate.
2. Row 8's F12b dead link + row 3's status table — the two navigation fixes that actively misdirect
   sessions today (docs-only commit).
3. Rows 4–5, 11 — one CLAUDE.md/REVIEW.md/module-doc reconciliation pass (docs-only commit).
4. Row 7 — Antigravity handoff candidate (mechanical, many files, unambiguous spec).
5. Row 6 — NEEDS-OPUS-REVIEW quant consultation, then parity test, then BS reference test.
6. Everything WARNING-and-below batched per the actions column; personas §a items scheduled by FR-9.

---

## Closing block

**Persona reviewed as: Chairman.**

**Perspective this synthesis itself did not cover:** an **independent verification auditor for the
synthesis layer**. This document trusts all six reports' factual claims wholesale — not one cited
line number, count, or DB value was re-checked against the repo, and the ranking above is therefore
only as sound as the weakest underlying verification. Worse, the six inputs share correlated blind
spots this method structurally cannot detect: all were written by the same model family under the
same prompt lineage against the same seed-issue list, so a gap *none* of them saw (the very thing the
closing-block mechanism exists to surface) is invisible to a chairman who reads only their prose.
RapidCouncil's design mitigates this with a Stage-2 peer-ranking round between Stage 1 and the
chairman; this epic ran no equivalent — the reviewers never read or ranked each other (except FR-3.1
reading FR-3, and FR-5 reading FR-2). A spot-verification pass over, say, three load-bearing claims
per report (the same discipline FR-1 applied to *its* handed-down facts) is the missing stage.
