---
model: claude-haiku-4-5
description: Run NiftyShield unit tests and report results
---

Run the NiftyShield unit test suite and report the results.

## Command

```bash
cd /path/to/NiftyShield && python -m pytest tests/unit/ -v --tb=short 2>&1
```

Use the actual repo path from the working directory context.

## What to Report

1. **Pass/fail summary** — total tests, passed, failed, errors, skipped
2. **Failed tests** — for each failure: test name, file, line, error message (condensed)
3. **Verdict** — one of:
   - ✅ All N tests passed — safe to proceed
   - ❌ N failures — list them; do not proceed until fixed
   - ⚠️ N errors (collection errors, import failures) — likely a missing dependency or broken import

## Rules

- All tests are offline — no network access required. If a test tries to make a network call, that is a bug.
- Expected total: ~400 tests. If count is significantly lower, flag it — likely a collection error hiding failures.
- Do not attempt to fix failures — report them and stop. Fixing is the human's job.
- If `pytest` is not installed: `pip install pytest --break-system-packages`, then re-run.
- Keep the output concise — failed test names + errors only, not the full verbose log.
