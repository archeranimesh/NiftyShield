# Suppression Comment Hygiene Triage — Story

**Source:** `docs/plan/full-repo-review/findings/FR-7_synthesis.md`, FR-7 row 10 (ERROR, downgraded from FR-4's CRITICAL per FR-7 divergence D2) — FR-4 §3, §4.

## T1

Add a carve-out to REVIEW.md's suppression-comment meta-rule for self-describing codes (`E402`, `F401` at minimum — confirm the full self-describing set with a quick pass over the 80 `# noqa` sites) so those don't require an explanatory comment. TD-ticket the 2 literal `assert`s in `src/` in TODOS.md for a follow-up fix (raise `ValueError` per G6) rather than fixing inline here — out of scope for a docs-triage task. Scope the 183-instance `except Exception` audit as its own separate follow-up story (do not attempt in this task) — note it in TODOS.md.

**Files touched:** `REVIEW.md`, `TODOS.md`

**Tests:** happy-path + error/edge-case per CLAUDE.md Step 4, in the files listed above.
