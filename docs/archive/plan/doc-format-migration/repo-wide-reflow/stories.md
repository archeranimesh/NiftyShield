# Repo-wide reflow — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the epic `README.md` status column, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

---

## DFM-5 — reflow every in-bounds Markdown file

**Files to change:** whitespace only, across (roughly, confirm with `git ls-files '*.md'`):
- root `.md` — `CLAUDE.md`, `AGENTS.md`, `CONTEXT.md`, `CONTEXT_TREE.md`, `DECISIONS.md`, `REFERENCES.md`, `DB_REGISTRY.md`, `LOGGING.md`, `FORMATTING.md`, `REVIEW.md`, `TODOS.md`, `PLANNER.md`,
  `README.md`, `ANTIGRAVITY.md`, `LITERATURE.md`, `BACKTEST_PLAN*.md`, `GEMINI.md`, `MEMORY*.md`, … — whatever `git ls-files ':(glob)*.md'` returns.
- `docs/**` except `docs/plan/**` and `docs/archive/**` — `docs/bugs/*.md`, `docs/council/*.md`, `docs/antigravity/*.md`, `docs/GLOSSARY.md`, `docs/plan/full-repo-review/findings/*.md` is under
  `plan/` so it belongs to `plan-folders/` — double-check the boundary.
- `.claude/**/*.md` — every `SKILL.md`, agent definition, `.claude/*.md`.
- `.github/**/*.md`, and any `*.md` under `src/` / `scripts/` / `tests/`.

**Before any code:**
- `git ls-files '*.md' | grep -vE '^(docs/plan/|docs/archive/)'` — the exact in-bounds list. Reconcile against the bullets above; the glob is the source of truth.
- `python -m scripts.dev.reflow_md --check <the list>` — how many actually change.

**What to implement:**

1. Batch by directory so each commit is reviewable:
   - batch 1 — root `.md`
   - batch 2 — `docs/` (non-plan, non-archive)
   - batch 3 — `.claude/**` + `.github/**`
   - batch 4 — `src` / `scripts` / `tests` strays (likely tiny)
2. Per batch: `python -m scripts.dev.reflow_md <paths>`, then `--check` (idempotent), then `git diff --word-diff` — confirm every hunk is whitespace-only except interior `> ` blockquote markers
   consolidating when a multi-line quote rewraps to one line. If any hunk shows a real word change, stop and investigate — `reflow_md.py` is not supposed to do that.
3. Run the affected hooks: `python scripts/dev/hooks/check_md_line_length.py <changed files>` — clean.
4. After the last batch, edit `docs/plan/README.md` §"Markdown line style": remove the "two RDO-17.5/17.6 POC folders … are the reference exemplars" carve-out and the "every other legacy folder still
   reflows opportunistically … until RDO-17.8" sentence — replace with a plain statement that the whole tree is fill-to-≤200 and the `enforcement/` gate keeps it so.

**Tests:** none — docs-only. The `reflow_md.py` behaviour is already covered by `tests/unit/scripts/dev/test_reflow_md.py`.

**Commit (per batch):** `docs: DFM-5 — fill-to-≤200 <batch name>` Final batch also carries the `docs/plan/README.md` §"Markdown line style" edit.
