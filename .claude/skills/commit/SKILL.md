---
disable-model-invocation: true
---

# NiftyShield Commit Message Format

Use this format for every commit in this project. Run manually — never triggered automatically.

## Format

```
<type>(<scope>): <what changed, imperative mood, ≤60 chars>

Why: <one sentence on the reason or the problem solved>
What:
- <file path>: <one-line description of change>
- <file path>: <one-line description of change>
Ref: <relevant constraint from Current Constraints, or "none">
```

## Types

| Type | When |
|---|---|
| `feat` | New capability added |
| `fix` | Bug or incorrect behaviour corrected |
| `refactor` | Restructuring with no behaviour change |
| `test` | Test added or updated |
| `chore` | Tooling, config, deps, scripts |
| `docs` | Documentation only |

## Scope

Folder name under `src/` or `scripts/`. Examples: `portfolio`, `mf`, `client`, `notifications`, `auth`, `instruments`, `scripts`.

## Rules

- Subject line: imperative mood, ≤60 chars, no period at end
- `Why:` — one sentence: the reason or problem solved, not a restatement of what changed
- `What:` — one bullet per file changed, path relative to repo root
- `Ref:` — cite the relevant constraint from `CONTEXT.md → Current Constraints`, or `"none"`

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

## Usage

When you ask Claude to generate a commit message, it will produce the above format ready to paste into:

```bash
git commit -m "$(cat <<'EOF'
feat(portfolio): add trade overlay to snapshot pipeline

Why: Snapshots were using definition prices not actual execution prices
What:
- src/portfolio/tracker.py: internalize apply_trade_positions overlay
- src/portfolio/store.py: add ensure_leg for trade-only legs
Ref: none
EOF
)"
```
