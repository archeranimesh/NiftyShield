# Paper IC Daily Snapshot Wiring — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session. Tick the box
> and append `| SHA: <sha>` (or `| no commit — read-only` for audit tasks) when done. Add one
> line to `TODOS.md`. Full story spec for each task: `stories.md` in this directory.

---

- [x] **SNAP-1** — Confirm `realized_pnl`/`unrealized_pnl` snapshot semantics (cumulative vs. daily delta) against existing three-track data. Read-only, no commit — findings appended to `stories.md`. **Owner: Claude.** Cumulative-as-of-date confirmed; found a strategy-lifecycle reset caveat for "since inception" and a `total_pnl` invariant violation (42/267 rows) in `paper_nav_snapshots` that SNAP-4 must account for. See `stories.md` SNAP-1 findings. | no commit — read-only.
- [x] **SNAP-2** — ~~Wire `PaperStore.record_leg_snapshot()` into `paper_ic_snapshot.py`~~ **NOT NEEDED** — `paper_nav_snapshots` (written by `scripts/portfolio/paper_snapshot.py`, `36 15 * * 1-5`) already has strategy-level `realized_pnl`/`unrealized_pnl`/`total_pnl` for all five IC variants, 2026-07-21 onward. The four SNAP end goals (daily graph, realized-since-inception, realized-this-month, unrealized-since-inception) only need strategy-level data — per-leg attribution was never a stated requirement. Closed without implementation. See `stories.md` SNAP-2 finding. | no commit — scoped out, no code change.
- [ ] **SNAP-3** — Audit whether CSP/CC/PP/Collar EOD scripts have the same missing-snapshot gap. Read-only, no commit — findings appended to `stories.md`. **Owner: Claude.** (No longer needs to run "in parallel with SNAP-2" — SNAP-2 is closed. Still worth running: confirm CSP/overlays also have `paper_nav_snapshots` coverage, the same way IC does.)
- [ ] **SNAP-4** — Build `scripts/reporting/paper_pnl_report.py`: daily P&L graph data, realized-since-inception, realized-this-month, unrealized-since-inception, per strategy. Blocked by SNAP-1 (semantics) only — **no longer blocked by SNAP-2**, since the source table (`paper_nav_snapshots`) already has live rows for all IC variants; query design should target `paper_nav_snapshots`, not `paper_leg_snapshots`. **Owner: Claude** first pass; a later "extend to more strategies" pass is a reasonable Antigravity candidate once the query shape is proven.
- [ ] **SNAP-5** — Fix `total_pnl` invariant not enforced at write time in `paper_nav_snapshots` (42/267 rows currently wrong). Not blocked by SNAP-4 — independent of the reporting script, but SNAP-4 should land first so its query-time recompute workaround is in place regardless of when this fix ships. **Owner: Animesh (backfill-strategy decision required before implementation) → Claude implements after decision.**

---

## Notes for whoever picks this up

- Backfill is explicitly out of scope (user directive, 2026-07-25) — do not attempt to
  reconstruct historical daily P&L for cycles that already closed before SNAP-2 lands.
- SNAP-2 and SNAP-4 both touch financial P&L data — do not skip the code-reviewer gate (or its
  documented Cowork substitution) per `CLAUDE.md`.
- If SNAP-3 finds a real gap for CSP/CC/PP/Collar, do not fold the fix into SNAP-2's commit —
  size it as a new SNAP-5+ story per the sequencing note in `stories.md`.
