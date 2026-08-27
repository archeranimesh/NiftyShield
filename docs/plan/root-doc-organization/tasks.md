# Root doc organization — tasks

Work top-down. Each phase = one commit. See `plan.md` for the file-by-file detail.
RDO-1 and RDO-2 are done. RDO-3, 4, 5, 7, 8 are independent. RDO-6 comes last (encodes
final state). RDO-8 was spun out of the RDO-2 audit and feeds RDO-5/RDO-6.

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
  trio), and replaced the stale 120-line "Imported Claude Cowork" appendix with a trimmed
  "Antigravity Reference" — Decimal/TEXT + UTC + async invariants inline, everything else
  (env vars, BrokerClient impl table, exception hierarchy) as pointers to `src/config.py` /
  `src/client/CLAUDE.md` / `ANTIGRAVITY.md` to avoid re-drift. Long-line wrap deferred to
  RDO-5/6 (mirror stays line-for-line with the un-wrapped `CLAUDE.md`; wrap both together).
  Follow-up `5a9c4f5`: audit pass fixed a non-existent `UpstoxSandboxClient`, an incomplete
  hand-maintained env table, and a restated exception list — all → pointers; added async
  conventions Antigravity can't see from the global `~/.claude/CLAUDE.md`. Open items the
  audit surfaced → **RDO-8**. Docs-only, no code-reviewer. | SHA: 5c25742
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
- [ ] **RDO-8** — Protocol-doc consistency cleanup (surfaced by the RDO-2 audit,
  2026-08-27). Independent of RDO-3..7; can be done in any order. Each bullet is a small
  targeted fix — one commit for the lot is fine since they are all protocol/doc consistency.
  1. **Docs-only commit gate conflict.** `ANTIGRAVITY.md` §"Commit Protocol" step 2 requires a
     `code-reviewer.md` + `REVIEW.md` persona review even for a docs/config-only commit;
     `CLAUDE.md` 5c and `AGENTS.md` 5c both say docs-only → skip `code-reviewer` entirely.
     Pick one rule and make all three files agree (recommend: keep the skip, it is the lighter
     and more-used path — align `ANTIGRAVITY.md` to it).
  2. **Dead `.agents/skills/` + `.codex/hooks/` trees.** Created by commit `16821d6`
     ("Codex protocol scaffolding"). `AGENTS.md` and `ANTIGRAVITY.md` now both point only at
     `.claude/…`. Confirm nothing reads `.agents/` or `.codex/` (grep configs, ask Animesh
     whether any Codex/Antigravity runner still references them), then delete both trees or
     leave a one-line pointer stub. If kept, add them to the `md-organize` re-sync scope.
  3. **`CLAUDE.md` module table stale.** Lists 5 `src/<module>/CLAUDE.md` rows; 8 exist on
     disk (missing `paper`, `nuvama`, `gamma`). Add the 3 missing rows to `CLAUDE.md`; then
     the `AGENTS.md` "also present on disk" note can be folded back into the main table so the
     two match line-for-line again. (Overlaps RDO-6's `CLAUDE.md` pointer-reconciliation step
     — do whichever lands first, then drop the dup from the other.)
  4. **`src/client/CLAUDE.md` "Four Implementations" heading.** Only 2 concrete `BrokerClient`
     classes are built (`UpstoxLiveClient`, `MockBrokerClient`); the table's other 2 rows are
     a token-variant and an unbuilt `ReplayMarketStream`. Reword the heading/table so the
     count is not misleading (e.g. "Implementations (2 built + 1 variant + 1 planned)").
  5. **`AGENTS.md` ↔ `CLAUDE.md` structural divergence for re-sync.** RDO-2 pulled CLAUDE.md's
     embedded "Rules for any review" (points 1–3, inside its AI-Collaboration section) into a
     standalone `## Rules for any review or handoff` section in `AGENTS.md`. Either lift
     `CLAUDE.md` to the same structure or document the delta in the RDO-6 re-sync step so the
     diff stays predictable.

## After each task
Tick the box, append `| SHA: <sha>`, update `docs/plan/README.md` status column for this
story, add one line to `TODOS.md` Session Log.
