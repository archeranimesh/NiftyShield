# Yearly Ops Wiring — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` + tick the box,
> update story status, add one line to `TODOS.md`.

---

## YW-1 — Daemon registration

**Files to change / create:**
- `scripts/monitor_daemon.py` — loop over the registry; second flag `MONITOR_YEARLY_OVERLAYS`.
- `src/config.py` — declare the env var (it declares every env var).
- `tests/unit/scripts/test_monitor_daemon_yearly.py`.

**Before any code:** `get_code_snippet("main")` region around lines 441-466 of `monitor_daemon.py` via `sed -n`; `search_graph("Settings")` for the flag convention.

**What to implement:** build overlay instances with `strategy_name=policy.strategy_name` and the policy injected; preserve the existing failure-isolation try/except per instance.

**Tests:**
- `test_flag_off_registers_monthly_only`, `test_flag_on_registers_yearly_instances_with_yearly_namespace`.

**Commit:** `feat(daemon): register yearly overlay strategies behind flag`

---

## YW-2 — Labels and reports

**Files to change / create:** `src/notifications/formatting.py` (`STRATEGY_LABELS`), `scripts/eod_summary.py` (label map), `src/reporting/eod_pt_summary.py`, `scripts/pre_market_brief.py`,
`scripts/strategies/three_track/paper_3track_snapshot.py` — more than 2 files: list them in the go-ahead.

**Before any code:** `get_code_snippet` for each builder; load `FORMATTING.md` and `src/notifications/CLAUDE.md` §"Instrument Label Formatting".

**What to implement:** each builder iterates namespaces from the registry and prefixes yearly rows ("Yearly CC" etc.); overlay P&L uses the yearly `strategy_name` as the key, `overlay_type` unchanged.

**Tests:** golden-table tests for each builder with one monthly and one yearly leg: `test_report_lists_yearly_rows_separately`, `test_monthly_only_output_unchanged`.

**Commit:** `feat(reporting): show yearly overlay book separately`

---

## YW-3 — Crons, runbook, registry notes

**Files to change / create:** `docs/` runbook entry, `DB_REGISTRY.md` (note: yearly namespace rides existing tables, no new table), `CONTEXT_TREE.md`, `CONTEXT.md` "What Exists" line, `DECISIONS.md`.

**What to implement:** state the new flag, the cron lines Animesh adds on the host (entry cron runs `--auto-cc/--auto-pp/--auto-collar --expiry-type yearly`), and the YF-1 schema finding.

**Tests:** none (docs-only).

**Commit:** `docs: record yearly overlay book ops wiring`
