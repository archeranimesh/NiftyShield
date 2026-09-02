# Token Efficiency — Measurement — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit.
See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Story complete — both tasks closed. Epic router advances to `fixed-overhead/`.**

- [x] **MEAS-1** — `scripts/dev/token_audit.py` — attribute a session transcript's tokens by bucket; compact table + `--json` output (bucket list in `stories.md`) |
      Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 79effcd
- [x] **MEAS-2** — run `token_audit.py` on 4–5 recent sessions; write the epic `README.md` "Baseline" section — per-bucket numbers + the 2–3 largest avoidable items |
      Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: a0dfa38

## Story done when

- **MEAS-1** — the script resolves a transcript (path or session id), attributes every
  token-bearing record to a bucket, prints the compact table and a `--json` object, declares
  `_SCRIPT_NAME` per `LOGGING.md`, and has happy-path + edge tests against a fixture
  transcript with no network.
- **MEAS-2** — the epic `README.md` "Baseline" section states real per-bucket token numbers
  from 4–5 recent sessions and names the largest avoidable items; the numbers are what
  `fixed-overhead/` and `suggestions-sweep/` tasks quote their deltas against.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Update the epic
`README.md` **Stories** table status column (`measurement/` row) and add one line to
`TODOS.md` Session Log. When the whole story is done, the epic router advances to
`fixed-overhead/`.
