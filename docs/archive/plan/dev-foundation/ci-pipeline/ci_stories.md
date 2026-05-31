# ci-pipeline — Story Specs

> One task per session. Find the first unchecked item in `ci_tasks.md`.
> After each task: tick `ci_tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md`.

---

## CI-1 — `.github/workflows/ci.yml`

**Owner:** Antigravity
**Files to create:**
- `.github/workflows/ci.yml`

**What to implement:**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: "pip"

      - name: Install dependencies
        run: pip install -e ".[dev]" --break-system-packages

      - name: Run CI
        run: make ci
        env:
          UPSTOX_ENV: test   # forces MockBrokerClient — no live API calls

      - name: Upload coverage report
        uses: actions/upload-artifact@v4
        if: matrix.python-version == '3.10'
        with:
          name: coverage-report
          path: htmlcov/
          retention-days: 7
```

**Note on secrets:** CI runs with `UPSTOX_ENV=test` which forces `MockBrokerClient`. No
real API tokens are required. Do NOT add any secrets to GitHub Actions for this story.
`@pytest.mark.sandbox` tests are excluded by default — they never run in CI.

**Verify:** Push a trivial change to a branch and confirm the Actions tab shows the workflow
running. (If push access is unavailable in the session, verify the YAML is syntactically
valid with `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`)

**Commit message:**
```
chore(ci): add GitHub Actions CI workflow

Why: automated regression gate on every push and PR to main
What:
- .github/workflows/ci.yml: matrix Python 3.10/3.11, make ci, coverage artifact
Ref: dev-foundation/ci-pipeline CI-1
```

---

## CI-2 — `pytest-xdist` parallel config + `@pytest.mark.slow`

**Owner:** Antigravity
**Files to change:**
- `pyproject.toml` — add `-n auto` to default pytest addopts for CI; keep serial for local
- `Makefile` — `test` target uses `-n auto`; add `test-serial` target for debugging
- Scan `tests/unit/` for tests that do real I/O or take > 2s — mark with `@pytest.mark.slow`

**What to implement:**

In `pyproject.toml`:
```toml
[tool.pytest.ini_options]
addopts = "-n auto"   # parallel by default
```

In `Makefile`:
```makefile
test:
	python -m pytest tests/unit/ --tb=short -q -n auto

test-serial:
	python -m pytest tests/unit/ --tb=short -q -p no:randomly
```

**Slow test candidates** (search for these patterns — they likely need `@pytest.mark.slow`):
- Any test that writes to `data/` real paths
- Any test using `tmp_path` that also calls external processes
- Tests in `tests/unit/backtest/` that read Parquet files

**Verify:** `make test` must pass with parallel execution. If any test fails only with `-n auto`
(passes serially), it is order-dependent — investigate before marking as slow.

**Commit message:**
```
chore(tests): enable pytest-xdist parallel execution and mark slow tests

Why: 1449 tests serially take ~60s; parallel cuts to ~15s
What:
- pyproject.toml: addopts = "-n auto"
- Makefile: test-serial target for debugging
- tests/unit/: @pytest.mark.slow on identified slow tests
Ref: dev-foundation/ci-pipeline CI-2
```

---

## CI-3 — `pytest-randomly` + order-independence verification

**Owner:** Antigravity
**Files to change:**
- `pyproject.toml` — no change needed (pytest-randomly auto-activates when installed)
- `Makefile` — `test-serial` target already has `-p no:randomly`

**What to implement:**

`pytest-randomly` is already in dev deps (DX-1). It auto-activates and randomises test
order on every run using a seed printed to the console.

Run the full suite 3 times with different seeds:
```bash
python -m pytest tests/unit/ --tb=short -q --randomly-seed=1001
python -m pytest tests/unit/ --tb=short -q --randomly-seed=2002
python -m pytest tests/unit/ --tb=short -q --randomly-seed=3003
```

If any run fails where others pass: the failing test is order-dependent. Fix the isolation
(use `tmp_path`, proper fixtures, no shared mutable state) before committing.

If all three pass: confirm by adding `--randomly-seed=last` to `Makefile`'s `ci` target
so CI always prints the seed used (makes failures reproducible).

**Commit message:**
```
chore(tests): verify test order independence with pytest-randomly

Why: order-dependent tests mask real bugs and fail non-deterministically in CI
What:
- Makefile: ci target logs --randomly-seed=last for reproducibility
- tests/unit/: fixed any isolation issues found during 3-seed verification
Ref: dev-foundation/ci-pipeline CI-3
```

---

## CI-4 — Coverage upload to GitHub Actions summary

**Owner:** Antigravity
**Files to change:**
- `.github/workflows/ci.yml` — add coverage comment step
- `pyproject.toml` — add `[tool.coverage.report]` config

**What to implement:**

In `pyproject.toml`:
```toml
[tool.coverage.run]
source = ["src"]
omit = ["src/analytics/*", "src/sandbox/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "@abstractmethod",
]
fail_under = 80
```

In `.github/workflows/ci.yml`, replace the `make ci` step with:
```yaml
- name: Run tests with coverage
  run: |
    python -m pytest tests/unit/ --cov=src --cov-report=xml \
        --cov-report=term-missing -n auto -q
  env:
    UPSTOX_ENV: test

- name: Coverage summary
  uses: irongut/CodeCoverageSummary@v1.3.0
  with:
    filename: coverage.xml
    badge: true
    fail_below_min: true
    thresholds: "70 80"
    output: both
    format: markdown
    hide_complexity: true
```

**Verify:** Coverage XML is generated at `coverage.xml`. The GitHub Actions summary tab shows
the coverage table on the next CI run.

**Commit message:**
```
chore(ci): add coverage threshold enforcement and GitHub Actions summary

Why: coverage gate prevents new code from shipping untested
What:
- pyproject.toml: [tool.coverage.run] + [tool.coverage.report] with fail_under=80
- .github/workflows/ci.yml: coverage XML + summary action
Ref: dev-foundation/ci-pipeline CI-4
```

---

## CI-5 — Docs close

**Owner:** Claude
**Files to change:**
- `CONTEXT.md` — add CI section: workflow file, badge, coverage threshold
- `DECISIONS.md` — add entry: no CD rationale (manual deploy for live trading system)
- `TODOS.md` — mark ci-pipeline complete, session log entry
