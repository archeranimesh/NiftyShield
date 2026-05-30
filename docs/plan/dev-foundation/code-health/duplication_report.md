# CH-1 — Duplicate Code Scan Report

**Generated:** 2026-05-30
**Tool:** `pylint --disable=all --enable=similarities --min-similarity-lines=4 src/`
**Overall rating:** 9.98/10
**jscpd:** not available in environment — skipped

---

## Summary

9 similarity clusters found across `src/`. All are minor. No cluster represents a large logic
block that would justify a shared utility module now — most are SQL DDL, field-list
declarations, or short HTTP boilerplate that is contextually bound.

---

## Bucket 1 — Extract to shared helper

These are identical or near-identical logic blocks where extraction would reduce maintenance
risk.

### DUP-1: Dhan API HTTP fetch pattern (3 sites)

**Files:**
- `src/auth/dhan_verify.py:100–107`
- `src/dhan/positions.py:42–48`
- `src/dhan/reader.py:91–97` (also extends to `:92–119`)

**Duplicated block (~6 lines):**
```python
resp = requests.get(url, headers=headers, timeout=10)
resp.raise_for_status()
data = resp.json()
if isinstance(data, list):
    return data
```

**Recommendation:** Extract `_dhan_get(url, headers) -> list | dict` into
`src/dhan/_http.py`. Three callers; the pattern is mechanically identical. Low risk.

---

### DUP-2: SQLite date-range query builder fragment

**Files:**
- `src/mf/store.py:305–312`
- `src/portfolio/store.py:431–438`

**Duplicated block (~7 lines):**
```python
query += " AND snapshot_date <= ?"
params.append(to_date.isoformat())
query += " ORDER BY snapshot_date"
with _connect(self.db_path) as conn:
    rows = conn.execute(query, params).fetchall()
```

**Recommendation:** The `_connect` + query pattern is spread across many store methods
already. These two sites share the exact date-range tail. Low priority — acceptable to defer
until a store base class is introduced (if ever).

---

### DUP-3: `get_prev_snapshots` cursor pattern

**Files:**
- `src/dhan/store.py:206–212`
- `src/portfolio/store.py:495–501`

**Duplicated block (~6 lines):**
```python
" WHERE snapshot_date < ?",
(d.isoformat(),),
).fetchone()
if not row or not row["prev_date"]:
    return {}
rows = conn.execute(
```

**Recommendation:** Both implement a "find previous snapshot date" query. Could share a
`_get_prev_snapshot_date(conn, table, date) -> str | None` helper. Low priority for now.

---

## Bucket 2 — Acceptable duplication

Structurally similar but contextually distinct — extracting would couple unrelated modules or
obscure intent.

### DUP-4: Pydantic model field list (Leg-like models)

**Files:**
- `src/models/portfolio.py:63–72` (`Leg` or `Trade` model)
- `src/paper/models.py:46–54` (`PaperTrade` model)

**Duplicated block (~9 fields):**
```python
strategy_name: str = Field(..., min_length=1)
leg_role: str = Field(..., min_length=1)
instrument_key: str = Field(..., min_length=1)
trade_date: date
action: TradeAction
quantity: int = Field(..., gt=0)
price: Decimal = Field(..., gt=0)
notes: str = ""
```

**Assessment:** `PaperTrade` intentionally mirrors `Leg`/`Trade` in shape (it's a shadow
record for paper positions) but lives in a separate module with a `paper_` prefix constraint
and additional fields. A shared base class (`BaseLegFields`) would couple `src/models/` to
`src/paper/` — wrong direction. **Leave as-is.**

---

### DUP-5: SQL DDL column block (trades tables)

**Files:**
- `src/paper/store.py:28–37`
- `src/portfolio/store.py:80–89`

**Duplicated block (~9 DDL lines):**
```sql
id             INTEGER PRIMARY KEY AUTOINCREMENT,
strategy_name  TEXT NOT NULL,
leg_role       TEXT NOT NULL,
instrument_key TEXT NOT NULL,
trade_date     TEXT NOT NULL,
action         TEXT NOT NULL,
quantity       INTEGER NOT NULL,
price          TEXT NOT NULL,
notes          TEXT NOT NULL DEFAULT '',
```

**Assessment:** Two separate tables (`paper_trades` and `trades`) with the same core schema.
They share columns by design (paper mirrors live). SQL DDL cannot be factored further without
a migration generator. **Acceptable.**

---

### DUP-6: `_build_strategy_pnl` loop body

**Files:**
- `src/portfolio/summary.py:162–205`
- `src/portfolio/tracker.py:221–237`

**Duplicated block (~12 lines):**
The `LegPnL` construction loop and `StrategyPnL` return, plus the `compute_pnl` async method
docstring lines match.

**Assessment:** `summary.py` contains a pure helper (`_build_portfolio_summary`) and
`tracker.py` contains a live-fetch method (`compute_pnl`). The loop body is structurally
similar but the surrounding context differs (pure function vs. async method with DB access).
A shared helper is feasible but would need careful signature design to avoid coupling.
**Defer to Phase 1 refactor when the two modules are reviewed together.**

---

### DUP-7: Finideas strategy Leg constructor calls

**Files:**
- `src/portfolio/strategies/finideas/finrakshak.py:28–35`
- `src/portfolio/strategies/finideas/ilts.py:44–51`

**Duplicated block (~7 lines):**
Both define a `Leg(instrument_key="NSE_FO|37810", display_name="NIFTY DEC 23000 PE", ...)`.

**Assessment:** These are two different strategy definitions that happen to share one
overlapping leg (same instrument, same quantity). This is a real trade position recorded in
two strategy files — it is correct, not accidental. **False positive / acceptable.**

---

## Bucket 3 — Already abstracted / false positives

No findings in this category. All R0801 clusters represent genuine code sharing opportunities
or acceptable structural parallelism.

---

## Action Items

| ID | Priority | Recommendation |
|----|----------|----------------|
| DUP-1 | Medium | Extract `_dhan_get()` into `src/dhan/_http.py`; 3 callers |
| DUP-2 | Low | Defer; revisit if a store base class is introduced |
| DUP-3 | Low | Defer; small helper possible but not urgent |
| DUP-4 | None | Intentional design — leave as-is |
| DUP-5 | None | SQL DDL structural parallel — leave as-is |
| DUP-6 | Low | Revisit in Phase 1 `portfolio/` refactor |
| DUP-7 | None | Same instrument in two distinct strategies — correct |

The only item worth acting on before Phase 1 is **DUP-1**: the Dhan HTTP fetch pattern
appears in `auth/`, `dhan/positions.py`, and `dhan/reader.py`. Extracting it to
`src/dhan/_http.py` is a 3-file mechanical change with no design ambiguity.
