# Root doc organization — prompt

> Cut the always-loaded root markdown to live context only, guard it with tooling, and standardize the `docs/plan/` story & epic format.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

22 markdown files sat at repo root (~1.05 MB / ~260K tokens). The conditional-loading table in `CLAUDE.md` already kept most of them out of the default session context — that part worked. The problems
were narrower: `CONTEXT.md` is read every session and was ~20K tokens with a pathological 18,740-char line; `AGENTS.md` (409 lines) was a drifted near-duplicate of `CLAUDE.md` (351 lines), so two
sources of truth for one protocol; `DECISIONS.md` was 336 KB / 2,302 lines with no index; nothing guarded against the next long-line regression; and no routine kept the docs current against the day's
commits.

RDO-17 was added later (2026-08-29) after the same review surfaced a second problem: the ~30 `docs/plan/` story folders had drifted into five different layouts, so `/work` could not reliably descend
an epic and a reader could not tell a story folder from an epic root. RDO-17 standardizes the format; RDO-17.5/17.6 are the two proof-of-concept full conversions that calibrate whether the remaining
~25 legacy folders get the same treatment.

## Scope guard

Docs + tooling only. No `src/` behaviour change. The only code touched is under `scripts/dev/hooks/` (the `md-line-length`, `check_story_structure`, `check_checkbox_consistency` hooks and their unit
tests) plus `.pre-commit-config.yaml`. Skill and hook markdown under `.claude/` and `.agents/` is in bounds. Nothing is deleted — content that leaves root is relocated under `docs/` or `docs/archive/`
with a pointer stub where another doc links to it. Every root-doc edit is a targeted `Edit`, never a `Write`.

## Session-start load hints

- `docs/plan/README.md` §Conventions — the canonical story/epic format and the markdown line style; every RDO-17.x task depends on it.
- `LOGGING.md` + the two hook scripts under `.claude/hooks/` — only for RDO-11 (graduating the doc-freshness hooks).
- No module `CLAUDE.md`, `REFERENCES.md`, `BACKTEST_PLAN.md`, `LITERATURE.md`, or council file applies — this story touches no domain code.
- This story has no `schema.md` — it changes no DB schema.

## Task overview

- **RDO-1** — slim `CONTEXT.md` to always-load core; module prose → `CONTEXT_TREE.md`.
- **RDO-2** — rewrite `AGENTS.md` as a standalone Antigravity-adjusted mirror of `CLAUDE.md`.
- **RDO-3** — (closed partial) lift 5 historical sections out of `DECISIONS.md`; real shrink → RDO-9.
- **RDO-4** — relocate `BUGS.md` + `GLOSSARY.md` out of root, fix inbound links.
- **RDO-5** — add the `md-line-length` pre-commit hook (200-char cap) + tests.
- **RDO-6** — `md-cleanup` → `md-organize` skill rewrite; clear the repo-wide line-length backlog.
- **RDO-7** — report-only `DOC STALENESS` content-gap check in `session-close`.
- **RDO-8** — 5 protocol-doc consistency fixes across `CLAUDE.md` / `AGENTS.md` / `ANTIGRAVITY.md`.
- **RDO-9** — semantic split of `DECISIONS.md` (rules stay, work-log → archive).
- **RDO-10** — reconcile RDO-7 / Phase 7 with the two shipped doc-freshness hooks.
- **RDO-11** — graduate the advisory doc-freshness hooks to enforcing (date-gated ≥ 2026-09-03).
- **RDO-12** — unified `/work` session entry point (delivered via the `session-entry-point` epic).
- **RDO-13** — make `docs/plan/README.md` §Conventions enforceable; cut `TODOS.md` to pointer-only.
- **RDO-14** — split `TODOS.md` into pointer-only Feature Backlog + Open Bugs.
- **RDO-15** — checkbox-consistency sweep + the one-checkbox-per-id convention.
- **RDO-16** — loop-closure check: one real session proves the doc-freshness mechanism end to end.
- **RDO-17.1** — rewrite §Conventions for the folder shapes + 5-field task line; split `_TEMPLATE/`.
- **RDO-17.2** — rework both structure hooks for the RDO-17.1 shapes + the tail-shape check.
- **RDO-17.3** — `/work` epic-descent steps; propagate the `| Review:` field.
- **RDO-17.4** — (superseded) partial structural retrofit of the two validation folders.
- **RDO-17.5** — full-convert `root-doc-organization/` to the canonical format; execute RDO-17.7 §A.
- **RDO-17.6** — full-convert `telegram-markdown-migration/` to the canonical epic format.
- **RDO-17.7** — §A fill-to-≤200 line style (shipped in 17.5); §B legacy-folder conversion rule (Owner: Animesh).

## Definition of done

Mirrors `tasks.md` §"Story done when" — read it there; that block is the whole-story completion bar and is verified at story close. In short: the always-loaded root docs are slim and
line-length-guarded, `AGENTS.md` is a live mirror, `DECISIONS.md` is rules + index only, the `md-organize` skill and the two structure hooks exist and enforce the format, and both validation folders
(`root-doc-organization/`, `telegram-markdown-migration/`) are fully converted with the hooks `--all` clean of their findings.

## Perspectives not covered

- **Merge-conflict cost during the transition.** RDO-1 and RDO-9 rewrote large sections of `CONTEXT.md` / `DECISIONS.md`, which other sessions edit often. They landed on quiet days but the plan never
  analyzed whether to freeze doc edits repo-wide during a cutover.
- **Whether `INSTRUCTION.md` should exist at all.** It is human-facing and overlaps `CLAUDE.md` + `.claude/` definitions heavily. This story only trims it; folding it into `README.md` was deferred and
  never revisited.
