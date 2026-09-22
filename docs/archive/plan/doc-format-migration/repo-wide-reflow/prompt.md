# Repo-wide reflow — prompt

> Fill-to-≤200 every Markdown file in the repo that `plan-folders/` does not cover.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

RDO-17.7 §A retired the semantic-linefeed style for fill-to-≤200 across the repo, but only two `docs/plan/` folders were actually swept. Every other Markdown file — the root protocol docs
(`CLAUDE.md`, `AGENTS.md`, `CONTEXT.md`, `DECISIONS.md`, `REFERENCES.md`, `LOGGING.md`, `FORMATTING.md`, `TODOS.md`, `README.md`, …), everything under `docs/` outside `plan/` (`docs/bugs/`,
`docs/council/`, `docs/antigravity/`, `docs/GLOSSARY.md`, the finding syntheses), and the `.claude/skills/**/SKILL.md` set — is still a mix of old ~110-char wraps and incidental fills. This story
makes the whole tree consistent so `enforcement/`'s repo-wide `--all` gate can be turned on without a wall of findings.

## Scope guard

**In bounds:** every `*.md` in the repo **except** `docs/plan/**` (that is `plan-folders/`), `docs/archive/**` (frozen history — Scope decision), and `docs/plan/_TEMPLATE/**` (deliberately short
guidance lines). This includes root `.md`, `docs/**` outside `plan/`, `.claude/**/*.md`, `.github/**/*.md`, and any `*.md` under `src/` / `scripts/` / `tests/`.

**Out of bounds:** the *content* of any file — this is a whitespace-only reflow. `docs/bugs/` task-line *format* (stays `**BNNN.x**`). The hook scripts and CI. Anything that is not `.md`. Docs-only,
no `src/` behaviour change.

## Session-start load hints

- `docs/plan/README.md` §"Markdown line style" — the canonical rule and the `reflow_md.py` invocation.
- `scripts/dev/reflow_md.py` module docstring — what it leaves verbatim, the word-preservation contract.

## Task overview

- **DFM-5** — run `reflow_md.py` over every in-bounds `.md`, in batches by directory, verifying each batch with `--check` and `git diff --word-diff`. One commit per batch (root docs; `docs/` non-plan;
  `.claude/` + `.github/`; `src`/`scripts`/`tests` strays). Then update `docs/plan/README.md` §"Markdown line style" to say the whole tree is now fill-to-≤200, not just the POC folders.

## Definition of done

`python -m scripts.dev.reflow_md --check` is clean on every `.md` in the repo except `docs/archive/**` and `docs/plan/_TEMPLATE/**`; every commit's diff is whitespace-only on reflow hunks (the sole
allowed non-whitespace delta is an interior `> ` blockquote marker consolidating on rewrap); `docs/plan/README.md` §"Markdown line style" no longer calls out the two POC folders as special.

## Perspectives not covered

Files that intentionally hold long unbreakable lines (a pasted base64 blob, a long URL table) — `reflow_md.py` already leaves an over-cap single token alone, but if a file needs a `<!--
lint-ignore-length -->` marker that DFM-5 did not add, `enforcement/`'s `--all` gate will surface it then. This story does not pre-audit for that case.
