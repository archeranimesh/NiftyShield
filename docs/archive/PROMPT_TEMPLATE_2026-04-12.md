# NiftyShield — Session Prompt Template

Copy this, fill in the bracketed fields, delete unused lines.
The more fields you fill, the less back-and-forth before code starts.

---

```
Read CONTEXT.md.

Task: [one sentence — what to implement]

Scope:
- Module: [src/module/ or scripts/]
- Files to change: [specific files, or "unknown — confirm before starting"]
- New files: [yes/no — describe if yes]

TODO ref: [paste the relevant item from CONTEXT.md → Immediate TODOs]

Constraints: [any deviation from project instructions, or "none"]

Tests: [standard / specific coverage needed / skip (rare)]

Additional context: [fixture path, instrument key, env var, or anything non-obvious]
```

---

## Examples

**Minimal (well-scoped task):**
```
Read CONTEXT.md.

Task: Add --date YYYY-MM-DD parameter to daily_snapshot.py for historical P&L query.

Scope:
- Files to change: scripts/daily_snapshot.py, src/portfolio/store.py, src/mf/store.py
- New files: no

TODO ref: TODO #1 — daily_snapshot.py enhancements (date parameter section)

Tests: standard
```

**For a new module:**
```
Read CONTEXT.md.

Task: Build src/notifications/telegram.py — send formatted P&L summary to Telegram after each cron run.

Scope:
- Module: src/notifications/
- Files to change: scripts/daily_snapshot.py (inject notifier)
- New files: src/notifications/__init__.py, src/notifications/telegram.py

TODO ref: TODO #2 — Telegram bot notifications

Constraints: non-fatal, skip if TELEGRAM_BOT_TOKEN not in env. raw requests only, no SDK.

Tests: standard — mock requests.post, test message format, test graceful skip when env vars absent.

Additional context: env vars TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID already documented in CONTEXT.md
```

---

## What to always include

| Field | Why |
|---|---|
| "Read CONTEXT.md" | Forces me to load current state before any code |
| Task | Scopes the work to one sentence — prevents scope creep |
| TODO ref | Ties the work to the agreed priority list |
| Constraints | Surfaces deviations from project instructions before I start |

## What you can skip

- Explaining project conventions (already in project instructions)
- Repeating architectural decisions (already in CONTEXT.md)
- Asking me to follow Decimal/async/test rules (already enforced)
- Explaining what BrokerClient is, what AMFI is, etc.
