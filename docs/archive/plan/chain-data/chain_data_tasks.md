# chain-data — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md` session log.
> Full story spec for each task: `docs/plan/chain-data/chain_data_stories.md`.
>
> **Prerequisite check before CD1.1:** Confirm `src/client/upstox_market.py` +
> `parse_upstox_option_chain` exist (task 0.2 deliverable). If not, stop — this story
> cannot start until 0.2 is committed.

---

## Phase CD1 — EOD snapshot writer + cron

- [x] **CD1.1** — `src/backtest/chain_writer.py`: Parquet writer for chain snapshots (write + idempotent overwrite) + tests | SHA: ce57240
- [x] **CD1.2** — `scripts/upstox_chain_snapshot.py`: EOD snapshot cron (3 expiries, holiday guard, 3:30 PM IST) + tests | SHA: 0db8767

## Phase CD2 — Intraday 5-min snapshot

- [x] **CD2.1** — `scripts/upstox_chain_intraday.py`: 5-min intraday cron (same schema, `--mode` flag optional) + tests | SHA: c1aea22

## Phase CD3 — Query utilities

- [x] **CD3.1** — `src/backtest/chain_reader.py`: DuckDB-based scan + filter utilities (time-range, strike, expiry) + tests | SHA: 7c0fe66

## Phase CD4 — Docs close

- [x] **CD4** — Docs close: `CONTEXT.md` tree, `DECISIONS.md` entry, `BACKTEST_PLAN_PHASE1.md` checkboxes 1.10 + 1.10a, `TODOS.md` session log | SHA: 80cf95e
