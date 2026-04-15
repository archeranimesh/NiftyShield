# Package marker — makes scripts/ a proper Python package so tooling
# (codebase-memory-mcp, type checkers, IDEs) can index and resolve symbols here.
# Runtime behaviour is unchanged: `python -m scripts.daily_snapshot` works with
# or without this file (namespace packages, PEP 420), but without it the indexer
# silently skips every function in this directory.
