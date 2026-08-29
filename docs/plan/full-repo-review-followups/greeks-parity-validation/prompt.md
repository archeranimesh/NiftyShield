Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/full-repo-review-followups/greeks-parity-validation/tasks.md` and find the first unchecked box. That is your
**only task** for this session. Do not look at any other unchecked item. One task.
Complete it fully. Stop.

**Origin:** Spawned from `docs/plan/full-repo-review/findings/FR-7_synthesis.md` (Chairman
Synthesis), FR-7 row 6 (CRITICAL, contested — see D1) — FR-5 GREEKS-1/PARITY-1, FR-2 F7. Independently re-verified against the live repo before this story was
created — see FR-9's commit message for the verification method.

No independent correctness check exists anywhere in the repo for Greeks or option-chain data:
confirmed zero references to put-call parity or a Black-Scholes reference model anywhere in `src/` or `tests/` (`grep -rli "put.call.parity|black.scholes|black_scholes|bs_price"` returns nothing).
Upstox's own feed is the uninspected ground truth.
FR-7's chairman keeps this CRITICAL over FR-2's WARNING framing because the epic's own evidence proves the consequence:
this absence is the confirmed reason the portfolio-pnl-critical-fix findings (row 1) survived undetected until manual DB reconciliation.
FR-5 tags this NEEDS-OPUS-REVIEW: tolerance bands and reference-model assumptions need a quant judgment call before implementation, not a mechanical fix.

**Surface & Model: Claude Code only, Opus for the council consult (`options-strategist`/`greeks-analyst`).** Cannot be an Antigravity handoff at any point:
Step 2b council checkpoints are Claude's responsibility and Antigravity never triggers the council (root CLAUDE.md's AI Collaboration section).
This story's own Task 1 is explicitly "do not implement directly" —
the entire first phase is a live council consult, which only exists on the Claude Code / Claude surface, not as an Antigravity-executable step.

**Pre-implementation gate:** State in one sentence which task, which files, which test file.
Do not write any code until this plan is stated.

**Story spec:** Read the matching story in `docs/plan/full-repo-review-followups/greeks-parity-validation/stories.md` for the full spec.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first using the
graph. Order: `git log --oneline -10 <file>` → `search_graph`/`get_code_snippet` →
`trace_path` → `search_code` → `sed -n` → `Read` (state why the graph was
insufficient).

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` and `search_graph('<EnumName>')` first — never write
a `_make_*`/`build_*` fixture helper from memory.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing.

**Financial logic commit — real `@code-reviewer` subagent mandatory** per CLAUDE.md's Agent AutoTrigger Rules (this touches P&L / Decimal / broker-adjacent paths).
Resolve any CRITICAL/ERROR finding before committing.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not
draft it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.
