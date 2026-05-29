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
