---
model: claude-sonnet-4-5
description: P3 script hygiene — AR-12. Defers module-level I/O imports in nuvama_intraday_tracker.py into async def main(). Only touches one script. Safe to run in parallel with p3-sql-agent and p3-protocol-agent.
---

You are executing Phase 1, Stream C of the P3 sprint for NiftyShield.

## Your Scope (files you may touch)

- `scripts/nuvama_intraday_tracker.py` only

**Do NOT touch:** `src/`, `scripts/daily_snapshot.py`, or any test files. This is a pure structural refactor of one script.

---

## AR-12: Defer Module-Level I/O Imports in `nuvama_intraday_tracker.py`

**Problem:** These imports are at module level, meaning the auth chain and SDK fire on import — the script can't be safely imported in tests:

```python
# CURRENT — at module level (top of file, outside any function)
from src.auth.nuvama_verify import load_api_connect
from src.nuvama.store import NuvamaStore
from src.nuvama.options_reader import parse_options_positions
from src.client.factory import create_client
from src.client.exceptions import LTPFetchError
```

**Fix:** Move all five imports inside `async def main()`, matching the `daily_snapshot.py` pattern:

```python
# AFTER — inside async def main():
async def main() -> int:
    from src.auth.nuvama_verify import load_api_connect
    from src.nuvama.store import NuvamaStore
    from src.nuvama.options_reader import parse_options_positions
    from src.client.factory import create_client
    from src.client.exceptions import LTPFetchError
    
    # ... rest of function unchanged
```

### Steps

1. Use `get_code_snippet` on the `main` function of `nuvama_intraday_tracker.py` to confirm the current structure.
2. Identify all five import statements at module level.
3. Move them to the top of `async def main()` — before the first use of any symbol they provide.
4. Ensure `logger` and any `from __future__ import annotations` stay at module level — only I/O-triggering imports move.
5. Verify the module is importable without `.env`: `python -c "import scripts.nuvama_intraday_tracker"` — must not raise.
6. No test file changes required — this is a pure structural refactor.

### Verification

```bash
# Must not import the SDK at module level after the fix:
python -c "import scripts.nuvama_intraday_tracker; print('OK')"

# Full suite must stay green:
python -m pytest tests/unit/ -v --tb=short
```

### Commit

```
refactor(scripts): defer I/O imports in nuvama_intraday_tracker into main()

Why: Module-level SDK imports block safe test imports and violate the deferred-I/O pattern established in daily_snapshot.py
What:
- scripts/nuvama_intraday_tracker.py: move load_api_connect, NuvamaStore, parse_options_positions, create_client, LTPFetchError imports inside async def main()
Ref: none
```
