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

**As-built (SHA `<—>`):** _record: resident `CLAUDE.md` line count before/after, the
`project_docs` token bucket before/after (per-turn), the resident/moved split actually
chosen, and confirmation the council-trigger path still fires._

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

**As-built (SHA `<—>`):** _record: per-file line count before/after, the auto-inject token
saving per directory-touch, and where each moved block landed._

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

**As-built (SHA `<—>`):** _record: the close-out's token cost before (fork) vs. after
(transcript-reading subagent), on a matched before/after session pair; confirm the compact
block content is unchanged._

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
