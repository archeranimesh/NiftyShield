# Token Efficiency — epic index

> Cut the per-session token cost of running NiftyShield through Claude Code. Three stories: a
> measurement tool first, then the fixed-overhead drivers (resident `CLAUDE.md`, the
> session-close context clone, MCP result bloat), then a full sweep of the ~40-row
> `suggestions.md` backlog into structural fixes or tooling enforcement. It is one epic
> because every fix in stories B and C must quote a real before/after number from the story-A
> tool — no change ships on a hand-wave.

## Why this epic exists

Spawned from a token audit Animesh asked for on 2026-09-01 after the ROLL-7 session
(`telegram-markdown-migration/strategy-rollout/` ROLL-7). That one task — a ~440-line diff —
cost roughly 740K tokens account-side: ~260K in the main loop, ~485K in subagents, of which
the `session-close` fork alone was ~285K because a fork clones the entire conversation.

Two structural drivers, neither addressed anywhere:

- **Per-turn fixed overhead.** Every turn re-sends ~15–20K of tool schemas plus the project
  `CLAUDE.md` (~400 lines of mandatory protocol), the global `CLAUDE.md`, `MEMORY.md`, and any
  module `CLAUDE.md` that auto-injects when a `src/` directory is touched.
- **Mandatory subagent fan-out.** The protocol requires `test-runner` after edits (run 3× in
  the ROLL-7 session as the diff grew), `code-reviewer` before commit, and a `session-close`
  fork at the end. Five sub-sessions for one task.

And the feedback loop that should have caught this is write-only. `suggestions.md` is
maintained by `.claude/skills/session-close/SKILL.md` Step 4b: it logs behavioural nudges
keyed by root cause, increments a per-slug `Count`, and sorts. It has no escalation —
`reread-file-already-in-context` sits at Count 13 and `pytest-inlined-not-test-runner` at
Count 7 across a month of sessions, and nothing ever converts a high-count slug into
remediation work. It also never proposes structural fixes, because it only pattern-matches
turn-by-turn actions, not fixed overhead.

## Baseline

Measured with `scripts/dev/token_audit.py` (MEAS-1, commit `79effcd`) over five recent
sessions spanning the range the epic cares about — a code+docs task with full subagent
fan-out, a plain code+docs story, a query-only diagnostic session, and two `/work` docs
restructures. All figures are account-side tokens (main loop + subagent-internal), rounded
to the nearest thousand.

| Bucket | `3dcf60ee` ROLL-7 | `5b1c99ee` TG-story | `d5d36b77` diag-only | `1c878711` RDO-17.7 | `724f9ef6` RDO-17.6 | Median |
|---|--:|--:|--:|--:|--:|--:|
| `subagent_internal` | 386K | 367K | 248K | 815K | 337K | 367K |
| `assistant_text` | 281K | 153K | 102K | 299K | 225K | 225K |
| `tool_results:Read` | 45K | 32K | <1K | 12K | 67K | 32K |
| `tool_results:Bash` | 27K | 24K | 32K | 35K | 14K | 27K |
| `system_prompt` (first-turn cache write) | 43K | 42K | — | 44K | 43K | 43K |
| `project_docs` (`CLAUDE.md`+`AGENTS.md`+`MEMORY.md`, on-disk est.) | 13K | 13K | 13K | 13K | 13K | 13K |
| `subagent_reports` | 3K | 3K | 2K | 5K | 1K | 3K |
| **TOTAL** | **807K** | **658K** | **397K** | **1,229K** | **703K** | **703K** |

Sessions: `3dcf60ee` / `5b1c99ee` / `d5d36b77` — 2026-09-01; `1c878711` / `724f9ef6` —
2026-08-29. `token_audit.py` counts `system_prompt` and `project_docs` as the one-time
first-turn cache write, not the reduced-rate re-read every subsequent turn — so a long
session's true resident-doc cost is higher than the row shows, and the `d5d36b77` dash is a
resumed session with no first-turn write of its own.

### Largest avoidable items

**Mandatory subagent fan-out is the dominant cost** — `subagent_internal` is the biggest
bucket in every session (median 367K, ~50% of the median session), and the `session-close`
fork is the worst single offender because a `fork` clones the entire conversation: in the
ROLL-7 session that started this epic the hand audit put the whole task at ~740K account-side
with the `session-close` fork alone ~285K of it. `fixed-overhead/` FIX-3 (run `session-close`
as a path-reading subagent, not a fork) and a review of how often `test-runner` re-fires
attack this row directly.

**`assistant_text` (median 225K) is inflated by re-derivation** — re-reading files already in
context (`reread-file-already-in-context` at Count 13 in `suggestions.md`), re-stating
codebase state that `CONTEXT.md` already carries, and verbose turn-by-turn narration.
`suggestions-sweep/` owns this.

**`tool_results:Read` (median 32K, up to 67K) is whole-file reads that Rule 0 already bans** —
graph queries and `sed` ranges would cut most of it; `fixed-overhead/` and the Rule 0 hook
tuning in `suggestions-sweep/` share it. The resident-doc buckets (`system_prompt` +
`project_docs`, ~55K first-turn and re-read every turn after) are the target of the
aggressive `CLAUDE.md` restructure in `fixed-overhead/` FIX-1.

## Scope decisions

Confirmed with Animesh, 2026-09-01:

- **Aggressive `CLAUDE.md` restructure.** Move reference tables, the Council Decision
  Protocol, and the AI-collaboration prose into an on-demand skill; keep only the load-bearing
  protocol resident. Not a conservative in-place trim.
- **Full sweep of `suggestions.md`.** Every one of the ~40 rows is clustered and then fixed
  structurally, enforced by a hook/config, or explicitly accepted as won't-fix with a reason —
  none are left to keep recurring.
- **`session-close` redesigned, not kept.** It runs as a subagent that reads the transcript
  file by path, not a full-context `fork`. The redesign task must measure the actual saving on
  a before/after session pair, the way the 2026-09-01 audit did.
- **Every fix quotes a measured delta.** See Cross-cutting constraints.

## Stories

| Story | Purpose | Status | Depends on | Closing SHA |
|---|---|---|---|---|
| `measurement/` | `token_audit.py` — attribute a session's tokens by bucket; establish the baseline every later task measures against | ✅ Done | — | 79effcd |
| `fixed-overhead/` | Skill-ify `CLAUDE.md`, trim module `CLAUDE.md` files, redesign `session-close` off the fork, strip MCP result bloat | ⬜ Not started | `measurement/` | — |
| `suggestions-sweep/` | Cluster all ~40 `suggestions.md` rows; fix / enforce / accept each; make Step 4b self-draining | ⬜ Not started | `measurement/` | — |

Status: ⬜ Not started · 🔄 In progress · ✅ Done. This column is the epic's progress view —
per-task checkboxes live only in each sub-story's `tasks.md`.

Story order: `measurement/` first (its tool is a hard prerequisite). `fixed-overhead/` and
`suggestions-sweep/` both depend only on `measurement/`, not on each other — a session may
pick up the first unchecked task in either once `measurement/` is done, but must finish one
task and stop.

## Cross-cutting constraints

- **Every task states its measured token delta.** Each `fixed-overhead/` and
  `suggestions-sweep/` task's As-built in `stories.md` records a real before/after number from
  `token_audit.py` — either a per-turn resident-token drop, a per-session subagent-token drop,
  or a per-call tool-result drop times a typical calls-per-session count. A task that cannot
  be measured says so explicitly and explains why (e.g. a pure protocol-text clarification).
- **No behaviour regression in the protocol.** Slimming `CLAUDE.md` or amending an AutoTrigger
  rule must not drop a real gate. Anything moved out of the resident file goes into a skill or
  hook that still fires when it matters — `check_story_structure.py`, the `commit` skill's
  gates, and the `@code-reviewer` / `@greeks-analyst` / `@roll-validator` AutoTriggers all
  stay enforced.
- **Hooks warn, never block.** New `PreToolUse` hooks from `suggestions-sweep/` follow the
  existing `.claude/hooks/` convention — they print guidance to stderr and exit 0. The
  decision stays with the session.
- **`suggestions.md` `Count` is skill-owned.** No task hand-edits the `Count` column; the
  sweep changes how Step 4b maintains the file, and seeds rows, but the running tally stays the
  skill's to write.

## Supersession / coordination

- **`full-repo-review/` FR-8 (`docs/plan/full-repo-review/findings/FR-8_practitioner-devex.md`)**
  — the job-type → surface/model routing guide. `fixed-overhead/` FIX-1 touches the same
  practitioner-experience surface; cross-check FR-8 before moving protocol text so the two do
  not contradict each other on which model runs what.
- **`.claude/skills/session-close/SKILL.md`** is touched by both `fixed-overhead/` FIX-3 (how
  it runs) and `suggestions-sweep/` SWEEP-7 (its Step 4b escalation logic). FIX-3 lands first
  (story order); SWEEP-7 rebases its edit onto the redesigned skill.
- **`.claude/skills/commit/SKILL.md`** is touched by `suggestions-sweep/` SWEEP-4 only.
- The `technical-debt/` list is the destination for SWEEP-7's escalated slugs — its
  "fix only when already in the file" convention is deliberately kept; escalated
  token-efficiency items are the exception and are marked as standalone-actionable in their
  `DEBT-*` line.

## Epic done when

- **`measurement/`** — `scripts/dev/token_audit.py` attributes any session transcript's tokens
  to system-prompt / `CLAUDE.md` / per-tool result / subagent-report / subagent-internal
  buckets and prints the compact table; `README.md` carries a Baseline section with real
  numbers from 4–5 recent sessions.
- **`fixed-overhead/`** — the resident `CLAUDE.md` is under the target line count with its
  reference material in an on-demand skill and `AGENTS.md` mirrored; the largest module
  `CLAUDE.md` files are trimmed; `session-close` runs without cloning context; MCP snippet
  results no longer carry fingerprint fields. Every task's As-built quotes its measured saving.
- **`suggestions-sweep/`** — every `suggestions.md` row as of epic start is in a documented
  cluster and has an outcome (structural fix landed / hook or config enforces it / accepted
  won't-fix with reason); Step 4b escalates a Count ≥ 5 slug into a tracked item and retires it
  from the active list.
