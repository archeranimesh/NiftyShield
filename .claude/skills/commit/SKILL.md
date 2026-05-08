# NiftyShield Commit Executor

Execute the full commit workflow. A written-out commit message is not a commit — this skill
runs the git commands and confirms the SHA. The phase is not closed until the SHA appears.

---

## Step 1 — Review the diff

```bash
git -C /path/to/repo diff HEAD
```

Scan for: Decimal violations, BrokerClient imports outside factory.py, missing type hints,
blocking calls in async paths. If the diff touches financial logic (Greeks, P&L, Decimal
fields), stop and invoke the `@code-reviewer` subagent before proceeding.

---

## Step 2 — Run the test suite

```bash
python -m pytest tests/unit/ --tb=no -q
```

All tests must pass. If any fail, do not proceed — fix failures first.

---

## Step 3 — Construct the commit message

Use this format exactly:

```
<type>(<scope>): <what changed, imperative mood, ≤60 chars>

Why: <one sentence — reason or problem solved, not a restatement of what changed>
What:
- <file path relative to repo root>: <one-line description>
- <file path relative to repo root>: <one-line description>
Ref: <relevant constraint from CONTEXT.md → Current Constraints, or "none">
```

**Types:** `feat` / `fix` / `refactor` / `test` / `chore` / `docs`
**Scope:** folder name under `src/` or `scripts/` (e.g. `portfolio`, `client`, `mf`, `scripts`)

Rules:
- Subject line ≤ 60 chars, imperative mood, no trailing period
- `Why:` explains the reason, never just restates `What:`
- One `What:` bullet per file changed
- Never bundle changes from separate phases into one commit

---

## Step 4 — Stage and commit

```bash
git -C /path/to/repo add <file1> <file2> ...
git -C /path/to/repo commit -m "$(cat <<'EOF'
<paste message here>
EOF
)"
```

Stage only the files for this phase. Never `git add -A` across phase boundaries.

---

## Step 5 — Confirm the SHA (mandatory)

```bash
git -C /path/to/repo log --oneline -1
```

The SHA must appear in output. This is proof of completion. If this step is skipped,
the phase is not closed.

---

## Type reference

| Type | When |
|---|---|
| `feat` | New capability added |
| `fix` | Bug or incorrect behaviour corrected |
| `refactor` | Restructuring with no behaviour change |
| `test` | Test added or updated |
| `chore` | Tooling, config, deps, scripts |
| `docs` | Documentation only |

## Examples

```
feat(portfolio): add daily snapshot pipeline with SQLite persistence

Why: Need automated daily P&L capture without manual intervention
What:
- scripts/daily_snapshot.py: cron-ready CLI, fetches LTPs, records snapshots
- src/portfolio/tracker.py: PortfolioTracker loads strategies, records via store
- src/portfolio/store.py: SQLite persistence with upsert semantics
Ref: none
```

```
fix(instruments): use UTC for expiry epoch to avoid IST offset bug

Why: datetime.fromtimestamp without tz=UTC shifts dates by 5.5hrs in IST
What:
- src/instruments/lookup.py: pass tz=timezone.utc to fromtimestamp
Ref: none
```

```
feat(client): add MockBrokerClient for offline order testing

Why: Order execution blocked until static IP provisioned; need testable path
What:
- src/client/mock_client.py: stateful offline broker with simulate_error + reset
- tests/unit/test_mock_client.py: 38 tests covering all BrokerClient methods
Ref: Order execution blocked (static IP required)
```
