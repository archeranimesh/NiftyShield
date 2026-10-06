# Far-Expiry Capture — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit.

**Open: FC-1..FC-5.**

- [ ] **FC-1** — Storage decision: audit `ChainWriter` Parquet versus a SQLite table against `DB_REGISTRY.md`; record the choice in `DECISIONS.md` (add `schema.md` only if SQLite) | Owner: Claude |
  Model: claude-sonnet-5-5 | Review: none | SHA: —
- [ ] **FC-2** — Writer/reader for far-expiry snapshots per FC-1, with a pure `chain_to_liquidity_rows` reducer | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **FC-3** — `scripts/pipeline/capture_far_expiry_chain.py`: trading-day guard, expiries from `get_expiry_candidates`, 4 s spacing, heartbeat, `LOGGING.md` shape | Owner: Claude | Model:
  claude-sonnet-5-5 | Review: code-reviewer | SHA: —
- [ ] **FC-4** — Add the daily cron on the Mac host and register the heartbeat with `healthcheck.py` | Owner: Animesh | Model: n/a | Review: none | SHA: —
- [ ] **FC-5** — `scripts/dev/far_expiry_liquidity_report.py`: per expiry and day, target-delta strike quote status, spread %, OI, count of non-zero-delta rows | Owner: Antigravity | Model: n/a |
  Review: code-reviewer | SHA: —

## Story done when

- **FC-1** — decision and reasoning in `DECISIONS.md`; `DB_REGISTRY.md` row added if a table is created.
- **FC-2** — round-trip and reducer tests green offline.
- **FC-3** — dry run against a fake client writes the expected rows; a holiday exits cleanly; 805 does not crash the run.
- **FC-4** — cron live; `healthcheck.py` flags a missed day.
- **FC-5** — report reproduces from stored data with no network.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story list and add one line to `TODOS.md` Session Log. When the whole story
is done, follow §Conventions *Completion → archive*.
