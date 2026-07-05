# Full Repo Review — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha> | Model: <model used>` when done. Add one line to
> `TODOS.md`. Full spec + model assignment + persona + prompt text for each task:
> `docs/plan/full-repo-review/stories.md`.
>
> FR-0 runs before everything — it validates whether Fable is actually worth its cost
> premium over Opus for this epic's three Fable-assigned tasks (FR-1, FR-3, FR-7), so the
> rest of the epic runs on a checked assumption rather than an untested one.
> FR-1 runs second even though it's a meta/protocol task, not a content-review task — it has
> no dependency on any other task's output (beyond FR-0) and decides whether this epic's
> own process (including the co-investor "Operating philosophy" in `prompt.md`) is sound
> before the other tasks execute under it. See `stories.md`'s ordering note for the full
> reasoning.

---

- [x] **FR-0** — Model validation pilot: Fable vs. Opus, same prompt, diffed (no persona — infrastructure check, run on **both Fable and Opus**) | SHA: c7e8740 | Model: Fable + Opus (both)
- [x] **FR-1** — Prompting methodology & AI-collaboration protocol review, incl. philosophy-promotion decision (Protocol Reviewer persona, **Fable, pending FR-0**) | SHA: 811ed02 | Model: Opus (downgraded from Fable per FR-0 recommendation)
- [x] **FR-2** — Financial modeling & Greeks correctness review (Quant Reviewer persona, **Opus**) | SHA: 9390330 | Model: Opus
- [x] **FR-3** — Architecture & design-doc consistency review (Systems Architect persona, **Fable, pending FR-0**) | SHA: 8a67ffe | Model: Sonnet (deviation from FR-0's low-confidence keep-Fable recommendation — no Fable subagent override available inline; noted in the findings file)
- [ ] **FR-3.1** — Full folder structure & taxonomy review, all trees grouped by category (Folder Structure Auditor persona, **Sonnet**, depends on FR-3 output)
- [ ] **FR-4** — Code quality & coding-standard compliance sweep (Standards Auditor persona, **Sonnet**)
- [ ] **FR-5** — Test adequacy & ground-truth coverage review (Test Auditor persona, **Sonnet**, escalate financial gaps to **Opus**)
- [ ] **FR-6** — Security & operational-risk review (Red-Team persona, **Opus**)
- [ ] **FR-7** — Missing-persona / blind-spot synthesis (Chairman persona, **Fable, pending FR-0**)
- [ ] **FR-8** — Tooling usage guide: Claude Code vs. Cowork vs. Antigravity handoff, by job type (Practitioner/DevEx persona, **Sonnet**)
- [ ] **FR-9** — Build implementation roadmap folder + DECISIONS.md update (no model assignment — mechanical synthesis of FR-1..FR-8 outputs)
