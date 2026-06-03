# BA-9 — Add Kite credential block to `src/config.py` + `.env.example`

> Assigned to: Claude
> Phase: 4 — Config + VIX Ingest
> Priority: LOW
> Blocked by: BA-8 must be merged first

---

## Goal

Add Kite/Zerodha API credentials to `Settings` and document them in `.env.example`.
Dhan credentials already exist in config (`dhan_client_id`, `dhan_access_token`) — mirror
that pattern for Kite.

---

## Files to change

| File | Action |
|------|--------|
| `src/config.py` | Add Kite credential fields |
| `.env.example` | Add Kite credential entries with comments |
| `tests/unit/test_config.py` | Extend — test Kite fields load from env |

---

## What to implement

### `src/config.py` — new fields

```python
# Kite / Zerodha
kite_api_key: str | None = None
kite_access_token: str | None = None   # daily OAuth token
kite_api_secret: str | None = None     # used for token generation only
```

All optional (None by default) — consistent with the rest of the credentials block.
`kite_api_secret` is loaded from env but never logged. Add `repr=False` on the field.

### `.env.example`

```dotenv
# Kite / Zerodha (set upstox_env=kite to activate)
KITE_API_KEY=your_kite_api_key
KITE_ACCESS_TOKEN=daily_access_token_here
KITE_API_SECRET=your_api_secret   # never commit — used only for token generation
```

---

## Tests — extend `tests/unit/test_config.py`

1. **Kite fields present:** `Settings()` has `kite_api_key`, `kite_access_token`, `kite_api_secret` attributes.
2. **Load from env:** `Settings(_env_file=None)` with `KITE_API_KEY="test_key"` in env → `settings.kite_api_key == "test_key"`.  # pragma: allowlist secret
3. **Default None:** without env vars, all three Kite fields are `None`.

---

## Commit message

```
feat(config): add Kite/Zerodha credential fields + .env.example entries

Why: completes config surface for Kite broker activation via upstox_env=kite.
What:
- src/config.py: kite_api_key, kite_access_token, kite_api_secret (all Optional)
- .env.example: Kite credential block with comments
- tests/unit/test_config.py: 3 additional config tests
Ref: docs/plan/broker-abstraction/stories/BA-9.md
```

---

## Pre-baked graph context

```
search_graph("Settings")           # current credential fields — mirror Dhan pattern
search_graph("dhan_client_id")     # exact pattern to replicate for Kite
```
