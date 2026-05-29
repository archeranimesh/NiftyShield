# ci-pipeline — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec: `ci_stories.md`.
>
> Owner: All tasks → Antigravity
> Prerequisite: dx-foundation fully complete

---

- [x] **CI-1** — Create `.github/workflows/ci.yml` (push/PR to main, Python 3.10, `make ci`) — **Antigravity** | SHA: d6e9899
- [ ] **CI-2** — Add `pytest-xdist` parallel config + `@pytest.mark.slow` on known slow tests — **Antigravity**
- [ ] **CI-3** — Add `pytest-randomly` to test config + verify no order-dependent failures — **Antigravity**
- [ ] **CI-4** — Wire coverage upload to GitHub Actions summary (artifact + PR comment) — **Antigravity**
- [ ] **CI-5** — Docs close: `CONTEXT.md` CI section, `DECISIONS.md` entry, `TODOS.md` log — **Claude**
