# Logging Standard Migration Completion — Tasks

> Find the first unchecked box below. That is the only task for this session.

- [x] **T1** — Mechanical batch fix, good Antigravity handoff shape (many files, zero design ambiguity):
  replace `logging.getLogger(__name__)` with `structlog.get_logger(__name__)` in all 21 `src/` files listed above. | SHAs: 344d98c, dc526eb, 060b7d6, dedd962

---

**Source:** `docs/plan/full-repo-review/findings/FR-7_synthesis.md`, FR-7 row 7 (CRITICAL) — FR-4 §1.
