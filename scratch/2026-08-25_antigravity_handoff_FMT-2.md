Read CONTEXT.md and ANTIGRAVITY.md. State "CONTEXT.md ✓" before anything else.
Then follow this handoff exactly — do not skip the PLANNING_GATE.

TASK IDENTITY
You are implementing **FMT-2** from the `telegram-markdown-migration` epic.
- Epic index: `docs/plan/telegram-markdown-migration/README.md`
- Task checklist (tick this when done): `docs/plan/telegram-markdown-migration/formatting-rules/tasks.md`
  — find the `FMT-2` line, currently unchecked (`- [ ]`)
- Full story spec (read this in full before planning — it has exact function signatures
  and the exact test list, do not re-derive either from scratch):
  `docs/plan/telegram-markdown-migration/formatting-rules/stories.md`, section `## FMT-2 — Value Formatters`
- Folder-level constraints (test gate, graph-before-Read rule, commit format):
  `docs/plan/telegram-markdown-migration/formatting-rules/prompt.md`
- Canonical formatting rules this task implements: `FORMATTING.md` §3 (repo root)
- Routing on the tasks.md line: Owner: Antigravity | Model: n/a | Review: none — mechanical,
  exhaustive spec, no judgment calls delegated to you.

Why this task exists / where it sits in the epic: FORMATTING.md exists because money alone
shipped in 5 different shapes across 18 scratch/ workshop scripts before this epic unified it.
FMT-2 is the first real-code task that promotes that spec into `src/notifications/formatting.py`
— every later `ROLL-*` ready-for-production message and FMT-3's table builders import from this
module. Nothing downstream can start until this lands (FMT-3 is directly blocked on it).

OBJECTIVE
Add `src/notifications/formatting.py` with four value formatters (`format_money`, `format_greek`,
`format_strike`, `format_pct`) plus their unit tests, implementing FMT-1's finalized spec
(FORMATTING.md §3) exactly as signed off in stories.md's FMT-2 section.

PLANNING_GATE (mandatory — do not skip)
Before writing any code or test:
1. State your plan: for each phase below, write one sentence describing what
   you will build, list the files you will touch, and the expected test count.
2. End with: "Awaiting go-ahead to begin Phase A."
3. Stop. Do not write any code until Animesh replies with "proceed" or equivalent.

If your plan deviates from the PHASES block (different files, different approach),
state the deviation explicitly so Animesh can relay it to Claude for resolution.

PHASES
Phase A — formatters: create `src/notifications/formatting.py` with the four functions,
  signatures exactly as specified in stories.md's FMT-2 section (reproduced below in
  CONTEXT_EXTRACT so you don't need to open the file to start, but read the file anyway —
  the docstrings carry rationale you'll want for edge cases).
  Touches: `src/notifications/formatting.py`, `src/notifications/__init__.py` (only if missing).
  Commit: "feat(notifications): add FMT-2 value formatters"
Phase B — tests: the exact happy-path + edge-case list stories.md specifies per function
  (reproduced below).
  Touches: `tests/unit/notifications/test_formatting.py`.
  Commit: "test(notifications): cover FMT-2 formatters"

GRAPH_POINTERS
Run these graph queries first before reading any source file:
- search_graph("escape_markdown")
- search_graph("mdcode")
- get_code_snippet("Users-abhadra-myWork-myCode-python-NiftyShield.src.notifications.markdown.escape_markdown")
- search_code("format_money") — confirm nothing already defines this name elsewhere in src/
- search_code("format_option_label") — `src/instruments/lookup.py`'s existing strike-formatting
  convention (integer, no decimal) that `format_strike` should match, per stories.md's note to
  reuse it rather than reinvent

BOUNDARIES
Do not touch:
- `src/notifications/markdown.py` (escape_markdown/mdcode — already shipped, MD-1)
- `src/notifications/telegram_gateway.py`, `src/notifications/telegram_notifier.py` (send paths — untouched by FMT-2)
- Any `scratch/*_format.py` file — read-only reference, not a port target for FMT-2 (that's FMT-3)
- `FMT-3`'s table builders (`build_kv_table`, `build_side_by_side_kv_table`, `build_leg_table`) —
  separate task, blocked on FMT-2 landing first; do not implement them here even though they'll
  live in the same file eventually
- Any other line in `formatting-rules/tasks.md` besides FMT-2's own checkbox
Invariants (non-negotiable):
- Decimal on all monetary fields; never float; SQLite stores as TEXT
- No imports of UpstoxLiveClient / MockBrokerClient outside src/client/factory.py
- __init__.py required in every new package directory
- UPSTOX_ENV=test for all run_command executions
- No SELECT * in any DB query

CONTEXT_EXTRACT

Exact signatures from stories.md's FMT-2 section (implement these, not a paraphrase):

```python
def format_money(value: Decimal) -> str:
    """2dp, comma thousands, ₹ prefix, sign before ₹ on negatives.
    Never accepts float — a float argument must raise TypeError, not silently coerce.
    Decimal("82628") -> "₹82,628.00", Decimal("86.68") -> "₹86.68",
    Decimal("-11.08") -> "-₹11.08".
    """

def format_greek(value: float | None, *, width: int | None = None) -> str:
    """2dp, always signed, '-' placeholder for None (not-applicable, not zero).
    width: optional right-align width for FMT-3's build_leg_table to reuse later —
    implement the param now even though no caller uses it yet.
    -0.03 -> "-0.03", 0.28 -> "+0.28", None -> "-".
    """

def format_strike(value: float | int) -> str:
    """Integer string, no decimal, no thousands separator (identifier, not quantity).
    23000.0 -> "23000". Reuse format_option_label's existing strike convention
    (src/instruments/lookup.py) rather than inventing a new one.
    """

def format_pct(value: float) -> str:
    """1dp; value is a plain number where 4 means 4%, not 0.04.
    Whole numbers print bare (no trailing .0): 4 -> "4%" (resolve any inconsistency
    against FMT-1's "0.2%" example row — stories.md flags this as an open call:
    if you find a real inconsistency, 1dp always shown ("4.0%") is the simpler,
    more defensible default — pick it and update FORMATTING.md's §3 row to match,
    do not leave the doc and the code disagreeing).
    """
```

Required tests per function (stories.md's exact list — do not invent a different set):
- `format_money`: `Decimal("86.68")` happy path; `Decimal("0")` edge case; float argument raises `TypeError`
- `format_greek`: `0.28` happy path (positive sign shown); `None` edge case (`"-"`); `-0.03` (negative sign)
- `format_strike`: `23000.0` happy path; `0` edge case (must not crash)
- `format_pct`: whole-number happy path; `0.0` edge case

FORMATTING.md §4 — three distinct states, do not collapse: "not applicable" → `-` (this is
`format_greek(None)`'s case), "unresolved" (fetch failed / no source value) → `N/A` (not this
task's concern — no formatter here emits N/A), real measured zero → the formatter's normal
output (`₹0.00`, `+0.00`, `0%`).

FORMATTING.md §6 — Escaping contract: formatters return **display strings, not MarkdownV2-safe
strings**. Do NOT call `escape_markdown()`/`mdcode()` inside these formatters — escaping happens
at the call site (a later task), never inside a formatter. Double-escaping every fenced-table
cell is the exact failure mode this avoids.

Relevant module state (CONTEXT.md, src/notifications/):
`src/notifications/telegram_gateway.py` — `send_approval_request`/`send_notification` both send
`parse_mode: MarkdownV2` (MD-4.1/4.2/4.3, 2026-08-25); callers already escape dynamic values via
`escape_markdown()` at their call sites — this is the consumption pattern FMT-2's formatters
feed into eventually, but this task does not touch the gateway.
`src/notifications/markdown.py` — `escape_markdown()`/`mdcode()` (MD-1, shipped, tested in
`tests/unit/notifications/test_markdown.py`) — the escaping layer downstream callers wrap
formatter output in; FMT-2 must not duplicate or call into this.

REVIEW_RULES
Before committing, check the diff against these Python hygiene rules:
- Mutable default arguments: def f(x=[]) or def f(x={}) — always use None + guard
- Late-binding closures: lambdas inside loops capturing loop variable
- Bare except: except: or except Exception: pass without logging
- Generator exhaustion: generator passed to two consumers
- Dict/set/list mutation during iteration
- __eq__ without __hash__ on any class defining __eq__
- None as sentinel when None is a valid domain value — use _MISSING = object()
- Set iteration order assumptions: list(some_set)[0]
- zip without strict=True on mismatched-length sequences
- copy.copy() on nested mutables — use copy.deepcopy()

DOD
- [ ] Tests pass: python -m pytest tests/unit/ --tb=no -q (all green)
- [ ] Exactly the test list above, one happy-path + one edge-case per function minimum
- [ ] `format_money` raises `TypeError` on a `float` argument (explicit test)
- [ ] CONTEXT.md updated (module tree) — new `src/notifications/formatting.py` entry
- [ ] TODOS.md updated (session log entry)
- [ ] One commit per phase — never bundle phases into a single commit
- [ ] Each commit executed (not drafted) — SHA confirmed via git log --oneline -1
- [ ] PHASE COMPLETE block emitted after every phase before starting the next
- [ ] Tick FMT-2's box in `docs/plan/telegram-markdown-migration/formatting-rules/tasks.md`
      with `| SHA: <sha>` — do not touch any other line in that file

QUALITY_GATES
Antigravity runs these gates using its own tooling — not Claude's sub-agents.

Test gate (replaces Claude's test-runner agent):
  run_command: python -m pytest tests/unit/ --tb=no -q
  All tests must pass before proceeding to review. If failures exist, fix them first.

Review gate (replaces Claude's code-reviewer agent) — this task is routed "Review: none" in
formatting-rules/tasks.md, so use the non-financial persona tier, not the real @code-reviewer
escalation:
  view_file: .claude/agents/code-reviewer.md
  view_file: REVIEW.md
  Adopt both as persona. Evaluate git diff HEAD against all rules in both files.
  Resolve CRITICAL/ERROR before committing. WARNING may be deferred with a note.

STOP_CONDITIONS
Stop mid-implementation and surface to Animesh (who relays to Claude) when:
  - A design decision arises that isn't resolved by CONTEXT.md, DECISIONS.md, FORMATTING.md,
    stories.md, or the graph
  - A required symbol or model field is missing from the codebase and needs a new design decision
  - A test is failing for a reason that suggests the spec is wrong, not the implementation
  - The `format_pct` whole-number-vs-1dp-always question above genuinely can't be resolved by
    picking the simpler default stories.md suggests — surface it rather than shipping two
    functions with disagreeing precision rules

Do NOT stop for: implementation style choices, naming decisions, minor refactors.
When stopping, include in the relay message: what the ambiguity is, the two options
you considered, and which you would pick if forced. Claude resolves it and you continue.

PHASE_COMPLETION_OUTPUT
At end of phase, produce this block:
PHASE COMPLETE
files_changed: [list]
tests_added: N
tests_passing: N of M
commit_sha: <7-char SHA>
ambiguities_noted: [list any stop-condition items that arose, or "none"]
