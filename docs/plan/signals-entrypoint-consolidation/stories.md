# Signals Entrypoint Consolidation — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. No `schema.md` — no DB schema change in this
> story.

---

## SEC-1 — One trading-day guard

**Intent:** every signal entrypoint currently either copy-pastes a `if not is_trading_day(market_today()): logger.info(...); return` block (`morning_signal`, `signal_report`, and — after SPT —
`signal_paper_entry`) or lacks the guard entirely (`record_signal_outcome`, which relies on `store.get_signal(today)` returning `None` → `sys.exit(1)`). Replace all of it with one helper.

- **`src/market_calendar.py`** — add:
  - `guard_trading_day(logger, script_name: str) -> bool` — returns `True` on a trading day;
    on a holiday/weekend logs one structured line
    (`f"{script_name}.skipped_non_trading_day"`, with the date) and returns `False`. Callers
    do `if not guard_trading_day(logger, _SCRIPT_NAME): return`.
  - `is_market_session_now(now: datetime | None = None) -> bool` — `True` iff `now` (default
    `market_now()`) is a trading day and the time is within 09:15–15:30 IST. `StrategyMonitor`
    currently inlines this window check in `_tick`.
- **Adopt** in `scripts/morning_signal.py`, `scripts/signal_report.py`, `scripts/signal_paper_entry.py`, and `src/strategy/monitor.py` (the `_tick` session check → `is_market_session_now`).
  `record_signal_outcome` adopts it via SEC-3's `signal_eod` merge — if SEC-3 is not yet done, add the guard to `record_signal_outcome.py` directly here and SEC-3 carries it into the merged script.

**Before any code:** `get_code_snippet("is_trading_day")`, `get_code_snippet("market_today")`, `search_graph("market_now")`, `get_code_snippet("_tick")` (the monitor window check),
`search_code("is_trading_day\\(market_today")` (every current call site).

**Tests:** `guard_trading_day` returns `True` on a Wednesday, `False` + one log line on Republic Day and on a Saturday; `is_market_session_now` `True` at 10:00 on a trading day, `False` at 08:00, at
16:00, and at 10:00 on a holiday. Each adopting call site keeps its existing skip behaviour (one regression test per script that it early-returns on a holiday).

**Commit:** `refactor(signals): single trading-day guard across signal entrypoints`

---

## SEC-2 — `DailySignal.is_actionable`

**Intent:** the `trade_action is not TradeAction.NO_TRADE` predicate is hand-written in `morning_signal` (gates entry-premium capture + the SPT tail-call), `record_signal_outcome` (`is_trade`),
`signal_report` (every section branches on it), and `signal_track_v1` (the SPT-3 entry hook). One property.

- **`src/signals/models.py`** — add to `DailySignal`:
  ```python
  @property
  def is_actionable(self) -> bool:
      """True when the consensus is a directional trade, not NO_TRADE."""
      return self.trade_action is not TradeAction.NO_TRADE
  ```
Frozen model — a computed property, no new field, no schema impact.
- **Refactor** the four call sites to `signal.is_actionable`. Pure mechanical swap; no behaviour change.

**Before any code:** `get_code_snippet("DailySignal")` (confirm it is the frozen Pydantic model and where `trade_action` lives), `get_code_snippet("TradeAction")`, `search_code("NO_TRADE")` (every
branch), `search_code("is_trade")`.

**Tests:** `is_actionable` is `True` for a `BUY_CALL` / `BUY_PUT` `DailySignal` and `False` for a `NO_TRADE` one (build both via a graph-checked helper — pull the `DailySignal` field list first, do
not write the `_make_*` from memory). One regression test per refactored call site is not required beyond the existing suite — the swap is covered by those tests already exercising the NO_TRADE path.

**Commit:** `refactor(signals): DailySignal.is_actionable replaces inline NO_TRADE checks`

---

## SEC-3 — Merge the two EOD scripts

**Intent:** `record_signal_outcome.py --auto` (16:00) and `signal_report.py` (16:35) run 35 minutes apart only so the outcome row is written before the report reads it. One script, one cron, one guard
— with the idealized `SignalOutcome` baseline row written exactly as today.

- **`scripts/signal_eod.py`** — `_SCRIPT_NAME = "scripts.signal_eod"`. `guard_trading_day` once at the top. Then:
  1. **Record phase** — the current `record_signal_outcome.py --auto` body verbatim: resolve
     the monthly option via `resolve_monthly_option`, fetch the 15:00 LTP, compute the
     held-to-close counterfactual, write the `SignalOutcome` row. This is the frictionless
     baseline — it is **not** the paper track and must not read `paper_*` tables.
  2. **Report phase** — the current `signal_report.py` body: aggregate, render, push the
     Telegram digest.
A failure in the record phase is logged and the report phase still runs (mirrors the existing cron-boundary isolation).
- **Flags** — keep `--auto` (record only) and add `--report-only` for manual re-runs; default (no flag) = both phases.
- **Retire** `scripts/record_signal_outcome.py` and `scripts/signal_report.py` (git rm) once `signal_eod.py` covers them. Update every doc reference (`CONTEXT.md`, `DECISIONS.md`, `LOGGING.md` if it
  names them, the runbook).
- **Crontab** — remove the `16:00 record_signal_outcome` and `16:35 signal_report` lines; add one `16:00 signal_eod` line. Deliver the exact replacement block.

**Keeps both signals:** the paper track (SPT, on `PaperStore`) and the idealized `SignalOutcome` baseline (here, on `SignalStore`) stay separate series measuring different things — the merge is of two
*advisory* scripts, orthogonal to the execution layer.

**Before any code:** `get_code_snippet("record_signal_outcome")` / its `main` + `--auto` branch, `get_code_snippet("signal_report")` / its `main`, `get_code_snippet("SignalOutcome")`,
`get_code_snippet("SignalStore")` (the `record_outcome` / report reads), `get_code_snippet("resolve_monthly_option")`.

**Tests:** the record phase writes a `SignalOutcome` row byte-identical to the old `record_signal_outcome --auto` for a fixed fixture `DailySignal` + LTP (regression); the report phase renders
unchanged from a fixture outcome set; `--auto` runs record only, `--report-only` runs report only, no flag runs both; a record-phase exception still lets the report phase run; holiday → both phases
skipped via the one guard. No network.

**Commit:** `refactor(signals): merge record_signal_outcome + signal_report into signal_eod`

---

## SEC-4 — Orchestration-only `morning_signal` (discretionary)

**Intent:** after SPT-6's tail-call, `scripts/morning_signal.py` mixes pipeline work (snapshot assembly, provider fan-out, aggregation, persistence, the paper-entry hand-off) with cron-boundary
concerns (logging setup, Telegram, exception isolation). Extract the pipeline.

- **`src/signals/pipeline.py`** — `run_morning_signal_pipeline(broker, store, *, bod_path) -> tuple[DailySignal, MarketSnapshot]` (or a small result dataclass): everything from
  `assemble_market_snapshot` through `store.record_signal` and the SPT-6 `open_signal_paper_entry` tail-call. Pure of Telegram and `setup_logging`.
- **`scripts/morning_signal.py`** — becomes: `setup_logging` → `create_client` → `store` → `run_morning_signal_pipeline(...)` → build + send the two Telegram messages (advisory + cost). The
  cron-boundary `try/except` around the paper entry moves inside the pipeline (or stays at the script, implementer's call — document it).

**Discretionary:** if the snapshot fetch, the provider fan-out `asyncio.gather`, and the Telegram send do not separate cleanly from the script's own I/O without contortion, this task is a no-op —
record the reason in the commit body and tick the box. Do not force a bad seam.

**Before any code:** `get_code_snippet("run")` (the `morning_signal` entry), `get_code_snippet("assemble_market_snapshot")`, `trace_path("morning_signal")`, the SPT-6 `open_signal_paper_entry`
signature.

**Tests:** `run_morning_signal_pipeline` returns a `DailySignal` + `MarketSnapshot` for a mock broker + in-memory store, persists exactly one signal row, and calls the paper-entry hook once when the
signal is actionable / not at all on `NO_TRADE`. No network.

**Commit:** `refactor(signals): extract run_morning_signal_pipeline` — or, if skipped, fold the "not worth it" note into SEC-5's commit and leave no empty commit.

---

## SEC-5 — `signal_paper_entry.py` keep-or-delete

**Intent:** SPT-6 shipped `scripts/signal_paper_entry.py` as a manual backfill tool on the assumption the `morning_signal` tail-call would occasionally fail and need a re-run. Review that assumption
against the actual track record once the tail-call has run for a while.

- **Keep** — if the tail-call has failed at least once in a way a manual re-entry fixed: keep the script, ensure it uses `guard_trading_day` + `is_actionable`, and document it in the runbook as the
  sanctioned recovery path.
- **Delete** — if the tail-call has been reliable: `git rm scripts/signal_paper_entry.py` and relocate the re-entry path to a `--replay-date YYYY-MM-DD` flag on `scripts/signal_eod.py` or a
  `scripts/dev/` helper (per the "no throwaway scripts for repeatable ops" rule — it stays a tested CLI, just not a top-level script).

**Before any code:** `git log --oneline -- scripts/signal_paper_entry.py` and `grep -c paper_entry_failed logs/morning_signal.log` (has it ever fired?); the SPT-6 story spec for the original
rationale.

**Tests:** if kept — the guard + `is_actionable` adoption is covered by SEC-1 / SEC-2 tests. If the `--replay-date` flag is added, one test that it re-runs the entry hook for the given date and no-ops
if a position for that date already exists.

**Commit:** `refactor(signals): <keep signal_paper_entry as backfill tool | fold re-entry into signal_eod --replay-date>`

---

## SEC-6 — Docs close

`CONTEXT.md` — update the `src/signals/` bullet's cron list to the final state (09:30 `morning_signal` incl. the paper-entry tail-call; 16:00 `signal_eod`; the monitor daemon for
`paper_signal_track_v1`; SPT-7 + `signal_paper_entry`/replay as manual tools) and record the final crontab. `DECISIONS.md` §P&L & Reporting — a note that `record_signal_outcome` + `signal_report`
merged into `signal_eod` (2 crons → 1), the idealized `SignalOutcome` baseline unchanged. `LOGGING.md` — swap any `record_signal_outcome` / `signal_report` `_SCRIPT_NAME` references for
`scripts.signal_eod`. `TODOS.md` — session-log line + delete the `signals-entrypoint-consolidation` backlog pointer. `docs/plan/README.md` — collapse the story row to a `✅ Archived →
docs/archive/plan/signals-entrypoint-consolidation/` pointer. Then `git mv docs/plan/signals-entrypoint-consolidation/ docs/archive/plan/` and append the `TODOS.md` line to
`docs/archive/TODOS_ARCHIVE.md` — same commit, per §Conventions *Completion → archive*.

**Commit:** `docs(signals-entrypoint-consolidation): close — <one line>`
