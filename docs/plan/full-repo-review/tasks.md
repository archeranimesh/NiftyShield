# Full Repo Review — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha> | Model: <model used>` when done. Add one line to
> `TODOS.md`. Full spec + model assignment + persona + prompt text for each task:
> `docs/plan/full-repo-review/stories.md`.
>
> FR-1 runs first even though it's a meta/protocol task, not a content-review task — it has
> no dependency on any other task's output and decides whether this epic's own process
> (including the co-investor "Operating philosophy" in `prompt.md`) is sound before the
> other tasks execute under it. See `stories.md`'s ordering note for the full reasoning.

---

- [ ] **FR-1** — Prompting methodology & AI-collaboration protocol review, incl. philosophy-promotion decision (Protocol Reviewer persona, **Fable**)
- [ ] **FR-2** — Financial modeling & Greeks correctness review (Quant Reviewer persona, **Opus**)
- [ ] **FR-3** — Architecture & design-doc consistency review (Systems Architect persona, **Fable**)
- [ ] **FR-4** — Code quality & coding-standard compliance sweep (Standards Auditor persona, **Sonnet**)
- [ ] **FR-5** — Test adequacy & ground-truth coverage review (Test Auditor persona, **Sonnet**, escalate financial gaps to **Opus**)
- [ ] **FR-6** — Security & operational-risk review (Red-Team persona, **Opus**)
- [ ] **FR-7** — Missing-persona / blind-spot synthesis (Chairman persona, **Fable**)
- [ ] **FR-8** — Tooling usage guide: Claude Code vs. Cowork vs. Antigravity handoff, by job type (Practitioner/DevEx persona, **Sonnet**)
- [ ] **FR-9** — Build implementation roadmap folder + DECISIONS.md update (no model assignment — mechanical synthesis of FR-1..FR-8 outputs)
