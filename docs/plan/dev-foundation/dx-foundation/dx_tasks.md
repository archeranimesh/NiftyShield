# dx-foundation — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec: `dx_stories.md`.
>
> Owner: DX-1/2/4/5/6 → Antigravity | DX-3 → Claude

---

- [x] **DX-1** — Create `pyproject.toml` (project metadata + all dev dependencies declared) — **Antigravity** | SHA: 0671073
- [x] **DX-2** — Configure `ruff` in `pyproject.toml` (lint rules + format settings) — **Antigravity** | SHA: 83e4abf
- [x] **DX-3** — Configure `mypy` in `pyproject.toml` (strict on `src/client/` + `src/paper/` first; permissive elsewhere) — **Claude** | SHA: pending-mac-commit
- [x] **DX-4** — Create `.pre-commit-config.yaml` (ruff, mypy, detect-secrets hooks) — **Antigravity** | SHA: 7f728e0
- [x] **DX-5** — Create `Makefile` (test, coverage, lint, fmt, security, ci, dead-code, index targets) — **Antigravity** | SHA: 7d4976e
- [x] **DX-6** — Add `.git/hooks/post-commit` script for graph re-index + `scripts/dev/install_hooks.sh` — **Antigravity** | SHA: 1b94b5c, cc5c78c
- [x] **DX-7** — Docs close: `CONTEXT.md` tooling section, `DECISIONS.md` entry, `TODOS.md` session log — **Claude** | SHA: 381da12
