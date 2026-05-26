# Paper Trading Implementation Tasks

> Story file for Antigravity — one task per session, work top to bottom.
> After each task: change `- [ ]` to `- [x]`, append `| SHA: <sha>`.
> Add one session log line to `TODOS.md`.

---

- [x] **Task A — `scripts/paper_csp_roll.py`** | SHA: fcfede8

  Create a script that automates rolling Leg 1 (CSP) positions in `paper_csp_nifty_v1`,
  mirroring `scripts/paper_3track_overlay_roll.py`.

  **Before any code:** query the graph —
  `get_code_snippet("paper_3track_overlay_roll")` for roll script structure;
  `get_code_snippet("PaperStore")` for `delete_trade` / `get_trades` / `record_trade` API;
  `get_code_snippet("PaperTrade")` for exact field list;
  `search_graph("get_expiry_candidates")` for expiry selection signature.

  **What the script does:**
  - Finds the open CSP leg in `paper_csp_nifty_v1` expiring within DTE ≤ 5 (or `--force` to bypass).
  - Parses expiry from instrument key — same `parse_expiry_from_key` pattern as the overlay roll script.
  - Closes expiring leg: inserts a closing trade (opposite action at current LTP) via `PaperStore.record_trade`.
  - Opens replacement leg: calls `get_expiry_candidates` for next monthly expiry, writes new trade.
  - Atomic: if open fails, rollback the close via `PaperStore.delete_trade`.
  - `--dry-run`: prints proposed close+open trades without writing to DB.
  - `--force`: bypasses DTE ≤ 5 gate.
  - LTP via `BrokerClient` protocol, injected via `factory.py` — never import concrete client directly.

  **Tests** in `tests/unit/paper/test_paper_csp_roll.py`:
  - Happy path: open CSP leg at DTE 4 → close + open roundtrip succeeds.
  - DTE gate: leg at DTE 6 → blocked unless `--force`.
  - Rollback: open fails → `delete_trade` called on the close record.
  - Dry run: no DB writes, output printed.

  **Commit:** `feat(scripts): add paper_csp_roll.py for CSP leg roll automation`

---

- [ ] **Task B — migrate private instrument loop in `paper_3track_overlay.py:243`** | SHA:

  Replace the `lookup._instruments` private attribute access with the `get_expiry_candidates`
  public API. Single loop, single file — do not touch anything else.

  **Before any code:**
  `search_code("lookup._instruments")` — find exact line(s) in `paper_3track_overlay.py`;
  `get_code_snippet("get_expiry_candidates")` — confirm signature and return type;
  `search_code("get_expiry_candidates")` in `paper_3track_entry.py` — see the existing call pattern;
  read surrounding context via `bash sed -n 'N,Mp'` — do not `view_file` the whole script.

  Use the same `preference` order already used in `paper_3track_entry.py`.

  **Tests:** add one test to `tests/unit/paper/test_paper_3track_overlay.py` asserting that the
  refactored path calls `get_expiry_candidates` (not `_instruments`) — mock `get_expiry_candidates`
  and assert it was called with the expected arguments.

  **Commit:** `refactor(scripts): migrate overlay expiry lookup to get_expiry_candidates public API`

---

- [ ] **Task C — CLI-12: surface `--notes` in `paper_snapshot.py` output** | SHA:

  `PaperTrade` has a `notes: str | None` field in `paper_trades`. No snapshot script reads it.
  Surface it in `scripts/paper_snapshot.py`.

  **Before any code:**
  `get_code_snippet("PaperTrade")` — verify `notes` field and type;
  `get_code_snippet("PaperStore.get_trades")` — confirm return type;
  `search_code("_run")` in `paper_snapshot.py` — locate where per-strategy P&L is printed.

  **What to add:** In `_run()`, after computing P&L for a strategy, call `store.get_trades(name)`
  and collect non-empty `trade.notes` from open trades (`trade.closed_at is None`). If any notes
  exist, print a `Notes:` line below the P&L table formatted as `[leg_role] {notes}` per leg,
  deduplicated. No `get_trade_notes()` helper — inline is fine.

  **Tests** (existing test file for `paper_snapshot.py`):
  - One open trade with notes + one without → notes line appears only for the one with notes.
  - All trades have null/empty notes → no notes line in output.

  **Commit:** `feat(scripts): surface trade notes in paper_snapshot output`
