# dev-foundation — Engineering Excellence Epic

> Root epic for developer tooling, CI pipeline, and code health.
> All three stories are independent of production logic — no BrokerClient, no SQLite, no Upstox API.
> Start with `dx-foundation` (prerequisite for CI). The other two can run in any order after that.

---

## Story Index

| Folder | What it covers | Owner | Status |
|--------|---------------|-------|--------|
| `dx-foundation/` | pyproject.toml, ruff, mypy, pre-commit, Makefile, post-commit hook | Mixed (see story) | ✅ Complete (DX-1 → DX-7 all shipped) |
| `ci-pipeline/` | GitHub Actions CI, pytest-cov threshold, pytest-xdist, pytest-randomly | Antigravity | ✅ Complete (CI-1 → CI-5 all shipped) |
| `code-health/` | Duplicate scan, dead code, GLOSSARY.md, __all__, Mermaid C4, structlog, pydantic-settings, healthcheck.py, hypothesis | Mixed (see story) | ✅ Complete (CH-1 → CH-10 shipped; CH-4 permanently skipped — see note) |

**CH-4 skip note:** Empty `__all__ = []` is worse than no `__all__` — it hides symbols and contradicts the codebase's explicit import pattern. Revisit only if the codebase shifts to re-exporting from package roots. See TODOS.md backlog for conditions.

---

## Epic Completion Summary

**Closed 2026-05-31.** All 21 tasks shipped across three sub-epics (1 permanently skipped by design).

| Sub-epic | Tasks | Shipped | Skipped | Key deliverables |
|----------|-------|---------|---------|-----------------|
| dx-foundation | 7 | 7 | 0 | `pyproject.toml`, ruff, mypy phased strict, pre-commit, Makefile, post-commit graph hook |
| ci-pipeline | 5 | 5 | 0 | GitHub Actions CI, pytest-xdist parallel, pytest-randomly, coverage gate 80%, PR summary action |
| code-health | 10 | 9 | 1 (CH-4) | `GLOSSARY.md`, `docs/architecture.md`, `src/config.py` (Settings), `src/utils/logging.py` (structlog), `scripts/healthcheck.py`, hypothesis tests on financial math |

**Remaining operational step:** Wire `scripts/healthcheck.py` cron — `30 16 * * 1-5`. See TODOS.md near-term actions.

---

## Next Implementation

The `dev-foundation` epic is the prerequisite for everything that follows. The next items in priority order:

**1. Build queue #3 — scripts-restructure SR1** (`docs/plan/scripts-restructure/`)
Scaffold only: create subdirectory `__init__.py` files under `scripts/` (`pipeline/`, `lookup/`, `record/`, `strategies/`, `seed/`, `council/`, `dev/`). ~30 min. Must run before paper-backbone so new daemon scripts land in the correct folder from day one. No file moves — SR2+ is post-market and lower urgency.

**2. Build queue #4 — paper-backbone: Strategy Monitor Daemon** (`docs/plan/paper-backbone/`)
Prerequisite for paper-exit-signals (#5). Core deliverables: `PaperStrategy` protocol, `StrategyMonitor`, `PaperExecutor`, `RapidCouncil`, `TelegramGateway`, DB migrations, daemon scripts. Hard deadline: Jun–Jul 2026.

**3. Build queue #5 — paper-exit-signals: Automated Exit Detection + Closure** (`docs/plan/paper-exit-signals/`)
Blocked by #4 PT-0. Council authority: `docs/council/2026-05-28_paper-trade-exit-philosophy.md` — all 10 thresholds binding.

**Start point:** Run SR1 first (scaffold is 1 commit, zero risk), then begin paper-backbone PT-0.

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
