# ic-full — Unified Iron Condor Task Checklist

> **Supersedes:** `docs/plan/ic-e2e` (IC-E2, IC-E3, IC-E4) and `docs/plan/ic-multi-expiry` (all).
> Do not pick up tasks from those plans.
>
> **Already done:** ic-e2e IC-E1 — `auto_execute` attribute + `STRATEGY_IC` constant (SHA: 17a9744).
>
> Find the first unchecked `- [ ]` **assigned to you**. One task per session.
> Tick box + append `| SHA: <sha>` when done. One line in `TODOS.md` session log.
> Full spec: `docs/plan/ic-full/stories/<TASK_ID>.md`
>
> **Goal:** Four independently tracked IC variants (weekly / monthly / leaps / yearly),
> fully automated — scheduled Wednesday 10:30 IST entry, auto-execute exits, EOD audit cron.

---

## Dependency map

```
IC-F1 (Claude)    ← IVR wiring          → unblocks IC-F3
IC-F2 (Claude)    ← ICExpiryConfig      → unblocks IC-F3, IC-F5, IC-F6, IC-F7
IC-F3 (Antigravity) ← parameterise IC  → unblocks IC-F5, IC-F6, IC-F7
IC-F4 (Claude)    ← weekly bucket       → unblocks IC-F6 (weekly entry DTE gate)
IC-F5 (Antigravity) ← daemon 4×        → independent after IC-F3
IC-F6 (Antigravity) ← entry script     → unblocks IC-F8
IC-F7 (Antigravity) ← EOD snapshot     → independent after IC-F3
IC-F8 (Claude)    ← scheduled crons    → final story; requires IC-F6 committed
```

---

## Phase F1 — IVR Wiring

- [x] **IC-F1** `[Claude]` — `src/strategy/ic_nifty_v1.py`: wire IVR into `describe_context` from VIX Parquet (same pattern as `paper_cc_entry.py`) + 2 tests | SHA: cd8415a

## Phase F2 — Config Model

- [x] **IC-F2** `[Claude]` — `src/strategy/ic_expiry_config.py`: `ICExpiryConfig` frozen dataclass with entry + exit thresholds per expiry type; `CONFIGS` presets for weekly/monthly/leaps/yearly; four `STRATEGY_IC_*` constants in `src/paper/constants.py` + 6 tests | SHA: 5921426

## Phase F3 — Parameterise IronCondorV1

- [x] **IC-F3** `[Antigravity]` — `src/strategy/ic_nifty_v1.py`: constructor accepts `ICExpiryConfig`; `strategy_name` → property; `auto_execute = True`; all hardcoded thresholds → config fields; `_auto_select_action()` priority method; existing + 4 new tests | SHA: 6296328

## Phase F4 — Weekly Expiry Bucket

- [ ] **IC-F4** `[Claude]` — `src/instruments/lookup.py`: `"weekly"` DTE≤14 Tuesday bucket in `get_expiry_candidates()`; docstring updated + 6 tests

## Phase F5 — Daemon Registration

- [ ] **IC-F5** `[Antigravity]` — `scripts/monitor_daemon.py`: replace single IC registration with loop over all four `CONFIGS` presets; per-instance guard preserved + 2 tests

## Phase F6 — Entry Script

- [ ] **IC-F6** `[Antigravity]` — `scripts/strategies/ic/paper_ic_entry.py`: `--expiry-type [weekly|monthly|leaps|yearly]`; all gates (IVR, duplicate, DTE-window, liquidity, portfolio-delta); entry delta + wing width from config; Telegram entry notification + 12 tests

## Phase F7 — EOD Snapshot

- [ ] **IC-F7** `[Antigravity]` — `scripts/strategies/ic/paper_ic_snapshot.py`: EOD audit cron; iterates all four variants; informational Telegram report (auto-execute handles exits — snapshot is audit log only) + 8 tests

## Phase F8 — Scheduled Entry Crons

- [ ] **IC-F8** `[Claude]` — four scheduled tasks via `schedule` skill: every Wednesday 10:30 IST, one per expiry type; each calls `paper_ic_entry.py --expiry-type X --no-dry-run`; DTE gate in entry script handles "right Wednesday" logic
