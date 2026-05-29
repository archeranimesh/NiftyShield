# dev-foundation — Engineering Excellence Epic

> Root epic for developer tooling, CI pipeline, and code health.
> All three stories are independent of production logic — no BrokerClient, no SQLite, no Upstox API.
> Start with `dx-foundation` (prerequisite for CI). The other two can run in any order after that.

---

## Story Index

| Folder | What it covers | Owner | Status |
|--------|---------------|-------|--------|
| `dx-foundation/` | pyproject.toml, ruff, mypy, pre-commit, Makefile, post-commit hook | Mixed (see story) | ⬜ Not started |
| `ci-pipeline/` | GitHub Actions CI, pytest-cov threshold, pytest-xdist, pytest-randomly | Antigravity | ⬜ Not started |
| `code-health/` | Duplicate scan, dead code, GLOSSARY.md, __all__, Mermaid C4, structlog, pydantic-settings, healthcheck.py, hypothesis | Mixed (see story) | ⬜ Not started |

---

## Ordering

```
dx-foundation  →  ci-pipeline
                  code-health    (parallel, independent)
```

`ci-pipeline` depends on `dx-foundation` because CI calls `make ci`.
`code-health` has no hard dependency but should run on a green CI baseline.

---

## Task Execution Bifurcation

### Claude tasks (8 total — judgment, domain knowledge, architectural synthesis)

| Task | Story | Why Claude |
|------|-------|------------|
| DX-3 | dx-foundation | Decides which modules get `mypy --strict` first — not mechanical |
| DX-7 | dx-foundation | Docs close requires synthesis across multiple changes |
| CI-5 | ci-pipeline | Docs close + DECISIONS.md rationale for no-CD decision |
| CH-1 | code-health | Interprets pylint similarity output — classifies what to dedup vs keep |
| CH-2 | code-health | Interprets vulture output — classifies what is truly dead vs dynamically used |
| CH-3 | code-health | GLOSSARY.md — requires trading domain knowledge |
| CH-5 | code-health | Mermaid C4 diagram — requires architectural understanding of all modules |
| CH-7a | code-health | Defines `Settings` model — must enumerate all env vars across codebase |
| CH-9a | code-health | Designs hypothesis edge cases — requires understanding of financial invariants |
| CH-10 | code-health | Docs close |

### Antigravity tasks (14 total — mechanical, multi-file, clear spec)

| Task | Story | Why Antigravity |
|------|-------|-----------------|
| DX-1 | dx-foundation | `pyproject.toml` — mechanical config, exact spec in story |
| DX-2 | dx-foundation | `ruff` config — mechanical config |
| DX-4 | dx-foundation | `.pre-commit-config.yaml` — mechanical config |
| DX-5 | dx-foundation | `Makefile` — mechanical, exact targets specified |
| DX-6 | dx-foundation | Post-commit hook + install script — mechanical shell scripts |
| CI-1 | ci-pipeline | GitHub Actions YAML — mechanical, fully specced |
| CI-2 | ci-pipeline | pytest-xdist config + slow test tagging — multi-file, TDD loop |
| CI-3 | ci-pipeline | pytest-randomly verification — multi-file, deterministic |
| CI-4 | ci-pipeline | Coverage upload wiring — mechanical YAML addition |
| CH-4 | code-health | `__all__` in all `__init__.py` — spans N files, purely mechanical |
| CH-6 | code-health | `setup_logging()` + wire into all scripts — multi-file, clear spec |
| CH-7b | code-health | Replace `os.getenv()` with `Settings` — grep-driven mechanical substitution |
| CH-8 | code-health | `scripts/healthcheck.py` — clear spec, no domain ambiguity |
| CH-9b | code-health | Implements `@given` tests from Claude's CH-9a design spec |

---

## Council

No council required for any story in this epic. None of the decisions are load-bearing,
costly to reverse, or span multiple disciplines simultaneously. All tooling choices have
clear community consensus (ruff, mypy, GitHub Actions).

---

## What this epic does NOT include

- No changes to `src/` business logic
- No new DB tables or migrations
- No BrokerClient or Upstox API changes
- No paper trading or backtest logic
