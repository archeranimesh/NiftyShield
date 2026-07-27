# Technical Debt — Stories

Each entry below only gets fixed opportunistically — see the trigger condition in `tasks.md` and
the "Never a standalone commit" rule in `prompt.md`. Full spec here so that when the trigger
fires, there's no need to reconstruct context under time pressure.

## DEBT-3 — License boilerplate

Every file should get a license header once a license is chosen for the project. **This is
blocked on a decision, not on code** — do not write header-insertion tooling or pick a license
unilaterally. When Animesh decides, record the choice in `DECISIONS.md` first, then this becomes
a mechanical one-time sweep (not "alongside adjacent refactoring" — it's the one exception that
can be its own commit, since it touches every file uniformly by design).

## DEBT-5 — `test_bhavcopy_ingest.py` missing append-path coverage

`write_to_parquet`'s merge branch calls `replace_schema_metadata` when appending to an existing
Parquet file (lineage metadata preservation) — this branch has no test today. **Trigger:** next
time `test_bhavcopy_ingest.py` or `write_to_parquet` is touched for another reason (e.g. a
`docs/plan/backtest-engine/phase1/` task extending the ingest pipeline).

**Fix:** add a write-twice test — write once, write again with overlapping/adjacent data, assert
the second run's lineage metadata (`replace_schema_metadata` output) survives the merge rather
than being dropped or overwritten with defaults. `get_code_snippet("write_to_parquet")` first to
confirm current signature before writing the test.

## DEBT-6 — Leg validation + calendar data gaps for historical backtesting

Three related but independently-triggerable sub-fixes, all touching `Leg` construction /
`market_calendar`:

**DEBT-6a** — Move the hardcoded expiry whitelist (`{2026-04-07, 2026-12-29}`) from `Leg` to a
`market_calendar` YAML file. `search_graph("Leg")` to find the current hardcoded location before
touching it. **Trigger:** next time `Leg` construction or `market_calendar` is touched for
another reason.

**DEBT-6b** — Holiday YAML datasets for 2017–2025 are missing in `src/market_calendar/data/` —
historical `Leg` construction pre-2026 currently fails open (i.e. treats unknown dates as
non-holidays rather than raising). **Trigger:** next time historical/backtest `Leg` construction
is touched — this is a real, not hypothetical, prerequisite for
`docs/plan/backtest-engine/phase1/` tasks that construct pre-2026 `Leg`s (e.g. 1.7's CSP
backtest across 2016–present, 1.9a's integrated backtest). If a `backtest-engine/phase1` task
hits this gap, treat it as unblocking that task's own trigger — don't silently work around the
fail-open behavior.

**DEBT-6c** — Formalise the `is_nifty` check: replace the current denylist-style substring match
with an `instrument_key`-based predicate. Current implementation (confirmed via grep,
2026-07-27): `src/models/portfolio.py:189` and `src/instruments/lot_size.py:29` both do
`"NIFTY" in key_upper and not any(...)` independently — two separate ad-hoc implementations of
the same check, not a single shared denylist. **Trigger:** next time either of those two files is
touched for another reason. Fix should consolidate both call sites onto one
`instrument_key`-based predicate, not just reformat one of the two independently.

## DEBT-7 — `daily_snapshot.py` dynamic dispatch `noqa: F401` suppressions

`scripts/portfolio/daily_snapshot.py` uses dynamic dispatch with `# noqa: F401` suppressions on
what look like unused imports — these hide real broken imports if the dispatched helpers are ever
renamed or moved (the suppression would silently mask the resulting `ImportError`/`AttributeError`
until runtime). **Trigger:** next time `daily_snapshot.py`'s dynamic-dispatch block is touched.

**Fix:** replace the dynamic-dispatch-via-string-import pattern with an explicit registry (e.g. a
`dict[str, Callable]` built from direct imports) so unused-import suppressions are no longer
needed and a renamed helper fails at import time, not at dispatch time. `trace_path` on the
current dispatch function first to see every call site before restructuring.
