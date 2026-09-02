# Token Efficiency — Fixed Overhead — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit.
See `prompt.md` for why the story exists and its hard constraints; see `stories.md` for the
per-task implementation spec. Every task's As-built records a measured token delta.

**Open: FIX-4 (next).**

FIX-1..FIX-4 are independent of each other — the `prompt.md` order is a suggested sequence,
not a hard dependency. Do not start any before `measurement/` is complete (the As-built
delta needs `token_audit.py`).

- [x] **FIX-1** — Skill-ify `CLAUDE.md` — reference tables + Council Protocol + AI-collab prose to a `protocol-reference` skill; resident keeps the load-bearing protocol; mirror `AGENTS.md` |
      Owner: Claude | Model: claude-opus-5 | Review: none | SHA: 41ac31e
- [x] **FIX-2** — Audit `src/*/CLAUDE.md` sizes; trim the 2–3 largest — deep detail to module docstrings or a `NOTES.md`, invariants + contracts stay resident |
      Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: ce45719
- [x] **FIX-3** — Redesign `session-close` skill to run as a transcript-reading subagent (reads the JSONL by path, no `fork` context clone); As-built records the measured per-session saving |
      Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 03d991f
- [ ] **FIX-4** — Strip `fp`/`sp`/`bt` fingerprint fields from `codebase-memory-mcp` `get_code_snippet` / `search_graph` results via a thin wrapper; file the upstream issue |
      Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>

## Story done when

- **FIX-1** — the resident `CLAUDE.md` is under its target line count (state the target and
  the before/after in the As-built); the moved material is in `protocol-reference/SKILL.md`
  and still discoverable (the resident file points to it, the skill is listed for `/work` and
  council triggers); `AGENTS.md` is a full standalone mirror of the new `CLAUDE.md`; the
  per-turn resident-token drop is measured.
- **FIX-2** — the 2–3 heaviest `src/*/CLAUDE.md` files are trimmed to invariants + contracts
  with reference detail relocated, each auto-inject saving measured; no module invariant is
  lost.
- **FIX-3** — `session-close` produces the same compact audit block without cloning
  conversation context; the As-built shows the before/after per-session token numbers
  (expect the `fork` line to fall from hundreds of K to tens of K).
- **FIX-4** — `get_code_snippet` / `search_graph` calls through the wrapper return only the
  fields the model uses; the per-call byte drop times a typical per-session call count is
  recorded; the upstream issue link is in the As-built.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Update the epic
`README.md` **Stories** table status column (`fixed-overhead/` row) and add one line to
`TODOS.md` Session Log. When the whole story is done, the epic router treats
`fixed-overhead/` as complete (`suggestions-sweep/` was already startable in parallel).
