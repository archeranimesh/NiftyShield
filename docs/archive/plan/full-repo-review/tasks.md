# Full Repo Review — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session. Tick the box and append `| SHA: <sha> | Model: <model used>` when done. Add one line to `TODOS.md`. Full spec + model
> assignment + persona + prompt text for each task: `docs/plan/full-repo-review/stories.md`. FR-0 runs before everything — it validates whether Fable is actually worth its cost premium over Opus for
> this epic's three Fable-assigned tasks (FR-1, FR-3, FR-7), so the rest of the epic runs on a checked assumption rather than an untested one. FR-1 runs second even though it's a meta/protocol task,
> not a content-review task — it has no dependency on any other task's output (beyond FR-0) and decides whether this epic's own process (including the co-investor "Operating philosophy" in
> `prompt.md`) is sound before the other tasks execute under it. See `stories.md`'s ordering note for the full reasoning.

---

- [x] **FR-0** — Model validation pilot: Fable vs. Opus, same prompt, diffed (no persona — infrastructure check, run on both Fable and Opus) | Owner: Claude | Model: Fable + Opus (both) | Review: none
  | SHA: c7e8740
- [x] **FR-1** — Prompting methodology & AI-collaboration protocol review, incl. philosophy-promotion decision (Protocol Reviewer persona, Fable, pending FR-0) | Owner: Claude | Model: Opus
  (downgraded from Fable per FR-0 recommendation) | Review: none | SHA: 811ed02
- [x] **FR-2** — Financial modeling & Greeks correctness review (Quant Reviewer persona, Opus) | Owner: Claude | Model: Opus | Review: none | SHA: 9390330
- [x] **FR-3** — Architecture & design-doc consistency review (Systems Architect persona, Fable, pending FR-0) | Owner: Claude | Model: Sonnet (deviation from FR-0's low-confidence keep-Fable
  recommendation — no Fable subagent override available inline; noted in the findings file) | Review: none | SHA: 8a67ffe
- [x] **FR-3.1** — Full folder structure & taxonomy review, all trees grouped by category (Folder Structure Auditor persona, Sonnet, depends on FR-3 output) | Owner: Claude | Model: claude-sonnet-5 |
  Review: none | SHA: d205d16
- [x] **FR-4** — Code quality & coding-standard compliance sweep (Standards Auditor persona, Sonnet) | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 3242fa8
- [x] **FR-5** — Test adequacy & ground-truth coverage review (Test Auditor persona, Sonnet, escalate financial gaps to Opus) | Owner: Claude | Model: Sonnet (2 findings tagged NEEDS-OPUS-REVIEW, not
  yet Opus-reviewed) | Review: none | SHA: 5e09860
- [x] **FR-6** — Security & operational-risk review (Red-Team persona, Opus) | Owner: Claude | Model: Sonnet (deviation from Opus assignment — no Opus subagent override available inline; noted here
  per epic's own deviation-logging pattern from FR-3) | Review: none | SHA: ed3791b
- [x] **FR-7** — Missing-persona / blind-spot synthesis (Chairman persona, Fable, pending FR-0) | Owner: Claude | Model: Fable | Review: none | SHA: d57ee7f
- [x] **FR-8** — Tooling usage guide: Claude Code vs. Cowork vs. Antigravity handoff, by job type (Practitioner/DevEx persona, Sonnet) | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA:
  308aa57
- [x] **FR-9** — Build implementation roadmap folder + DECISIONS.md update (mechanical synthesis of FR-1..FR-8 outputs, no model assignment) | Owner: Claude | Model: claude-sonnet-5 | Review: none |
  SHA: 149408f
