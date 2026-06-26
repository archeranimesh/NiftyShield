# IC-F8 — Scheduled entry crons and EOD audit cron

> **Assigned to: Claude** — uses `schedule` skill to create five scheduled tasks.

**Prerequisite:** IC-F6 committed (`paper_ic_entry.py` must exist before scheduling it).

**No code files to create** — this story creates scheduled tasks via the `schedule` skill
and records the task IDs. The output is five running scheduled tasks, not source files.

---

## Context

### Entry schedule design

All four IC entry scripts run on **Wednesday at 10:30 IST**. The DTE window check inside
each script determines whether to actually enter or skip:

| Expiry type | DTE at entry (Wednesday) | DTE window gate | Enters when |
|---|---|---|---|
| Weekly | Next Tuesday ≈ DTE 6 | warn if outside 5–8; never block | Every Wednesday if IVR passes |
| Monthly | Next monthly ≈ DTE 30–35 | warn if outside 30–45; never block | Wednesday after last-Tuesday monthly expiry |
| Leaps | Next quarterly ≈ DTE 60–90 | warn if outside 60–90; never block | Wednesday after quarterly expiry (Mar/Jun/Sep/Dec) |
| Yearly | Next June/Dec ≈ DTE 180–270 | warn if outside 180–270; never block | Wednesday after yearly expiry |

No calendar math in the scheduler — the entry script's duplicate guard + IVR gate +
DTE window gate is the decision layer. The scheduler just fires every Wednesday.

IST 10:30 = UTC 05:00 → cron: `0 5 * * 3` (Wednesday = 3).

### EOD audit schedule

`paper_ic_snapshot.py` runs at 15:45 IST every market day.
IST 15:45 = UTC 10:15 → cron: `15 10 * * 1-5`.

---

## What to implement

Use the `schedule` skill to create **five** scheduled tasks:

### Task 1 — Weekly IC entry
- **Schedule:** Every Wednesday at 10:30 IST (cron `0 5 * * 3`)
- **Command:**
  ```
  cd /path/to/NiftyShield && python scripts/strategies/ic/paper_ic_entry.py --expiry-type weekly --no-dry-run
  ```
- **Description:** Weekly IC entry — enters if IVR ≥ 0.15 and no duplicate open position

### Task 2 — Monthly IC entry
- **Schedule:** Every Wednesday at 10:30 IST (cron `0 5 * * 3`)
- **Command:**
  ```
  cd /path/to/NiftyShield && python scripts/strategies/ic/paper_ic_entry.py --expiry-type monthly --no-dry-run
  ```
- **Description:** Monthly IC entry — enters only if DTE 30–45 (Wednesday after monthly expiry)

### Task 3 — Leaps IC entry
- **Schedule:** Every Wednesday at 10:30 IST (cron `0 5 * * 3`)
- **Command:**
  ```
  cd /path/to/NiftyShield && python scripts/strategies/ic/paper_ic_entry.py --expiry-type leaps --no-dry-run
  ```
- **Description:** Leaps IC entry — enters only if DTE 60–90 (Wednesday after quarterly expiry)

### Task 4 — Yearly IC entry
- **Schedule:** Every Wednesday at 10:30 IST (cron `0 5 * * 3`)
- **Command:**
  ```
  cd /path/to/NiftyShield && python scripts/strategies/ic/paper_ic_entry.py --expiry-type yearly --no-dry-run
  ```
- **Description:** Yearly IC entry — enters only if DTE 180–270 (Wednesday after yearly expiry)

### Task 5 — EOD IC audit snapshot
- **Schedule:** Every market day at 15:45 IST (cron `15 10 * * 1-5`)
- **Command:**
  ```
  cd /path/to/NiftyShield && python scripts/strategies/ic/paper_ic_snapshot.py
  ```
- **Description:** EOD IC audit — position summary + unresolved signal check for all four variants

---

## After creating the tasks

Record all five task IDs in `REFERENCES.md` under a new section:

```markdown
## Scheduled Task IDs — IC Automation

| Task | ID | Schedule (IST) | Script |
|---|---|---|---|
| IC Weekly Entry | <id> | Wed 10:30 | paper_ic_entry.py --expiry-type weekly |
| IC Monthly Entry | <id> | Wed 10:30 | paper_ic_entry.py --expiry-type monthly |
| IC Leaps Entry | <id> | Wed 10:30 | paper_ic_entry.py --expiry-type leaps |
| IC Yearly Entry | <id> | Wed 10:30 | paper_ic_entry.py --expiry-type yearly |
| IC EOD Snapshot | <id> | Mon–Fri 15:45 | paper_ic_snapshot.py |
```

---

## Commit (docs only — no code reviewer needed)

```
docs(references): record IC scheduled task IDs

Why: Task IDs needed for future enable/disable/update of IC entry crons.
What:
- REFERENCES.md: Scheduled Task IDs — IC Automation section
Ref: ic-full IC-F8
```

---

## Notes for future maintenance

- To **pause** weekly IC entry (e.g. high-VIX regime): use `mcp__scheduled-tasks__update_scheduled_task` to disable the weekly task ID.
- To **change entry time**: update the cron expression via the same tool.
- To **add a new expiry type**: add a new `CONFIGS` entry (IC-F2 pattern), register in daemon (IC-F5 pattern), create a new scheduled task here.
- The four Wednesday tasks run sequentially in the scheduler's execution context. If the weekly entry script takes >5 minutes (unlikely — it's a chain fetch + 4 DB writes), there is no impact on the other entry tasks since each is an independent scheduled task.
