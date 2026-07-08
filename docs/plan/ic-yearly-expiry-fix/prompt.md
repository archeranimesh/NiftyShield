Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/ic-yearly-expiry-fix/tasks.md` and find the first unchecked box. That is your **only
task** for this session. Do not look at any other unchecked item. One task. Complete it fully.
Stop.

**Story spec:** Read the matching story in `docs/plan/ic-yearly-expiry-fix/stories.md` for the
full spec.

**Background:** IC V1's yearly bucket resolved to a June 2027 contract instead of December 2026
on 2026-07-08, because `InstrumentLookup.get_expiry_candidates()` treats June and December as
interchangeable `"yearly"` candidates gated by a 201–420 DTE band, and December's DTE (174) fell
under that floor at the time. Per Animesh: NSE Nifty's annual contract is always December's last
Tuesday — June is a half-yearly milestone, not a valid substitute. See `DECISIONS.md` (once YE-4
lands) and this story's YE-1 for the full writeup.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first using the
graph. Order: `git log` → graph query (`search_graph`/`get_code_snippet`/`trace_path`) →
`search_code` → `sed -n` → `Read` (state why the graph was insufficient).

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` first — do not write fixtures from memory.

**YE-1 is read-only.** Do not edit any file for YE-1 — output is the audit table appended to
`stories.md` under a new `### YE-1 findings` heading. Use `Edit`, not `Write`, to append it.

**Blast radius reminder (YE-2/YE-3):** `get_expiry_candidates()` is consumed by 8 call sites.
Do not fix this "just for IC V1" — the whole point of YE-1 is knowing what else moves when the
shared method changes. If YE-1 surfaces a caller that needs June-as-yearly behavior, stop and
flag it in `stories.md` rather than silently special-casing IC V1 around a shared-method
ambiguity.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing (except YE-1, which has no tests to run — it's audit-only).

**Financial-logic gate:** YE-2/YE-3 touch shared expiry-resolution logic feeding real order
placement (strike/expiry selection for paper trades). Per `CLAUDE.md`'s AutoTrigger table, run
the real `@code-reviewer` subagent against `git diff HEAD` before committing YE-2 and YE-3 —
inline self-review does not satisfy this gate. Resolve CRITICAL/ERROR findings before commit;
WARNING may be deferred with a documented reason in the commit message.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft
it and stop.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.
