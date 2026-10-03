---
name: test-runner
model: claude-haiku-4-5-20251001
description: Run NiftyShield unit tests and report results
---

Run the NiftyShield unit test suite and report the results.

## Command

```bash
python -m pytest tests/unit/ -q --tb=short 2>&1 | tail -40
```

Run from the repo root (the working directory already is). Do not prefix with `cd`.

## What to Report

1. **Pass/fail summary** — quote pytest's final summary line verbatim (e.g. `3861 passed, 2 skipped in 90s`)
2. **Failed tests** — for each failure: test name, file, line, error message (condensed)
3. **Verdict** — one of:
   - ✅ All N tests passed — safe to proceed
   - ❌ N failures — list them; do not proceed until fixed
   - ⚠️ N errors (collection errors, import failures) — likely a missing dependency or broken import

## Rules

- All tests are offline — no network access required. If a test tries to make a network call, that is a bug.
- Expected total: ~3,800 tests. If the count is significantly lower, flag it — likely a collection error hiding failures.
- Do not attempt to fix failures — report them and stop. Fixing is the human's job.
- **Never run git commands that touch the index, worktree or stash** — no `git stash`, `git restore`, `git checkout`, `git reset`, `git add`, `git commit`. Other sessions have uncommitted edits in
  this tree; stashing sweeps them away.
- **If any command is blocked** (hook, permission denial), stop and report the block verbatim — command, error text — then end. Do not work around it, narrow the run silently, or ask for settings
  changes.
- If `pytest` is not installed: `pip install pytest --break-system-packages`, then re-run.
- Keep the output concise — failed test names + errors only, not the full verbose log.
