# DS Capability Map — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: DSM-1.** DSM-2 (council run) and DSM-3 (absorb) are done; the broader capability matrix moved to `ds-router-migration/` DSR-0 because the council ruled it post-roll.

- [ ] **DSM-1** — Roll-critical verification: Upstox BOD lists Dec 2027 contracts; Dhan 806 / stale-token response shapes; Upstox Greeks flip on a second expiry; record in `roll_checks.md` | Owner:
  Claude | Model: claude-sonnet-5-5 | Review: none | SHA: <—>
- [x] **DSM-2** — Run the council: `bash docs/plan/data-source-routing/council/submit.sh` (server up first) | Owner: Animesh | Model: n/a | Review: none | SHA: 1cc4c30
- [x] **DSM-3** — Absorb the council ruling: `DECISIONS.md` row, `docs/council/README.md` topic row, spec `ds-chain-seam` and `ds-chain-monitoring`, re-scope DSM-1 | Owner: Claude | Model:
  claude-sonnet-5-5 | Review: none | SHA: <pending>

## Story done when

- **DSM-1** — `roll_checks.md` records, each marked verified-by-probe or `unverified — owner Animesh`: whether the Upstox instrument master lists Dec 2027 NIFTY contracts (and on what date), the exact
  Dhan response for 806 and for a stale or missing token, and the Upstox zero-to-non-zero Greeks flip on a second expiry.
- **DSM-2** — `docs/archive/council/data_architecture/2026-10-07_data-source-routing.md` exists.
- **DSM-3** — Summary Table decisions are in `DECISIONS.md`; dissent logged; both code stories are specced.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story list and add one line to `TODOS.md` Session Log. When the whole story
is done, follow §Conventions *Completion → archive*.
