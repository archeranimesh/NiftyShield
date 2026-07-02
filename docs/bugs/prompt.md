# docs/bugs/ — Session Orientation

> **What this folder covers:** Confirmed defects in live code, tracked outside the story
> workflow in `docs/plan/`. Stories are forward work against a spec; bugs are regressions
> or logic errors found in code that already shipped. Keep them separate — a bug fix is not
> a story task, and cramming it into a story's `*_tasks.md` buries severity/root-cause
> context that fixes actually need.
>
> When to log here vs. `docs/plan/`: if the defect is in code that has already been
> committed and is running (paper trading, cron scripts, live gates), it's a bug — log it
> here. If it's an unimplemented spec item, it's a story task.

---

## Context

This folder was created 2026-07-02 after triaging IC entry log rejections
(`logs/ic_weekly.log`, `logs/ic_monthly.log`, `logs/ic_v2_monthly.log`) surfaced two
confirmed defects in gates that had been silently blocking or corrupting entries:

- `src/risk/delta_tracker.py` — put/call misclassification corrupting the portfolio delta
  gate (BUG-002).
- `scripts/strategies/ic/ic_entry_gates.py::_post_expiry_gate` — inverted monthly
  settlement check (BUG-003).

Full findings: `bugs.md`. Both are unfixed as of folder creation — this is a registry,
not a changelog.

**Relationship to root `BUGS.md`:** a bug registry already existed at the repo root
(`BUGS.md`, single open entry: `BUG-001`, `daily_snapshot.py` backfill gap — unrelated,
low severity, no code-level fix scheduled). This folder does not replace it, but is now
the canonical home for *new* bug entries going forward — story-adjacent structure
(`prompt.md`/`task.md`/registry) fits an active-development phase better than a flat file.
ID numbering is a single shared sequence across both files — continue from the highest
number used in either (`BUG-001` in root `BUGS.md`, so this folder starts at `BUG-002`).
Do not renumber `BUG-001` in the root file. If `BUG-001` is ever fixed, delete it from
root `BUGS.md` per that file's own convention ("fix lands, then delete the entry") —
do not migrate it here.

---

## Session start protocol

1. Read this file + `bugs.md` + `CONTEXT.md`.
2. Check `task.md` — first unchecked item only, same convention as `docs/plan/*/[]_tasks.md`.
3. Before fixing: re-confirm root cause against current code (bugs.md is a snapshot at
   discovery time — the file may have moved on since). Use the graph
   (`search_graph` / `get_code_snippet` / `trace_path`), not `Read`, per Rule 0.
4. Financial-logic bugs (delta, P&L, Decimal paths, BrokerClient boundaries) require the
   real `@code-reviewer` subagent before commit — no exceptions, per root `CLAUDE.md`.
5. After fix: flip status in `bugs.md` to `✅ Fixed` + commit SHA, tick `task.md`, add a
   `TODOS.md` session log line, update `CONTEXT.md` if module structure changed.
6. One bug fix per commit. Do not bundle BUG-002 and BUG-003 fixes together — they touch
   unrelated files and have independent blast radius.

---

## Task overview

| Bug | Severity | Status | Fix task |
|---|---|---|---|
| BUG-002 — delta sign/magnitude corrupted by put-call misclassification | CRITICAL | 🔴 Open | Pending — needs decision on cross-strategy aggregation scope first |
| BUG-003 — `_post_expiry_gate` inverted monthly window | HIGH | 🔴 Open | Pending |

**Next task:** none yet — both bugs are logged and root-caused but no fix has been
scoped/approved. See `task.md` for the first unchecked item.
