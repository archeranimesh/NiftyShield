# Logging Standard Migration Completion — Story

**Source:** `docs/plan/full-repo-review/findings/FR-7_synthesis.md`, FR-7 row 7 (CRITICAL) — FR-4 §1.

## T1

Mechanical batch fix, good Antigravity handoff shape (many files, zero design ambiguity): replace `logging.getLogger(__name__)` with `structlog.get_logger(__name__)` in all 21 `src/` files listed above (import swap from `logging` to `structlog` where not already imported). Add the required `setup_logging()` call (with the `_SCRIPT_NAME` convention per LOGGING.md, since these are entrypoints not library modules) to the 24 `scripts/` files currently missing it — re-derive the exact file list with `grep -rL "setup_logging(" scripts --include=*.py` before starting, since the count may have shifted since this finding was written. Extend the `no-script-main-logger` pre-commit hook to also flag bare `logging.getLogger(__name__)` in `src/` (currently only checks `scripts/`). Tests: existing test suite must stay green (`python -m pytest tests/unit/ --tb=no -q`); no new tests required since this is a logging-call substitution, not new logic — but spot-check that structured JSON output still parses for 2-3 changed files.

**Files touched:** 21 `src/` files (listed in origin), 24 `scripts/` files, `.claude/hooks/no-script-main-logger` (or equivalent pre-commit config)

**Tests:** happy-path + error/edge-case per CLAUDE.md Step 4, in the files listed above.
