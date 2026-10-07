# DS Capability Map — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: DSM-1..DSM-3.**

- [ ] **DSM-1** — Capability matrix: verify token renewal, VIX, batch LTP, order margin, 805/806, live-feed and MCP claims against primary sources; write `capability_matrix.md` | Owner: Claude |
  Model: claude-sonnet-5-5 | Review: none | SHA: <—>
- [ ] **DSM-2** — Run the council: `bash docs/plan/data-source-routing/council/submit.sh` (server up first) | Owner: Animesh | Model: n/a | Review: none | SHA: <—>
- [ ] **DSM-3** — Absorb the council ruling: `DECISIONS.md` rows, `docs/council/README.md` topic row, spec `ds-chain-seam` and `ds-chain-monitoring` `stories.md` | Owner: Claude | Model:
  claude-sonnet-5-5 | Review: none | SHA: <—>

## Story done when

- **DSM-1** — every cell of `capability_matrix.md` is verified-by-probe, verified-by-doc, or explicitly `unverified` with an owner; no secondhand claim stands as fact.
- **DSM-2** — `docs/council/<date>_data-source-routing.md` exists.
- **DSM-3** — Summary Table decisions are in `DECISIONS.md`; Dissenting Notes logged; both code stories are specced.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story list and add one line to `TODOS.md` Session Log. When the whole story
is done, follow §Conventions *Completion → archive*.
