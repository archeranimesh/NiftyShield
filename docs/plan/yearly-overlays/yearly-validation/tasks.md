# Yearly Validation — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit.

**Open: YV-1..YV-5.**

- [ ] **YV-1** — Independence tests: monthly and yearly books never block or mix each other (positions, exit events, collateral gate, coverage) | Owner: Claude | Model: claude-sonnet-5-5 | Review:
  code-reviewer | SHA: —
- [ ] **YV-2** — E2E dry-run tests for `--auto-cc/--auto-pp/--auto-collar --expiry-type yearly` against `MockBrokerClient`, temp SQLite, YF-2 fixtures, zero-Greeks case included | Owner: Antigravity |
  Model: n/a | Review: code-reviewer | SHA: —
- [ ] **YV-3** — Opt-in live smoke (`-m live`): dry run against the real Dec 2026 chain, no writes; record the output in the story | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: —
- [ ] **YV-4** — IC coexistence check: weekly/monthly/leaps/yearly distinct names; `leaps` = quarterly, `yearly` = December across frozen dates; daemon and snapshot loops cover all four | Owner:
  Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: —
- [ ] **YV-5** — Paper-run and roll runbook: first yearly CC in paper on Dec 2026, review cadence, and the go/no-go checklist for the Dec 2027 roll | Owner: Animesh | Model: n/a | Review: none | SHA:
  —

## Story done when

- **YV-1** — both directions asserted for every shared consumer.
- **YV-2** — three entrypoints pass dry-run offline; zero-Greeks case fails cleanly, never opens a leg on zero delta.
- **YV-3** — live output recorded; no row written to any DB.
- **YV-4** — all four IC types resolve as intended on 2026-10-06, 2026-12-30 and 2027-03-31.
- **YV-5** — checklist lists Dhan chain adapter, capture history and liquidity gate as roll preconditions.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story list and add one line to `TODOS.md` Session Log. When the whole story
is done, follow §Conventions *Completion → archive*.
