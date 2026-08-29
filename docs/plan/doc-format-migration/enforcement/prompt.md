# Format enforcement — prompt

> Make the canonical format self-enforcing: widen the doc hooks repo-wide, gate them in CI, and scaffold new folders from the template.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

**Blocked until `plan-folders/` and `repo-wide-reflow/` are both complete.** DFM-6 and DFM-9 turn on repo-wide gates that would fail CI the moment they merge if the tree were not already clean. If
either upstream story has an unchecked box, stop and say so.

## Why this story exists

The format is advisory for legacy content today: `check_story_structure.py` runs `--staged-added` (new folders only), `check_checkbox_consistency.py` is not in `.pre-commit-config.yaml` at all,
`md-line-length` only covers root `.md` + `docs/plan/**` + `docs/bugs/**` staged files, and `ci.yml` runs none of the three. Once the batch conversion lands, nothing stops a folder drifting back. This
story closes that: the hooks cover the whole tree, CI fails on any finding, and a new folder starts conforming because it was stamped from `_TEMPLATE/`.

## Scope guard

**In bounds:** `scripts/dev/hooks/check_md_line_length.py`, `scripts/dev/hooks/check_story_structure.py`, `scripts/dev/hooks/check_checkbox_consistency.py`, `.pre-commit-config.yaml`,
`.github/workflows/ci.yml`, a new `scripts/dev/new_plan_folder.py` + its tests, a new `.claude/skills/new-story/` skill, and the `docs/plan/README.md` §Conventions +
`.claude/skills/md-organize/SKILL.md` edits that document the change. Each hook-script change ships with unit tests.

**Out of bounds:** the doc-freshness hooks (`doc_update_gate.sh`, `state_doc_freshness.sh`) — those are RDO-11's, different scripts. Any `src/` module. The conversion itself (done upstream).

## Session-start load hints

- `LOGGING.md` — the `scripts/` logger-name rule (`_SCRIPT_NAME = "scripts.dev.hooks.<module>"`), enforced by the `no-script-main-logger` pre-commit hook. `new_plan_folder.py` must follow it.
- `.pre-commit-config.yaml` — the current `local` hook block, `files:` patterns, `--staged-added` wiring.
- `.github/workflows/ci.yml` — the existing `test` job; DFM-9 adds a job alongside it (watch for a rebase against RDO-11 if that lands first).
- `scripts/dev/hooks/check_story_structure.py` — the `--all` vs `--staged-added` arg handling and the "grandfathers legacy shapes" note at the bottom of `main`.
- `docs/plan/_TEMPLATE/` — what `new_plan_folder.py` copies.

## Task overview

- **DFM-6** — widen `md-line-length` hook `files:` to every `.md` in the repo except `docs/archive/` and `_TEMPLATE/`; keep the 200-char cap and the `<!-- lint-ignore-length -->` escape.
- **DFM-7** — `check_story_structure.py` gains a `--staged` mode (added **or** modified folders) and drops the legacy grandfather for any folder not on a shrinking allowlist; wire `--staged` into
  pre-commit in place of `--staged-added`.
- **DFM-8** — add `check_checkbox_consistency.py` to `.pre-commit-config.yaml` (staged `tasks.md` / `task.md` + the `## Story done when` blocks).
- **DFM-9** — new `ci.yml` job `docs-format`: runs all three hooks with `--all` and fails on any finding; update `.claude/skills/md-organize/SKILL.md` to note the audit is now a local pre-check, not
  the gate.
- **DFM-10** — `scripts/dev/new_plan_folder.py` (`--story <slug>` / `--epic <slug>` → copies `_TEMPLATE/`, substitutes slug + title, drops the HTML comments) + tests + a `.claude/skills/new-story/`
  wrapper skill; reference it from `docs/plan/README.md` §Conventions *Folder shapes*.

## Definition of done

All three doc hooks run repo-wide (`--all`) in a CI job that fails on any finding; `check_checkbox_consistency` is in `.pre-commit-config.yaml`; `check_story_structure` gates modified folders;
`new_plan_folder.py` + `/new-story` scaffold a conforming folder; `docs/plan/README.md` §Conventions states the format is enforced, not advisory; every new hook-script line has unit coverage and the
full suite is green.

## Perspectives not covered

Developer friction — turning `check_story_structure` from "new folders only" to "any touched folder" means an unrelated one-line fix inside a legacy-shaped folder could now fail pre-commit before that
folder is converted. DFM-7's shrinking allowlist is meant to bridge that, but the allowlist has to actually be maintained; if `plan-folders/` genuinely converts everything first, the allowlist is
empty from day one and this risk is moot. Confirm the ordering held before relying on that.
