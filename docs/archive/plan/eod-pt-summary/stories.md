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

**Fix:** The confirmed spec below is sourced field-by-field from the scratch script as of
2026-08-13 (delivered `file_uuid: 31ead4a7-8856-44f1-8910-96b3e6329fb4`). It is the reference
PT-2 promotes — where this text and the scratch script disagree, the scratch script wins and
this text is the bug.

### Message split

`build_summary_parts(store, broker, lookup, snap_date) -> list[str]` returns **1, 2, or 3**
strings, one per Telegram message, each sent as its own `_send_telegram_markdown()` call so a
failure on one (rate-limit, etc.) never blocks the others:

1. **`EOD PT Summary — <ISO date>`** — always present (renders an "no open positions across any
   paper strategy." line when empty, still its own message).
2. **`Closed Today — <ISO date>`** — present only when at least one leg fully closed on
   `snap_date`; omitted entirely otherwise (never an empty "nothing closed" message).
3. **`Summary — Strategy P&L / Ann.% on Margin`** — present only when `strategy_meta` is
   non-empty, i.e. there was at least one open leg. Built from **open positions only** — today's
   realized closes are deliberately NOT folded in, to avoid conflating mark-to-market with
   realized round-trip P&L under one number (`_render_summary` docstring).

The open table was tried sub-tabled per strategy and explicitly reverted by Animesh ("the
previous version was better") — it is one flat table with a Strategy column; the per-strategy
breakdown he wanted is message 3, not a restructure of message 1.

### Messages 1 & 2 — table shape (`_render_table`, shared)

Seven columns: **Strategy · Instrument · Qty · Avg · `<value>` · P&L · Chg**, where `<value>` is
`LTP` for message 1 (live mark) and `Exit` for message 2 (realized exit price). Strategy and
Instrument are left-justified; Qty/Avg/`<value>`/P&L/Chg are right-justified. A `TOTAL` row
closes the table with the summed P&L in the P&L column only (every other cell blank) so it lands
directly under the per-leg P&L figures. Message 1 appends a `(partial — some legs missing LTP)`
line when any leg's LTP fetch returned nothing; message 2 is always exact (both prices realized).

Per-cell derivation from `PaperPosition` / the closed-leg tuple:

- **Strategy** — friendly label from `_STRATEGY_LABELS` keyed by `strategy_name`, plus two traps
  that PT-2 must carry forward (both confirmed against the live DB 2026-08-13, not the stale
  class-level defaults):
  - **3-Track:** base legs persist under `paper_nifty_spot` / `paper_nifty_futures` /
    `paper_nifty_proxy` (→ "Nifty Spot" / "Nifty Future" / "Nifty Proxy"), **not**
    `NiftyTrackComparisonV1.strategy_name` (that is only the signal-registration umbrella).
  - **Overlays:** CC / PP / Collar are **not** separate `strategy_name`s — all three share
    `STRATEGY_OVERLAY` (`"paper_nifty_overlay"`) and are split by `leg_role` prefix
    (`overlay_cc` → "CC", `overlay_pp` → "PP", `overlay_collar` → "Collar"); an unrecognized
    prefix logs a warning and renders "Overlay (?)". The standalone `STRATEGY_CC_OVERLAY` /
    `STRATEGY_PP_OVERLAY` / `STRATEGY_COLLAR_OVERLAY` constants are stale for the live DB.
- **Instrument** (`_instrument_label`) — options: `<underlying> <strike> <expiry "DD MON YY"> <CE/PE>`,
  CE/PE **last**. This is a deliberate one-off deviation from the repo-wide
  `format_leg_label()` / `format_option_label()` standard (`<underlying> <strike> <CE/PE> <expiry>`,
  telegram-leg-labels epic, used by every other Telegram message); built locally because the
  canonical helper has no field-order option. Strike renders as int when integral, else the
  plain `Decimal`. A missing strike logs a warning and degrades to the raw `instrument_key`
  (same fallback contract as `format_leg_label`). Futures: `<underlying> FUT <expiry>`. Equity
  (3-Track proxy/spot): the trading symbol as-is. Expiry formatting (`_fmt_expiry_label`):
  ISO `YYYY-MM-DD` → `DD MON YY` upper-cased; a non-ISO value passes through unchanged.
- **Qty** (`_fmt_qty`) — `PaperPosition.net_qty`, signed (negative = net short), with comma
  thousands separators to match the other numeric columns (`f"{qty:,}"`). `net_qty` is the raw
  traded unit count off `paper_trades.quantity` (a 1-lot leg is stored as `65`), **not** a lot
  count.
- **Avg** (`_entry_price`) — `avg_sell_price` when `net_qty < 0` (short), `avg_cost` when
  `net_qty > 0` (long).
- **LTP / Exit** — message 1: one batched `broker.get_ltp(all_open_keys)` call (uniform across
  options/futures/equity); a fetch exception logs `eod_pt_summary.ltp_fetch_failed` and leaves
  every LTP `None` (rows degrade to `N/A`, non-fatal). Message 2: the realized exit price from
  trade-history replay.
- **P&L** (`_pnl_rupees`) — signed rupees, **no `LOT_SIZE` multiplier for any instrument type**:
  short `(entry - ltp) * abs(net_qty)`, long `(ltp - entry) * net_qty`. An earlier scratch cut
  multiplied by `LOT_SIZE` on top of `net_qty` and inflated P&L 65x across every non-equity row;
  `IronCondorV2._compute_combined_pnl`'s own `* LOT_SIZE` is a different computation (per-unit
  prices summed across legs, one lot assumed) and does not generalize here. `None` when LTP is
  missing (excluded from the TOTAL, flagged by the partial line).
- **Chg** (`_chg_pct`) — `(ltp - entry) / entry * 100`, i.e. pure price move vs entry, **not**
  P&L% and independent of qty sign; `N/A` when LTP missing or `entry == 0`. Rendered `+.2f%`.

Money cells (`_fmt_money`): `f"{val:,.2f}"` or `N/A`.

### Message 2 — "closed today" detection (`_closed_legs_for_strategy`)

`get_positions()` / `get_trades()` only surface currently-**open** net positions, so a leg that
closed today is otherwise invisible. This replays the full `store.get_trades(strategy_name)`
history grouped by `(leg_role, instrument_key)`, runs the same net_qty-cycle accounting
`get_positions()` does internally (cycle resets when `net_qty` hits 0), and emits a row for any
cycle whose closing trade landed on `snap_date` and returned `net_qty` to exactly 0. **Partial
closes are not reported here** — a reduced-but-nonzero `net_qty` is still an open position
(visible in message 1 with a smaller Qty); only a full round-trip counts. Entry/exit prices are
the volume-weighted averages of the opening and closing trade runs; `qty_signed` carries the
held direction (negative = was short) so the same P&L-sign formula applies. Closed-row P&L is
computed inline with the identical short/long formula (no `LOT_SIZE`).

### Message 3 — strategy P&L / Ann.% (`_render_summary`)

Four columns: **Strategy · P&L · Margin · Ann.%**, Strategy left-justified, rest right. One row
per friendly strategy label seen in the open book (P&L accumulated per label in
`_collect_rows`), then a `TOTAL` row carrying the overall open P&L.

`ann_pct = (pnl / final_margin) * (365 / days_held) * 100` — simple annualization, not
compounded; `days_held = (snap_date - entry_date).days`, `entry_date` taken from the first leg
of the group (all legs of one entry cycle share it, PG-1). Margin comes from
`store.get_margin_snapshot(strategy_name, entry_date)` keyed on the **real** `strategy_name`
(so CC/PP/Collar all key off `STRATEGY_OVERLAY`, not their friendly labels). `paper_margin_snapshots`
is populated for IC V1/V2 only today — CSP, the overlays, and 3-Track have no margin-calculator
wired up, so their Margin and Ann.% render `N/A` (never a substituted `required_margin` or
hardcoded estimate). `Ann.%` is also `N/A` when `final_margin <= 0` or `days_held <= 0`
(same-day entry / clock skew — avoids a meaningless four-digit number). A lookup exception logs
`eod_pt_summary.margin_lookup_failed` and treats it as no snapshot (non-fatal). A strategy whose
P&L sum dropped a leg to a missing LTP gets a trailing `*` on its P&L cell and the table appends
`(* — partial: one or more legs missing LTP, P&L understated)`.

### MarkdownV2 send (`_send_telegram_markdown`, `escape_markdown`, `_PART_EMOJI`)

Raw `aiohttp` POST to `api.telegram.org/bot<token>/sendMessage` with
`parse_mode="MarkdownV2"`, 10s total timeout — **not** `TelegramGateway.send_notification()`
(HTML-only, wrong fence semantics for a table). The message is
`f"{escaped_header}\n\`\`\`{body}\n\`\`\`"`: the first line of the part is split off as the title,
prefixed with its emoji, and `escape_markdown()`-ed (backslash-escaping the
`_*[]()~\`>#+-=|{}.!` reserved set); everything after the title goes inside a fenced code block
where MarkdownV2 does not parse entities, so only the header is escaped. A non-200 response
prints and logs Telegram's actual `description` field (a bare `raise_for_status()` swallows it)
and returns `False`; any exception logs `eod_pt_summary.telegram_failed` and returns `False`.
**Never raises past the caller** — this is the repo-wide non-fatal Telegram contract and PT-2
must preserve it.

Per-message emoji (`_part_emoji`, title-prefix match, cosmetic): `EOD PT Summary` → 📝,
`Closed Today` → ✅, `Summary —` → 📊, fallback → 📋.

### CLI surface (preserve in PT-2's `scripts/eod_pt_summary.py`)

`--date YYYY-MM-DD` (default today) · `--dry-run/--no-dry-run` (default on; falls back to a
zero-LTP mock broker if live client init fails) · `--send` (default off — print only, never
sends) · `--db-path` (default `DEFAULT_DB_PATH`) · `--bod-path` (default `DEFAULT_BOD_PATH`).
Without `--send` it prints every part and a "`N message(s) would be sent`" line. With `--send`
but no `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` it prints a warning, logs
`eod_pt_summary.telegram_not_configured`, and returns.

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
