# Token Efficiency — Fixed Overhead — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: set `SHA:` on the task line + tick the box, update the epic `README.md`
> Stories status column, add one line to `TODOS.md`, and record the measured token delta in
> that task's As-built here. See `docs/plan/README.md` §Conventions.

---

## FIX-1 — Skill-ify `CLAUDE.md`

**Files to change / create:**
- `CLAUDE.md` — remove the reference material, leave the load-bearing protocol + a pointer
  to the new skill
- `AGENTS.md` — re-mirror the trimmed `CLAUDE.md` in full (per `agents-md-mirrors-claude-md`
  memory — standalone, never a stub)
- `.claude/skills/protocol-reference/SKILL.md` — new; holds the moved material
- `.claude/skills/protocol-reference/` — any supporting file the skill splits out

**Before any code:**
- Read `CLAUDE.md` in full and `docs/plan/full-repo-review/findings/FR-8_practitioner-devex.md`.
- `ls .claude/skills/` and read one existing `SKILL.md` for the house format.
- Run `token_audit.py` on 2–3 recent sessions and note the current `project_docs` bucket
  number — that is the before figure.

**What to implement:**

1. Decide the resident / moved split. **Stays resident** (a session needs it before it can
   act, every time): the "Rule 0 — Graph before Read" decision tree, "Rule 1 — Bash Output
   Discipline", the "Pre-Task Protocol" Steps 0–5 skeleton (one or two lines each, pointing
   to the skill for detail), the "Agent AutoTrigger Rules" table, the "Python Standards" +
   "Logging standard" sections, and the "Module CLAUDE.md files" one-liner that says they
   auto-load. **Moves to the skill:** the full "Quick reference" table, the full "Council
   Decision Protocol" (reading priority, Stage-3 extraction, post-read actions), the "AI
   Collaboration — Antigravity and human review" prose, "Rules for any review or handoff",
   and the long-form explanation under each Step.
2. Write `protocol-reference/SKILL.md` with a description that triggers it on: a council file
   being referenced, a handoff/review being planned, "what does Step N require", the
   quick-reference lookups. Structure it so a session can load just the section it needs.
3. Trim `CLAUDE.md`. Every removed block leaves a one-line stub: what it covered + "full
   detail: invoke `protocol-reference`". Keep the file's own section order.
4. Re-generate `AGENTS.md` as the full mirror of the new `CLAUDE.md` (same content, its own
   autoload framing per the existing file).
5. Verify the council-trigger path still works end to end: a session that references a
   `docs/council/` file must still be routed through the reading-priority order — if that was
   only encoded in `CLAUDE.md` prose, the skill description must make it fire.

**Tests:** none (`.md` only). Run `python -m pytest tests/unit/ --tb=no -q` to prove nothing
imported a path that moved, plus `check_md_line_length` at commit.

**Commit:** `refactor(protocol): move CLAUDE.md reference material to a skill`

**As-built (SHA `41ac31e`):**

**Measured delta.** `project_docs` bucket (`token_audit.py`, session `3dcf60ee`): **12,554 →
9,556 tokens, −2,998 (−23.9%)**. The bucket is a deterministic `chars/4` estimate over the
on-disk `CLAUDE.md` + `AGENTS.md` + `MEMORY.md`, so it is the same number in every session and
the before/after is noise-free (verified identical at 12,554 across sessions `ed6e79b9`,
`2202a6bc`, `3dcf60ee` before the change).

| File | Lines before | Lines after | Chars before | Chars after |
|---|--:|--:|--:|--:|
| `CLAUDE.md` | 409 | 309 | 22,907 | 16,805 |
| `AGENTS.md` | 474 | 377 | 27,149 | 21,153 |
| `.claude/skills/protocol-reference/SKILL.md` | — | 196 | — | 10,296 |

**Target missed, stated honestly.** The plan set a ≤200-line target for the resident
`CLAUDE.md`; the delivered file is 309. The 200 figure was a pre-work estimate made before
auditing what the story's own spec marks "stays resident" — Rule 0, Rule 1, the Steps 0–5
skeleton, the AutoTrigger table, Python Standards and the Logging standard together account
for ~270 lines on their own. Reaching 200 would have required dropping one of those, i.e. a
real gate, which the story's hard constraints forbid. 309 is the floor without a gate loss.

**Deliberate non-optimisation.** The file keeps its existing ~95-char wrap rather than being
reflowed to fill-to-200. Reflowing would have cut the line count to roughly half with **zero**
token saving — the line-count metric would have looked far better while the actual cost stayed
flat. Line counts here are therefore directly comparable to the before figures.

**Resident / moved split actually chosen.** Moved to the skill, as five numbered sections:
§1 Council Decision Protocol, §2 Quick reference, §3 AI Collaboration (incl. the four handoff
elements and Phase Completion Output verification, which were previously only in FR-8),
§4 Rules for any review or handoff, §5 Module `CLAUDE.md` index. Stayed resident: Rule 0,
Rule 1, Step 1 (its conditional-load list converted from bullets to a table), Python
Standards, Logging standard, Steps 2/2b/3/3b/4/5a–5d, the AutoTrigger table. Step 3b's
prose "when to choose" bullets became a two-row table; the long-form rationale under Steps 1,
2b, 3b, 4, 5 was compressed, not relocated.

**No gate dropped — verified mechanically.** Every backtick-quoted `.md` / `.py` / path
reference in the pre-change `CLAUDE.md` was checked against (new `CLAUDE.md` + skill). Four
did not match: `prompt.md` and `*_tasks.md` (generic filenames from the `/work` prose, not
paths — `work/SKILL.md` carries the real routing), the `#when-to-trigger-the-council` anchor
(dropped deliberately — the three-condition check is now stated verbatim resident and is the
sole source of truth, so pointing at the anchor would undercut it), and the FR-7 citation in
Step 5a, which **was** a real loss and has been restored in both files. Section-header audit:
all twelve pre-Step-5 sections resident, four reference sections in the skill, none missing.

**Council-trigger path fires — three independent routes.** (1) Step 2b carries an explicit
imperative: "Reading a council file that already exists is a separate mandatory gate — invoke
`protocol-reference` §1 before acting on any `docs/council/` output." (2) The resident
reference table is followed by "**§1 is a gate, not a lookup**". (3) The skill registered in
the session's skill listing on creation, with trigger phrases "council file", "council
decision", "read the council output". Note for future skill work: this repo's `SKILL.md` files
carry **no YAML frontmatter** — discovery is by H1 plus the resident pointer, so the resident
imperative is load-bearing and must not be trimmed away later.

**Skill-load trade is net positive — confirmed, not assumed** (the `prompt.md` "Perspectives
not covered" item required this). The skill costs 2,574 tokens when loaded, once, and only in
sessions that reference a council file or need a quick-reference lookup. A session that never
loads it saves the full 2,998. A session that loads it once still nets +424 on the first turn
alone and keeps saving on every turn after, since the resident set is re-read each turn while
the skill is not. Positive in both cases.

**Scope addition beyond the spec.** `md-organize` Step 7 documents three protocol mirrors, not
one. The new skill was therefore also mirrored to `.agents/skills/protocol-reference/SKILL.md`
(byte-identical) — without it, `AGENTS.md`'s pointer would dangle on the Antigravity surface
and the "no gate dropped" constraint would hold for Claude but not Antigravity. Confirmed the
repo convention that `AGENTS.md` and `.agents/skills/**` reference `.claude/` paths, and
normalised an initial mistake where this task wrote `.agents/` paths into `AGENTS.md`.
`.claude/skills/work/SKILL.md` (the third mirror) needed no change — Step 1's routing
semantics are unchanged.

**Gates run.** `python -m pytest tests/unit/ --tb=no -q` → 3074 passed, 2 skipped.
`pre-commit run md-line-length --files CLAUDE.md AGENTS.md` → Passed (longest line 190 in
both; four over-length lines introduced during the rewrite were fixed by shortening table
cells and lifting the `DB_REGISTRY.md` detail into a sentence below the table, per
`md-organize` §5a — no fact dropped). Structural mirror diff of section headers shows only the
three intended deltas: the H1 suffix, the reference-section heading (Antigravity has no
skill-invocation mechanism), and the `Antigravity Reference (supplementary)` section.

---

## FIX-2 — Trim the heaviest module `CLAUDE.md` files

**Files to change / create:**
- The 2–3 largest `src/*/CLAUDE.md` (measure first — likely `src/notifications/CLAUDE.md`,
  `src/paper/CLAUDE.md`, `src/client/CLAUDE.md`)
- Where deep detail is relocated: the relevant module docstring, or a new module `NOTES.md`
  (not auto-injected)

**Before any code:**
- `wc -l src/*/CLAUDE.md` — pick the largest.
- Run `token_audit.py` on a session that touched one of those modules; note the
  `project_docs` contribution from the module block (the before figure).
- Read the target module's code to judge which statements are load-bearing invariants
  (Decimal-as-TEXT, non-fatal contract, protocol rules a caller must obey) vs. reference
  narration (history, worked examples, "why it exists" prose).

**What to implement:**

1. For each target file, keep resident: the invariants, the contracts a caller must not
   break, the "read this before touching X" pointers. Move out: history, elimination trails,
   worked examples, multi-paragraph rationale — into the module docstring or `NOTES.md`, with
   a one-line pointer left in the `CLAUDE.md`.
2. Do not change any invariant's wording — this is relocation, not a rewrite.
3. Keep each file's section headers so existing cross-references (`§"Instrument Label
   Formatting"`, `§"Escaping Helpers"`) still resolve.

**Tests:** none (`.md` only). Full unit gate to prove no import broke; `check_md_line_length`
at commit.

**Commit:** `refactor(<module>): slim CLAUDE.md to invariants, relocate detail`
(one commit per module if they are done in separate sessions — never bundle).

**As-built (SHA `ce45719`):**

**Targets were picked by measurement, and the spec's guess was half wrong.** `stories.md`
predicted `notifications` / `paper` / `client`; `wc -c` puts `portfolio` second and `paper`
fourth, so the three trimmed are **`notifications`, `portfolio`, `client`**. `paper` (980 tok)
was left alone — its content is almost entirely invariants (the `paper_` prefix guard, the
Decimal-as-TEXT rule, the `total_pnl` write-time check), with nothing worth relocating.

**Measurement method.** `token_audit.py` deliberately excludes module `CLAUDE.md` from its
`project_docs` bucket — its own docstring says detecting which module files fired for a given
session would need per-turn tool-argument inspection the tool does not do. So the before/after
here is that tool's own estimator (`_estimate_tokens`, chars/4) applied directly to each file.
That is the same arithmetic `project_docs` uses, just pointed at the module files, and it is
the only honest source for this figure short of extending the tool.

| File | Before | After | Δ | Lines |
|---|--:|--:|--:|---|
| `src/notifications/CLAUDE.md` | 3,086 | 1,998 | **−1,088** | 195 → 140 |
| `src/portfolio/CLAUDE.md` | 1,112 | 930 | **−182** | 83 → 76 |
| `src/client/CLAUDE.md` | 1,062 | 877 | **−185** | 100 → 80 |
| **Total auto-injected** | **5,260** | **3,805** | **−1,455 (−28%)** | 378 → 296 |

**Per-directory-touch saving.** A module `CLAUDE.md` is injected the first time a session
touches that directory and is then resident in the prefix for every subsequent turn. So the
saving is per-turn, not per-session: a `src/notifications/` session drops **1,088 tokens off
every turn after the first touch**, `src/portfolio/` 182, `src/client/` 185. A session touching
all three saves 1,455/turn. Against the epic Baseline's ~55K first-turn resident-doc figure
(`system_prompt` + `project_docs`), that is ~2.6% for the three-module case and ~2% for the
common `src/notifications/` case — small next to `subagent_internal`, but paid on every turn of
every session in the module, which is exactly the cost class this story targets.

**Total on-disk text went up slightly, and that is the intended trade.** The three new
`NOTES.md` files are 1,782 / 459 / 506 tokens; adding their headers and pointers means
`notifications` now holds 3,780 tokens across two files where it held 3,086 in one. Nothing was
deleted — the relocation is the whole point, and only the `CLAUDE.md` half is paid per turn.

**Where each moved block landed** (all to a new non-auto-loaded `NOTES.md` in the same
directory, each leaving a one-line pointer in `CLAUDE.md`):

- `src/notifications/NOTES.md` — the MarkdownV2 migration history and the stale `<pre>`-wrap
  correction note; the `DELTA_WARN` origin of the escaping bug class; the full
  `_BASELINE_UNESCAPED` allowlist mechanics and the MD-3/4/7 audited-call-site paragraph; the
  four value formatters and three table builders with full signatures, examples and rationale;
  the emoji-presentation-variant alignment risk; `STRATEGY_LABELS` / `LEG_ROLE_LABELS`; the
  `telegram-leg-labels` origin line.
- `src/portfolio/NOTES.md` — why `overlay_coverage.py` sits in this directory; the
  `apply_trade_positions()` call-site list; the `models.py` field enumeration and the strategy
  registry (both `CONTEXT_TREE.md`-shaped material).
- `src/client/NOTES.md` — the implementations table; the per-sub-protocol method split; the
  `MockBrokerClient` setup API code block; the `upstox_market.py` legacy narration.

**What deliberately stayed resident.** Every invariant and every contract a caller must not
break, verbatim — this was relocation, not a rewrite. `notifications`: the non-fatal `send()`
contract including the REVIEW.md G5 inline-comment rule (`REVIEW.md` line 717 cites this file
by name), `build_notifier()` returning `None`, `TELEGRAM_MESSAGE_BUDGET`, the no-auto-escape
boundary, both escaping helpers, BUG-038's known gap, the guard test's "fix the call site, do
not add a baseline entry" rule, the formatter-returns-unescaped contract, the `build_leg_table`
1dp locked-in exception, and the whole Instrument Label Formatting section. `portfolio`: the
Decimal-as-TEXT invariant, the `trades.strategy_name` silent-failure constraint, the
`apply_trade_positions` behaviour contract, `ensure_leg`, `store.py`'s SELL-prices-excluded
rule. `client`: the no-concrete-imports-outside-`factory.py` cardinal rule, the blocked-methods
table, the exception hierarchy with its retryable/terminal split, the two-token constraint.

**Cross-references verified, none dangling.** All section headers were kept, so
`§"Instrument Label Formatting"` (root `CLAUDE.md` line 80, `AGENTS.md` line 104,
`CONTEXT_TREE.md` line 182) and `§"Value Formatting & Table Builders"` still resolve;
`FORMATTING.md` lines 15/172, `REVIEW.md` line 717 and `AGENTS.md` lines 362/368 all point at
sections that survived. Unlike FIX-1, no `.agents/` mirror work was needed — module docs have
no `src/*/AGENTS.md` counterpart, and `.agents/` carries only skill mirrors.

**Gates run.** `python -m pytest tests/unit/ --tb=no -q` → 3074 passed, 2 skipped (proves no
import referenced a moved path). `md-line-length` does not cover `src/**` (it is scoped to root
+ `docs/plan` + `docs/bugs`), and the pre-commit run confirmed it skipped; no `.py` in the diff,
so `code-reviewer` was correctly not triggered — the task line is `Review: none`.

---

## FIX-3 — `session-close` without the context clone

**Files to change / create:**
- `.claude/skills/session-close/SKILL.md`
- Any `.claude/skills/session-close/` support file it references

**Before any code:**
- Read `.claude/skills/session-close/SKILL.md` in full, and the section of the root
  `CLAUDE.md` (Step 5d) that spawns it.
- Confirm how a subagent can be handed a transcript path: the parent knows its own session
  transcript location, and can pass it in the spawn prompt. Verify a non-`fork` subagent can
  read that file.
- Run `token_audit.py` on a recent session that ran `session-close`; note the
  `subagent_internal` figure attributable to the close-out fork (the before number).

**What to implement:**

1. Change Step 5d of the root `CLAUDE.md` (or wherever the spawn is defined): instead of
   "spawn a `fork` subagent", spawn a fresh `general-purpose` (or a dedicated
   `session-auditor`) subagent and pass it the transcript path + the `token_audit.py`
   invocation. The subagent reads the transcript from disk — it does not inherit the
   conversation.
2. Rewrite `SKILL.md` so its steps operate on a transcript file argument, not on "this
   session" implicitly: Step 1 reads the transcript, Steps 2–4 analyse it, Step 5 emits the
   compact block. Keep the compact block format identical.
3. Fold `token_audit.py` into the skill: the efficiency section now quotes real per-bucket
   numbers, not estimates.
4. Keep the "never a legitimate skip" rule and the Step 5 trivial-clean-report fallback.
5. Leave Step 4b's `suggestions.md` logic as-is here — SWEEP-7 rewrites it and will rebase
   onto this version.

**Tests:** none (`.md` only). Run the redesigned close-out on one real session to confirm it
still produces the block; that run is the after measurement.

**Commit:** `refactor(session-close): read transcript by path, drop the context fork`

**As-built (SHA `<pending>`):** `CLAUDE.md` §5d and its `AGENTS.md` mirror now spawn a fresh
`general-purpose` subagent with the transcript path, never `fork`. `SKILL.md` (and its
`.agents/` mirror) Step 1 rewritten to extract the action log via bounded `jq` over the
transcript + `git log`, not conversation recall; a new §3c-2 folds `token_audit.py` into the
TOKEN EFFICIENCY section so its numbers are real per-bucket figures, not chars/4 estimates.

Measured on session `ed6e79b9` (194KB transcript, docs-only FIX-2 task): the original
`fork`-based close-out cost **116,375** `subagent_internal` tokens (61% of that session's
191,235-token total). Running the redesigned skill as a fresh subagent against the same
transcript path cost **52,523** total tokens (10 tool uses: `jq` action-log extraction,
`git log`, `token_audit.py`, analysis) — a **~55% drop**, and the compact block it produced
matches the format and content of the original. The fork's median cost across 9 recent
sessions was ~254K (range 116K–380K); the saving scales further on longer sessions since a
`fork` clones the whole conversation while the redesigned skill's cost is bounded by
extraction, not conversation length.

---

## FIX-4 — Strip fingerprint bloat from MCP graph results

**Files to change / create:**
- A thin wrapper the session calls instead of the raw MCP tool — decide the shape in step 1
  (a `scripts/dev/` helper, or a documented "always pipe through `jq 'del(.fp,.sp,.bt)'`"
  note, or a skill helper). Prefer the lowest-machinery option that actually gets used.
- `tests/unit/scripts/dev/` test if the wrapper is a script
- An upstream issue against the `codebase-memory-mcp` project

**Before any code:**
- Capture one raw `get_code_snippet` and one `search_graph` result. Identify every field the
  model never consumes (`fp`, `sp`, `bt`, and any other opaque blob). Count the tokens.
- Check whether the MCP server exposes a "compact" / "fields" parameter already — if it does,
  FIX-4 is just "always pass it" + a doc line, no wrapper.

**What to implement:**

1. If the server has a field-filter param: document "always use it" in the
   `codebase-memory` skill and the `CLAUDE.md` Rule 0 tool list; done.
2. Else: build the thinnest wrapper that strips the unused fields, and point Rule 0's
   "Need a symbol?" step at it.
3. File the upstream issue: raw responses carry ~N tokens of consumer-unusable fingerprint
   data per call; request a compact mode. Link it in the As-built.

**Tests (if a wrapper script is added):**
- `test_wrapper_strips_fingerprint_fields` — `fp` / `sp` / `bt` absent from output
- `test_wrapper_preserves_source_and_signature` — the fields the model needs survive

**Commit:** `chore(graph): strip unused fingerprint fields from MCP snippet results`

**As-built (SHA `<—>`):** _record: tokens per call before/after, a typical per-session
`get_code_snippet` + `search_graph` call count from the Baseline, the resulting per-session
saving, and the upstream issue link._
