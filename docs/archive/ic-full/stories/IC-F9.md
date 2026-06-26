# IC-F9 — Eliminate `_parse_expiry` monkey-patch in `paper_ic_snapshot.py`

> **Assigned to: Claude** — single-file refactor; no TDD loop needed.

**Prerequisites:**
- IC-F7 — `paper_ic_snapshot.py` committed (SHA: 90bdd29)

**Problem:**
`paper_ic_snapshot.py` instantiates `IronCondorV1` then immediately overrides its
private `_parse_expiry` method with a more robust regex:

```python
# paper_ic_snapshot.py lines 160–169
ic._parse_expiry = lambda key: (
    datetime.strptime(
        _EXPIRY_RE_ROBUST.search(key).group(1).upper(),
        "%d%b%Y",
    ).date()
    if _EXPIRY_RE_ROBUST.search(key)
    else None
)
```

This works today but is fragile:
- If `_parse_expiry` is renamed or inlined in `IronCondorV1`, the patch silently
  stops applying and the snapshot falls back to the weaker regex without any error.
- It couples the snapshot script's correctness to a private implementation detail
  of the strategy class.

The root cause is that `IronCondorV1._parse_expiry` uses a narrower pattern
(`NSE_FO|NIFTY<date>(PE|CE)`) whereas the snapshot needs a more permissive one
that handles the `NIFTY<date><strike>(PE|CE)` format that appears in live position
keys.

---

## Implementation

### Option A — Widen the pattern in `IronCondorV1` (preferred)

Replace the private `_EXPIRY_RE` in `src/strategy/ic_nifty_v1.py` with
`_EXPIRY_RE_ROBUST` (or equivalent) so `_parse_expiry` handles both key formats.
Remove the monkey-patch block from `paper_ic_snapshot.py`.

Check all callers of `_parse_expiry` in `ic_nifty_v1.py` to confirm the wider
pattern does not produce false positives.

### Option B — Expose a module-level helper

Extract `_parse_expiry` logic into a module-level function in `ic_nifty_v1.py`
(e.g. `parse_ic_expiry(instrument_key) -> date | None`) and call it directly from
the snapshot, bypassing the strategy instance entirely.

**Recommendation:** Option A — fewer moving parts; the wider regex is strictly more
correct and benefits all callers.

---

## Files to change

- `src/strategy/ic_nifty_v1.py` — widen `_EXPIRY_RE` / `_parse_expiry`
- `scripts/strategies/ic/paper_ic_snapshot.py` — remove monkey-patch block
  (lines 160–169); remove `_EXPIRY_RE_ROBUST` if no longer used elsewhere

---

## Tests

1. Happy path: `_parse_expiry` resolves both key formats:
   - `NSE_FO|NIFTY26JUN202624000PE` → `date(2026, 6, 26)`
   - `NSE_FO|NIFTY26JUN2026PE24000` → `date(2026, 6, 26)`
2. Edge: unrecognised key → `None` (no exception).

Existing `ic_nifty_v1` tests must continue to pass unchanged.

---

## Commit

```
refactor(strategy): widen _parse_expiry regex; remove snapshot monkey-patch

Why: snapshot was overriding ic._parse_expiry at runtime to handle live key
format — fragile coupling to a private method.
What:
- src/strategy/ic_nifty_v1.py: _EXPIRY_RE accepts both key formats
- scripts/strategies/ic/paper_ic_snapshot.py: remove monkey-patch block
Ref: ic-full IC-F9
```
