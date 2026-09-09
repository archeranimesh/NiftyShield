# Subagent dispatch — telegram-markdown-migration ROLL-7 / ROLL-10 / ROLL-11

Prepared 2026-09-01 (session that shipped ROLL-6, SHA `2471f01`). Purpose: hand three
independent `strategy-rollout/` tasks to subagents / fresh sessions without them colliding.

Each task = one epic session = one code commit + one docs-close commit, per
`docs/plan/telegram-markdown-migration/prompt.md` (the router) and its Step-4 "one task per
session, stop" rule. A subagent doing one of these runs the full protocol itself, including
its own `@test-runner` (spawn it — do not run `pytest` inline) and, where flagged,
`@code-reviewer`.

---

## 1. Analysis

### Why these three, and not the others

| Task | Owner | Blocked by | Files (disjoint from the other two) | Gate |
|---|---|---|---|---|
| **ROLL-7** | Claude | nothing (backbone + formatting-rules done) — **unblocks ROLL-8 & ROLL-12** | `src/strategy/reentry_mixin.py`, `src/notifications/formatting.py` (+`STRATEGY_LABELS`/`LEG_ROLE_LABELS`), `tests/unit/strategy/test_reentry_mixin.py` | Review: none¹ |
| **ROLL-10** | Claude | nothing | `scripts/dev/paper_track_snapshot.py`, `src/paper/track_snapshot.py`, `tests/unit/scripts/test_paper_track_snapshot.py` (new) | Review: none¹ · **greeks-analyst may fire²** |
| **ROLL-11** | Claude | nothing | `scripts/healthcheck.py`, `tests/unit/test_healthcheck.py` | Review: none¹ |

¹ `tasks.md` marks all three `Review: none`. None carries a "Financial-logic commit note" in
its `stories.md` spec (ROLL-9 does; these don't). Running `@code-reviewer` anyway is prudent —
all three refactor production logic, not just message strings — but it is **not** the mandatory
Opus gate. Judgment call for the implementing session.

² ROLL-10 edits `src/paper/track_snapshot.py`. CLAUDE.md AutoTrigger: "Any change to
`src/paper/` … → greeks-analyst". The change is a plain `consecutive_days: int` field, not a
Greek — but a strict reading triggers the agent. Spawn it; it will clear fast.

**Not in this batch:**
- ROLL-8, ROLL-12 — need ROLL-7's label tables. Dispatch only after ROLL-7's SHA lands.
- ROLL-9, ROLL-13 — real `@code-reviewer` (Opus) gate + financial P&L rendering. Heavier;
  give each its own focused session.
- ROLL-15 + ROLL-16 — sequential pair, both rewrite the large `paper_3track_snapshot.py`;
  ROLL-16 also real-sequences after ROLL-10.
- ROLL-17 — **design incomplete** (6 open decisions). Needs a `message-format-workshop.md`
  session with Animesh before any code.
- ROLL-5 — docs-close synthesis; blocked until every other ROLL box is ticked.

### Stale text to ignore in `stories.md`

ROLL-10 and ROLL-11 specs say *"backbone/ (MD-1..MD-5) status: NOT shipped"* and *"reference
script inlines its own copy of `escape_markdown()`"*. **Both are stale.** As of 2026-08-25:
- `escape_markdown()` / `mdcode()` are real in `src/notifications/markdown.py` — import them.
- `src/notifications/formatting.py` exists with `format_money` / `format_greek` / `pnl_emoji` /
  the table builders. So the "colocate-then-promote" judgment resolves to **promote**: new
  helpers (`STRATEGY_LABELS`, `LEG_ROLE_LABELS`, `CheckResult` + its message builder) land in
  `src/notifications/formatting.py`, not colocated in the script.
- ROLL-6 shipped `StrategyPnLRow` / `format_summary_money` / `build_strategy_table` there too;
  ROLL-7's fuller-form `STRATEGY_LABELS` is a *separate* dict from ROLL-6's table-column
  `_STRATEGY_META` (spec §1 says so) — do not merge them, but flag the future
  `id -> {short, long}` consolidation the ROLL-7 spec already raises.

### Each task has real production-logic scope (not a pure format port)

- **ROLL-7** — refactor the 3 gates in `ReEntryMixin._check_reentry` (`src/strategy/reentry_mixin.py`,
  `blocked_reason` built at lines ~120-160) to each yield `(short_reason: str, detail: str | None)`
  instead of one prose string; the 2 structural-failure strings ("IVR history insufficient",
  "open position check failed") get the same shape. Do **not** string-split the existing prose.
- **ROLL-10** — plumb `consecutive_days` as its own field on `TrackSnapshot` (computed by
  `ProxyDeltaMonitor.update_and_check`, currently folded into a string in
  `generate_track_snapshot` ~L349 and discarded). Ship the `proxy_delta_alert` string verbatim
  in the `Rule Breach:` line for now (don't parse it back apart).
- **ROLL-11** — breaking change: `run_checks()` returns `list[CheckResult]` (new frozen
  dataclass: `label`, `severity: Literal["ok","warn","critical"]`, `status_word`,
  `detail: str | None`) not `list[str]`. Existing tests `test_run_checks_all_pass`,
  `test_run_checks_missing_daily_snapshot`, `test_main_success_flow`, `test_main_failure_alerts`,
  `test_main_non_trading_day` all need updating.

---

## 2. Conflict map — why serial, not parallel

Every ROLL-* task edits these four shared files on the way to its commit:

1. `tests/unit/notifications/test_escaping_guard.py` — each removes (or converts) its own
   `_BASELINE_UNESCAPED` entry. The guard's `test_no_new_unescaped_send_call_sites` /
   `test_baseline_entries_are_still_unescaped` fail until it does — cannot be deferred.
   - ROLL-7 entry: `("src/strategy/reentry_mixin.py", 210)`
   - ROLL-10 entry: `("scripts/dev/paper_track_snapshot.py", 167)`
   - ROLL-11 entry: `("scripts/healthcheck.py", 254)`
   (These are *different dict keys*, so a 3-way git merge auto-resolves — but only if commits
   are rebased, not made concurrently on `main`.)
2. `docs/plan/telegram-markdown-migration/strategy-rollout/tasks.md` — tick box + SHA + the
   `**Open: …**` line.
3. `docs/plan/README.md` — the `strategy-rollout/ next: ROLL-N` line.
4. `TODOS.md` — session-log entry.

Plus `src/notifications/formatting.py`: ROLL-7 adds label dicts there; ROLL-10 and ROLL-11
also add helpers there. Three sessions appending to the same module = churn.

**Recommendation: run them serially.** Dispatch ROLL-7 → wait for its two SHAs → dispatch
ROLL-11 → wait → dispatch ROLL-10. Each starts from an up-to-date `main`, no merge needed.

If you insist on parallel: give each subagent an explicit task ID up front (the router's
ROLL-7..16 coordination note requires this), have each rebase onto `main` before its final
commit, and expect to hand-resolve items 2-4 above (small, single-line each).

---

## 3. Dispatch prompts (paste as the first message of a fresh session, one per session)

Each assumes the session auto-loads `CLAUDE.md`. The prompt overrides the router's
"first unchecked box" search with an explicit task claim — legitimate per the router's
ROLL-7..16 coordination note.

### 3a — ROLL-7

```
Follow docs/plan/telegram-markdown-migration/prompt.md. I am assigning you ROLL-7
specifically (re-entry blocked/eligible notice) — do not pick the "first unchecked" box,
claim ROLL-7. Read CONTEXT.md, the epic README, strategy-rollout/prompt.md, and the ROLL-7
section of strategy-rollout/stories.md.

Key points for this task:
- Owner: Claude, Model: claude-sonnet-5, Review: none in tasks.md — but this refactors
  ReEntryMixin._check_reentry's gate-reason construction (production logic), so run the real
  @code-reviewer subagent against `git diff HEAD` before committing anyway.
- backbone/ + formatting-rules/ ARE shipped (stories.md may imply otherwise) — import
  escape_markdown/mdcode from src/notifications/markdown.py; put the new STRATEGY_LABELS /
  LEG_ROLE_LABELS dicts in src/notifications/formatting.py (not colocated).
- STRATEGY_LABELS is the fuller-form dict, SEPARATE from ROLL-6's _STRATEGY_META in
  scripts/eod_summary.py — do not merge; leave the "id -> {short,long}" consolidation flagged.
- Refactor the 3 gates + 2 structural-failure strings in _check_reentry to
  (short_reason, detail) pairs. Do NOT string-split existing prose.
- Extend tests/unit/strategy/test_reentry_mixin.py (exists), don't create a new file.
- Test gate: python -m pytest tests/unit/ --tb=no -q — spawn @test-runner, don't run inline.
- After: two commits (feat code, then docs-close with SHA), tick ROLL-7 in tasks.md, update
  the epic README Stories row is n/a (still in progress), update docs/plan/README.md
  "next: ROLL-7" -> "next: ROLL-8", add a TODOS.md session-log line. Then stop.
```

### 3b — ROLL-11

```
Follow docs/plan/telegram-markdown-migration/prompt.md. I am assigning you ROLL-11
specifically (system healthcheck alert) — claim ROLL-11, not the first unchecked box. Read
CONTEXT.md, the epic README, strategy-rollout/prompt.md, and the ROLL-11 section of
strategy-rollout/stories.md.

Key points:
- Owner: Claude, Model: claude-sonnet-5, Review: none. Optional @code-reviewer (breaking
  return-type change to run_checks(), not financial) — implementer's call.
- backbone/ + formatting-rules/ ARE shipped (stories.md "NOT shipped" note is stale) —
  import from src/notifications/markdown.py; put the new CheckResult dataclass + grouped
  message builder in src/notifications/formatting.py.
- Breaking change: run_checks() returns list[CheckResult] not list[str]. CheckResult is a
  frozen dataclass: label:str, severity:Literal["ok","warn","critical"], status_word:str,
  detail:str|None. Update main()'s alert-message builder to consume it.
- Existing tests need updating for the new return type: test_run_checks_all_pass,
  test_run_checks_missing_daily_snapshot, test_main_success_flow, test_main_failure_alerts,
  test_main_non_trading_day. Extend tests/unit/test_healthcheck.py, don't create a new file.
- Confirmed format: reference scratch/2026-08-10_healthcheck_alert_format.py — grouped by
  severity, timestamp is [HH:MM] only (no date, no "IST"), omit the trailing "SYSTEMS NORMAL"
  line entirely when every check fails. Single "DEGRADED" overall word — do NOT invent a
  DOWN/CRITICAL tier.
- Remove/convert the _BASELINE_UNESCAPED entry ("scripts/healthcheck.py", 254) in
  tests/unit/notifications/test_escaping_guard.py in the same commit (per its maintenance
  contract) — if main() itself won't contain the escaping call, convert it to a
  heuristic-limitation note like the eod_summary.py:200 entry rather than deleting it.
- Test gate: spawn @test-runner. Two commits (code, docs-close+SHA). Tick ROLL-11, update
  docs/plan/README.md next-pointer, TODOS.md line. Stop.
```

### 3c — ROLL-10

```
Follow docs/plan/telegram-markdown-migration/prompt.md. I am assigning you ROLL-10
specifically (proxy delta CRITICAL alert) — claim ROLL-10, not the first unchecked box. Read
CONTEXT.md, the epic README, strategy-rollout/prompt.md, and the ROLL-10 section of
strategy-rollout/stories.md.

Key points:
- Owner: Claude, Model: claude-sonnet-5, Review: none. This edits src/paper/track_snapshot.py
  -> spawn @greeks-analyst per the AutoTrigger rule (the change is a plain consecutive_days:int
  field, not a Greek, so it should clear quickly, but the rule triggers on any src/paper/ edit).
- backbone/ + formatting-rules/ ARE shipped (stories.md "NOT shipped" note is stale) — import
  escape_markdown from src/notifications/markdown.py; use format_greek from
  src/notifications/formatting.py for the Delta value, then escape_markdown() the WHOLE
  formatted string (sign AND decimal point are both reserved — this was a live 400 bug in the
  workshop, finding 1).
- Real scope: add consecutive_days as its own field on TrackSnapshot, plumbed from
  ProxyDeltaMonitor.update_and_check through generate_track_snapshot (currently computed then
  discarded into a string ~L349). Ship proxy_delta_alert VERBATIM (escaped) in the
  "Rule Breach:" line for now — do NOT parse the threshold/day-count back out of it.
- Do NOT add a "🤖 Action:" line (finding 2 — no upstream action signal exists, would
  fabricate data).
- Only the CRITICAL branch sends; WARNING/OK are console-only and out of scope. The near-
  duplicate in paper_3track_snapshot.py::_run is ROLL-16, NOT this task — leave it alone.
- New test file: tests/unit/scripts/test_paper_track_snapshot.py (does not exist yet).
  Confirm src/paper/ package __init__.py / re-index note if you add a new test package dir.
- Remove/convert the _BASELINE_UNESCAPED entry ("scripts/dev/paper_track_snapshot.py", 167)
  in test_escaping_guard.py in the same commit.
- Test gate: spawn @test-runner. Two commits (code, docs-close+SHA). Tick ROLL-10, update
  docs/plan/README.md next-pointer, TODOS.md line. Stop.
```

---

## 4. After all three land

- Verify each: `git log --oneline` shows 6 commits (3 feat + 3 docs), each ROLL box ticked
  with a real SHA, `python -m pytest tests/unit/ --tb=no -q` green.
- `docs/plan/README.md` "next" pointer should read ROLL-8 (or ROLL-9 if you also want to skip
  the Antigravity-owned ROLL-8).
- ROLL-8 and ROLL-12 are now unblocked (ROLL-7's label tables exist) — both `Owner: Antigravity`,
  so they go via the `handoff-antigravity` skill, not a Claude subagent.
- Re-run `mcp__codebase-memory-mcp__index_repository` once at the end (all three touched
  `src/`).
