# Docs Navigation & Staleness Cleanup — Story

**Source:** `docs/plan/full-repo-review/findings/FR-7_synthesis.md`, FR-7 rows 3, 8, 14 (CRITICAL + ERROR) — FR-3 F1, FR-1 F-E6/F12a/F12b, FR-3 F5, FR-3.1 F10, FR-3 F2.

## T1

Rewrite `docs/plan/README.md`'s status table rows for `dev-foundation`, `council-refactor`, `paper-backbone`, `ic-nifty-v2` against `docs/archive/plan/` + `DECISIONS.md` (targeted Edit only).
Fix `docs/council/README.md`'s taxonomy section to the actual `docs/archive/council/{strategy,risk,research,data_architecture,misc}/` structure
and its Archived Decisions tables to include the missing `data_architecture/` entries and the 2026-06-26 q11/q12 decisions.
Fix the two dead links: `docs/plan/variance-gate/prompt.md:18` → `docs/archive/council/risk/2026-05-02_...`;
`DECISIONS.md` lines 397-407 → the correct `docs/archive/council/strategy/2026-06-26_...` revised path (verify against the newer `paper-exit-codification/prompt.md`,
which already points at the correct path). Remove the stale `src/nuvama/CLAUDE.md` "doesn't exist yet" line from CONTEXT.md.
Docs-only — no test gate, but grep-verify no other doc still references the dead paths after the edit.

**Files touched:** `docs/plan/README.md`, `docs/council/README.md`, `DECISIONS.md`, `CONTEXT.md`

**Tests:** happy-path + error/edge-case per CLAUDE.md Step 4, in the files listed above.
