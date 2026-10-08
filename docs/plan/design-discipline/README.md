
# Design Discipline — epic index

> Make Python design principles and clean-code rules a gate before every code proposal, then measure how much of the existing code follows them and calibrate the gate. Two stories: the gate ships
> first and pays off immediately; the baseline is longer and only needs the decision card, so it must not hold the gate back.

## Why this epic exists

Requested by Animesh (2026-10-08). A plan was drafted without applying `docs/refactor/design-principles.md`, because the rule sat after the plan gate and its trigger was too narrow. A read of about 70
bugs shows the same design gaps recurring (no single seam for a multi-step state change, per-variant copies of one mechanism, untyped collaborators, silent failures). `docs/refactor/` is generic prose
from another project, and `code-review-checklist.md` is not used by the `code-reviewer` agent. Nobody knows how much existing code follows the principles.

## Scope decisions

- **Two stories** (Animesh, 2026-10-08): `design-gate/` (docs, skills, hook) and `design-baseline/` (one tested `scripts/dev/` tool, a report, a backlog, a calibration review).
- **Two-tier card** (confirmed): Tier 1 baseline principles apply to all code irrespective of bug history; Tier 2 is evidence-ranked from the bug archive. History orders the card; it does not bound
  it.
- **GoF patterns** are audited for Python applicability before the card is written; a pattern with no concrete in-repo problem is "not needed here", never recommended speculatively.
- **Gate strength** (confirmed): the hook warns first and blocks after calibration; `Design: n/a — <reason>` is accepted for docs-only and one-line changes.
- **Bug Design lens** (confirmed): required only for bugs that touch `src/` or `scripts/`.
- **Checklist reconciliation**: keep `code-review-checklist.md` §1–3, make §5 a done-criterion for refactor stories, drop §4 (FCID unused here) and §6 (duplicates CLAUDE.md Steps 3–5).
- **No council** (Step 2b): the work is cheap to reverse and not multi-discipline. A read-only council critique of the finished card is optional after DG-4.
- **Logging** is a separate epic, not part of this one.
- **No `src/` change, no DB schema change.** No `schema.md`.

## Architecture and design review

Skill, hook and doc work in `design-gate/`: no new module, class or seam. `design-baseline/` adds `scripts/dev/design_scan.py`, a pure read-only CLI with a registry `dict` of one-function checks (a
new check adds an entry, not a branch). Dependency direction: the scan reads the tree and git history only; nothing imports it.

## Stories

| Story | Purpose | Status | Depends on | Closing SHA |
|---|---|---|---|---|
| `design-gate/` | Evidence, GoF audit, docs triage, decision card, skill and plan gate, other surfaces, bug lens, hook, reviewer (DG-1..9) | ⬜ Not started | — | — |
| `design-baseline/` | Conformance scan, baseline report, refactor backlog, calibration review (DBL-1..4) | ⬜ Not started | `design-gate` DG-4 | — |

Status: ⬜ Not started · 🔄 In progress · ✅ Done. This column is the epic's progress view — per-task checkboxes live only in each sub-story's `tasks.md`.

## Cross-cutting constraints

- **Offline-first**: the scan makes no network or DB access; its tests use inline source strings and temp trees.
- **No silent enforcement jump**: the hook starts as a warning; the block flip happens only at DBL-4.
- **`AGENTS.md` mirrors `CLAUDE.md`** in full whenever the protocol text changes.
- **Docs follow the fill-to-≤200 style** (`reflow_md`).

## Supersession / coordination

Supersedes the single-story `design-discipline/` scaffold (`9f8500a`..`3b1a083`). Separate from the logging epic, which owns `LOGGING.md` and `src/utils/logging.py`; DG-3 must not edit `LOGGING.md`.

## Epic done when

- **design-gate** — the gate is live on all surfaces, in warn mode, with the bug lens and reviewer wired.
- **design-baseline** — the baseline report and backlog exist and the calibration review has decided the hook mode.
