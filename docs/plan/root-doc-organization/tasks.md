# Root doc organization — tasks

Work top-down. Each phase = one commit. See `plan.md` for the file-by-file detail.
Phases 1, 3, 4, 5, 7 are independent. Phase 2 is blocked on an Animesh decision.
Phase 6 comes last (encodes final state).

- [ ] **RDO-1** — Slim `CONTEXT.md` to ≤400 lines, no line >200 chars; move module prose to
  `CONTEXT_TREE.md`. Verify: fresh `Read CONTEXT.md` returns whole file, no display-cap hit.
- [ ] **RDO-2** — AGENTS.md decision + action. **Blocked:** ask Animesh — does any non-Claude
  tool read `AGENTS.md` here? Then delete-and-migrate, or collapse to a <20-line pointer.
- [ ] **RDO-3** — Create `docs/archive/DECISIONS_ARCHIVE_2026H1.md`, move pre-2026-06-01
  entries, add date-descending `## Index` to root `DECISIONS.md`. Verify: ≤800 lines,
  inbound `DECISIONS.md#` anchors still resolve or are redirected in the index.
- [ ] **RDO-4** — Move `BUGS.md` → `docs/archive/BUGS_LEGACY.md` (3-line stub at root);
  move `GLOSSARY.md` → `docs/GLOSSARY.md` (no stub, add `CLAUDE.md` Quick-reference row).
  Fix all inbound links.
- [ ] **RDO-5** — Add `scripts/hooks/check_root_md_line_length.py` + `.pre-commit-config.yaml`
  entry `root-md-line-length`. Verify: `pre-commit run root-md-line-length --all-files` green
  after RDO-1..4.
- [ ] **RDO-6** — Rename `.claude/skills/md-cleanup/` → `md-organize/`, rewrite `SKILL.md`:
  broaden triggers, fix the "must stay at root" table, add CONTEXT.md re-slim + DECISIONS
  roll + line-length + `CLAUDE.md` pointer-reconciliation steps.
- [ ] **RDO-7** — Add report-only `DOC STALENESS` section to
  `.claude/skills/session-close/SKILL.md` (Option A in `plan.md`). Report only — no
  unattended commits.

## After each task
Tick the box, append `| SHA: <sha>`, update `docs/plan/README.md` status column for this
story, add one line to `TODOS.md` Session Log.
