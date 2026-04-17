# NiftyShield — How to Work with Claude

> Practical workflow for every session. Tear-off prompts for each task type.
> The system is only as good as the prompts you give it — this file is your cheat sheet.

---

## The Repo's Context Layer (quick map)

| File | What it answers | When to mention it |
|---|---|---|
| `CONTEXT.md` | What exists, what doesn't, live DB state | Always — Claude reads it first |
| `DECISIONS.md` | Why it was built this way | New modules, architecture changes |
| `REFERENCES.md` | Instrument keys, AMFI codes, API quirks | Anything touching market data |
| `TODOS.md` | Open work + session log | Starting new feature, reviewing priority |
| `PLANNER.md` | Sprint roadmap, blocked items | Multi-session planning |
| `src/<module>/CLAUDE.md` | Module-specific invariants | Auto-loaded when you name the module |

---

## Session Start Workflow

Every session, your first message should be one of the templates below. Do not skip this — Claude's context resets between sessions and it needs to re-anchor.

**Minimal opener (for any task):**
```
Read CONTEXT.md. Then: [your task here]
```

**For feature work:**
```
Read CONTEXT.md, TODOS.md, and PLANNER.md. I want to implement [feature].
Confirm scope before starting.
```

**For architecture changes:**
```
Read CONTEXT.md and DECISIONS.md. I want to [change]. Walk me through the implications before touching code.
```

**For anything touching market data:**
```
Read CONTEXT.md and REFERENCES.md. [Task involving instrument keys / AMFI codes / API endpoints]
```

---

## Per-Task Prompt Templates

### 1 — Implement a new feature

```
Read CONTEXT.md + TODOS.md + PLANNER.md.

Task: [one sentence description]
Module: src/[module]/
Expected outputs: [list files]
Tests required: yes — offline only, no network

Confirm scope and plan before starting.
```

**What happens:** Claude reads context, states a one-sentence plan with filenames, waits for your go-ahead if >2 files are touched. After implementation it updates CONTEXT.md, TODOS.md.

---

### 2 — Fix a bug

```
Read CONTEXT.md.

Bug: [describe the symptom]
Where I think it is: [file/function if known, or "unknown"]
Reproduce: [command or test name if available]

Diagnose first, then propose a fix. Don't change anything until I confirm.
```

**What happens:** Claude reads context, locates the bug, explains root cause, proposes minimal targeted fix. You approve before any edit.

---

### 3 — Add or update tests

```
Read CONTEXT.md.

Add tests for: [function / class / module]
Coverage gaps: [what's missing — e.g. "error path for get_position when no trades exist"]
Test file: tests/unit/[module]/test_[file].py
Offline only — no network calls.
```

---

### 4 — Record a trade (routine operation)

No AI needed — run directly:
```bash
python -m scripts.record_trade \
  --strategy finideas_ilts \
  --leg-role EBBETF0431_LONG \
  --instrument-key "NSE_EQ|INE..." \
  --action BUY \
  --qty 10 \
  --price 1390.00 \
  --trade-date 2026-04-14 \
  --dry-run   # remove when ready
```
`--strategy` must be `finideas_ilts` or `finrakshak` — nothing else.

---

### 5 — Run snapshot manually / check P&L

```bash
# Live mode (needs UPSTOX_ANALYTICS_TOKEN in .env)
python -m scripts.daily_snapshot

# Historical mode (no API call)
python -m scripts.daily_snapshot --date 2026-04-11

# Test mode (MockBrokerClient, no token needed)
UPSTOX_ENV=test python -m scripts.daily_snapshot
```

---

### 6 — Add a new strategy leg or roll an existing one

```
Read CONTEXT.md and REFERENCES.md.

I need to [add leg to finideas_ilts / roll NIFTY_JUN_PE].
New instrument: [name, key from REFERENCES.md]
Action: [what changes — new leg definition in ilts.py, new Trade row, both]

Confirm plan before touching DB or code.
```

**For a roll:** Claude will draft the `record_trade.py` commands (SELL old, BUY new) as a dry-run first. You verify, then run without `--dry-run`.

---

### 7 — Code review before committing

Invoke the code reviewer agent:
```
Run the code-reviewer agent on [file or module].
Focus on Decimal usage and BrokerClient protocol compliance.
```

Or for a targeted check:
```
Review src/[module]/[file].py — check Decimal invariants, type hints, and async correctness.
```

---

### 8 — Run tests and verify nothing broke

Invoke the test runner agent:
```
Run the test-runner agent. Report pass/fail count and any failures.
```

Or directly:
```bash
python -m pytest tests/unit/ -v --tb=short
# Expected: ~400 tests, all green
```

---

### 9 — Generate a commit message

After implementation is done:
```
Generate a commit message for what we just built.
```

Claude will produce the project-standard format:
```
<type>(<scope>): <subject ≤60 chars>

Why: <reason>
What:
- <file>: <change>
Ref: <constraint or "none">
```

Copy the output directly into:
```bash
git commit -m "$(cat <<'EOF'
[paste here]
EOF
)"
```

---

### 10 — Update project instructions in Claude Desktop

After significant refactors or new modules:
```
Update the Claude Desktop project instructions to reflect [what changed].
Keep it trimmed — anything now in CONTEXT.md or DECISIONS.md should not be duplicated there.
```

The live project instructions live in Claude Desktop → Project → Instructions directly.

---

### 11 — Archive or housekeeping

```
Archive [file] to docs/archive/[name_YYYY-MM-DD.ext].
Verify the archive exists before deleting the original.
Update CONTEXT.md to reflect the removal.
```

---

## End-of-Session Checklist

After any implementation session, make sure Claude has:

- [ ] Updated `CONTEXT.md` module tree (new files added)
- [ ] Updated `DECISIONS.md` (any new architectural choice)
- [ ] Added a session log entry to `TODOS.md`
- [ ] Marked completed TODOs in `TODOS.md`
- [ ] Updated `PLANNER.md` if sprint status changed

If you forget, start next session with:
```
Read CONTEXT.md and TODOS.md. Update docs to reflect what we built last session: [brief description].
```

---

## What Each Agent Does

| Agent | Model | Invoke when |
|---|---|---|
| `code-reviewer` | Opus | Before merging anything that touches monetary fields, BrokerClient, or async paths |
| `test-runner` | Haiku | After any code change — quick sanity check before commit |

Both live in `.claude/agents/`. Claude Desktop auto-discovers them.

---

## Key Invariants (things Claude checks automatically from module CLAUDE.md files)

When you work in `src/portfolio/` — Claude knows: Leg ≠ Trade, Decimal TEXT in SQLite, `apply_trade_positions()` pattern, `strategy_name` must be `finideas_ilts` or `finrakshak`.

When you work in `src/mf/` — Claude knows: ledger model (never mutate rows), AMFI source, Decimal TEXT round-trip, `MFHolding` lives in `models.py`.

When you work in `src/client/` — Claude knows: no concrete imports outside `factory.py`, 4 implementations, which methods are blocked and why.

When you work in `src/notifications/` — Claude knows: `send()` must never raise, `build_notifier()` returns None, HTML parse_mode.

These fire automatically — you don't need to repeat the invariants in your prompt.

---

## Quick Reference — Common Commands

```bash
# Tests
python -m pytest tests/unit/                        # full suite
python -m pytest tests/unit/portfolio/ -v           # one module
python -m pytest -k "test_apply_trade" -v           # one test

# Snapshot
python -m scripts.daily_snapshot                    # live
python -m scripts.daily_snapshot --date 2026-04-11  # historical
UPSTOX_ENV=test python -m scripts.daily_snapshot    # mock/offline

# Trade recording
python -m scripts.record_trade --help
python -m scripts.record_trade --dry-run ...        # always dry-run first

# Auth
python -m src.auth.login                            # Upstox OAuth
python -m src.auth.nuvama_login                     # Nuvama (one-time)
python -m src.auth.nuvama_verify                    # check Nuvama session

# Instrument lookup
python -m src.instruments.lookup --find-legs "NIFTY"
```
