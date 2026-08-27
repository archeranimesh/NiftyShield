# Root doc organization — tasks

Work top-down. Each phase = one commit. See `plan.md` for the file-by-file detail.
Phases 1, 3, 4, 5, 7 are independent. Phase 2 is blocked on an Animesh decision.
Phase 6 comes last (encodes final state).

- [x] **RDO-1** — Slim `CONTEXT.md` to ≤400 lines, no line >200 chars; move module prose to
  `CONTEXT_TREE.md`. Verify: fresh `Read CONTEXT.md` returns whole file, no display-cap hit.
  Done 2026-08-27: 159 lines, max 199 chars, ~2.6K tokens (was ~20K). Full-file `Read` clean.
  Old prose archived verbatim → `docs/archive/CONTEXT_WHAT_EXISTS_2026-08.md`; `CONTEXT_TREE.md`
  enriched with the missing structural facts (`overlay_coverage.py`, `notifications/formatting.py`,
  Developer + Research tooling sections). Note: `CONTEXT_TREE.md` still has pre-existing >200-char
  lines — full re-wrap deferred to RDO-5/RDO-6 (RDO-1 DoD gates `CONTEXT.md` only). | SHA: fd1bd0b
- [x] **RDO-2** — AGENTS.md decision + action. Animesh 2026-08-27: Antigravity autoloads
  `AGENTS.md` by name; it must stay a full standalone protocol equivalent to `CLAUDE.md` — do
  not delete. Action taken: rewrote `AGENTS.md` as a faithful, Antigravity-adjusted mirror of
  the current `CLAUDE.md` (agent identity → Antigravity; broken `.Codex/…` paths → `.claude/…`;
  module refs corrected to `CLAUDE.md`), added back the ~6 sections `CLAUDE.md` gained since the
  fork (Logging-standard/`no-script-main-logger`, Step 2b authoritative-mechanism, Step 3b
  independence note, full Quick-ref rows, `docs/plan/README.md` in 5a, Step 5d, review-rules
  trio), and replaced the stale 120-line "Imported Claude Cowork" appendix with a trimmed,
  corrected "Antigravity Reference" section (current env vars, BrokerClient composition-root,
  Decimal/TEXT + UTC invariants, pointer to `ANTIGRAVITY.md`). Long-line wrap deferred to
  RDO-5/6 (mirror stays line-for-line with the un-wrapped `CLAUDE.md`; wrap both together).
  Docs-only, no code-reviewer. | SHA: 5c25742
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
  roll + line-length + `CLAUDE.md` pointer-reconciliation steps. **Add (RDO-2):** an
  "AGENTS.md ← CLAUDE.md re-sync" step — diff the two protocol bodies and re-apply the
  Antigravity deltas whenever `CLAUDE.md` changed since the last sync.
- [ ] **RDO-7** — Add report-only `DOC STALENESS` section to
  `.claude/skills/session-close/SKILL.md` (Option A in `plan.md`). Report only — no
  unattended commits.

## After each task
Tick the box, append `| SHA: <sha>`, update `docs/plan/README.md` status column for this
story, add one line to `TODOS.md` Session Log.
