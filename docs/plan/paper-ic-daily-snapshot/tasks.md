# Paper IC Daily Snapshot Wiring — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session. Tick the box
> and append `| SHA: <sha>` (or `| no commit — read-only` for audit tasks) when done. Add one
> line to `TODOS.md`. Full story spec for each task: `stories.md` in this directory.

---

- [ ] **SNAP-1** — Confirm `realized_pnl`/`unrealized_pnl` snapshot semantics (cumulative vs. daily delta) against existing three-track data. Read-only, no commit — findings appended to `stories.md`. **Owner: Claude.**
- [ ] **SNAP-2** — Wire `PaperStore.record_leg_snapshot()` into `paper_ic_snapshot.py` for all five IC variants (V1 weekly/monthly/leaps/yearly, V2 monthly). Blocked by SNAP-1. **Owner: Claude** (financial-logic gate, live graph-query dependency — see stories.md rationale).
- [ ] **SNAP-3** — Audit whether CSP/CC/PP/Collar EOD scripts have the same missing-snapshot gap. Read-only, no commit — findings appended to `stories.md`. Can run in parallel with SNAP-2. **Owner: Claude.**
- [ ] **SNAP-4** — Build `scripts/reporting/paper_pnl_report.py`: daily P&L graph data, realized-since-inception, realized-this-month, unrealized-since-inception, per strategy. Blocked by SNAP-1 (semantics) and SNAP-2 (needs live rows to validate against). **Owner: Claude** first pass; a later "extend to more strategies" pass is a reasonable Antigravity candidate once the query shape is proven.

---

## Notes for whoever picks this up

- Backfill is explicitly out of scope (user directive, 2026-07-25) — do not attempt to
  reconstruct historical daily P&L for cycles that already closed before SNAP-2 lands.
- SNAP-2 and SNAP-4 both touch financial P&L data — do not skip the code-reviewer gate (or its
  documented Cowork substitution) per `CLAUDE.md`.
- If SNAP-3 finds a real gap for CSP/CC/PP/Collar, do not fold the fix into SNAP-2's commit —
  size it as a new SNAP-5+ story per the sequencing note in `stories.md`.
