Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/ic-time-stop-dte-tiering/tasks.md` and find the first unchecked box. That is your
**only task** for this session. Do not look at any other unchecked item. One task. Complete it
fully. Stop.

**Story spec:** Read the matching story in `docs/plan/ic-time-stop-dte-tiering/stories.md` for
the full spec.

**Background:** `IronCondorV1`'s per-bucket `time_stop_dte`/`dte_warn` (`ic_expiry_config.py`)
were scaled to each bucket's entry DTE window (weekly 2/4, monthly 14/21, leaps 45/60, yearly
60/90) — a linear extrapolation from `IC-M1.md` with no backtest or empirical basis. Operator
challenged this (2026-08-05 conversation: leaps' 45-DTE stop truncates most of the theta curve;
monthly's realistic hold is already short relative to its 14-DTE stop) and it went to council.
Ruling: `docs/council/2026-08-05_ic-time-stop-dte-tiering.md` — **read Stage 3 first, it is
authoritative; Stage 1 is background only** (and in this file specifically, Stage 1 responses
each hallucinated a fake multi-party council framing because the prompt included a prior ruling
doc as context — the actual per-model recommendations embedded in each response are still real
and were correctly extracted by the chairman, but treat any claim of "the panel discussed X"
inside a Stage 1 section with suspicion; only Stage 3's own words are load-bearing per
`docs/council/README.md`'s reading priority).

**Ruling summary:** uniform terminal-DTE rule replaces entry-scaled tiers. `time_stop_dte=7`,
`dte_warn=14` for monthly/leaps/yearly. Weekly unchanged (`time_stop_dte=2`, `dte_warn=4`) — its
5–8 DTE entry window makes 7 DTE meaningless. Attached requirement: counterfactual DTE logging
(mark/Greeks/spread at 14/10/7/5 DTE on every IC exit) so the 7-DTE default can be validated
against real data after 6 monthly cycles, per the ruling's own "not a permanent calibration"
framing.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first using the
graph. Order: `git log` → graph query (`search_graph`/`get_code_snippet`/`trace_path`) →
`search_code` → `sed -n` → `Read` (state why the graph was insufficient).

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` first — do not write fixtures from memory. This applies
directly to DT-3b (`PaperExitEvent`/`create_exit_event` call sites) — the field list has grown
incrementally (`delta_stop_would_fire`, `premium_stop_would_fire` were both added after initial
ship) and a from-memory fixture will miss the current signature.

**Do not bundle DT-1/DT-2 (config + docs) with DT-3a/DT-3b (counterfactual logging) in one
commit.** Different phases per `CLAUDE.md` Step 5 — DT-1/DT-2 is a pure parameter+docs change;
DT-3a is read-only audit (no commit expected unless `stories.md` itself is updated); DT-3b is new
schema + wiring + tests. Each task in `tasks.md` gets its own commit.

**Task routing (`[Claude]` / `[Antigravity]` tags in `tasks.md`) follows `CLAUDE.md` Step 3b:**
DT-1, DT-2, DT-3a, and DT-4 are Claude's — single/2-file, either mechanical-but-financial
(DT-1, needs the code-reviewer gate) or genuinely ambiguous/exploratory (DT-3a, the write-path
audit). DT-3b is the one Antigravity-appropriate task here — 3+ files, TDD-style edit/test loop,
fully pinned-down spec **once DT-3a lands**. If DT-3a is still unchecked, do not start DT-3b
regardless of which surface picks up the next session.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing each task.

**Financial-logic gate:** DT-1 changes live exit-signal thresholds for real (paper) order
placement; DT-3b touches `PaperStore` schema and whatever module DT-3a confirms writes IC exit
events. Per `CLAUDE.md`'s AutoTrigger table, run the real `@code-reviewer` subagent against
`git diff HEAD` before committing DT-1 and DT-3b — inline self-review does not satisfy this gate.
Resolve CRITICAL/ERROR findings before commit; WARNING may be deferred with a documented reason
in the commit message. DT-2, DT-3a, and DT-4 are docs/audit-only — no code-reviewer gate.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft
it and stop.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.
