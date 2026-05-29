.PHONY: test coverage lint fmt security ci dead-code help

test: ## Run offline unit tests (fast)
	python -m pytest tests/unit/ --tb=short -q -n auto

test-serial: ## Run offline unit tests serially
	python -m pytest tests/unit/ --tb=short -q -p no:randomly -o addopts=""

coverage: ## Run tests with coverage report + enforce threshold
	python -m pytest tests/unit/ --cov=src --cov-report=term-missing \
	    --cov-fail-under=80 -q

lint: ## Lint + type check
	ruff check src/ scripts/
	mypy src/ --config-file=pyproject.toml

fmt: ## Auto-format (modifies files)
	ruff format src/ scripts/
	ruff check src/ scripts/ --fix

security: ## Security scan
	bandit -r src/ -ll -q
	pre-commit run detect-secrets --all-files

dupes: ## Duplicate code report (advisory, does not fail)
	pylint --disable=all --enable=similarities src/ || true

dead-code: ## Dead code report (advisory, does not fail)
	vulture src/ || true

ci: lint test coverage security ## Full CI sequence (what GitHub Actions runs)


help: ## Show help messages for Makefile targets
	@grep -E '^[a-zA-Z_-]+:.*?##' Makefile | awk 'BEGIN {FS = ":.*?## "}; {printf "%-15s %s\n", $$1, $$2}'
