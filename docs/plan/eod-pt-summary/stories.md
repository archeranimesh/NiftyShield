# EOD PT Summary — Implementation Stories

## PT-1 — Document the confirmed 3-message split

**Problem:** The report's shape (columns, formats, message split) was iterated live with
Animesh in a Cowork session against `scratch/2026-08-13_eod_pt_summary.py` and confirmed
message-by-message, but that confirmation only exists as chat history + scratch code. There is
no durable spec a future session (or a different engineer) can read without replaying the whole
conversation.

**Root cause:** N/A — this is a documentation task, not a bug fix. The scratch script is correct
and already validated against the real DB; the gap is that its shape isn't written down anywhere
outside the code itself.

**Fix:** Write this task's confirmed spec below, sourced from the scratch script as of
2026-08-13 (delivered `file_uuid: 31ead4a7-8856-44f1-8910-96b3e6329fb4`).

Three independent Telegram messages, each sent separately (a failure sending one must not block
the others — see `_send_telegram_markdown()`, which is non-fatal per-call):

1. **`EOD PT Summary — <date>`** — open positions across every paper strategy (IC V1, IC V1
   Leaps, IC V2 monthly, CSP, Nifty Spot, Nifty Future, Nifty Proxy, CC, PP, Collar). Columns:
   Strategy, Instrument, Qty (signed), Avg, LTP, P&L, Chg. TOTAL row at the bottom of the P&L
   column. Flat single table (not sub-tabled per strategy — that was tried and explicitly
   reverted by Animesh: "the previous version was better").
2. **`Closed Today — <date>`** — same column shape, but rows are legs whose net_qty cycle fully
   closed (opened and closed) landing on the snapshot date, sourced via full trade-history replay
   (`store.get_trades()`), not `get_positions()` (closed legs don't appear in open-position
   queries). Omitted entirely if empty (no empty "Closed Today" message is sent).
3. **`Summary — Strategy P&L / Ann.% on Margin`** — one row per strategy with open and/or closed
   P&L this period: total P&L and annualized % return on margin, where
   `ann_pct = (pnl / final_margin) * (365 / days_held) * 100`. `days_held` from
   `entry_date` → snapshot date. Renders `N/A` when there's no `MarginSnapshot` for
   `(strategy_name, entry_date)` or `days_held <= 0` — margin-based Ann.% is currently only
   available for IC V1/V2 (the only strategies with `get_margin_snapshot()` data); CC/PP/Collar/
   CSP/3-Track rows show `N/A` in that column, not a fabricated number.

Instrument label format: `<strike> <CE/PE> <expiry "DD MON YY">` for options (CE/PE placed last,
a deliberate deviation from the repo-wide `format_leg_label` convention in
`src/instruments/lookup.py` — see prompt.md's flag on this), `NIFTY FUT <expiry>` for futures,
plain symbol for equity/proxy legs.

P&L formula (uniform across all row types, no `LOT_SIZE` multiplier — `net_qty` already carries
the raw unit count): short `(avg_cost - ltp) * abs(net_qty)`, long `(ltp - avg_cost) * net_qty`.
This fixed a real 65x P&L inflation bug found in the scratch script's first cut (see prompt.md
origin note) — any port to `src/` must carry the fix forward, not the buggy pattern from
`IronCondorV2._compute_combined_pnl`.

MarkdownV2 send: raw `aiohttp` POST (not `TelegramGateway.send_notification`, which is
HTML-only), title line escaped via `escape_markdown()`, body wrapped in a fenced code block
(entities inside a fence aren't parsed, so only the title needs escaping). This is the pattern
already used by `scratch/2026-08-08_eod_paper_summary_format.py`.

**Tests required:** None — PT-1 is documentation only, no code changes.

**Files touched:** `docs/plan/eod-pt-summary/stories.md` (this file). No `src/`/`scripts/`
changes.

---

## PT-2 — Promote to tested `src/` code + real cron

**Problem:** `scratch/2026-08-13_eod_pt_summary.py` is throwaway-convention code (per repo
CLAUDE.md, `scratch/` is explicitly not held to test/type-check standards) but is now Animesh's
daily-use report. It needs to become a maintained, tested module with a real cron entry, the same
way other scratch prototypes in this repo have graduated (e.g. `paper-ic-daily-snapshot/`'s
SNAP-4 → `scripts/reporting/paper_pnl_report.py`).

**Root cause:** N/A — this is a promotion task. The logic in the scratch script is already
correct and has been validated function-by-function against the real DB and real pasted
Telegram examples during the Cowork session (see prompt.md origin note); the task is packaging,
not re-deriving the logic.

**Before starting — resolve with Animesh:** This repo already has two adjacent reports:
`scripts/eod_summary.py` (production cron, `35 15 * * 1-5`, coarser NAV-snapshot-based summary
from `paper_nav_snapshots`, sent via `TelegramGateway.send_plain_message()`, already flagged as
in-scope for `telegram-markdown-migration/README.md`'s ROLL-6) and
`scripts/reporting/paper_pnl_report.py` (built under the archived `paper-ic-daily-snapshot/`
epic's SNAP-4). Ask Animesh explicitly: should the new PT report (a) replace
`scripts/eod_summary.py` outright, (b) run alongside it as a separate, more detailed cron, or
(c) absorb/replace `paper_pnl_report.py` specifically while leaving `eod_summary.py`'s coarser
NAV-snapshot digest as-is? Do not guess — the three reports read from different tables
(`paper_nav_snapshots` vs. live `PaperStore.get_positions()` + broker LTP vs. whatever
`paper_pnl_report.py` sources) and silently duplicating or dropping one of them is a support
regression, not a cleanup.

**Fix (once the coordination question is answered):**
- Move data-collection functions (`_collect_rows`, `_closed_legs_for_strategy`,
  `_collect_closed_rows`, `_entry_price`, `_pnl_rupees`, `_chg_pct`) into
  `src/reporting/eod_pt_summary.py` (new module) with the same signatures validated in scratch —
  do not redesign the function boundaries, only add types/docstrings/tests.
- Move rendering (`_render_table`, `_render_summary`, `_fmt_money`, `_fmt_pct`,
  `_fmt_expiry_label`, `_instrument_label`, `build_summary_parts`) into the same module or a
  sibling `src/reporting/eod_pt_summary_render.py` if the module gets large.
- Move `escape_markdown`/`_send_telegram_markdown` to wherever the `telegram-markdown-migration/
  backbone/` epic's shared helper lands, if that has shipped by the time this task starts;
  otherwise keep the scratch script's inlined copy and add a `# TODO(telegram-markdown-migration):
  replace with shared helper` marker, per that epic's stated plan.
- New cron script `scripts/eod_pt_summary.py` — thin wrapper: build `PaperStore`/`InstrumentLookup`
  /broker client, call `build_summary_parts()`, send each part via the promoted send helper,
  non-fatal per message (a failed send must not raise past the cron entrypoint — same contract as
  every other Telegram-sending script in this repo, see prompt.md).
- Preserve the `--send`/`--dry-run`/`--date`/`--db-path`/`--bod-path` CLI surface from the
  scratch script for manual reruns/backfills.

**Tests required:**
- `tests/unit/reporting/test_eod_pt_summary.py`: `_pnl_rupees` short/long cases (assert NO
  `LOT_SIZE` multiplication — regression test for the 65x bug); `_instrument_label` for CE/PE/FUT/
  EQ; `_fmt_expiry_label` ISO→"DD MON YY"; `_closed_legs_for_strategy` against a synthetic trade
  history replicating the pasted `IC closed — CLOSE_FULL` example (4-leg full close, assert it
  surfaces even though `get_positions()` wouldn't return it); `_render_summary` Ann.% formula and
  the `N/A` branch for strategies with no `MarginSnapshot`; `build_summary_parts` returns exactly
  2 or 3 parts depending on whether closed/summary sections are non-empty.
- Mock `BrokerClient.get_ltp` and the `aiohttp` POST — no network calls in tests, per prompt.md's
  test gate.
- Run `get_code_snippet('PaperPosition')`, `get_code_snippet('PaperTrade')`,
  `get_code_snippet('MarginSnapshot')` before writing any fixture that constructs these — do not
  guess field names from the scratch script's local tuples (prompt.md rule).

**Files touched:** `src/reporting/eod_pt_summary.py` (new), possibly
`src/reporting/eod_pt_summary_render.py` (new), `scripts/eod_pt_summary.py` (new),
`tests/unit/reporting/test_eod_pt_summary.py` (new). Do not modify `scripts/eod_summary.py` or
`scripts/reporting/paper_pnl_report.py` until Animesh's coordination answer is in — that answer
may itself require changes to one or both, tracked as a follow-up task once known.

---

## PT-3 — Docs close

**Problem:** Repo convention (per `docs/plan/README.md` "Conventions" and the project's own
CLAUDE.md) requires closing out an epic's docs (`CONTEXT.md`, `DECISIONS.md`, `TODOS.md`,
`docs/plan/README.md`'s index) once its tasks ship, so the next session/engineer doesn't have to
reconstruct status from git log.

**Root cause:** N/A — housekeeping task.

**Fix:**
- Add a one-line summary of PT-1/PT-2's outcome to `TODOS.md` and `DECISIONS.md` (if PT-2's
  coordination question produced a decision worth recording — it likely will, since it changes
  the shape of an existing production cron).
- Confirm/refresh the `eod-pt-summary/` row already added to `docs/plan/README.md`'s "Active
  Stories" table (added manually 2026-08-13 alongside this file) once PT-1/PT-2 are marked done.
- If `scripts/eod_summary.py` is retired or changed per PT-2's outcome, update
  `telegram-markdown-migration/README.md`'s ROLL-6 entry to reflect the new reality instead of
  leaving it pointing at a superseded script.

**Tests required:** None — docs only.

**Files touched:** `TODOS.md`, `DECISIONS.md`, `docs/plan/README.md`,
`docs/plan/telegram-markdown-migration/README.md` (conditionally).
