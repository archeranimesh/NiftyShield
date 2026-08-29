# Root doc organization — tasks

Token-efficiency cleanup of the ~22 root `.md` files, doc-maintenance automation, and the `docs/plan/` story-format standardization (RDO-17). Docs + tooling only — no `src/` behaviour change.
`prompt.md` says why the story exists; `stories.md` carries the per-task spec — a full forward spec for the open tasks and a short as-built digest for each shipped one; `plan.md` keeps the original
file-by-file root inventory (D6 extra file). Work top-down: the first unchecked `- [ ]` line is the task. Each task is one commit plus a follow-up that records its SHA and ticks the box.

**Open: RDO-16 (next, after RDO-6 — shipped), RDO-11 (date-gated ≥ 2026-09-03), RDO-17.8 (decided — pending close).** RDO-17.5 (`5508e41`) + RDO-17.6 (`cf46ff4`) shipped the two POC full conversions;
RDO-17.7 §A shipped the fill-to-≤200 *guidance* inside RDO-17.5 (`7d28d16`), then RDO-17.7 swept both POC folders to that style in full; RDO-17.8 (the legacy-folder rule) is decided — batch-convert
everything — and now lives as the `docs/plan/doc-format-migration/` epic.

## Tasks

- [x] **RDO-1** — slim CONTEXT.md to always-load core; module prose → CONTEXT_TREE.md, old prose archived verbatim | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: fd1bd0b
- [x] **RDO-2** — rewrite AGENTS.md as an Antigravity-adjusted standalone mirror of CLAUDE.md (+ 5a9c4f5 audit pass) | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 5c25742
- [x] **RDO-3** — closed partial — 5 historical sections lifted to docs/archive/DECISIONS_pre-2026-07.md; real shrink = RDO-9 | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 7bbfaff
- [x] **RDO-4** — BUGS.md → docs/archive/BUGS_LEGACY.md (stub), GLOSSARY.md → docs/GLOSSARY.md; all inbound links fixed | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 5bb5848
- [x] **RDO-5** — add check_md_line_length.py + md-line-length pre-commit hook (200-char cap) + 3 unit tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 7c78799
- [x] **RDO-6** — md-cleanup → md-organize skill rewrite; clear the repo-wide md-line-length backlog to --all-files green | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 3eb3834
- [x] **RDO-7** — add a report-only DOC STALENESS content-gap check to the session-close skill | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: d24f15d
- [x] **RDO-8** — 5 protocol-doc consistency fixes (CLAUDE.md / AGENTS.md / ANTIGRAVITY.md); git rm the dead .codex/ tree | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: bf26d81
- [x] **RDO-9** — semantic split of DECISIONS.md — completed-work log → docs/archive/DECISIONS_worklog_2026.md | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 2fb5c5b
- [x] **RDO-10** — reconcile RDO-7 / Phase 7 with the two shipped doc-freshness hooks; tune the staleness thresholds | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: a4431ec
- [ ] **RDO-11** — graduate the advisory doc-freshness hooks to enforcing after a ~1-week observation window | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>
- [x] **RDO-12** — unified /work session entry point — delivered via the session-entry-point epic (SEP-1..4) | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 42eabb2
- [x] **RDO-13** — §Conventions made canonical + check_story_structure.py + _TEMPLATE/; TODOS.md cut to pointer-only | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 3c50826
- [x] **RDO-14** — split TODOS.md into pointer-only Feature Backlog + Open Bugs; add the Completion→archive rule | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: e7cecab
- [x] **RDO-15** — check_checkbox_consistency.py + the one-checkbox-per-id convention (done-when blocks → prose) | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 5e48451
- [ ] **RDO-16** — loop-closure check — one real session confirms the doc-freshness mechanism works end to end | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>
- [x] **RDO-17.1** — rewrite §Conventions (folder shapes, 3-file story set, 5-field task line); _TEMPLATE/ → story/ + epic/ | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 7b6d05f
- [x] **RDO-17.2** — rework both structure hooks for the RDO-17.1 shapes + the 5-field tail check + hook unit tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: fe280bd
- [x] **RDO-17.3** — /work epic-descent steps + epic router template; propagate | Review: into 3 skills + CLAUDE.md 5a | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 28d0d9c
- [x] **RDO-17.4** — partial structural retrofit of both validation folders — superseded by RDO-17.5 / RDO-17.6 | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 35d9f42
- [x] **RDO-17.5** — full-convert root-doc-organization/ — every task line canonical, stories.md covers all tasks | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 5508e41
- [x] **RDO-17.6** — full-convert telegram-markdown-migration/ to the canonical epic format (router, Stories table) | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: cf46ff4
- [x] **RDO-17.7** — sweep both POC folders to fill-to-≤200 in full; add reusable `scripts/dev/reflow_md.py` + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 526e431
- [ ] **RDO-17.8** — legacy-folder rule (was 17.7 §B): decided — batch-convert all; execution is the `doc-format-migration/` epic | Owner: Animesh | Model: n/a | Review: none | SHA: <—>

## Story done when

Acceptance criteria — prose, no checkboxes (RDO-15 convention a). Verified at story close; per-task status lives only in the working list above, which is the single source of truth.

- **RDO-1** — CONTEXT.md ≤ 400 lines, no line > 200 chars, session-start cost ≈ 6K tokens; module prose relocated to CONTEXT_TREE.md with the old version archived verbatim.
- **RDO-2** — AGENTS.md is a full standalone protocol mirror of CLAUDE.md (Antigravity autoloads it by name; not a stub, not deleted).
- **RDO-3** — closed as a partial; the 5 self-contained historical sections are archived and the real DECISIONS.md shrink is carried by RDO-9.
- **RDO-4** — BUGS.md and GLOSSARY.md relocated out of root, stub left where linked, all inbound links fixed.
- **RDO-5** — md-line-length hook (200-char cap) added and enforcing on staged files, with check_md_line_length.py + unit tests; repo-wide --all-files green is not an RDO-5 gate.
- **RDO-6** — md-organize skill exists; the "stay at root" table matches reality; it carries the CONTEXT re-slim / DECISIONS roll / line-length sweep / CLAUDE.md pointer-reconcile / mirror re-sync
  steps.
- **RDO-7** — the session-close DOC STALENESS report is added, scoped to the content gaps the two freshness hooks cannot see (missing CONTEXT_TREE.md row for a new module; a story's README status not
  advanced).
- **RDO-8** — all 5 protocol-doc consistency fixes landed (SHA bf26d81).
- **RDO-9** — completed-work-log entries split to docs/archive/DECISIONS_worklog_2026.md; the 9a still-enforced list signed off by Animesh; md-line-length green (SHA 2fb5c5b).
- **RDO-10** — both hooks are in plan.md Phase 7 inventory with an RDO-6 verification step; #4 narrowed to a future read-only Telegram digest; md-organize name settled; thresholds tuned (SHA a4431ec).
- **RDO-11** — the hook-enforcement decision is made and recorded as a STILL-ENFORCED RULE entry in DECISIONS.md.
- **RDO-12** — the /work skill exists and routes Feature/Bug; CLAUDE.md + AGENTS.md point at it; the session-entry-point epic (SEP-1..4) is complete and archived.
- **RDO-13** — docs/plan/README.md §Conventions is canonical and self-contained; _TEMPLATE/ + check_story_structure.py exist; ticked task lines carry the Owner|Model|SHA tail (SHA 3c50826).
- **RDO-14** — TODOS.md is split into pointer-only ## Feature Backlog + ## Open Bugs; the §Conventions Completion→archive rule is added; the file reflowed (SHA e7cecab).
- **RDO-15** — check_checkbox_consistency.py runs clean across docs/plan/** + docs/bugs/; the one-checkbox-per-id convention is recorded in §Conventions + _TEMPLATE/.
- **RDO-16** — the loop-closure check passes: a stale doc is flagged at SessionStart, acted on, and the flag clears the next session (see the working-list task).
- **RDO-17** — §Conventions defines the flat-story vs epic-with-sub-stories shapes, the 3-file story set, the conditional schema.md, and the Owner|Model|Review|SHA task line; _TEMPLATE/ has story/ +
  epic/ variants; both structure hooks enforce it (legacy folders grandfathered pre-commit); /work walks an epic's sub-stories in order; root-doc-organization/ (17.5) and telegram-markdown-migration/
  (17.6) are fully converted; RDO-17.7 retires the semantic-linefeed style for fill-to-≤200 (guidance + `scripts/dev/reflow_md.py` + a full sweep of both POC folders); RDO-17.8 decided the
  legacy-folder rule (batch-convert all) → the `doc-format-migration/` epic.
- **prompt.md** — DoD rewritten to the delivered design: the dead pre-2026H1 date-cutoff line dropped, the hook rename + semantic-split reality stated (done in 2fb5c5b), realigned to
  _TEMPLATE/story/prompt.md by RDO-17.5.

RDO-1, RDO-2 done. RDO-3 closed as partial (remainder = RDO-9).

## After each task

Set `SHA:` on the task line to the real commit SHA and tick the box (the RDO-17.x tail is the full `| Owner | Model | Review | SHA` per `docs/plan/README.md` §Conventions). Update the
`docs/plan/README.md` status entry for this story and add one line to the `TODOS.md` Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do not leave it
half-archived.
