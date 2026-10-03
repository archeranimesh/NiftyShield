# Gamma Scan Phase B — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Blocked until** `../risk-gamma-phase-a/` is complete and ≥ 5 trading days of `gamma_chain_snapshots` exist.

**Open: GS-1, GS-2, GS-3, GS-4, GS-5, GS-6.**

- [ ] **GS-1** — `gamma_signal_log` model, DDL (`DB_REGISTRY.md` entry) and `GammaStore` insert/update methods | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **GS-2** — `src/gamma/signals.py`: Layers 0–4 as predicates returning reason codes in an ordered `SignalStack` | Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: —
- [ ] **GS-3** — `DepthSource` Protocol + Dhan L2 adapter + `NullDepth` (reduced mode) | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **GS-4** — `ranking.py` (§6 formula) and `exits.py` (E1/E2/E3) as pure functions | Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: —
- [ ] **GS-5** — `scripts/gamma_scan.py` thin orchestration: lock, atomic no-open-position check, paper-entry adapter around `record_paper_trade` | Owner: Claude | Model: claude-sonnet-5 | Review:
  code-reviewer | SHA: —
- [ ] **GS-6** — Cron entry `*/5 9-15 * * 3,4` + `--dry-run` validation on the first qualifying Wednesday | Owner: Animesh | Model: n/a | Review: none | SHA: —

## Story done when

- **GS-1** — `gamma_signal_log` created idempotently; insert, exit-field update and watchlist-hit query covered by tests; `DB_REGISTRY.md` updated.
- **GS-2** — every layer predicate has a pass and a fail test; the stack stops at the first failing layer and returns its reason code; Layer 3 Condition B is inert until 20 days of history exist.
- **GS-3** — `DepthSource` has a Dhan adapter and a `NullDepth`; missing key or API failure degrades to reduced mode without raising.
- **GS-4** — ranking formula and E1/E2/E3 exit rules are pure and unit-tested with boundary values.
- **GS-5** — end-to-end test with all collaborators mocked; a second concurrent run exits without trading; a duplicate-direction signal does not open a second position.
- **GS-6** — cron live; one full dry-run session reviewed; findings logged in `TODOS.md`.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story list (and the epic row in `docs/plan/README.md`) and add one line to
`TODOS.md` Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
