# code-health — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec: `health_stories.md`.
>
> CH-1/2/3/5/7(define)/9(design) → Claude | CH-4/6/7(implement)/8/9(implement) → Antigravity

---

## Scan tasks (one-time, advisory — run before starting implementation tasks)

- [x] **CH-1** — Run `pylint --enable=similarities` across `src/`; produce `docs/plan/dev-foundation/code-health/duplication_report.md` — **Claude** | SHA: 11b7e36
- [x] **CH-2** — Run `vulture src/`; produce `docs/plan/dev-foundation/code-health/dead_code_report.md` — **Claude** | SHA: 55eef02

## Docs / structure tasks

- [ ] **CH-3** — Create `GLOSSARY.md` at repo root (~40 domain terms) — **Claude**
- [ ] **CH-4** — Add `__all__` to all `src/` `__init__.py` files — **Antigravity**
- [ ] **CH-5** — Create `docs/architecture.md` with Mermaid C4 container diagram — **Claude**

## Runtime quality tasks

- [ ] **CH-6** — Create `src/utils/logging.py` with `setup_logging()` (structlog JSON); wire into all scripts — **Antigravity**
- [ ] **CH-7a** — Claude: define `Settings` model in `src/config.py` mapping all env vars — **Claude**
- [ ] **CH-7b** — Replace all `os.getenv()` calls in `scripts/` and `src/` with `Settings` — **Antigravity**
- [ ] **CH-8** — Create `scripts/healthcheck.py` (snapshot recency + DB + Telegram alert) — **Antigravity**

## Test quality tasks

- [ ] **CH-9a** — Claude: design `hypothesis` edge cases for `compute_ivr`, `aggregate_delta`, P&L arithmetic — **Claude**
- [ ] **CH-9b** — Implement `@given` tests from CH-9a design — **Antigravity**

## Close

- [ ] **CH-10** — Docs close: `CONTEXT.md`, `DECISIONS.md`, `TODOS.md` — **Claude**
