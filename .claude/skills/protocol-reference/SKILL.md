# NiftyShield — Protocol Reference Skill

> On-demand reference material split out of the resident `CLAUDE.md` so the auto-loaded protocol carries only what a session needs *before it can act*. Nothing here is optional when it applies — it is
> deferred, not downgraded. **Trigger phrases:** "council file", "council decision", "read the council output", "protocol reference", "quick reference", "where does X live", "hand off to Antigravity",
> "review rules", "what does Step N require". **Load §1 whenever a `docs/council/` file is shared or referenced — that is a mandatory gate, not a lookup.** The other sections are lookups; read only
> the one you need.

---

## Contents

| § | Section | Load when |
|---|---|---|
| 1 | Council Decision Protocol | A council response file is shared or referenced — **mandatory** |
| 2 | Quick reference | You need the canonical path for a doc, table, log, or fixture |
| 3 | AI Collaboration — Antigravity and human review | Planning a handoff, or reviewing Antigravity's work |
| 4 | Rules for any review or handoff | Writing any review, audit, finding, or handoff document |
| 5 | Module `CLAUDE.md` index | You want to know what a module's auto-loaded file covers |

---

## §1 — Council Decision Protocol

When a council response file (`docs/council/YYYY-MM-DD_<topic>.md`) is shared or referenced, follow this parsing and action order — do not treat all three stages equally.

### Reading priority

| Stage | Section header | Role | What to do |
|-------|---------------|------|------------|
| 3 | `## Stage 3 — Chairman Synthesis` | **Authoritative recommendation** | Read this first and fully — this is what gets implemented |
| 2 | `## Aggregate Rankings (Stage 2 Peer Review)` | Peer credibility signal | Use to weight Stage 1 opinions when Stage 3 leaves a nuance unresolved |
| 1 | `## Stage 1 — Individual Responses` | Raw panel opinions | Background context only — do NOT implement from Stage 1 directly |

### Inside Stage 3 — what to extract

1. **Summary Table** (always present at end of Stage 3): canonical before/after for each decision. This is the implementation spec.
2. **Dissenting Notes** section: minority positions that were noted but overruled. Log these in `DECISIONS.md` under "Noted, deferred" — they are first candidates for post-validation testing.
3. **Implementation Sequencing** (if present): lists which docs to update and in what order. Follow it literally.
4. **Additional Rules Surfaced**: supplementary constraints that emerged during review. Treat these as mandatory additions to the relevant plan/strategy doc.

### Mandatory post-read actions

After reading a council file, always:

1. Update `DECISIONS.md` — add a row for each decision in the Summary Table with the council date and topic as the source.
2. Update the relevant plan or strategy doc (named in Implementation Sequencing) — edit it to reflect Stage 3 recommendations, not the original design.
3. Do **not** implement code until `DECISIONS.md` and the strategy doc reflect the council output. The council decision gates implementation.

### Aggregate Rankings — how to interpret

```
- model-A: avg rank 1.0 (4 votes)   ← panel judged this the strongest response
- model-B: avg rank 2.25 (4 votes)
- model-C: avg rank 2.75 (4 votes)
```

The chairman draws heavily on the top-ranked response. If Stage 3 feels thin on a topic, the highest-ranked Stage 1 response is the right place to look for supporting detail. Never use a lower-ranked
response to contradict Stage 3.

Trigger criteria and the request workflow (when to *call* a council, as opposed to how to read one) live in `docs/council/README.md`. The three-condition check itself stays resident in `CLAUDE.md`
Step 2b.

---

## §2 — Quick reference

| What | Where |
|---|---|
| Start-of-task entry point (route to feature / bug, load prompt) | `/work` — `.claude/skills/work/SKILL.md` |
| Graph project ID | `Users-abhadra-myWork-myCode-python-NiftyShield` |
| Project state | `CONTEXT.md` |
| Architecture decisions | `DECISIONS.md` |
| Instrument keys / AMFI codes / API quirks | `REFERENCES.md` |
| SQLite table registry (writer, cadence, purpose per table — check before any DB write) | `DB_REGISTRY.md` |
| Open TODOs + session log | `TODOS.md` |
| Multi-sprint roadmap | `PLANNER.md` |
| Strategy definitions (code) | `src/portfolio/strategies/finideas/` |
| Shared DB connection | `src/db.py` |
| Exception hierarchy | `src/client/exceptions.py` |
| API fixtures | `tests/fixtures/responses/` |
| Live DB | `data/portfolio/portfolio.sqlite` |
| Cron log | `logs/snapshot.log` |
| Run all tests | `python -m pytest tests/unit/` |
| Commit format | `.claude/skills/commit/SKILL.md` |
| Session close / protocol audit | `.claude/skills/session-close/SKILL.md` |
| Python review checklist | `REVIEW.md` |
| Logging standard (entrypoint rule, line shape, event naming) | `LOGGING.md` |
| Telegram value/table formatting standard (decimals, alignment, sign display) | `FORMATTING.md` |
| Bug registry (confirmed defects) | `docs/bugs/bugs.md` |
| Domain glossary (options terms, strategy names, conventions) | `docs/GLOSSARY.md` |
| Backtest → paper → live pipeline plan | `BACKTEST_PLAN.md` |
| Council trigger criteria + workflow | `docs/council/README.md` |
| Completed council decisions | `docs/council/YYYY-MM-DD_<topic>.md` |
| Antigravity operating protocol | `ANTIGRAVITY.md` |
| Claude–Antigravity workflow division | `docs/antigravity/ai_collaboration_plan.md` |
| Which surface (Claude Code / Cowork / Antigravity) + model to use, by job type | `docs/plan/full-repo-review/findings/FR-8_practitioner-devex.md` |

---

## §3 — AI Collaboration — Antigravity and human review

Claude plans, runs graph queries, owns council decisions, and runs the mandatory `@code-reviewer` gate. Antigravity does autonomous multi-file implementation, TDD loops, and commit execution — its
operating rules (and its `multi_replace_file_content` / `write_to_file` edit tools) are in `ANTIGRAVITY.md`.

Antigravity may have authored uncommitted or recently committed code. Review it with the real `@code-reviewer` agent against `git diff HEAD` — its own persona review is approximate and does not load
`REVIEW.md`.

- Workflow division by phase: `docs/antigravity/ai_collaboration_plan.md`
- Job-type → surface/model routing: `docs/plan/full-repo-review/findings/FR-8_practitioner-devex.md`

### Handoff prompt — the four mandatory elements

Per `docs/antigravity/ai_collaboration_plan.md` §4 Phase B. The `handoff-antigravity` skill produces this; the elements are listed here so a reviewer can check one.

1. **Reading list** — explicit paths Antigravity must read before writing any code. `CONTEXT.md` is mandatory in every handoff; add `BACKTEST_PLAN.md`, `DECISIONS.md`, the relevant module `CLAUDE.md`
   as the task requires.
2. **Objective** — one sentence stating what to build.
3. **Pointers** — explicit file paths or graph queries. Do not rely on Antigravity to discover scope on its own.
4. **Boundaries** — files that must not be touched, off-limits patterns, financial-gate reminders.

Do not paste code into the handoff prompt.

### Verifying a Phase Completion Output

- `files_changed` — cross-check against `git diff --name-only HEAD~1`.
- `tests_added` / `tests_passing` — cross-check against the `pytest --tb=no -q` summary line and `grep -c "def test_"` on the new test file(s).
- `commit_sha` — the load-bearing check: confirm it matches the tip of `git log --oneline -1` before treating the phase as closed.

If verification fails, Claude opens a fix session with the failure details. Note the practical consequence of FR-1's F-C1: if the fix requires the `code-reviewer` / `test-runner` gates, that fix
session must run them directly in Claude Code — a re-handoff to Antigravity does not satisfy them, because Antigravity cannot spawn `.claude/agents/*`.

Antigravity's scope ceiling is 3–5 files; beyond 5, decompose into sub-phases with separate handoffs and commits before delegating.

---

## §4 — Rules for any review or handoff

Promoted from the full-repo-review epic per its FR-1 finding that these three generalize beyond the epic itself (`docs/plan/full-repo-review/findings/FR-1_protocol-reviewer.md` Step 5).

1. **Rate severity by mission impact, not by finding volume.** Severity is tied to actual business impact (does this expose capital, does this cost a real decision-quality point) — not to how many
   findings make a review look thorough. A padded list of INFO-level nitpicks is as useless as a review that rubber-stamps everything.
2. **Verify your own citations before asserting them.** Before citing a file, line, or `DECISIONS.md` entry as "live" or "current," check it against the repo — do not trust a prior pass or your own
   memory of the codebase.
3. **Every review or handoff states at least one perspective it did not cover** — write "none identified" explicitly if genuinely nothing comes to mind; never omit the section.

---

## §5 — Module `CLAUDE.md` index

Each file auto-loads when you work inside that directory — you never need to read one manually. This index says what each covers, so you can tell whether a task will pull it in.

| Module | What its `CLAUDE.md` covers |
|---|---|
| `src/portfolio/` | Leg/Trade distinction, Decimal invariant, `apply_trade_positions()`, strategy_name constraint |
| `src/mf/` | Transaction ledger model, AMFI source, Decimal TEXT invariant, MFHolding location |
| `src/client/` | BrokerClient protocol rule, implementations (2 built + 1 variant + 1 planned), blocked methods, two-token constraint |
| `src/notifications/` | Non-fatal contract, `build_notifier()` → None, HTML parse_mode, Instrument Label Formatting |
| `src/dhan/` | LTP via Upstox batch, two-phase fetch, classification config, double-count prevention |
| `src/paper/` | Paper-trading engine — `PaperStore` tables, `PaperTracker` P&L, fill simulator, `TradeState` enum |
| `src/nuvama/` | Bonds + options readers (pure parse + aggregate), `NuvamaStore` SQL-layer aggregation |
| `src/gamma/` | Near-Expiry Gamma Buy scaffolding — frozen models + `GammaStore` |
| `src/strategy/` | `PaperStrategy` protocol, `StrategyMonitor` daemon, `SignalTrackV1` signals paper-track execution layer, `signal_exit.py` pure evaluator |
