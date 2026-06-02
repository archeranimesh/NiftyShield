# PA2 — Cleanup: retire paper_csp_roll.py + docs update
> **Assigned to: Claude** — targeted Edit calls only; no new code.

**Files to change:**
- `scripts/strategies/csp/paper_csp_roll.py` — delete
- `CONTEXT.md` — remove `paper_csp_roll.py` from scripts list; add note that CSP roll is now handled by the backbone
- `DECISIONS.md` — new entry: "paper_csp_roll.py retired; roll logic absorbed into CSPNiftyV1 + PaperExecutor"
- `TODOS.md` — session log entry

**Prerequisite:** PA1.1 and PA1.3 must both be committed and green before this runs. Cron entries for both retired scripts must be removed from the system crontab before or alongside this task.

---

## Steps

1. Confirm PA1.1 and PA1.3 are committed: check SHAs in tasks file.
2. Delete both scripts:
   ```
   git rm scripts/strategies/csp/paper_csp_roll.py
   git rm scripts/strategies/three_track/paper_3track_overlay_roll.py
   ```
3. Run tests to confirm nothing imports either: `python -m pytest tests/unit/ --tb=no -q`
4. Edit `CONTEXT.md` — remove both scripts from the scripts tree; note that CSP and 3-track overlay rolls are now backbone-managed.
5. Edit `DECISIONS.md` — add rows:
   - `paper_csp_roll.py retired (PA2) — roll signal + strike selection moved into CSPNiftyV1._select_roll_target`
   - `paper_3track_overlay_roll.py retired (PA2) — overlay roll signals moved into NiftyTrackComparisonV1._select_overlay_roll_target`
6. Edit `TODOS.md` — add session log entry.
7. Commit.

---

## Commit

```
chore(scripts): retire paper_csp_roll + paper_3track_overlay_roll

Why: Roll logic absorbed into CSPNiftyV1 (PA1.1) and
NiftyTrackComparisonV1 (PA1.3); executor handles legs_to_open.
What:
- scripts/strategies/csp/paper_csp_roll.py: deleted
- scripts/strategies/three_track/paper_3track_overlay_roll.py: deleted
- CONTEXT.md: remove retired scripts from tree
- DECISIONS.md: retirement decisions logged
Ref: paper-backbone-adj PA2
```
