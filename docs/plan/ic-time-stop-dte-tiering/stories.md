# IC Time-Stop DTE Tiering — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Origin: operator challenge (2026-08-05 conversation) → council ruling
> `docs/council/2026-08-05_ic-time-stop-dte-tiering.md`.

---

## DT-1 — Update `ic_expiry_config.py` CONFIGS

**Context:** `CONFIGS` in `src/strategy/ic_expiry_config.py` currently scales `time_stop_dte`/
`dte_warn` to each bucket's entry-DTE window (weekly 2/4, monthly 14/21, leaps 45/60, yearly
60/90). The council ruling rejects this scaling — an option's terminal gamma/pin risk is a
function of its *current* remaining DTE, not how much DTE it had at entry. Ruling: replace with
a uniform terminal-DTE rule for monthly/leaps/yearly; weekly is a structural exception (5–8 DTE
entry window, a 7-DTE stop would never fire on a live trading day) and stays as-is.

**Files to change:**
- `src/strategy/ic_expiry_config.py` — `CONFIGS` dict only, six integer literals
- No test file changes expected — `test_ic_expiry_config.py`'s invariant tests
  (`test_time_stop_lt_dte_warn`, `test_dte_warn_lo_lt_dte_warn_hi`) assert relationships, not
  literal values, so they should pass unchanged. Run them anyway; do not assume.

**Before any code:**
```
get_code_snippet("ic_expiry_config.CONFIGS")   # confirm current literals before editing
search_code("time_stop_dte=14")                 # confirm no other file duplicates these literals
git log --oneline -10 src/strategy/ic_expiry_config.py
```

**Change:**

```python
"monthly": ICExpiryConfig(
    ...
    time_stop_dte=7,     # was 14
    dte_warn=14,          # was 21
    ...
),
"leaps": ICExpiryConfig(
    ...
    time_stop_dte=7,     # was 45
    dte_warn=14,          # was 60
    ...
),
"yearly": ICExpiryConfig(
    ...
    time_stop_dte=7,     # was 60
    dte_warn=14,          # was 90
    ...
),
```

`weekly` block: **no change** (`time_stop_dte=2`, `dte_warn=4`). Do not touch `dte_warn_lo`/
`dte_warn_hi` (entry-window bounds) on any bucket — those are unrelated to this ruling and
outside its scope.

**Do not touch:** `profit_target_pct`, `loss_stop_pct`, `delta_stop`, `delta_warn`,
`roll_wing_delta_lo/hi`, `roll_wing_target_delta` — the ruling is explicit that none of these
change.

**Tests:**
```
python -m pytest tests/unit/strategy/test_ic_expiry_config.py -v
python -m pytest tests/unit/ --tb=no -q
```
Both must be green. If `test_time_stop_lt_dte_warn` or `test_dte_warn_lo_lt_dte_warn_hi` fail,
stop and re-read the ruling — do not force a passing value that contradicts the Summary Table.

**Commit:** `fix(strategy): uniform 7-DTE IC time-stop replaces entry-scaled tiers`
(`Why:` cite the council ruling filename; `Ref: docs/council/2026-08-05_ic-time-stop-dte-tiering.md`)

---

## DT-2 — Docs: `DECISIONS.md` + `IC-M1.md` Correction

**Context:** `IC-M1.md` (`docs/archive/ic-multi-expiry/stories/IC-M1.md`) is the story of record
that introduced the now-superseded scaled values, on the stated assumption "Leaps and yearly
ICs need substantially wider time buffers" — no empirical basis, later rejected by council. It's
an archived file (implementation already shipped), so this is a corrective annotation, not a
rewrite of history — do not alter the original CONFIGS code block in that file; append a note.

**Files to change (targeted `Edit` only, never `Write`):**
- `DECISIONS.md` — new entry, most-recent-first position (top of file, matching existing style)
- `docs/archive/ic-multi-expiry/stories/IC-M1.md` — append a correction note, do not rewrite

**Before any code:**
```
git log --oneline -5 DECISIONS.md
```

**`DECISIONS.md` entry to add** (top of file, after the header block, matching the existing
bold-title-then-prose bullet style — see the two 2026-08-04 entries already there for exact
format):

```markdown
**IC time-stop DTE de-tiered — uniform terminal rule (2026-08-05, council ruling):**
`ic_expiry_config.py`'s per-bucket `time_stop_dte`/`dte_warn` no longer scale to entry-DTE
window. Council ruling (`docs/council/2026-08-05_ic-time-stop-dte-tiering.md`, unanimous on the
core diagnosis across 3 panelists) rejected `IC-M1.md`'s entry-DTE-proportional scaling
(weekly 2/4, monthly 14/21, leaps 45/60, yearly 60/90) as unsound — an option's terminal
gamma/pin risk depends on *current* remaining DTE, not entry tenor; the wide leaps/yearly
buffers were truncating theta capture with no demonstrated risk benefit. New values: monthly,
leaps, and yearly all use `time_stop_dte=7`, `dte_warn=14`. Weekly unchanged
(`time_stop_dte=2`, `dte_warn=4` — 5–8 DTE entry window makes 7 DTE unreachable). The panel
split 5-vs-14 DTE for the uniform value (Response A: IC's defined-risk wing structure permits
holding to 5 DTE, mirroring the 2026-06-26 CC/PP/Collar `DTE_REVIEW≤5` ruling; Response B/C:
wide wings cap max loss but don't hedge near-strike gamma, so IC still needs execution-risk
buffer beyond 5) — chairman resolved at 7 as a Phase 0 research default, not a final
calibration, paired with mandatory counterfactual DTE logging (DT-3) and a review after 6
monthly cycles. Liquidity-by-tenor concern (raised as a possible justification for the old wider
buffers) was rejected — NSE Nifty contracts converge to a shared order book by original
calendar month regardless of entry-tenor label, so no execution-quality case for wider buffers
exists. **Noted, deferred (dissenting/future-work):** a separate `MAX_DAYS_IN_TRADE`
capital-velocity parameter was proposed to decouple ROI-per-margin-day concerns from the
risk-driven time-stop — not built now, flagged for a future story if leaps/yearly capital
lockup becomes a measured problem.
```

**`IC-M1.md` — append at end of file** (after the existing content, new heading, do not touch
anything above it):

```markdown
---

## 2026-08-05 Correction — Entry-DTE Scaling Superseded

The `time_stop_dte`/`dte_warn` scaling this story introduced (weekly 2/4, monthly 14/21,
leaps 45/60, yearly 60/90) was rejected by council ruling
`docs/council/2026-08-05_ic-time-stop-dte-tiering.md`: no empirical or theoretical basis
existed for entry-DTE-proportional buffers beyond linear intuition. Current values live in
`ic_expiry_config.py` — see `DECISIONS.md` 2026-08-05 for the full account. This file is kept
as the historical record of the original (superseded) design, not the current spec.
```

**Tests:** none — docs-only task, no code-reviewer gate per `prompt.md`.

**Commit:** `docs: record IC time-stop de-tiering council ruling in DECISIONS.md`

---

## DT-3a — Audit: Confirm IC's Actual `paper_exit_events` Write Path `[Claude]`

**Context:** The council ruling's 7-DTE value is explicitly a Phase 0 research default, not a
validated number — it's paired with a requirement to log what the combined mark/Greeks/spread
*would have been* at 14/10/7/5 DTE on every IC exit, so a 6-monthly-cycle review can tighten
toward 5 or loosen toward 10–14 with real data instead of re-litigating the argument. DT-3
(3a+3b) is **recommended but not blocking** per the ruling — DT-1/DT-2 can ship and the 7-DTE
value takes effect regardless of whether this lands in the same session.

**Why this is Claude's task, not Antigravity's:** the write path is genuinely unresolved (see
below) — this is exploratory graph-tracing to resolve an ambiguity, not a mechanical edit
against a pinned-down spec. Per `CLAUDE.md` Step 3b, that routes to Claude. Once the call site
is confirmed and this section is updated with the finding, DT-3b (the actual schema + wiring +
tests) has a fully pinned-down spec and is a good Antigravity handoff.

**This story starts with an audit, not an implementation — do not skip it.** `paper_exit_events`
(`src/paper/store.py::PaperStore.create_exit_event`) already has the right shape for this
(existing precedent: `delta_stop_would_fire`/`premium_stop_would_fire` are exactly this pattern
— a nullable "counterfactual, would this other rule have fired" column). But as of this writing,
`create_exit_event` has **no confirmed caller inside the IC path** — `ic_nifty_v1.py` and
`paper_ic_snapshot.py` were graph-searched and neither calls it directly; the only confirmed
callers are `reentry_mixin.py` and `overlay_closer.py` (3-track overlay strategies, not IC). Yet
`paper_ic_snapshot.py::process_variant` *reads* `paper_exit_events` (`status='ACTED'` query) for
its EOD report's "Intraday actions" line — meaning something writes IC rows into that table,
most likely `StrategyMonitor`'s generic auto-execute dispatch path, not `IronCondorV1` itself.

**Audit step (do first, before writing any code):**
```
trace_path("create_exit_event")                          # every actual caller, not just the 3 found so far
search_graph(query="StrategyMonitor _route_event auto-execute exit event")
get_code_snippet("StrategyMonitor._route_event")          # confirm whether IC events flow through here
search_code("paper_exit_events", path_filter="src/strategy/monitor.py")
```
If the write path is `StrategyMonitor._route_event` (or another shared dispatcher covering both
IC and the 3-track overlays), the schema change and wiring below apply there, not inside
`IronCondorV1.check_signals` — **update this section of `stories.md` with the confirmed call
site before DT-3b starts**, same discipline as `ic-yearly-expiry-fix`'s YE-1. Do not hand DT-3b
to Antigravity until this is nailed down — an unresolved-ambiguity spec handed to a mechanical
implementer is exactly the failure mode Step 3b routing exists to avoid.

**DT-3a output:** an updated version of the "Files to change" list below, with the actual
confirmed module/function in place of the placeholder, plus a one-line note in this file
confirming DT-3b is now unblocked. **DT-3a does not write any implementation code** — audit
only, per the `ic-yearly-expiry-fix` YE-1 precedent (`docs/plan/ic-yearly-expiry-fix/tasks.md`).

---

## DT-3b — Counterfactual DTE Logging: Implementation `[Antigravity]`

**Do not start until DT-3a's findings are written into this file.** The spec below is
provisional pending that audit.

**Files to change (confirm/adjust against DT-3a's audit findings before editing):**
- `src/paper/store.py` — schema migration (new nullable column) + `create_exit_event` param
- Whichever module the audit confirms writes IC exit events (see above)
- `src/strategy/ic_nifty_v1.py::check_signals` — compute the counterfactual marks/Greeks at
  14/10/7/5 DTE from the already-fetched `market: OptionChain` (no extra chain fetch needed —
  the same snapshot serves both the real signal evaluation and the counterfactual capture,
  since "what would the mark have been at DTE X" for a *past* checkpoint requires historical
  data this project doesn't warehouse per-DTE; scope this to **forward-only**: from the exit
  tick onward, log what DTE bucket triggered the exit and the mark at that moment only — do NOT
  attempt to reconstruct historical marks for DTE values already in the past relative to the
  exit tick, that requires a chain history store this project does not have. Flag this
  forward-only scoping explicitly in the commit message so a future reader doesn't assume this
  logs true retrospective counterfactuals.)
- Tests: `tests/unit/paper/test_paper_store_exit_events.py` + tests for whichever module writes
  IC events (per audit)

**New column (add via a migration script, following `scripts/dev/migrate_exit_events_decimal.py`
as the precedent for schema migrations on this table):**
```sql
ALTER TABLE paper_exit_events ADD COLUMN counterfactual_dte_marks TEXT;  -- JSON, nullable
```
JSON shape: `{"exit_dte": 7, "mark_at_exit": "45.20", "short_put_delta": "-0.12",
"short_call_delta": "0.09", "spread_pct_put": "2.1", "spread_pct_call": "1.8"}` — captured once,
at the moment any IC exit signal fires (TIME_STOP, PROFIT_TARGET, LOSS_STOP, DELTA_STOP,
ROLL_WING), not per-DTE-bucket (per the forward-only scoping above).

**Tests:**
- Happy path: exit event created with a populated `counterfactual_dte_marks` JSON string,
  round-trips through `get_exit_event`/`get_open_exit_events` unchanged
- Edge case: `counterfactual_dte_marks=None` (existing callers from `reentry_mixin.py`/
  `overlay_closer.py` that don't pass it) — column stays nullable, no regression to 3-track
  overlay exit-event tests

**Commit:** `feat(paper): counterfactual DTE-exit logging for IC time-stop validation`

---

## DT-4 — Docs Close

**Goal:** Confirm docs updated, add `TODOS.md` session log entry, update `docs/plan/README.md`
status, set a reminder for the 6-monthly-cycle review the ruling mandates. No further code
changes.

**Files to change (targeted `Edit` only, never `Write`):**
- `CONTEXT.md` — one clause on `ic_expiry_config.py`'s line noting the uniform 7-DTE terminal
  rule (and, if DT-3 shipped, that `paper_exit_events` now carries counterfactual DTE marks)
- `TODOS.md` — session log entry: DT-1..DT-4 (or DT-1/DT-2 if DT-3 deferred) complete, note the
  6-monthly-cycle review date is not yet due
- `docs/plan/README.md` — add a row for `ic-time-stop-dte-tiering/` under "Active Stories" (or
  move to a "Shipped/Archived" line if all four tasks landed) — follow the exact table format
  already used for the other rows in that file
- `DECISIONS.md` — not needed again; DT-2 already added the entry

**Verify:**
- `python -m pytest tests/unit/ --tb=no -q` green
- All four (or however many shipped) tasks in `tasks.md` ticked with SHAs
- No stray uncommitted changes (`git status`)

**Commit:** `docs: ic-time-stop-dte-tiering session close`
