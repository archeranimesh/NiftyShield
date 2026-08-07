# Paper IC Daily Snapshot Wiring — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session. Tick the box
> and append `| SHA: <sha>` (or `| no commit — read-only` for audit tasks) when done. Add one
> line to `TODOS.md`. Full story spec for each task: `stories.md` in this directory.

---

- [x] **SNAP-1** — Confirm `realized_pnl`/`unrealized_pnl` snapshot semantics (cumulative vs. daily delta) against existing three-track data. Read-only, no commit — findings appended to `stories.md`. **Owner: Claude.** Cumulative-as-of-date confirmed; found a strategy-lifecycle reset caveat for "since inception" and a `total_pnl` invariant violation (42/267 rows) in `paper_nav_snapshots` that SNAP-4 must account for. See `stories.md` SNAP-1 findings. | no commit — read-only.
- [x] **SNAP-2** — ~~Wire `PaperStore.record_leg_snapshot()` into `paper_ic_snapshot.py`~~ **NOT NEEDED** — `paper_nav_snapshots` (written by `scripts/portfolio/paper_snapshot.py`, `36 15 * * 1-5`) already has strategy-level `realized_pnl`/`unrealized_pnl`/`total_pnl` for all five IC variants, 2026-07-21 onward. The four SNAP end goals (daily graph, realized-since-inception, realized-this-month, unrealized-since-inception) only need strategy-level data — per-leg attribution was never a stated requirement. Closed without implementation. See `stories.md` SNAP-2 finding. | no commit — scoped out, no code change.
- [x] **SNAP-3** — Audit whether CSP/CC/PP/Collar EOD scripts have the same missing-snapshot gap. Read-only, no commit — findings appended to `stories.md`. **Owner: Claude.** No gap: `paper_snapshot.py` is a general batch runner covering every strategy in `paper_trades` via `record_daily_snapshot()`, same as IC. CSP has full `paper_nav_snapshots` coverage. CC/PP/Collar overlay have zero rows everywhere because they've never traded yet (pre-bootstrap) — not a wiring gap. See `stories.md` SNAP-3 findings. | no commit — read-only.
- [x] **SNAP-4** — Built `scripts/reporting/paper_pnl_report.py` (+ `build_pnl_report()` importable pure function): daily P&L graph data (recomputed `realized+unrealized` per snapshot, never trusts stored `total_pnl` — SNAP-1's invariant-violation finding), realized-since-inception (via `get_strategy_realized_pnl()`, summed from `paper_trades` directly so it survives cycle resets per SNAP-1's caveat), realized-this-month (nav-snapshot baseline-diff, mid-month-open fallback), unrealized-since-inception (latest snapshot). CLI (`--strategy`, `--json`) plus plain-text output. Tests: happy path (3-day multi-leg fixture, deliberately-wrong stored `total_pnl` to prove recompute) + zero-snapshot-rows edge case. `python -m pytest tests/unit/` — 2730 passed, 2 skipped (1 pre-existing failure + 2 pre-existing import errors, all unrelated — sandboxed network egress blocked / missing optional deps). Code-reviewer gate: Cowork substitution — REVIEW.md checklist applied directly (no mutable defaults, no bare/broad `except`, no `assert` outside tests, no `@staticmethod`, structlog keyword-arg logging per `LOGGING.md`'s documented G7 override, import ordering matches project convention, line length within the project's actual configured 100-char limit per `pyproject.toml` — REVIEW.md's G2 "80" text is stale relative to the real tool config, same drift already present in `paper_ic_snapshot.py`). **Owner: Claude.** | SHA: 04687f1.
- [ ] **SNAP-5** — Fix `total_pnl` invariant not enforced at write time in `paper_nav_snapshots` (42/267 rows currently wrong). Not blocked by SNAP-4 — independent of the reporting script, but SNAP-4 should land first so its query-time recompute workaround is in place regardless of when this fix ships. **Decision made 2026-08-07: Option A (backfill in place).** **Owner: Claude.**

---

## Notes for whoever picks this up

- Backfill is explicitly out of scope (user directive, 2026-07-25) — do not attempt to
  reconstruct historical daily P&L for cycles that already closed before SNAP-2 lands.
- SNAP-2 and SNAP-4 both touch financial P&L data — do not skip the code-reviewer gate (or its
  documented Cowork substitution) per `CLAUDE.md`.
- If SNAP-3 finds a real gap for CSP/CC/PP/Collar, do not fold the fix into SNAP-2's commit —
  size it as a new SNAP-5+ story per the sequencing note in `stories.md`.
