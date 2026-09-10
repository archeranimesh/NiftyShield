# Unified exit message — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: set `SHA:` on the task line + tick the box, flip this sub-story's row in the
> epic `README.md` **Stories** table, add one line to `TODOS.md` Session Log.

Sub-story 3 (last) of the `telegram-message-unification/` epic. Depends on `unified-entry-message/` +
`overlay-entry-message/` (both shipped — sub-stories are not individually archived) — this story
assumes `src/notifications/entry_message.py` and the sign-aware `_credit_line` already exist and
mirrors their structure. UXM-8 is the epic close: it archives the whole `telegram-message-unification/`
folder.

No DB schema change — no `schema.md`. Cycles are reconstructed from the `paper_trades`
ledger; exit reasons come from `paper_exit_events`, which already exists.

---

## UXM-1 — `cycle_stats` helper + gross-short-premium decay + shared leg-group resolver

**Files to change:**
- `src/paper/cycle_pnl.py` — add three `Cycle` fields (`short_credit_per_unit`,
  `short_buyback_per_unit`, `short_decay_pct`); add `CycleStats` frozen dataclass +
  `cycle_stats(trades)`; move `resolve_target` + `_Group` (and any private helper they need)
  in from `scripts/dev/cycle_pnl_report.py`.
- `scripts/dev/cycle_pnl_report.py` — replace the local `resolve_target` / `_Group` with an
  import from `src.paper.cycle_pnl`. **No change to the CLI output** — the report keeps
  rendering the existing net `decay_pct` column; the new short-basis field is additive.
- `tests/unit/paper/test_cycle_pnl.py` — extend.

**Before any code (graph queries):**
- `get_code_snippet("Cycle")` + `get_code_snippet("reconstruct_cycles")` +
  `get_code_snippet("_build_cycle")` + `get_code_snippet("_signed_premium_per_unit")` +
  `get_code_snippet("_entry_exit_legs")` — the current `Cycle` fields (`realized_pnl`,
  `entry_date`, `exit_date`, `days_in_trade`, `entry_credit_per_unit`, `exit_cost_per_unit`,
  `decay_pct`, `is_open`, `index`, `trades`) and exactly how `entry_credit_per_unit` /
  `exit_cost_per_unit` are computed, so the short-only variant mirrors that logic.
- `get_code_snippet("PaperTrade")` — the fields that identify a leg as a short (a
  SELL-to-open) vs a hedge/long leg, and the per-unit price.
- `get_code_snippet("resolve_target")` + `search_code("_Group")` in
  `scripts/dev/cycle_pnl_report.py` — the full definition + every reference, so the move is
  complete.
- `trace_path("resolve_target")` — confirm the CLI is the only caller today.

**What to implement:**

1. Move `resolve_target(target: str) -> list[_Group]` and the `_Group` dataclass verbatim to
   `src/paper/cycle_pnl.py` (rename `_Group` → `LegGroup`, public — `src/` and the CLI both
   import it). Keep the alias table (`ic-all`, `cc`, `pp`, `collar`, `overlay-all`, …) as-is.
2. Gross-short-premium decay — three new `Cycle` fields, set in `_build_cycle`, leaving the
   existing net `entry_credit_per_unit` / `exit_cost_per_unit` / `decay_pct` untouched:
   - `short_credit_per_unit: Decimal` — sum of the per-unit SELL-to-open prices of the
     cycle's **short** legs only (hedges / long legs excluded). `0` when the cycle has no
     short leg (a pure long PP).
   - `short_buyback_per_unit: Decimal | None` — sum of the per-unit BUY-to-close prices of
     those same short legs. `None` while the cycle is open.
   - `short_decay_pct: Decimal | None` —
     `100 * (short_credit_per_unit - short_buyback_per_unit) / short_credit_per_unit`.
     `None` when the cycle is open **or** `short_credit_per_unit <= 0` (no short leg). This
     is the basis every exit card and `cycle_stats` uses — stable across IC / CSP / CC /
     Collar (all have a short leg), correctly absent for PP.
3. `CycleStats` frozen dataclass:
   `closed_count: int`, `wins: int`, `losses: int`, `win_rate: float | None`
   (`None` when `closed_count == 0`), `avg_win: Decimal`, `avg_loss: Decimal`
   (signed, ≤ 0), `best: Decimal`, `worst: Decimal`, `avg_hold_days: float`,
   `avg_decay_pct: Decimal | None` (mean of `short_decay_pct` over the closed cycles that
   have one; `None` when none do).
4. `cycle_stats(trades: Sequence[PaperTrade]) -> CycleStats` — pure, over
   `[c for c in reconstruct_cycles(trades) if not c.is_open]`. A cycle is a win when
   `realized_pnl > 0`. `avg_decay_pct` skips cycles whose `short_decay_pct is None`.
   Empty closed list → all-zero / `None` stats, never raises.

**Tests (no network, no real DB — build `PaperTrade` lists via a fixture helper; run
`get_code_snippet("PaperTrade")` first, do not construct from memory):**
- `test_short_decay_pct_single_short` — CSP-shaped cycle sold @ 88, bought back @ 12 →
  `short_decay_pct == Decimal("86.36...")` (2-dp tolerance), net `decay_pct` still populated.
- `test_short_decay_pct_multi_short` — IC-shaped: short put 12 + short call 11 (credit 23),
  bought back 5 + 3 → `short_decay_pct` over the 23 base, hedges ignored.
- `test_short_decay_pct_none_for_pure_long` — PP-shaped (BUY-to-open only) →
  `short_credit_per_unit == 0`, `short_decay_pct is None`.
- `test_short_decay_pct_collar` — collar: short call basis only, long put excluded → a
  sensible 40–70% figure where the net `decay_pct` would have been `None`.
- `test_cycle_stats_happy` — 3 wins / 2 losses → `win_rate == 0.6`, `avg_win` / `avg_loss`
  / `best` / `worst` correct, `avg_decay_pct` = mean of the cycles' `short_decay_pct`.
- `test_cycle_stats_empty` — no closed cycles → `closed_count == 0`, `win_rate is None`,
  `avg_decay_pct is None`, no exception.
- `test_resolve_target_moved` — `resolve_target("cc")` from `src.paper.cycle_pnl` returns the
  same group(s) the CLI produced before the move.

**Commit:** `feat(paper): gross-short-premium decay + cycle_stats + shared LegGroup resolver`

---

## UXM-2 — The shared exit renderer

**Files to change / create:**
- `src/notifications/exit_message.py` — **new**. `ExitMessage`, `ExitKind`,
  `format_exit_message`.
- `src/notifications/formatting.py` — add `build_close_leg_table` (Act / Instrument / Entry /
  Exit / P&L). `build_leg_table` and `LegRow` are **not** touched.
- `tests/unit/notifications/test_exit_message.py` — **new**.

**Before any code (graph queries):**
- `get_code_snippet("build_leg_table")` + `get_code_snippet("LegRow")` — mirror the column /
  width / fence approach; the close table needs its own row type.
- `get_code_snippet("format_money")` + `get_code_snippet("format_expiry")` +
  `search_graph("format_greek")` — reused helpers (no delta column in the close table, so
  `format_greek` is not needed here).
- `get_code_snippet("CycleStats")` + `get_code_snippet("get_last_cycle_realized_pnl")` +
  `get_code_snippet("get_strategy_realized_pnl")` — the footer inputs.
- `get_code_snippet("_credit_line")` in `entry_message.py` — the sign-aware `Net credit` /
  `Net debit` pattern; the exit footer's P&L lines follow the same `+₹` / `-₹` convention
  (use `format_money(v, signed=True)` — `cycle_pnl_report.py` already does).

**What to implement:**

1. `ExitKind(str, Enum)` — `CLOSE` / `ROLL` / `CRASH_MONETIZE` / `WAITING`. Maps to the
   headline emoji: `✅` / `🔄` / `💰` / `⛔`. Caller passes it explicitly (derived from
   `action.action_type` at the call site, not string-sniffed in the renderer).
2. `CloseLegRow` frozen dataclass for `build_close_leg_table`:
   `role: str` (`[S]` when `startswith("Short")`, else `[B]` — same rule as `LegRow`),
   `instrument: str`, `entry: float`, `exit: float`, `pnl: Decimal`.
   `build_close_leg_table(rows: list[CloseLegRow]) -> str` — fenced-ready, right-aligned
   numerics, `pnl` via `format_money(signed=True)`. Raises on empty (mirror `build_leg_table`).
3. `ExitMessage` frozen dataclass:
   - `headline_label: str` (`"IC v1"` / `"CSP"` / `"CC"` / `"PP"` / `"Collar"`),
     `kind: ExitKind`, `signal: str` (free-text exit reason, escaped).
   - `dte: int`, `held_days: int` — required.
   - `legs: list[CloseLegRow]` — 1..N.
   - `this_exit_pnl: Decimal` — required. `per_lot: bool = False` — IC passes `True` to also
     show `(₹X/lot)`.
   - `cycle_pnl: Decimal | None`, `cycle_index: int | None`, `cycle_decay_pct: Decimal | None`,
     `cycle_short_credit: Decimal | None`, `cycle_short_buyback: Decimal | None`,
     `cycle_held_days: int | None` — read straight off the just-closed `Cycle`
     (`realized_pnl` / `index` / `short_decay_pct` / `short_credit_per_unit` /
     `short_buyback_per_unit` / `days_in_trade` — the **gross-short-premium** basis from
     UXM-1, not the net `decay_pct`). All `None` for a partial close where no cycle closed.
     `cycle_decay_pct` / the credit→buyback pair are additionally `None` for a pure-long
     cycle with no short leg (PP) — the cycle line then shows only P&L + held days.
   - `inception_pnl: Decimal` — required (`get_strategy_realized_pnl`).
   - `stats: CycleStats | None` — win-rate row rendered only when
     `stats is not None and stats.closed_count >= 5`.
   - `overlay_total_pnl: Decimal | None = None` — the `📊 Overlay P&L (total realized)` row,
     overlay strategies only.
   - `state_line: str | None = None` — the `→ *State:* …` line (PP crash-monetize keeps its
     `RE_ENTRY_PENDING` note).
4. `format_exit_message(msg) -> str` layout:
   ```
   {emoji} *{label} Closed* — {signal}          (ROLL → "Rolled", WAITING → "Closed — waiting")
   *Signal:* {signal}   *DTE:* {dte}   *Held:* {held}d
   <blank>
   ```{close leg table}```
   <blank>
   ━━━━━━━━━━━━━━━━━━━━━━━━
   💰 *This exit:* {+₹this}   [(₹x/lot) when per_lot]
   🔁 *Cycle #{i}:* {+₹cycle}  ·  ₹{short_credit} → ₹{short_buyback}  ·  {d}% decay  ·  {h}d
   📈 *Inception:* {+₹inception}
   🎯 *Win rate:* {r}%  ({W}W / {L}L)   {D}% avg decay   avg {+₹aw} / {-₹al}
   📊 *Overlay P&L (total realized):* {₹overlay}              [only when overlay_total_pnl set]
   → *State:* {state_line}                                    [only when state_line set]
   ```
   Cycle-line rules:
   - Omit the whole `🔁` line when `cycle_pnl is None` (partial close).
   - Drop the `₹{short_credit} → ₹{short_buyback}  ·  {d}% decay` middle segment when
     `cycle_decay_pct is None` (pure-long cycle, no short leg — PP) — the line becomes
     `🔁 *Cycle #{i}:* {+₹cycle}  ·  {h}d`. IC / CSP / CC / Collar all keep the segment
     (the gross-short-premium basis is defined for every cycle with a short leg).
   - Collapse `This exit` + `Cycle` into one when `cycle_pnl is not None and
     abs(this_exit_pnl - cycle_pnl) < Decimal("1")` — keep the `🔁` line, drop the `💰` one.
   Win-rate line:
   - Rendered only when `stats is not None and stats.closed_count >= 5`.
   - The `{D}% avg decay` segment is shown only when `stats.avg_decay_pct is not None`
     (at least one closed cycle had a short leg).
   Every interpolated value pre-escaped; the fenced table emitted literally.

**Tests (no network, no real DB):**
- `test_full_close_collapses_this_exit_and_cycle` — equal values → one combined row.
- `test_partial_close_omits_cycle_row` — `cycle_pnl=None` → no `🔁` line, `💰 This exit` shown.
- `test_cycle_line_shows_short_credit_cost_decay` — cycle with a short leg →
  `₹142.50 → ₹42.00  ·  70% decay` segment present on the `🔁` line.
- `test_cycle_line_drops_decay_segment_for_pure_long` — `cycle_decay_pct=None` (PP) → `🔁`
  line is just P&L + `{h}d`, no `→` / `decay`.
- `test_win_rate_hidden_below_five_cycles` — `stats.closed_count == 4` → no `🎯` line.
- `test_win_rate_shown_at_five` — `closed_count == 5` → `🎯 *Win rate:*` present, correct %.
- `test_win_rate_line_omits_avg_decay_when_none` — `stats.avg_decay_pct=None` → no
  `% avg decay` segment, win rate + avg win/loss still shown.
- `test_net_loss_renders_minus_sign` — negative `inception_pnl` → `-₹` not `₹-`.
- `test_overlay_total_line_only_when_set` — both branches.
- `test_close_leg_table_badges` — a `[S]` and a `[B]` row render correctly, P&L signed.
- `test_roll_kind_headline` — `ExitKind.ROLL` → `🔄 *CSP Rolled* — …`.

**Commit:** `feat(notifications): shared exit-confirmation renderer (ExitMessage)`

---

## UXM-3 — Migrate IC v1 + v2 close notifications

**Files to change:**
- `src/strategy/ic_nifty_v1.py` (~805–838) and `src/strategy/ic_nifty_v2.py` (~2205–2238) —
  replace the hand-rolled `text = (...)` with `format_exit_message(ExitMessage(...))`.
- `tests/unit/strategy/test_ic_nifty_v1.py`, `test_ic_nifty_v2.py`.

**Before any code (graph queries):**
- `get_code_snippet("ICNiftyV1._send_close_notification")` (and v2's equivalent) — the
  `closed_trades` shape, where `triggering_signal` / `action_type` come from, the existing
  `get_strategy_realized_pnl` call (reuse it for `inception_pnl`).
- `get_code_snippet("resolve_target")` / `get_code_snippet("cycle_stats")` — build the IC
  leg group (`resolve_target(self.strategy_name)` or the `ic-*` alias), then
  `reconstruct_cycles` + `cycle_stats` + `get_last_cycle_realized_pnl` off
  `self._store.get_trades(self.strategy_name)`.
- `get_code_snippet("ApprovedAction")` — the `action_type` values, to map `→ ExitKind`
  (`CLOSE_FULL` → `CLOSE`, `ROLL_*` → `ROLL`).

**What to implement:**

1. Build `legs: list[CloseLegRow]` from `closed_trades` — `entry` from the opening fill
   (`t.entry` / the position `avg_*`), `exit` from the close fill, `pnl` per-leg realized.
2. `this_exit_pnl` = sum of the per-leg P&L in this action; the `cycle_*` fields
   (`cycle_pnl` / `cycle_index` / `cycle_decay_pct` / `cycle_short_credit` / `cycle_short_buyback`
   / `cycle_held_days`) read straight off the just-closed `Cycle`; `inception_pnl` from the
   existing `get_strategy_realized_pnl`; `stats` from `cycle_stats`.
3. `headline_label="IC v1"` / `"IC v2"`, `per_lot=True`, `kind` from `action_type`.
4. Keep the non-fatal `try/except` + `ic_nifty_v*.send_notification*` log. Deferred import of
   `cycle_pnl` if a circular import appears (the module already does this for `tracker`).

**Tests:** happy close → body has `✅ *IC v1 Closed*`, the 4-leg table, `📈 *Inception:*`;
notify failure → non-fatal, close still completes.

**Commit:** `refactor(strategy): IC v1/v2 close message onto shared exit renderer`

---

## UXM-4 — Migrate CSP + the recorder `--close` path

**Files to change:**
- `src/strategy/csp_nifty_v1.py` (~635 `_reentry_notification`, ~460–475 `⛔ waiting`).
- `scripts/record/record_paper_trade.py` — the `--notify` flag (added in UEM-2) currently
  no-ops on `--close`; make it send an exit card on a successful close.
- `tests/unit/strategy/test_csp_nifty_v1.py`, `tests/unit/scripts/test_record_paper_trade.py`.

**Before any code (graph queries):**
- `get_code_snippet("CSPNiftyV1._reentry_notification")` + `search_code("CSP closed — waiting")`
  — both message sites, and what leg / price / signal data is in scope at each.
- `get_code_snippet("record_trade")` in `record_paper_trade.py` + the `--close` branch
  (~684–908) — where `net qty = 0` is confirmed; the close fill price; the resolved leg.
- `get_code_snippet("cycle_stats")` / `reconstruct_cycles` — same footer construction as UXM-3.

**What to implement:**

1. CSP `_reentry_notification`: `format_exit_message(ExitMessage(headline_label="CSP",
   kind=ExitKind.CLOSE, ...))` with the single short-put `CloseLegRow`, this-exit P&L, the
   cycle + inception + stats footer. Drop the `New position opened. Re-entry eligibility …`
   prose — the re-entry gets its own entry card (UEM-2). The `⛔ waiting` variant is
   `kind=ExitKind.WAITING` (headline `⛔ *CSP Closed — waiting*`), same footer.
2. `record_paper_trade.py`: at the confirmed `net qty = 0` close point, if `args.notify`,
   build an `ExitMessage` (one leg, `kind=CLOSE`, cycle + inception footer off
   `store.get_trades`) and send via `TelegramNotifier` in the existing non-fatal block.
   `--close` without `--notify` stays stdout-only.

**Tests:**
- `test_csp_close_sends_exit_card` — `✅ *CSP Closed*`, one `[S]` row, `📈 *Inception:*`.
- `test_csp_waiting_uses_waiting_kind` — `⛔ *CSP Closed — waiting*`.
- `test_record_close_notify_sends_exit_card` / `test_record_close_no_notify_silent`.

**Commit:** `feat(strategy): CSP close message + record_paper_trade --close exit card`

---

## UXM-5 — Migrate CC + PP + Collar strategy-class close notifications

**Files to change:**
- `src/strategy/cc_overlay_v1.py` (~333–390), `pp_overlay_v1.py` (~352–410),
  `collar_overlay_v1.py` (~641–735) — `_send_close_notification` bodies.
- `tests/unit/strategy/test_cc_overlay_v1.py`, `test_pp_overlay_v1.py`,
  `test_collar_overlay_v1.py`.

**Before any code (graph queries):**
- `get_code_snippet` on each `_send_close_notification` — the `pos` / `action.metadata`
  (`mark`, `delta`, `dte`) shape, the `format_leg_label` call, the dispatch chain.
- `get_code_snippet("resolve_target")` — the `cc` / `pp` / `collar` aliases give the leg
  group for `reconstruct_cycles` / `cycle_stats`.
- `search_graph("get_strategy_realized_pnl")` — `overlay_total_pnl` =
  `get_strategy_realized_pnl(store, STRATEGY_OVERLAY)` (what `auto_close.py` uses).

**What to implement:**

1. Each `_send_close_notification` builds an `ExitMessage`:
   - CC: one `CloseLegRow(role="Short Call", …)`, `headline_label="CC"`.
   - PP: one `CloseLegRow(role="Long Put", …)`, `headline_label="PP"`;
     `kind=ExitKind.CRASH_MONETIZE` + `state_line="RE_ENTRY_PENDING (monitoring IVR ≤ 0.60,
     DTE ≥ 14)"` when `action.action_type` is the crash path, else `ROLL` / `CLOSE`.
   - Collar: two rows (`"Short Call"` then `"Long Put"`), `headline_label="Collar"`.
   - `this_exit_pnl` from the closed leg(s); `overlay_total_pnl` set; cycle + inception +
     stats footer as UXM-3.
2. Keep every non-fatal `try/except` + `<class>.send_close_notification_failed` log and the
   `send_notification` → `send_plain_message` → `send` dispatch chain.

**Tests (per class):** close → `✅ *CC Closed*` / `💰 *PP Closed*` / `✅ *Collar Closed*`,
right leg count, `📊 *Overlay P&L (total realized):*` present, footer P&L lines; PP crash
path → `state_line` rendered; notify failure non-fatal.

**Commit:** `refactor(strategy): CC/PP/Collar close messages onto shared exit renderer`

---

## UXM-6 — Migrate the `auto_close.py` daemon paths

**Files to change:**
- `src/strategy/auto_close.py` (~270–360) — the Collar / CC / PP `msg = (...)` branches.
- `tests/unit/strategy/test_auto_close.py`.

**Before any code (graph queries):**
- `get_code_snippet` on the `_notify` / message-building function (~240–365) — the
  `legs` dict shape (`key`, `entry`, `exit`, `pnl`, `role`, `delta`), `net_pnl`,
  `realized_pnl` (already `get_strategy_realized_pnl`), `exit_signal`, `_label`, `_fmt_pnl`.
- Confirm the `overlay_pp` `CRASH_MONETIZE` branch's `→ RE_ENTRY_PENDING` state text — carry
  it into `state_line` verbatim.

**What to implement:**

1. Replace the three hand-rolled `msg` branches with one `format_exit_message` call —
   `legs` → `CloseLegRow` list, `this_exit_pnl = net_pnl`, `overlay_total_pnl = realized_pnl`,
   `headline_label` / leg roles from the `legs` dict, `kind` + `state_line` from
   `exit_signal`. Cycle + `cycle_stats` footer off `store.get_trades(strategy_name)` filtered
   by the overlay leg group (`resolve_target`).
2. `await notifier.send(msg)` in the existing non-fatal `try/except` — unchanged.

**Tests:** each overlay type → the shared card; `CRASH_MONETIZE` → `state_line`; the
`Overlay P&L (total realized)` figure matches `get_strategy_realized_pnl(store,
STRATEGY_OVERLAY)`.

**Commit:** `refactor(strategy): auto_close daemon messages onto shared exit renderer`

---

## UXM-7 — Pre-market brief redesign

The daily `scripts/pre_market_brief.py` message is the last unmigrated Telegram surface: it
emits literal `<b>…</b>` HTML tags run through `escape_markdown()` then sent as MarkdownV2
(so the tags render as literal `\<b\>` text), raw `paper_*` strategy ids, an inconsistent
`₹+110.50` / `₹-888.88` sign convention, and no portfolio total. This task brings it to the
fenced-table house style and breaks the `paper_nifty_overlay` umbrella into its CC / Collar /
PP components. Depends on UXM-1's `resolve_target` / `LegGroup` in `src/paper/cycle_pnl.py`.

**Files to change:**
- `scripts/pre_market_brief.py` — the message builder (~140–195).
- `src/notifications/formatting.py` — add any `paper_*` id the brief lists that is missing
  from `STRATEGY_LABELS` (`strategy_label()` raises on an unmapped id). Likely
  `paper_nifty_futures` / `paper_nifty_proxy` / `paper_nifty_spot` — confirm first.
- `tests/unit/scripts/test_pre_market_brief.py` — new or extended.

**Before any code (graph queries):**
- Read the whole message-building block via `get_code_snippet` — the `<b>` wrapping, the
  `escape_markdown` calls, the `float(unrealized):+,.2f` formatting, `send_plain_message`.
- `get_code_snippet("strategy_label")` + `search_graph("STRATEGY_LABELS")` — the mapped ids,
  and that it raises (not falls back) on an unmapped one.
- `get_code_snippet("resolve_target")` (post-UXM-1, in `src.paper.cycle_pnl`) +
  `search_code("_OVERLAY_GROUPS")` — the `cc` / `collar` / `pp` leg-role filters.
- `search_code("build_leg_table")` / `search_graph("build_strategy_table")` — reuse an
  existing fenced-table builder if one fits; only add a new one if none does.
- `get_code_snippet("format_money")` — `signed=True` gives `+1,234.50` / `-1,234.50`,
  Indian grouping, no `₹` glyph inside a column.

**What to implement:**

1. Drop all `<b>` HTML. Header:
   `☀️ *NiftyShield Pre-Market Brief*` /
   `*Date:* {format_expiry(date.today())}   *India VIX IVR:* {ivr}%` — both lines' dynamic
   values pre-escaped, the fenced table emitted literally.
2. One fenced table: `Strategy | Legs | Unrealized P&L`, one row per strategy via
   `strategy_label(name)`, P&L via `format_money(v, signed=True)`.
3. `paper_nifty_overlay` renders as a parent row (its aggregate) followed by indented
   `├ CC` / `├ Collar` / `└ PP` sub-rows, each filtered by the `resolve_target` leg-role
   group. A sub-group with zero open legs shows `—` for both Legs and P&L.
4. A trailing `Total` row: portfolio-wide open-leg count + summed unrealized P&L
   (the overlay counted once, via its parent aggregate — not double-counted with the
   sub-rows).
5. Keep the existing "no open positions" early-return path; just fix its `<b>` / parse mode
   the same way. Keep `gateway.send_plain_message` and the non-fatal send handling.

**Tests (no network, no real DB):**
- `test_brief_is_markdownv2_no_html` — rendered body contains no `<b>` / `</b>`.
- `test_overlay_breaks_into_cc_collar_pp` — a store with overlay legs across two of the three
  → parent row + three sub-rows, the empty one showing `—`.
- `test_total_row_sums_without_double_counting_overlay` — total P&L == sum of the
  per-strategy aggregates (overlay parent once).
- `test_unmapped_strategy_id` — decide + assert the behaviour (add the id to `STRATEGY_LABELS`
  so this can't happen, and assert `strategy_label` covers every id `get_strategy_names`
  can return).
- `test_no_open_positions_path` — early return renders clean MarkdownV2, no `<b>`.

**Commit:** `refactor(scripts): pre-market brief to fenced house style + overlay breakout`

---

## UXM-8 — Docs close

**Files to change:** `CONTEXT.md`, `src/notifications/CLAUDE.md`, `DECISIONS.md`,
`docs/plan/telegram-message-unification/README.md`, `docs/plan/README.md`, `TODOS.md`,
`docs/archive/TODOS_ARCHIVE.md`, plus the epic-folder `git mv`. Targeted `Edit` only, never `Write`.

1. `CONTEXT.md` "What Exists" `src/notifications/` bullet — add
   `exit_message.py (shared close-confirmation renderer — IC/CSP/CC/PP/Collar + this-exit /
   cycle / inception P&L + win-rate, UXM-1..7)`; note `cycle_pnl.py` gained `short_decay_pct`
   on `Cycle`, `cycle_stats`, and `LegGroup` / `resolve_target`; note `pre_market_brief.py`
   is now MarkdownV2 + overlay breakout.
2. `src/notifications/CLAUDE.md` — the close card is `format_exit_message`; the footer's
   inception number is `get_strategy_realized_pnl` (authoritative), cycle stats are the
   approximation; win rate gated at `closed_count >= 5`.
3. `DECISIONS.md` §P&L & Reporting — one dated line: unified exit renderer; three P&L levels
   (this-exit / cycle / inception) with inception from the store not the cycle sum; win-rate
   + avg-decay stats from `cycle_stats`; decay on the **gross-short-premium** basis
   (`short_decay_pct`, `None` for pure-long PP) not the net `decay_pct`; `auto_close.py` +
   strategy-class + recorder all on one renderer; `pre_market_brief.py` migrated off HTML
   with the overlay broken into CC / Collar / PP.
4. Epic close (UXM-8 is the last sub-story — archive the **whole epic**, per `docs/plan/README.md`
   §Conventions *Completion → archive*):
   - `docs/plan/telegram-message-unification/README.md` — flip the `unified-exit-message/` Stories row
     to ✅ and set the **Epic done when** block satisfied.
   - `git mv docs/plan/telegram-message-unification docs/archive/plan/telegram-message-unification`.
   - `docs/plan/README.md` — collapse the `telegram-message-unification/` epic entry under
     `## Active Epics` to a one-line `✅ Archived → docs/archive/plan/telegram-message-unification/`.
   - `TODOS.md` — delete the Feature Backlog epic line, append it to `docs/archive/TODOS_ARCHIVE.md`
     under a dated heading; add a Session Log line.
   One commit.

**Commit:** `docs: close telegram-message-unification epic (UEM/OEM/UXM)`
