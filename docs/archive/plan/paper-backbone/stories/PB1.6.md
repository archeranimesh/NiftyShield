# PB1.6 — `src/paper/store.py`: DB migrations + approval store methods + tests
> **Assigned to: Antigravity** — pure DB migrations + CRUD, zero ambiguity, fully spec'd DDL in schema.md.

**Files to change:**
- `src/paper/store.py` — add three table migrations + approval CRUD methods
- `tests/unit/paper/test_paper_store_approvals.py` — new test file (keep existing tests untouched)

**Before implementing:** Read `docs/plan/paper-backbone/paper_backbone_schema.md` — exact DDL
for all three new tables. Do not write DDL from memory.

**What to implement in `PaperStore`:**

Three table migrations added to the `executescript` block inside `PaperStore.__init__`
(the existing pattern uses `conn.executescript(_SCHEMA)` — extend `_SCHEMA` with the three
new `CREATE TABLE IF NOT EXISTS` statements from `paper_backbone_schema.md`):

```
pending_approvals, council_outputs, daemon_heartbeat
```

New methods:

```python
def create_approval(
    self,
    strategy_name: str,
    event_type: str,
    council_output_json: str,
    telegram_msg_id: int | None,
    expires_at: str,            # ISO UTC
) -> int:
    """INSERT into pending_approvals, status=PENDING. Returns new row id."""

def resolve_approval(
    self,
    approval_id: int,
    status: Literal["APPROVED", "REJECTED", "EXPIRED"],
    approved_rank: int | None = None,
) -> None:
    """UPDATE pending_approvals: set status, resolved_at=now(), approved_rank."""

def get_pending_approvals(self) -> list[dict]:
    """SELECT all rows with status=PENDING, ordered by created_at ASC."""

def write_heartbeat(
    self,
    pid: int,
    strategies: list[str],
    last_event: str | None = None,
) -> None:
    """INSERT OR REPLACE into daemon_heartbeat (id=1). Updates last_beat=now UTC."""

def get_heartbeat(self) -> dict | None:
    """SELECT the single daemon_heartbeat row. Returns None if absent."""
```

**Tests (`tests/unit/paper/test_paper_store_approvals.py`):**

All tests use `tmp_path` fixture with a fresh `PaperStore`.

- `create_approval` → `get_pending_approvals` returns one row with status `PENDING`.
- `resolve_approval(APPROVED, rank=1)` → row no longer in `get_pending_approvals`;
  `resolved_at` is set.
- `resolve_approval(EXPIRED)` → row no longer in `get_pending_approvals`.
- `create_approval` called twice → `get_pending_approvals` returns two rows.
- `resolve_approval` one of two → `get_pending_approvals` returns one row.
- `write_heartbeat` then `get_heartbeat` → round-trip; `pid`, `strategies` JSON correct.
- `write_heartbeat` called twice → still one row (upsert).
- `get_heartbeat` on empty DB → `None`.
- All three new tables created by `PaperStore.__init__` → existing `paper_trades` table
  unaffected (confirm row count unchanged after migration).

**Commit:** `feat(paper): add pending_approvals + council_outputs + daemon_heartbeat migrations and store methods`

---

## Pre-baked Context

> Graph queries pre-run 2026-05-31. Skip "Before any code" graph calls — use these directly.

**`PaperStore.__init__`** — `src/paper/store.py:110`. Constructor: `PaperStore(db_path: Path | str)`.
Existing init pattern:
```python
self.db_path = Path(db_path)
self.db_path.parent.mkdir(parents=True, exist_ok=True)
with _connect(self.db_path) as conn:
    conn.executescript(_SCHEMA)
    # Migration: ALTER TABLE ... ADD COLUMN ... (in try/except OperationalError)
```
The `_SCHEMA` module-level string contains all `CREATE TABLE IF NOT EXISTS` statements.
**Extend `_SCHEMA`** — append the three new table DDLs from `paper_backbone_schema.md`.
Do NOT add a new `executescript` call — append to the existing `_SCHEMA` constant.

**DB connect internal** — `PaperStore` uses `_connect` (module-private alias of `src.db.connect`).
Look at the imports at the top of `src/paper/store.py` to confirm the alias name before writing.

**Existing tables** — `paper_trades`, `paper_nav_snapshots`, `paper_proxy_delta_log`, `paper_leg_snapshots`.
The `_SCHEMA` string creates all four. Your new DDL appends three more (`pending_approvals`,
`council_outputs`, `daemon_heartbeat`).

**`strategies` field in `write_heartbeat`** — store as JSON string (`json.dumps(strategies)`);
read back with `json.loads`. The `daemon_heartbeat` table stores it as TEXT.
