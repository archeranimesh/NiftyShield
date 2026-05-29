# dx-foundation — Story Specs

> One task per session. Find the first unchecked item in `dx_tasks.md`.
> After each task: tick `dx_tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md`.

---

## DX-1 — `pyproject.toml`: project metadata + dev dependencies

**Owner:** Antigravity
**Files to create/change:**
- `pyproject.toml` — new file at repo root

**What to implement:**

```toml
[project]
name = "niftyshield"
version = "0.1.0"
requires-python = ">=3.10"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "pytest-xdist>=3.0",
    "pytest-randomly>=3.0",
    "hypothesis>=6.0",
    "ruff>=0.4",
    "mypy>=1.10",
    "pre-commit>=3.0",
    "detect-secrets>=1.4",
    "commitizen>=3.0",
    "vulture>=2.0",
    "bandit>=1.7",
    "pylint>=3.0",
    "structlog>=24.0",
    "pydantic-settings>=2.0",
]

[tool.pytest.ini_options]
testpaths = ["tests/unit"]
asyncio_mode = "auto"
markers = [
    "slow: marks tests as slow (deselect with '-m not slow')",
    "sandbox: marks tests requiring Upstox sandbox token",
]
```

Do not add `[tool.ruff]` or `[tool.mypy]` sections here — those come in DX-2 and DX-3.

**Verify:** `pip install -e ".[dev]" --break-system-packages` must complete without error.
Run `python -m pytest tests/unit/ --tb=no -q` — all existing tests must stay green.

**Commit message:**
```
chore(root): add pyproject.toml with dev dependency declarations

Why: single install command replaces ad-hoc pip installs each session
What:
- pyproject.toml: project metadata + dev extras + pytest config
Ref: dev-foundation/dx-foundation DX-1
```

---

## DX-2 — `ruff` configuration in `pyproject.toml`

**Owner:** Antigravity
**Files to change:**
- `pyproject.toml` — append `[tool.ruff]` and `[tool.ruff.lint]` sections

**What to implement:**

```toml
[tool.ruff]
line-length = 100
target-version = "py310"
exclude = ["docs/", "data/", ".git/"]

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "UP",  # pyupgrade
]
ignore = [
    "E501",  # line too long — ruff format handles this
    "B008",  # do not perform function calls in default args (Pydantic validators)
]

[tool.ruff.lint.isort]
known-first-party = ["src"]
```

**Verify:** `ruff check src/ scripts/` must run without crashing (warnings expected; no errors).
`ruff format --check src/ scripts/` — note how many files would be reformatted (do not reformat yet — that is a separate commit to avoid polluting git blame).

**Commit message:**
```
chore(root): configure ruff lint and format rules

Why: enforce consistent style across src/ and scripts/
What:
- pyproject.toml: [tool.ruff] + [tool.ruff.lint] sections
Ref: dev-foundation/dx-foundation DX-2
```

---

## DX-3 — `mypy` configuration in `pyproject.toml`

**Owner:** Claude
**Files to change:**
- `pyproject.toml` — append `[tool.mypy]` section + per-module overrides

**What to implement:**

Start strict only on the two highest-risk modules. Everything else gets permissive defaults
while the team catches up. This avoids a wall of mypy errors on day one.

```toml
[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_ignores = true
no_implicit_optional = true

# Strict modules — financial logic and protocol boundary
[[tool.mypy.overrides]]
module = ["src.client.*", "src.paper.*"]
disallow_untyped_defs = true
disallow_any_generics = true
strict_equality = true

# Third-party without stubs — silence missing import errors
[[tool.mypy.overrides]]
module = [
    "upstox_client.*",
    "NorenRestApiPy.*",
    "dhanhq.*",
    "rapidfuzz.*",
    "duckdb.*",
]
ignore_missing_imports = true
```

**Verify:** `mypy src/client/ src/paper/` — note all errors. Do NOT fix them in this task.
Create `docs/plan/dev-foundation/dx-foundation/mypy_baseline.md` listing the error count per
module. This becomes the baseline to track against over time.

**Commit message:**
```
chore(root): add mypy configuration with phased strict rollout

Why: enforce type safety on client/paper first — highest Decimal + protocol risk
What:
- pyproject.toml: [tool.mypy] section + per-module overrides
- dx-foundation/mypy_baseline.md: error count baseline per module
Ref: dev-foundation/dx-foundation DX-3
```

---

## DX-4 — `.pre-commit-config.yaml`

**Owner:** Antigravity
**Files to create:**
- `.pre-commit-config.yaml` — repo root

**What to implement:**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        args: [--config-file=pyproject.toml]
        additional_dependencies: [pydantic>=2.0, types-requests]
        files: ^src/(client|paper)/

  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: [--baseline, .secrets.baseline]
        exclude: (tests/fixtures|\.env\.example)
```

Also create `.secrets.baseline` by running `detect-secrets scan > .secrets.baseline`.

**Note:** mypy hook is scoped to `src/client/` and `src/paper/` only (matching DX-3 strictness
boundaries). Expanding it to other modules is a future task once baseline errors are fixed.

**Install:** `pre-commit install` must run without error.

**Verify:** Make a trivial whitespace change in any `src/` file and run `git add` + `git commit --dry-run` to confirm hooks fire.

**Commit message:**
```
chore(root): add pre-commit hooks for ruff, mypy, detect-secrets

Why: block formatting/type/secrets issues before they reach the repo
What:
- .pre-commit-config.yaml: ruff + ruff-format + mypy (client/paper) + detect-secrets
- .secrets.baseline: initial clean baseline
Ref: dev-foundation/dx-foundation DX-4
```

---

## DX-5 — `Makefile`

**Owner:** Antigravity
**Files to create:**
- `Makefile` — repo root

**What to implement:**

```makefile
.PHONY: test coverage lint fmt security ci dead-code index help

# Run offline unit tests (fast)
test:
	python -m pytest tests/unit/ --tb=short -q

# Run tests with coverage report + enforce threshold
coverage:
	python -m pytest tests/unit/ --cov=src --cov-report=term-missing \
	    --cov-fail-under=80 -q

# Lint + type check
lint:
	ruff check src/ scripts/
	mypy src/client/ src/paper/ --config-file=pyproject.toml

# Auto-format (modifies files)
fmt:
	ruff format src/ scripts/
	ruff check src/ scripts/ --fix

# Security scan
security:
	bandit -r src/ -ll -q
	detect-secrets scan --baseline .secrets.baseline

# Duplicate code report (advisory, does not fail)
dupes:
	pylint --disable=all --enable=similarities src/ || true

# Dead code report (advisory, does not fail)
dead-code:
	vulture src/ || true

# Full CI sequence (what GitHub Actions runs)
ci: lint test coverage security

# Re-index codebase graph (run after adding new modules)
index:
	python -c "print('Re-index via codebase-memory-mcp in your AI session')"

help:
	@grep -E '^[a-zA-Z_-]+:.*?##' Makefile | awk 'BEGIN {FS = ":.*?## "}; {printf "%-15s %s\n", $$1, $$2}'
```

**Verify:** `make test` must pass. `make lint` must run without crashing (warnings OK).
`make ci` dry-run: confirm all targets execute in sequence.

**Commit message:**
```
chore(root): add Makefile with standard dev targets

Why: single entry point for test/lint/ci — used by pre-commit and GitHub Actions
What:
- Makefile: test, coverage, lint, fmt, security, ci, dupes, dead-code, index targets
Ref: dev-foundation/dx-foundation DX-5
```

---

## DX-6 — Post-commit hook + install script

**Owner:** Antigravity
**Files to create:**
- `scripts/dev/install_hooks.sh` — installs pre-commit + post-commit hooks
- `scripts/dev/post_commit_hook.sh` — the post-commit hook body

**What to implement:**

`scripts/dev/post_commit_hook.sh`:
```bash
#!/bin/bash
# Post-commit: remind to re-index codebase graph if src/ or scripts/ changed
CHANGED=$(git diff --name-only HEAD~1 HEAD 2>/dev/null | grep -E '^(src|scripts)/')
if [ -n "$CHANGED" ]; then
    echo "⚡ src/ or scripts/ changed — run 'make index' in your AI session to re-index the graph."
fi
```

`scripts/dev/install_hooks.sh`:
```bash
#!/bin/bash
set -e
echo "Installing pre-commit hooks..."
pre-commit install
echo "Installing post-commit hook..."
cp scripts/dev/post_commit_hook.sh .git/hooks/post-commit
chmod +x .git/hooks/post-commit
echo "Done. Run 'make ci' to verify everything is wired."
```

Add to `README.md` (dev setup section, or create if absent):
```
## Developer setup
pip install -e ".[dev]"
bash scripts/dev/install_hooks.sh
```

**Commit message:**
```
chore(scripts): add hook installer and post-commit graph re-index reminder

Why: graph goes stale silently after src/ changes; reminder enforces discipline
What:
- scripts/dev/install_hooks.sh: installs pre-commit + post-commit in one command
- scripts/dev/post_commit_hook.sh: echoes re-index reminder when src/ touched
Ref: dev-foundation/dx-foundation DX-6
```

---

## DX-7 — Docs close

**Owner:** Claude
**Files to change:**
- `CONTEXT.md` — add "Developer Tooling" section listing pyproject.toml, Makefile, pre-commit
- `DECISIONS.md` — add entry: mypy phased rollout rationale
- `TODOS.md` — mark dx-foundation complete, add session log entry

**No commit needed** — docs close is bundled with the last code commit or done as a standalone
`docs` commit if DX-6 and DX-7 are separate sessions.
