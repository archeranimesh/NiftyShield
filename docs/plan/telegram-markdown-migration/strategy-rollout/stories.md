# Telegram Markdown Migration — Strategy Rollout — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.

**Sequencing rationale (why this order, not alphabetical or file-count order):** IC EOD audit
is informational-only — a wrong-looking message costs nothing beyond a re-read. The comparison
report is also informational but touches a known existing bug (hand-counted widths), so it's
worth fixing early while the pattern is fresh. Close/roll notifications fire on real position
events — worth getting right, but a formatting glitch there is still just a notification, not
a trade action. Approval requests are the only message type in this list that gates an actual
trade action via an interactive keyboard callback — highest consequence of a formatting
regression (a broken button or unreadable approval text could block or confuse a real trade
decision), so it goes last and gets the coordination check.

---

## ROLL-0 — Capture Long-Leg Delta + Theta in IC EOD Audit (data-only, no Markdown dependency)

**Confirmed 2026-08-07 (message-format-workshop session):** this is a small, self-contained
data-capture fix, not a new epic/story, and it does **not** depend on `backbone/` or
`formatting-rules/` shipping — it changes what `process_variant` extracts from the live chain it
already fetches, independent of parse_mode. Sequenced before `ROLL-1` here because `ROLL-1`'s
Markdown port should consume this data once it exists, not re-derive it — but `ROLL-0` can land
and ship value (a corrected plain-text report line) on its own, any time.

**The gap, confirmed by reading the real code (not assumed):** `process_variant()`
(`scripts/strategies/ic/paper_ic_snapshot.py`, lines 143-402, shared by both `IronCondorV1` and
`IronCondorV2` via the `strategy_cls` param — this function is NOT duplicated per version) already
fetches the live option chain once per variant and already resolves every leg's `OptionLeg` via
`ic._find_leg(chain, pos.instrument_key)` inside its `role_order` loop — for all four roles,
including the two long legs (`long_put_hedge`, `long_call_hedge`). `OptionLeg` already carries
`.delta`, `.theta`, `.gamma`, `.vega` (same fields `_extract_greeks_from_chain` in
`src/portfolio/tracker.py` reads off the identical chain-parsing output — confirmed, not assumed).
The gap is purely in what the loop body *does* with the already-resolved `opt_leg`:

```python
if role in ["short_put", "short_call"]:
    delta_val = (
        opt_leg.delta
        if (opt_leg is not None and opt_leg.delta is not None)
        else 0.0
    )
    ...
else:  # long_put_hedge, long_call_hedge
    label = role_labels[role]
    pos_lines.append(f"  {label} {strike_suffix}  {ltp_str}")
```

Two problems in this block, both in scope for this task:
1. The `else` branch (long legs) never reads `opt_leg.delta`/`opt_leg.theta` at all, despite
   `opt_leg` already being resolved and in scope — delta/theta for long legs is discarded, not
   unavailable.
2. The short-leg branch's `else 0.0` fallback conflates "delta is genuinely zero" with "delta
   could not be resolved" — a chain-lookup miss silently prints `δ=0.00`, which reads as a real
   flat-delta leg rather than missing data. Fix to `None` (rendered as `-`, matching FMT-1's
   existing None-handling convention for Greeks) while touching this code, since the distinction
   matters for exactly the Net Δ computation this task adds.

**`_find_leg` confirmed identical between V1 and V2** (2026-08-07, read both in full) — same
regex-first/BOD-fallback logic, same `OptionLeg | None` return type, only the log event name
differs (`ic_nifty_v1.strike_decimal_failed` vs `ic_nifty_v2.strike_parse_failed`). Leg-role
strings are also identical across both (`short_put`/`short_call`/`long_put_hedge`/
`long_call_hedge` — confirmed via grep against `ic_nifty_v2.py`). So this task requires no
per-version branching in `process_variant` — one code path already serves both.

**Applies to every active IC variant automatically — confirmed via `_run()`, not assumed.**
`_run()` calls `process_variant()` once per entry in two loops: `for expiry_type, config in
CONFIGS.items()` (V1 — all four of `weekly`/`monthly`/`leaps`/`yearly`, real strategy_names
`paper_ic_nifty_v1_{weekly,monthly,leaps,yearly}` per `src/paper/constants.py`'s
`STRATEGY_IC_WEEKLY/MONTHLY/LEAPS/YEARLY`) and `for expiry_type, config in CONFIGS_V2.items()`
(V2 — currently `monthly` only; `CONFIGS_V2` is Phase 1-scoped per `src/strategy/
ic_expiry_config_v2.py`, `paper_ic_nifty_v2_weekly`/`_leaps`/`_yearly` do not exist as runnable
strategies yet — do not add them to any test fixture as if they're live). Since this task edits
`process_variant()` itself, not a per-variant call site, every variant in both loops gets the
long-leg Greeks capture and the Net Δ/θ line with zero additional code — no per-variant task
needed here or in `ROLL-1`. `scratch/2026-08-07_ic_eod_audit_v2_telegram_format.py` gained a
`VARIANTS` dict + `--variant` CLI flag (5 entries: the four V1 expiries plus V2 monthly) purely
to demonstrate `build_message()` is already variant-agnostic — not because the real
implementation needs a variants list of its own.

**Files to change:**
- `scripts/strategies/ic/paper_ic_snapshot.py` — `process_variant()`'s role-loop body
- Matching test file: `tests/unit/strategies/ic/test_paper_ic_snapshot.py`

**What to change:**
1. For all four roles (not just the two shorts), capture `opt_leg.delta` and `opt_leg.theta`
   into per-leg variables, `None` on any resolution miss (chain lookup fails, `opt_leg is None`,
   or the field itself is `None`) — do not default to `0.0` for any role.
2. Compute `net_delta`/`net_theta` across all four legs using the same never-silently-partial
   rule already proven in `scratch/2026-08-07_ic_eod_audit_v2_telegram_format.py`'s
   `compute_net_greek()`: if ANY leg's value is `None`, the net is `None` ("incomplete"), never a
   partial sum that looks complete. Port that helper's logic (or the function itself) rather than
   reimplementing the None-handling ad hoc.
3. Add a `Net Δ: ... | Net θ: ...` line to the existing plain-text `report` string (between the
   `DTE/Nifty/IVR` line and the `Position:` block) — this lands in the *current* pre-Markdown
   report format, independent of `ROLL-1`. When incomplete, print `Net Δ: incomplete` /
   `Net θ: incomplete` (or `N/A` — pick one, match this file's existing `N/A` convention for
   missing combined-mark/margin-snapshot data rather than inventing a new missing-data string).
4. `ROLL-1`'s later Markdown port consumes these same per-leg delta/theta values and the
   computed net — it should not need to re-derive them from `opt_leg` a second time. If `ROLL-1`
   is implemented before `ROLL-0` for any reason, it must still not skip this fix; sequence exists
   only as a suggestion, not a hard gate, since neither depends on the other's *code*, only on
   not duplicating the extraction logic.

**Tests:**
- Happy path: all four legs resolve real delta/theta from a mocked chain → `Net Δ`/`Net θ` print
  correct sums (add a fixture chain with non-zero long-leg deltas/thetas, not all-zero, so the
  test would actually fail if the long-leg extraction were silently dropped again)
- Edge case: one leg's chain lookup misses (mirrors `test_chain_fetch_fails_for_one_variant`'s
  existing pattern for the variant-level miss, but scoped to a single leg within an otherwise
  successful chain fetch) → `Net Δ`/`Net θ` both print the incomplete/`N/A` state, not a partial
  sum
- Regression: a short leg's `opt_leg.delta is None` (real chain-lookup miss, not a genuine 0.0
  delta) → per-leg display shows the None-placeholder, not `0.00` — proves the `else 0.0` bug is
  actually fixed, not just papered over by the new Net Δ line

**Commit:** `feat(ic): capture long-leg delta/theta and net position Greeks in EOD audit`

---

## ROLL-1 — IC EOD Audit

**Reference implementation superseded 2026-08-07.** The original prototype
(`scratch/2026-08-07_ic_eod_audit_telegram_format.py`, `strategy_id=paper_ic_nifty_v1_monthly`,
legacy `parse_mode=Markdown`) is now historical only — it proved the bold+fenced-table concept
but predates both the MarkdownV2 revision (see epic `README.md`) and the confirmed layout below.
**The live reference is `scratch/2026-08-07_ic_eod_audit_v2_telegram_format.py`**
(`strategy_id=paper_ic_nifty_v2_monthly`, real V2 IC position data, `parse_mode=MarkdownV2`) —
produced via `message-format-workshop.md`, confirmed on-device 2026-08-07. Port from this file,
not the v1 one.

**Confirmed message structure (updated 2026-08-07 — now includes Expiry, Net Δ/Net θ, AND the
FMT-1c color-coded header/hashtag; hashtag auto-detection confirmed working live on-device):**

```
🔵 📅 *IC EOD Audit — Monthly (V2)* | #IC_Monthly_V2
`paper_ic_nifty_v2_monthly`
*Expiry:* 25 Aug 26 | *DTE:* 18 | *Nifty:* 24,571
*IVR:* 0.16 | *Net Δ:* incomplete | *Net θ:* incomplete
```
Act Strike Type     Δ   LTP Entry
---------------------------------
[S] 24200  PE   -0.23  89.0  97.8
[B] 23500  PE       -  18.0     -
[S] 25100  CE   +0.23  74.2  81.1
[B] 25500  CE       -  19.8     -
```
💰 *Credit:* ₹128.92 ➡️ *Mark:* ₹125.40
✅ *Captured:* ₹3.52 (2.7%) | *ROI:* 0.2% (₹229)
🏦 *Margin:* ₹97,243
🟢 *Alert:* None
⚙️ *Actions:* None
```

(Backslash escaping of literal `.`/`(`/`)`/`|`/`#`/`_` omitted above for readability — see the
scratch script for the actual MarkdownV2 source with `escape_markdown()` applied throughout.)

**Expiry row — confirmed 2026-08-07, `format_expiry()`: `"25 Aug 26"` (day, short month, 2-digit
year, no leading zero on the day — `strftime("%d %b %y").lstrip("0")`, portable across platforms
unlike `%-d`). Not yet in FMT-1's spec table; add it there when this ships.** Zero new data
fetch — `process_variant()` already resolves the real `expiry` date object (via the BOD
instrument lookup) purely to compute `dte`, then discards it; DTE is derived FROM expiry, not the
other way round, so the real implementation must print that already-resolved value directly and
must NOT reconstruct an expiry date from DTE the way the scratch script's data fixture does
(that script has no live lookup to call, so it fakes the date as `snap_date + dte` purely for
demo purposes — this shortcut is invalid in the real implementation, which already has the true
value in scope). Nifty moved to the end of the Expiry/DTE line (was previously first); IVR moved
onto the Net Δ/θ line rather than dropped, since the requested 3-field row had no room for it.

**Header design fully specified in `formatting-rules/stories.md` FMT-1c — read that before
implementing, do not re-derive the color/emoji mapping from scratch.** Summary: color+emoji encode
timeframe only (🟡⚡ weekly, 🔵📅 monthly, 🟢🔭 leaps, 🟠🌌 yearly) — never version, so the scheme
doesn't need new colors if V2 ever gains more than its current single (monthly) expiry bucket.
Version is a separate `\(V2\)`-style text badge in the title (V1 stays unbadged). The hashtag
(`#IC_{Timeframe}_{Version}`) sits on the title line, unwrapped by any code span — wrapping it in
backticks (as an earlier external draft of this scheme did) silently kills Telegram's hashtag
auto-detection, since Telegram doesn't parse entities inside code spans. The existing
`` `{strategy_id}` `` code-span line is kept as its own separate line below the title for
exact-string copy/audit — it and the hashtag serve different jobs, don't merge them.

**"Net Δ: incomplete" is the honest current state, not a placeholder to fix in this task.** It
prints `incomplete` because the real position's long-leg deltas and all four legs' thetas aren't
captured yet — that data-availability gap is `ROLL-0` (above), a separate task this one depends
on for the *data*, not the formatting. `ROLL-1` renders whatever `net_delta`/`net_theta` it's
given (a number, or the `None`-triggered incomplete state) — it must NOT itself attempt to
compute or backfill the net Greeks; that's ROLL-0's job. If `ROLL-0` has landed by the time this
task starts, the confirmed layout above should show real numbers instead of `incomplete` — update
this block's example to match live data at that point rather than leaving it stale. Alert and
Actions are two separate lines (⚠️/🟢 and ⚙️ respectively), not one combined `Alert | Actions`
line — corrected from an earlier draft of this spec.

**Files to change:**
- `scripts/strategies/ic/paper_ic_snapshot.py` — the message-building function (find via
  `search_graph`, not assumed — TL-3 in `telegram-leg-labels` already touched entry-preview
  text in a related script; confirm this one's current function name/location fresh)
- Matching test file in `tests/unit/`

**Before any code:**
```
get_code_snippet(<message-building function in paper_ic_snapshot.py>)   # find via search_graph first
```
Port `scratch/2026-08-07_ic_eod_audit_v2_telegram_format.py`'s `build_message()` structure: bold
header + `mdcode()`-wrapped strategy_id, bold Nifty/DTE/IVR line, fenced leg table, bold
Credit/Mark line, bold Captured/ROI line (with `pnl_emoji()` — see below), bold Margin line, bold
Alert/Actions line (with `alert_emoji()`) — using `formatting-rules/`'s `build_leg_table` /
`format_money` / `format_greek` / `format_strike` / `format_pct`, and `backbone/`'s `mdcode()` /
`escape_markdown()` for every dynamic value AND every literal reserved character in the static
template text (parentheses, pipes, decimal points — MarkdownV2's reserved set is wider than
legacy Markdown's, see `backbone/stories.md`). Do not hand-roll formatting logic that FMT-2/FMT-3
already built. This message does **not** use a side-by-side kv table (`build_side_by_side_kv_table`)
— the confirmed layout is a single linear stack of bold summary lines plus the one fenced leg
table, not two Snapshot/P&L tables side by side as an earlier draft of this task assumed. Update
this task's `get_code_snippet` step accordingly if the target function still expects that shape.

**New: dynamic status emojis (FMT-1b, `formatting-rules/stories.md`).** `✅`/`🔻`/`➖` on
`pnl_emoji(captured_credit)` (sign of credit-minus-mark, not a hardcoded `✅`) and `🟢`/`⚠️` on
`alert_emoji(signals)` (presence-based, not a substring match on the signal code — see FMT-1b for
the rejected substring-matching design and why). Both must land in `formatting-rules/` (FMT-2 or
a new FMT-2b) before this task can import them; if `formatting-rules/` ships without them, add
them there first rather than defining them locally in this script.

**Also confirmed 2026-08-07 — negative-money sign fix (see FMT-1's updated table):**
`format_money` must put the sign before the `₹`, not after (`-₹11.08`, not `₹-11.08`). This only
manifests once a strategy is in a loss state; caught via the scratch script's `--scenario loss`
test path (see below) before it shipped as a live bug.

**Scenario test harness (new convention, not previously part of this workshop's scope):**
`scratch/2026-08-07_ic_eod_audit_v2_telegram_format.py` gained a `SCENARIOS` dict + `--scenario`
CLI flag (`profit` / `loss` / `flat` / `alert` / `loss_alert` / `full_greeks`) so
`pnl_emoji`/`alert_emoji`/`compute_net_greek`'s branches can be exercised without hand-editing the
data dict — `--list-scenarios` to enumerate, `--send` required to actually post (default is
print-only, to avoid an accidental live send while browsing scenarios). `full_greeks` uses
synthetic (clearly-labeled non-real) complete delta+theta data across all four legs specifically
to demonstrate the Net Δ/Net θ line rendering a real number instead of `incomplete` — worth
noting during the port that this scenario's synthetic long-leg deltas produced `Net Δ: -0.01`,
not the naive `+0.00` you'd get from summing only the two short legs, i.e. proof the
never-silently-partial rule in `compute_net_greek()` (see `ROLL-0`) actually changes the displayed
number once real data is complete, not just whether the line prints. Worth carrying the
named-scenario-preset pattern into the real test file for this message, not just the scratch
script — the same loss/alert/flat/full_greeks branches need real pytest coverage, not just visual
on-device confirmation.

**Applies to every active IC variant automatically — same reasoning as `ROLL-0`.** This task
edits `process_variant()`'s message-building logic (the function itself, not a per-call-site
wrapper), and `_run()` already calls it once per variant across both `CONFIGS` (V1: weekly/
monthly/leaps/yearly) and `CONFIGS_V2` (V2: monthly only, Phase 1-scoped — see `ROLL-0`'s note,
do not assume V2 weekly/leaps/yearly exist). No per-variant task, test file, or code path is
needed — one port covers `IC EOD Audit — weekly (paper_ic_nifty_v1_weekly)` through
`— yearly (paper_ic_nifty_v1_yearly)` and V2's monthly identically, since `strategy_label`/
`strategy_id`/`dte`/`nifty`/`ivr`/legs/`margin` are all already per-variant *data*, not per-variant
*code*. `scratch/2026-08-07_ic_eod_audit_v2_telegram_format.py`'s new `VARIANTS` dict + `--variant`
flag (5 entries) demonstrates this — every variant renders correctly with zero branching in
`build_message()`. The FMT-1c color-coded header is the one piece that DOES need a per-variant
**data** lookup (timeframe → color/emoji, `V1`-vs-`V2` → badge) — still not per-variant *code*,
since `build_header()`'s `_TIMEFRAME_META`/`VARIANT_META` dicts (see FMT-1c) are the single source
both `process_variant()`'s V1 and V2 call paths read from identically.

**Tests:** update the existing message-format test(s) for this script to assert the new
structure; keep at least one test that constructs a leg with an underscore-bearing signal code
to prove the `mdcode()` wrapping survived the port (this is the exact bug this whole epic
started from — don't let the regression test get lost in the rewrite). Add tests for
`pnl_emoji`/`alert_emoji`/`compute_net_greek`'s branches in the message-building test file too
(loss state, alert state, flat P&L, complete vs. incomplete Greeks) — the scratch script's
`SCENARIOS` presets are a ready-made list of cases to port into real assertions, not just visual
checks. Do not duplicate `ROLL-0`'s net-Greeks unit tests here — this task's tests should assert
the *rendering* of `net_delta`/`net_theta` (numeric vs. incomplete), not re-test the summation
logic itself. Do not duplicate FMT-1c's own header unit tests here either (color/emoji-per-timeframe,
version-badge presence, hashtag-not-in-code-span) if `build_header()` lands as its own
independently-tested unit — this task's tests should assert that `process_variant()` *calls* it
correctly per variant (right timeframe in, right header out), via one test per one of the five
active variants, not re-verify the color/emoji table.

**Commit:** `feat(ic): migrate EOD audit message to Markdown table format`

---

## ROLL-2 — IC Monthly Comparison Report

**⚠️ Supersedes `docs/plan/telegram-ic-comparison-formatting/` TGFMT-2..9 (marked superseded
2026-08-07) — read that folder's `tasks.md` note first.** TGFMT-1 already shipped (SHA
`a69d817`) a dynamic-width fix to `build_comparison_report()` — the hand-counted-20-char-budget
bug is **already fixed**, do not re-fix it from scratch. This task's job is narrower than
originally scoped: port the already-correct alignment logic to use
`formatting-rules/`'s `build_side_by_side_kv_table` (for consistency with every other message
in this epic) and add Markdown bold/parse_mode — not fix a bug that no longer exists.

**Confirmed message structure (2026-08-07, `message-format-workshop.md` session) — reference
implementation `scratch/2026-08-07_ic_monthly_comparison_telegram_format.py`:**

```
⚖️ *IC Monthly (V1 vs V2)* | 2026-08-07
```text
Metric         V1     V2
------------------------
DTE            18     18
Credit        ₹87   ₹129
Captured      +4%    +3%
Put Δ       -0.03  -0.23
Call Δ      +0.28  +0.23
------------------------
Flt P&L (M)   N/A    N/A
Bkd P&L (M)    ₹0    ₹58
Flt P&L (I)  ₹359   ₹587
Bkd P&L (I)   N/A    N/A
------------------------
Lock Zone     N/A   None
Adjustments    0R 0R, 0L
Signals      None   None
------------------------
```
🏆 *Edge so far:* `V2 (+₹286 vs V1)`
```

(Escaping omitted for readability, as in `ROLL-1`'s block — see the scratch script for the actual
MarkdownV2 source. `N/A` values above reflect this session's real data, which didn't include
Legs/Bkd(I)/Flt(M) — see the per-field sourcing below for what the real implementation shows once
wired.) This single-table layout (dashed-rule row groups inside one fenced block) supersedes an
earlier draft of this task that assumed `build_side_by_side_kv_table` (two separate bordered
tables joined with `\|`) — confirmed on-device that one fenced comparison table reads better for
this specific message than two adjacent kv tables; `formatting-rules/`'s `build_side_by_side_kv_table`
may still be the right generic helper for *other* future two-column messages, just not this one.

**Two still-open feature asks carried forward from TGFMT-2/TGFMT-3 — include in this task's
scope, don't drop them. Per-field data sourcing confirmed 2026-08-07 by reading the real code
(not assumed) — two of the three are wiring, one is genuinely new:**

1. **Legs row** — open-leg count out of 4, with a 🔴 suffix if <4. **Already available, zero new
   queries.** `build_stats()` (`scripts/strategies/ic/paper_ic_monthly_comparison.py`, confirmed
   via `get_code_snippet`) already computes `open_pos = [p for p in positions if p.net_qty != 0]`
   as its very first line — just thread `len(open_pos)` through to `ICMonthlyStats` and the
   report. Render as `n/4` with a `🔴` suffix when `n < 4`.

2. **`Bkd (I)`** (realized P&L, since inception) — **already available via an existing public
   helper, but the original TGFMT carry-forward note above (superseded by this correction) was
   WRONG about the source.** `src/paper/tracker.py::get_strategy_realized_pnl(store,
   strategy_name)` is the correct source — it sums from `paper_trades` directly, matching how
   realized P&L is computed everywhere else in the codebase. **Do NOT read
   `paper_nav_snapshots.realized_pnl`'s latest row** (which `_get_monthly_realized_pnl` already
   fetches internally as `curr_val` and discards, tempting as it looks) — per `CONTEXT.md`'s
   SNAP-1 finding, that column resets to 0 on a full open→close→reopen cycle, so it silently
   undercounts "since inception" for any strategy that has ever fully closed and reopened. This
   correction matters: an implementer following the old carry-forward note literally would ship a
   Bkd(I) that's wrong specifically for strategies with a closed-and-reopened history — exactly
   the case "since inception" needs to be right for.

3. **`Flt (M)`** (unrealized P&L, month-only delta) — **the one genuinely new calculation.**
   `Flt (I)` is not a sum-since-inception the way `Bkd (I)` is — unrealized P&L has no flow to
   accumulate, it's a point-in-time mark-to-market value (`_get_unrealized_pnl`'s existing
   `paper_nav_snapshots.unrealized_pnl` read for today already IS `Flt (I)`, confirmed — no new
   function needed for that half). `Flt (M)` is a different quantity: today's unrealized minus
   unrealized-as-of-month-start, mirroring `_get_monthly_realized_pnl`'s exact existing
   curr-row/prev-row pattern but against the `unrealized_pnl` column instead of `realized_pnl` —
   new `_get_unrealized_pnl_month_change()`. **Confirmed 2026-08-07: `Flt (M)` and `Flt (I)` are
   NOT generally equal** — they coincide only when the position had zero unrealized P&L at
   month-start (i.e., wasn't open yet before the 1st of this calendar month), which depends on
   the actual `entry_date` vs. today, not something to assume either way. This is exactly why the
   test below is mandatory, not optional: implementing `Flt (M)` as a copy of `Flt (I)` would
   look correct on any position that happened to be open the whole month and only silently break
   on a mid-month entry.

**Files to change:**
- `scripts/strategies/ic/paper_ic_monthly_comparison.py` — `build_comparison_report()`,
  `ICMonthlyStats` (add `open_leg_count: int`, `inception_realized_pnl: Decimal`,
  `unrealized_pnl_month_change: Decimal`), `build_stats()` (thread `len(open_pos)` through, call
  `get_strategy_realized_pnl()`), new `_get_unrealized_pnl_month_change()`
- `src/paper/tracker.py` — no change needed, `get_strategy_realized_pnl()` already exists and is
  exported; just import and call it from `paper_ic_monthly_comparison.py`
- `tests/unit/strategies/ic/test_paper_ic_monthly_comparison.py`

**Before any code:**
```
get_code_snippet("build_comparison_report")   # confirm current (TGFMT-1-fixed) implementation
get_code_snippet("ICMonthlyStats")
get_code_snippet("build_stats")               # open_pos already available at the top, confirmed 2026-08-07
get_code_snippet("get_strategy_realized_pnl") # src/paper/tracker.py — confirm current signature before importing
get_code_snippet("_get_monthly_realized_pnl") # the pattern _get_unrealized_pnl_month_change() must mirror
```
Build the message using a single fenced comparison table (see the confirmed structure above and
`scratch/2026-08-07_ic_monthly_comparison_telegram_format.py`'s `build_compare_table()` — a
generic `list[list[(label, v1, v2)]]` row-groups builder with a dashed rule between groups and
`max(len(x) for x in ...)`-computed widths, never a hand-counted constant, same discipline
`build_leg_table` already follows). This does not use `formatting-rules/`'s
`build_side_by_side_kv_table` — an earlier draft of this task assumed it would, but the confirmed
on-device layout is one fenced table with row groups, not two bordered kv tables side by side;
`build_compare_table` (or an equivalent promoted into `formatting-rules/`'s `formatting.py`, judgment
call for the implementer) is the actual match. Preserve existing warn-emoji-on-value behavior
(`🔴` suffix for a flagged value) for the new Legs row specifically — check
`_build_side_by_side_report` in `scratch/2026-08-07_telegram_ic_comparison_format_repro.py` for
how a similar flag was represented in the pre-Markdown version before deciding whether it survives
unchanged.

**Tests:** existing `test_comparison_report_format` and `test_comparison_report_one_missing`
must still pass (or be updated if the exact output string changed — expected, since parse_mode
and table-builder call are changing; update assertions to match, don't weaken them). Keep
TGFMT-1's existing long-label regression test (`"Realized (inception)"` or equivalent) — it
must still pass under the new table builder, proving the dynamic-width property survived the
port. Add, specifically:
- `test_legs_row_shows_open_count` — 4/4 legs open, no 🔴
- `test_legs_row_shows_warning_when_incomplete` — <4 legs open, 🔴 suffix present
- `test_bkd_inception_uses_get_strategy_realized_pnl` — mocks `get_strategy_realized_pnl` and
  asserts its return value (not `paper_nav_snapshots.realized_pnl`'s raw latest row) appears in
  the report; regression test for the corrected sourcing above — a test that only checked "some
  number appears" would pass even if a future edit silently reverted to the wrong (cycle-resetting)
  source
- `test_flt_month_differs_from_flt_inception` — the mandatory "`Flt (M) != Flt (I)`" assertion
  from the feature-ask spec above; construct fixture data where a mid-month entry makes them
  genuinely different, not just numerically coincidental
- `test_flt_month_change_uses_correct_snapshot_rows` — mirrors whatever regression test
  `_get_monthly_realized_pnl` already has (if any — check via `search_graph` before writing this
  from scratch) for its curr-row/prev-row boundary logic, applied to the new
  `_get_unrealized_pnl_month_change()`

**Financial-logic commit note:** the Bkd/Flt month-delta calc is P&L-adjacent — real
`@code-reviewer` against `git diff HEAD` required per root `CLAUDE.md`.

**Commit:** `feat(ic): comparison report Markdown migration + Legs row + Bkd/Flt month split`

---

## ROLL-3 — Strategy Close/Roll Notifications

**Files to change:** same 7 files as `backbone/` MD-3 —
`src/strategy/auto_close.py`, `csp_nifty_v1.py`, `cc_overlay_v1.py`, `collar_overlay_v1.py`,
`ic_nifty_v1.py`, `ic_nifty_v2.py`, `pp_overlay_v1.py`.

**Scope judgment call, per method — decide, don't force a table everywhere:** these messages
are typically single-position-event summaries (one leg closed, one roll executed), not
multi-row tables like the EOD audit. Read each method's current message text before deciding
whether it benefits from `build_kv_table` (e.g. a close event with several P&L figures) or just
needs bold headers + `mdcode()`-wrapped identifiers with no table structure at all (e.g. a
short one-line roll confirmation). Do not force every message into a table shape just because
the tooling now exists — match the format to what the message actually needs, using
`formatting-rules/`'s value formatters (`format_money`, `format_greek`, etc.) regardless of
whether a table is used.

**Tests:** update each strategy's existing close/roll-notification tests to assert the new
message structure. Since `MD-3` already added underscore-survival regression tests at the
escaping layer, these tests can focus on visual/structural correctness (bold markers present,
correct formatter used per value type) rather than re-proving the escaping itself.

**Commit:** `feat(strategy): migrate close/roll notifications to Markdown formatting` (one
commit per strategy file is also acceptable given 7 files touched — use judgment per
`CLAUDE.md`'s "typical phase boundaries" guidance; do not bundle all 7 into a single unreviewable
diff if the changes turn out to be substantial per file)

---

## ROLL-4 — Approval Request Messages

**Files to change:**
- `src/notifications/telegram_gateway.py` — `TelegramGateway.send_approval_request`
- `tests/unit/notifications/test_telegram_gateway.py`

**Mandatory pre-step:** re-read `docs/plan/full-repo-review-followups/telegram-approval-auth-fix/tasks.md`
in full before touching this method. If it has open tasks, coordinate (land its fix first, or
do both changes in the same session with the auth fix as the first commit) — do not let this
task's formatting changes and that story's auth changes race as uncoordinated diffs to the same
function.

**Scope:** apply bold/formatting to the approval-request message body using `formatting-rules/`
helpers, consistent with ROLL-3's per-message judgment call. Confirm callback button
label/data are unaffected by the parse-mode change (buttons are a separate Telegram API field,
not part of the parsed message body, but verify against the current implementation rather than
assuming).

**Tests:** existing `test_send_approval_request_returns_message_id_on_success` and related
tests must still pass; add a test proving a strategy_id or instrument label with an underscore
in the approval message body survives correctly (same regression-test pattern as ROLL-1).

**Commit:** `feat(notifications): migrate approval request message to Markdown formatting`

---

## ROLL-6 — EOD Paper Summary

**Not in the epic's original confirmed-callers list** (see `README.md`'s 2026-08-08 addendum)
— `scripts/eod_summary.py` currently sends via raw HTML `parse_mode` directly, bypassing
`TelegramNotifier.send()` entirely, which is why `backbone/`'s original audit missed it. This
task covers both the transport switch (HTML → `TelegramNotifier.send()` + MarkdownV2) and the
format migration in one pass, since the message was never wired through the shared notifier to
begin with.

**Confirmed message structure — FINAL v2 (2026-08-08, `message-format-workshop.md` session,
iterated live on-device) — reference implementation
`scratch/2026-08-08_eod_paper_summary_format.py`:**

```
📝 NiftyShield Paper EOD | 07 Aug 2026
Activities: 0 | Net P&L: +₹65,404 ✅
```text
STRATEGY       |      FLT |      BKD |    TOTAL
===============|==========|==========|=========
> TRACK TOTAL  |  +47,520 |   -3,443 |  +44,077
 Fut           |     -150 |        - |     -150
 Proxy         |   -2,971 |   -3,443 |   -6,414
 Spot          |  +50,640 |        - |  +50,640
---------------|----------|----------|---------
> IC TOTAL     |   +5,144 |   +4,490 |   +9,634
 V1 Wkly       |        - |   +2,759 |   +2,759
 V1 Mth        |     +359 |   +3,486 |   +3,846
 V1 Leap       |   +4,079 |        - |   +4,079
 V1 Yrly       |     +120 |        - |     +120
 V2 Mth        |     +587 |   -1,756 |   -1,169
---------------|----------|----------|---------
> OVERLAY TOTAL|     +115 |     +555 |     +669
 Collar        |     +210 |      -86 |     +125
 CC            |        - |     +640 |     +640
 PP            |      -95 |        - |      -95
---------------|----------|----------|---------
> CSP TOTAL    |        - |  +11,024 |  +11,024
 V1            |        - |  +11,024 |  +11,024
```
#EOD_SUMMARY
```

(Escaping omitted for readability, as in `ROLL-1`'s block — see the scratch script for the
actual MarkdownV2 source. `#EOD_SUMMARY` sits on its own line AFTER the closing fence, not in
the header — MarkdownV2 doesn't parse entities, including Telegram's auto-hashtag-detection,
inside a fenced code block, so it could never have lived inside the table. Still a whole-message
tag, not per-strategy — this message aggregates 12 strategies in one send, unlike the
single-strategy IC EOD Audit where the tag identifies which one variant the message is about.
On-device hashtag tappability for this escaped-`#`/`_` pattern was already confirmed working in
`FMT-1c` — not re-verified from scratch here, same mechanism.)

**v1 → v2 revision summary (v1 was an 8-row flat list, superseded — see the scratch script's
module docstring "Iteration history" for the full blow-by-blow, not reproduced here):**
1. Grew from 8 to 12 strategies, grouped into 4 buckets (confirmed strategy_id → bucket mapping
   below).
2. Each bucket's subtotal row renders ABOVE its member rows (`"> BUCKET TOTAL"`), not below —
   see `FMT-1d`'s "Bucket grouping + totals-first" note for the confirmed rationale and the
   explicit caveat that this is a scan-speed trade-off specific to this message, not a pattern
   to assume elsewhere.
3. Member row labels dropped their redundant bucket-name prefix (`V1 Leap` not `IC V1 Leap`,
   `Fut` not `Nifty Fut`, `V1` not `CSP V1`) — the bucket's own total row already establishes
   context.
4. Zero cells render as `-`, not `0` (`FMT-1d`).
5. `Activities` and `Net P&L` merged onto one line with a `pnl_emoji()` indicator (`FMT-1b`'s
   existing spec, reused not reinvented) — the `📊 Strategy Performance` section label was
   dropped as redundant.
6. Column headers went ALL CAPS (`STRATEGY`/`FLT`/`BKD`/`TOTAL`), and the table gained a double
   rule (`====`) under the header distinct from the single rule (`----`) between buckets.
7. The bucket-total prefix is plain ASCII `>`, not `▶` — see `FMT-1e` (new) for why: Telegram
   renders `▶` via its emoji-presentation glyph even inside a fence, breaking alignment.

**Confirmed strategy_id → bucket mapping (verified via `src/paper/constants.py` and
`src/strategy/ic_expiry_config_v2.py`/`ic_nifty_v2.py`, not assumed):**

| Bucket | strategy_id | Display label |
|---|---|---|
| Track | `paper_nifty_futures` | `Fut` |
| Track | `paper_nifty_proxy` | `Proxy` |
| Track | `paper_nifty_spot` | `Spot` |
| IC | `paper_ic_nifty_v1_weekly` | `V1 Wkly` |
| IC | `paper_ic_nifty_v1_monthly` | `V1 Mth` |
| IC | `paper_ic_nifty_v1_leaps` | `V1 Leap` |
| IC | `paper_ic_nifty_v1_yearly` | `V1 Yrly` |
| IC | `paper_ic_nifty_v2_monthly` | `V2 Mth` |
| Overlay | `paper_collar_v1` | `Collar` |
| Overlay | `paper_covered_call_v1` | `CC` |
| Overlay | `paper_protective_put_v1` | `PP` |
| CSP | `paper_csp_nifty_v1` | `V1` |

**Bkd sourcing — confirmed 2026-08-08, mirrors `ROLL-2`'s corrected finding:** `Bkd` (realized
P&L) must be **since-inception, survives close/reopen cycles** — source from
`get_strategy_realized_pnl(store, strategy_name)` (`src/paper/tracker.py`, sums from the
append-only `paper_trades` ledger), **not** `paper_nav_snapshots.realized_pnl`'s latest row,
which resets to 0 on a full open→close→reopen cycle (confirmed live for `paper_nifty_futures` on
2026-08-05, per `CONTEXT.md` SNAP-1). Apply uniformly across all 12 strategies, not just the
Track bucket (which is the one most likely to have actually cycled). `Flt` stays a point-in-time
mark-to-market read from `paper_nav_snapshots.unrealized_pnl`'s latest row — no change there.

**Design decisions locked in this session, don't re-litigate:**
1. Display names are human-readable, bucket-prefix-free (see mapping table above). `Mth` is the
   confirmed abbreviation for "monthly."
2. Money in the table uses `FMT-1d`'s integer-table exception, not `format_money`'s 2dp default.
   `₹` appears once, on the `Net P&L` line only. Zero renders as `-`.
3. Column headers are `FLT`/`BKD` (all caps), reusing `ROLL-2`'s `Flt`/`Bkd` vocabulary — not
   `Unrealized`/`Realized` or any other pair.
4. `Bkd` sources from `get_strategy_realized_pnl()` (since-inception, cycle-safe) — see the
   sourcing note above. This is the single most important correctness point in this task; a
   naive read of the snapshot column will silently undercount cyclical strategies.
5. Table columns are fixed-width via `max(len(x) for x in ...)`, never a hand-counted literal —
   same discipline as every other table in this epic.
6. Bucket subtotal rows use `>` (plain ASCII), never `▶` or any other symbol not explicitly
   confirmed safe inside a fence — see `FMT-1e`.
7. A `strategy_id` present in the query result but not mapped to any bucket must raise loudly at
   message-build time, not silently drop the row — new strategies added to the DB need an
   explicit bucket assignment before they'll show up here.

**Files to change:**
- `scripts/eod_summary.py` — replace the raw HTML `<b>...</b>` message construction (currently
  `main()`, message-building starts ~line 79) with a call into a new
  `build_eod_summary_message()`, sent via `TelegramGateway`/`TelegramNotifier.send()` with
  `parse_mode=MarkdownV2` instead of the current direct HTML send. Must call
  `get_strategy_realized_pnl()` per strategy for `Bkd`, not read `paper_nav_snapshots` directly
  for that field (see Bkd sourcing note above).
- `src/notifications/formatting.py` — promote the scratch script's `build_strategy_table()` (the
  `FMT-1d`/`FMT-1e` bucketed, totals-first table builder), `_fmt_table_money()`, and the
  `_DISPLAY_NAME`/`_BUCKETS` mapping (or an equivalent structure — judgment call for the
  implementer whether this belongs in `formatting.py` or a `scripts/eod_summary.py`-local
  constant, since the bucket mapping is specific to this one message, unlike `format_money`/
  `pnl_emoji` which are genuinely reusable) once `formatting-rules/` FMT-2/FMT-3 have landed
- `tests/unit/scripts/test_eod_summary.py` (new, or extend existing test file if one already
  covers `eod_summary.py` — check via `search_graph` before assuming there's nothing there)

**Before any code:**
```
get_code_snippet("eod_summary")            # confirm current main()/message-building implementation
search_graph("TelegramGateway")            # confirm the send method signature this should call instead of raw HTML
search_graph("build_leg_table")            # confirm FMT-3's promoted table-builder pattern to mirror
search_graph("get_strategy_realized_pnl")  # confirm current signature before wiring Bkd sourcing
```

**Tests:**
- `test_build_eod_summary_message_matches_confirmed_format` — golden-output test against the
  confirmed v2 structure above (or a close variant using fixture Decimal values), asserting
  exact table alignment, bucket ordering (Track/IC/Overlay/CSP), and the `FLT`/`BKD`/`TOTAL`
  header
- `test_eod_summary_bucket_subtotal_is_sum_of_members` — each bucket's `> BUCKET TOTAL` row must
  equal the sum of its member rows' `Flt`/`Bkd` independently — a test that only checks the
  grand `Net P&L` total would pass even if a bucket subtotal silently drifted
- `test_eod_summary_bkd_uses_get_strategy_realized_pnl` — mocks `get_strategy_realized_pnl` and
  asserts its return value (not `paper_nav_snapshots.realized_pnl`'s raw latest row) appears in
  the report; regression test for the corrected sourcing above, same pattern `ROLL-2` needed —
  a test that only checked "some number appears" would pass even if a future edit silently
  reverted to the cycle-resetting source
- `test_eod_summary_unmapped_strategy_raises` — a `strategy_id` not present in the bucket
  mapping must raise, not silently vanish from the message
- `test_eod_summary_table_money_no_decimals` — regression test for the `FMT-1d` integer-table
  exception; a fixture value with cents (e.g. `Decimal("359.12")`) must render as `+359`, not
  `+359.12` or `+359.1`
- `test_eod_summary_zero_value_renders_dash` — `Decimal("0.00")` renders as `-`, not `0`/`+0`/`-0`
- `test_eod_summary_hashtag_survives_escaping` — same regression-test pattern as `ROLL-1`: the
  literal `#EOD_SUMMARY` string, once escaped and sent, must round-trip correctly (this project's
  test suite can assert on the escaped source string containing `\#EOD\_SUMMARY`, matching how
  `MD-1`'s existing escaping tests are structured — check that pattern via `search_graph` before
  writing this one)
- `test_eod_summary_net_pnl_sums_all_buckets` — `Net P&L` line equals the sum of every bucket
  subtotal (which in turn equals the sum of every row), not a separately-fetched aggregate that
  could silently drift from the table

**Financial-logic commit note:** the `Bkd` sourcing change (since-inception vs. cycle-resetting)
is P&L-adjacent — real `@code-reviewer` against `git diff HEAD` required per root `CLAUDE.md`.

**Commit:** `feat(scripts): migrate EOD paper summary to MarkdownV2 + bucketed Flt/Bkd table`

---

## ROLL-7 — Re-entry Blocked/Eligible Notice

**Not in the epic's original confirmed-callers list** — added 2026-08-08 via
`missing-message-workshop-prompt.md`/`message-format-workshop.md` (queue item 1,
`docs/plan/telegram-markdown-migration/TODO.md`). Simplest message in the queue: single
status notice, no table, no multi-source data.

**Confirmed real source:** `ReEntryMixin._check_reentry`
(`src/strategy/reentry_mixin.py:189-210`), inherited by `CSPNiftyV1`, `CCOverlayV1`, and
`CollarOverlayV1` (`src/strategy/CLAUDE.md` — all three `ReEntryMixin` subclasses). TODO.md's
queue line named only the BLOCKED half; reading the real method in full (per this workshop's
own protocol) surfaced a second branch sharing the same code path — both are in scope for this
task:

```python
status_line = (
    f"✅ {strategy_name} {leg_role} Re-entry ELIGIBLE — run {script_hint}"
    if signal == ELIGIBLE
    else f"⛔ {strategy_name} {leg_role} Re-entry BLOCKED"
)
msg = f"{status_line}\n{notes}"
```
sent via `self._notifier.send_plain_message(msg)`.

**Confirmed message structure (2026-08-08, `message-format-workshop.md` session, kv-line
counter-proposal from Animesh, superseding this workshop's initial single-packed-line draft)
— reference implementation `scratch/2026-08-08_reentry_notice_format.py`:**

```
⛔ RE\-ENTRY BLOCKED: IC V1 Monthly
Leg: Short Call
Reason: DTE\=9 < 14 \(Too close to expiry\)
```
```
✅ RE\-ENTRY ELIGIBLE: CSP V1
Leg: Short Put
Status: All Gates Passed
Execute:
`scripts/record/record_paper_trade.py`
```

(Backslash escaping shown as actual MarkdownV2 source, as in `ROLL-1`/`ROLL-2`'s blocks — see
the scratch script for all four confirmed scenarios: `blocked_dte`, `blocked_ivr`,
`blocked_open_position`, `eligible`.)

**Two things this message needs that the plain-escaping port didn't — both real scope, not
cosmetic:**

1. **Strategy display label (`STRATEGY_LABELS`).** `ReEntryMixin.strategy_name` is the raw id
   (`paper_csp_nifty_v1`); the confirmed headline uses a human label ("CSP V1"). No generic
   id→label mapping exists in `src/strategy/` yet. `ROLL-6`'s `_DISPLAY_NAME` table is NOT
   reused here as-is — it's sized for a narrow table column ("V1 Mth", "Fut") and reads badly
   as a standalone headline ("RE-ENTRY BLOCKED: V1 Mth"). This task defines its own fuller-form
   `STRATEGY_LABELS` dict (same 12 strategy_ids, longer label text — see the scratch script for
   the full table). **Revisit once `ROLL-6` ships:** consider promoting one shared
   `id -> {short, long}` label struct in `formatting.py` that both messages read from, rather
   than maintaining two independent label tables long-term — flagged, not resolved, don't
   silently duplicate-and-drift.
2. **Structured `(short_reason, detail)` per gate, not string-split prose.** The real
   `_check_reentry` currently builds one free-text `blocked_reason` string per gate (e.g.
   `"DTE=9 < 14 — too close to expiry for re-entry"`). Splitting that string on the em dash at
   render time to recover "DTE=9 < 14" + "(Too close to expiry)" would be brittle — a future
   gate's reason might not contain an em dash, or a different one. **This task must refactor
   the three gates inside `_check_reentry` (DTE, IVR, open-position) to each produce a
   `(short_reason: str, detail: str | None)` pair instead of one prose string**, and have the
   message-building code format the pair — not fake the split. This is real production-logic
   scope beyond MD-3's "escaping only" boundary, which is fine: `strategy-rollout/` is
   explicitly allowed to reword message content (`ROLL-3`'s charter), unlike `backbone/`. The
   `IVR history insufficient` / `open position check failed` non-gate-specific failure
   `blocked_reason` strings (structural, not one of the three named gates) also need a
   `(short_reason, detail)` shape — treat as a 4th/5th case, don't leave them as a fallback
   raw-string path that skips the new formatting.

`Leg:` labels (`LEG_ROLE_LABELS`) use an explicit dict, not `.title()` —
`"overlay_cc".title()` produces "Overlay Cc", not "Overlay CC"; CC/PP acronyms need the same
explicit treatment this epic already gives them elsewhere (`FMT-1c`'s IC/V1/V2 badges,
`ROLL-6`'s CC/PP display names).

**Open question, deliberately not resolved in the confirmed format:** the raw `strategy_id`
(kept as its own `` `code span` `` line in `ROLL-1`'s IC audit header, for exact-string
copy/grep against logs) is dropped entirely from this message, per Animesh's confirmed
example. If exact-id grep-ability turns out to matter for this message too, add it back as a
third/fourth line during implementation — don't assume the omission was an oversight, it was a
confirmed choice, but don't treat it as permanently closed either if a real workflow need
surfaces.

**Files to change:**
- `src/strategy/reentry_mixin.py` — `ReEntryMixin._check_reentry` (the three gates' reason
  construction, plus the two `structural failure` reason strings noted above; the
  message-building/formatting call)
- New: strategy label + leg-role label lookups (`STRATEGY_LABELS`/`LEG_ROLE_LABELS` or
  equivalent) — land in `src/notifications/formatting.py` alongside `formatting-rules/`'s other
  helpers if that module has shipped by the time this task starts, otherwise colocate in
  `reentry_mixin.py` and move later (judgment call for the implementer, same shape as `FMT-1c`'s
  header-location judgment call)
- Matching test file: `tests/unit/strategy/test_reentry_mixin.py` (existing file — extend, not
  new, per `search_graph` before assuming)

**Before any code:**
```
get_code_snippet("ReEntryMixin._check_reentry")   # confirm current gate/reason construction fresh
search_graph("STRATEGY_LABELS")                    # confirm no such mapping already exists elsewhere
search_graph("_DISPLAY_NAME")                       # ROLL-6's table, if it has landed — do not duplicate blindly
```

**Tests:**
- One test per scenario in the reference script (`eligible`, `blocked_dte`, `blocked_ivr`,
  `blocked_open_position`) asserting the exact kv-line structure and correct escaping
- `test_reentry_notice_escapes_underscore_leg_role` — a leg_role/strategy_name fixture
  containing an underscore survives label-lookup + `escape_markdown()` correctly — the
  regression test every message in this epic carries forward
- `test_reentry_notice_unmapped_strategy_raises` — a `strategy_name` not present in
  `STRATEGY_LABELS` raises loudly (`ValueError`), not silently falls back to the raw id or
  drops the notification
- `test_reentry_notice_unmapped_leg_role_raises` — same, for `LEG_ROLE_LABELS`
- `test_blocked_reason_is_structured_pair` — each of the three gates (DTE/IVR/open-position)
  and the two structural-failure paths return a `(short_reason, detail)` tuple, not a single
  prose string — regression test for the string-split-is-brittle fix this task makes
- `test_eligible_execute_line_uses_mdcode` — `script_hint` renders as a backtick-wrapped code
  span in the ELIGIBLE branch

**Commit:** `feat(strategy): migrate re-entry notice to Markdown kv-line format`

---

## ROLL-8 — Generic Strategy WARN Event Alert

**Not in the epic's original confirmed-callers list** — added 2026-08-08 via
`missing-message-workshop-prompt.md`/`message-format-workshop.md` (queue item 2,
`docs/plan/telegram-markdown-migration/TODO.md`). One f-string line, generic across every
monitored strategy/event type — not IC-specific like `ROLL-1`/`ROLL-2`, and distinct from the
per-strategy close/roll notifications `ROLL-3` covers.

**Confirmed real source:** `StrategyMonitor._route_event`'s WARN branch
(`src/strategy/monitor.py:366-367`), the shared dispatch path every `PaperStrategy.check_signals()`
implementation's WARN-severity `SignalEvent`s route through (already deduped OFF->ON by
`warn_signal_state`/`is_warn_active` before this text is built — see `_route_event`'s docstring).
Distinct from `send_approval_request` (line 410, same file, `ROLL-4`'s ACTION-severity path):

```python
text = f"[{strategy.strategy_name}] {event.event_type}: {event.description}"
await self._notifier.send_plain_message(text)
```

**Confirmed message structure — REVISED v2 (2026-08-08, same `message-format-workshop.md`
session — cause->effect compact counter-proposal from Animesh, superseding the v1 kv-line
draft below).** v1 (superseded, kept for the elimination trail — "kv-line, ROLL-7 style"
option, selected over a single-bold-line minimal-change option and a
raw-strategy-id-no-label-table option):

```
⚠️ *IC V1 Monthly*
Event: `DELTA_BREACH`
short put delta \-0\.42 exceeds threshold \-0\.40 \(review roll candidates\)\.
```

**v2 (final, reference implementation `scratch/2026-08-08_strategy_event_alert_format.py`):**

```
⚠️ DELTA BREACH \- IC V1 Monthly
Leg: Short Put
short put delta \-0\.42 exceeds threshold \-0\.40 \(review roll candidates\)\.
```

(Backslash escaping shown as actual MarkdownV2 source, as in `ROLL-1`/`ROLL-2`/`ROLL-7`'s
blocks.) v1 -> v2 revision, and what was explicitly rejected along the way:

1. **`event_type` folded into the headline via mechanical `.replace("_", " ")` only** —
   `DELTA_BREACH` -> `DELTA BREACH`. A first pasted mockup this session proposed inventing new
   headline vocabulary per event_type (e.g. `ROLL_BASE_FIRST` -> "SEQUENCE LOCK") — rejected:
   that's a rename, not a reformat, and would need an open-ended event_type -> label dict
   maintained forever as new signals get added. Plain `.replace("_", " ")` costs nothing and
   stays honest to the real identifier (no `mdcode()`/code-span treatment of `event_type` in
   v2 — it's now prose in the headline, not a kept-for-audit identifier the way `ROLL-1`'s
   `strategy_id` code-span line or `ROLL-7`'s `script_hint` are).
2. **`Leg:` line added — real, not invented.** `event.payload.get("leg_role", "")` is already
   read by `_route_event` itself (used in the WARN dedup key), so this is genuinely
   available data, not a refactor. Omitted entirely when absent/empty (some event types carry
   no leg_role) rather than printing a blank placeholder line.
3. **`Metric:`/`Action:` fields from the first mockup were NOT carried over — structurally
   can't be, not just deferred.** `_route_event`'s WARN branch only has `strategy_name`,
   `event_type`, and `event.description` (one pre-built prose string) in scope. Decomposing it
   into separate numeric-delta/limit/action fields would require every `check_signals()`
   emitter across every strategy to start passing structured payload fields instead of prose —
   real scope beyond this task, not a formatting choice. Parsing the existing string at render
   time to fake the split was considered and rejected — the same brittle-string-splitting
   pattern `ROLL-7`'s spec already rejected for `_check_reentry`'s `blocked_reason`. `description`
   stays one `escape_markdown()`'d line.
4. **Emoji stays fixed `⚠️`, not tiered per event_type (`🚨` for "breach" vs `⚠️` for "warn"),
   confirmed as a real correctness point, not a missing nice-to-have.** `_route_event`'s WARN
   branch is the ONLY severity that ever reaches this text-building code — ACTION-severity
   events either auto-execute or route to `send_approval_request` (`ROLL-4`), never this line;
   INFO just logs. Every message through this path IS a WARN by construction, so a tiered emoji
   would misrepresent severity, not merely skip an enhancement. Same underlying objection
   `FMT-1b` already raised against selecting `alert_emoji` by matching the signal-code string —
   applied here to emoji-per-event-type instead of presence-based alerting.

**Reuses ROLL-7's `STRATEGY_LABELS` table (same 12 strategy_ids, fuller-form human labels,
e.g. "IC V1 Monthly" not ROLL-6's table-column "IC V1 Mth") and its `LEG_ROLE_LABELS` table —
does not redefine either independently.** Confirmed 2026-08-08: keep the fuller form for this
standalone headline, do not switch to ROLL-6's abbreviated form. The reference scratch script
duplicates both dicts inline (neither script is real `src/` code yet), same
flagged-not-resolved duplication point ROLL-7's own docstring already raises: once either
`ROLL-7` or this task ships for real, the surviving one should promote shared
`STRATEGY_LABELS`/`LEG_ROLE_LABELS` into `src/notifications/formatting.py` and the other should
import them, not maintain a second copy. Whichever of `ROLL-7`/`ROLL-8` lands first in real code
should do that promotion as part of its own commit.

**No new FMT-1 formatting rule surfaced this session** — this message reuses ROLL-7's existing
label/`escape_markdown()` conventions, minus `mdcode()` (dropped in v2 — `event_type` is now
headline prose, not a kept identifier). No new parameter type or table shape.

**Files to change:**
- `src/strategy/monitor.py` — `StrategyMonitor._route_event`'s WARN branch (text-building only;
  the dedup/`warn_signal_state` logic above it is unrelated and untouched)
- New: `STRATEGY_LABELS`/`LEG_ROLE_LABELS` lookup — land in `src/notifications/formatting.py`
  if that module (or `ROLL-7`'s label tables) has shipped by the time this task starts;
  otherwise colocate locally and flag for the same promotion `ROLL-7` already flags
- Matching test file: `tests/unit/strategy/test_strategy_monitor.py` (existing file — extend,
  not new, per `search_graph` before assuming)

**Before any code:**
```
get_code_snippet("StrategyMonitor._route_event")   # confirm current WARN-branch text fresh
search_graph("STRATEGY_LABELS")                      # confirm whether ROLL-7's tables have landed
```

**Tests:**
- One test per scenario in the reference script (`delta_breach`, `proxy_delta_warn`,
  `roll_base_first_warn`, `no_leg_role`) asserting the exact headline/Leg/description structure
  and correct escaping
- `test_event_alert_headline_humanizes_event_type` — `event_type="ROLL_BASE_FIRST"` renders as
  `ROLL BASE FIRST` in the headline (mechanical `.replace("_", " ")`, not a relabeling dict) —
  regression test proving the headline stays a reformat of the real identifier, not an invented
  synonym
- `test_event_alert_escapes_underscore_description` — a `description`/`strategy_name` fixture
  containing an underscore (`DELTA_WARN`, the exact bug that started this epic) survives
  label-lookup + `escape_markdown()` correctly — the regression test every message in this epic
  carries forward
- `test_event_alert_unmapped_strategy_raises` — a `strategy_name` not present in
  `STRATEGY_LABELS` raises loudly (`ValueError`), not silently falls back to the raw id or drops
  the notification — same discipline `ROLL-6`/`ROLL-7` both require
- `test_event_alert_omits_leg_line_when_absent` — `event.payload` with no `leg_role` produces no
  `Leg:` line at all, proving the optional-line rule above is actually honored (not a blank
  placeholder line)
- `test_event_alert_severity_never_tiered` — regression test for the fixed-`⚠️` design decision:
  construct two WARN events with different `event_type` values and assert both render the same
  leading emoji, proving no substring-based severity/emoji inference crept in

**Commit:** `feat(strategy): migrate generic WARN event alert to Markdown kv-line format`

---

## ROLL-9 — Three-Track Base-Leg Roll Notification

**Not in the epic's original confirmed-callers list** — added via
`missing-message-workshop-prompt.md`/`message-format-workshop.md` (queue item 3,
`docs/plan/telegram-markdown-migration/TODO.md`). TODO.md's queue line ("Two lines, single
position event") undersold the real message — the current pre-migration code is 6 lines, not 2.

**Confirmed real source:** the message-construction block inside `_notify_roll`
(`scripts/strategies/three_track/paper_3track_roll.py:296-313`, called from `_run()` after a
roll's close/open trades are persisted):

```python
msg = (
    f"🔄 BASE LEG ROLLED\n"
    f"Strategy: {pos.strategy_name}\n"
    f"Leg: {pos.leg_role}\n"
    f"Closed: {pos.instrument_key} @ ₹{close_price}\n"
    f"Opened: {next_key} @ ₹{open_price}\n"
    f"{status_line}"
)
```

Handles both rollable leg roles: `base_futures` (DTE≤1, via `get_next_contract`) and
`base_ditm_call` (DTE<20, via `get_next_contract_in_band` — same strike, next
monthly/quarterly/yearly-band expiry only, confirmed via that method's implementation). Separate
from the backbone-managed overlay/CSP rolls `ROLL-3` covers (`CSPNiftyV1`/
`NiftyTrackComparisonV1` via `PaperExecutor`).

**Confirmed message structure — two distinct layouts, one per leg role (this session,
`message-format-workshop.md`, iterated on-device through 3 rounds) — reference implementation
`scratch/2026-08-10_3track_roll_notification_format.py`:**

`base_futures`:
```
🔄 ROLL: NIFTY FUT [AUG ➡️ SEP]
💰 P&L: +₹7,812.50 🟢
📐 Spread: 43.25 pts (Contango)

⬇️ OUT: ₹24,812.50
⬆️ IN: ₹24,855.75
✅ L-Gate: PASS
```

`base_ditm_call`:
```
🔄 ROLL: PROXY DITM CALL
🎟️ [NIFTY 24000 CE] AUG ➡️ SEP
💰 P&L: -₹393.00 🔴
📐 Spread: 25.62 pts (Debit)

⬇️ OUT: ₹86.68
⬆️ IN: ₹112.30
⚠️ L-Gate: WARN
```

Gate/partial line — one of three values in both layouts:
```
🚨 PARTIAL ROLL — VERIFY POSITIONS MANUALLY   (partial=True; overrides gate_passed)
✅ L-Gate: PASS                                (partial=False, gate_passed=True)
⚠️ L-Gate: WARN                                (partial=False, gate_passed=False)
```

(Escaping omitted above for readability, as in every other block in this file — see the
scratch script's 7 scenarios for the actual MarkdownV2 source with `escape_markdown()`/
`mdcode()` applied throughout.)

**Confirmed field-by-field data-availability audit — flagged explicitly during the workshop
per Animesh's own request ("which of these need code changes vs. pure reformatting"), do not
skip this when implementing:**

1. **OUT/IN prices, L-Gate status, partial-roll override** — zero new data. `close_price`,
   `open_price`, `gate_passed`, `partial` are all already `_notify_roll`'s existing local
   values at the point the message is built.
2. **Spread + curve/premium label** — zero new data. `open_price - close_price`; sign picks
   the label (see below). Both values already local.
3. **Closed-leg realized P&L** (`💰 P&L` line) — small change, not a new data source.
   `pnl = (close_price - pos.avg_cost) * abs(pos.net_qty)`. `pos` (the `PaperPosition`) is
   already the loop variable in scope at the call site — `avg_cost`/`net_qty` are its existing
   attributes, no new fetch, no signature change to `_notify_roll` needed since `pos` is
   already passed through. Uses `avg_cost`, **not** `avg_sell_price` — both `base_futures` and
   `base_ditm_call` are long proxy/hedge positions (bought, never sold short), confirmed via
   CONTEXT.md's `src/paper/`/`src/strategy/` sections; `avg_sell_price` would read 0 for these
   legs. This is genuinely new message content (`_notify_roll` currently shows no P&L at all),
   not a reformat — in scope per this folder's charter (unlike `backbone/`'s escaping-only
   boundary).
4. **Month labels** (`[AUG ➡️ SEP]`) — small change, not a new lookup. `expiry_date` (current
   contract) is already resolved earlier in `_run()` via `_get_expiry_date()`; `next_inst` (the
   dict `get_next_contract`/`get_next_contract_in_band` returns) already carries a raw
   `expiry` field, confirmed via `InstrumentLookup.get_next_contract_in_band`'s own
   implementation (it returns the full instrument dict from `self._instruments`, which
   includes `expiry`). Format via `parse_expiry()` + `.strftime("%b").upper()` on both — no
   new broker/DB call.
5. **DITM strike** (`🎟️ [NIFTY 24000 CE] ...` line) — same non-fetch as month labels.
   `InstrumentLookup.get_by_key()` (called internally by both `_get_expiry_date` and
   `get_next_contract_in_band`) already returns a dict carrying `strike_price` — read it off
   the same lookup already being done, don't add a second call.
6. **DITM L-Gate failure reason** (e.g. "Wide Bid/Ask") — **explicitly out of scope for this
   task, confirmed with Animesh.** `check_ditm_liquidity_gate`
   (`paper_3track_roll.py:125-132`) collapses two independent checks
   (`oi >= PROXY_OI_MIN`, `spread <= PROXY_SPREAD_MAX`) into a single bool today. Surfacing
   which one failed needs that function's return type changed (e.g. to a small result object
   naming the failed check), which is real gate-logic scope beyond a message-formatting task —
   defer to a follow-up if the specific reason is wanted later. This task ships `⚠️ L-Gate:
   WARN` with no parenthetical.

**Curve/premium spread label — two different terms for two different leg roles, not one
generic label. Confirmed correction mid-session (Animesh):** "Contango"/"Backwardation" is
real futures calendar-spread terminology (far-month price > near-month price = contango, the
same curve-slope concept as spot-vs-future, just applied between two futures expiries) — valid
for `base_futures`. It does **not** apply to `base_ditm_call`, which is an option premium
difference between two expiries of the *same strike*, not a futures curve — that leg uses
"Debit"/"Credit" instead (farther-dated call costs more to roll into = Debit, cheaper = Credit).
**Add both label pairs to `formatting-rules/stories.md` FMT-1 if not already covered by the
time this ships** — see the note below, since neither pair exists in FMT-1's table today.

**P&L sign display — new local override, not a change to `format_money`'s global default.**
FMT-1's existing negative-money rule (sign before `₹`) is reused as-is, but the P&L line also
needs an explicit `+` on positive values (unlike `format_money`'s current spec, which only
distinguishes negative). Implement as a `signed: bool = False` kwarg on `format_money` (default
`False` preserves every existing caller's behavior) rather than a second formatter function —
confirm this doesn't already exist under a different name before adding it.

**OUT/IN arrows and P&L/status emoji — confirmed, do not diverge:** `⬇️`/`⬆️` are shared
identically across both leg-role layouts (an earlier draft used 📤/📥 for the DITM variant
specifically, for visual distinction — rejected in favor of consistency). P&L emoji is
`🟢`/`🔴`/`➖` (>0/<0/==0) — a **separate** function from `FMT-1b`'s not-yet-real `pnl_emoji()`
spec (which uses `✅`/`🔻`/`➖`); if `FMT-1b` ships before this task's real implementation,
reconcile which palette wins rather than shipping two inconsistent pnl-emoji conventions side
by side — flagged, not resolved.

**Not yet verified on-device:** `⬇️`/`⬆️` (U+2B07/U+2B06) carry the emoji-presentation
variation selector, the same class of glyph `FMT-1e` flagged for `▶` inside a fenced table.
This message has no fence, so `FMT-1e`'s alignment-breaking concern doesn't technically apply,
but the on-device rendering of the stacked arrow+text lines was confirmed acceptable by
Animesh during this session's live sends — noting here only because `FMT-1e`'s glyph-class
warning is otherwise scoped to fenced tables and this is the first confirmed non-fenced use.

**Files to change:**
- `scripts/strategies/three_track/paper_3track_roll.py` — `_notify_roll`'s message-construction
  block; likely needs `pos.avg_cost`/`abs(pos.net_qty)` and the resolved `expiry_date`/
  `next_inst["expiry"]`/`strike_price` threaded through if they aren't already all in the same
  local scope as the message build (confirm via `get_code_snippet` before assuming — the audit
  above was done against the version read this session, re-verify if the file has changed)
- New: `STRATEGY_SHORT_LABELS` (`{"paper_nifty_futures": "FUTURES", "paper_nifty_proxy":
  "PROXY", "paper_nifty_spot": "SPOT"}` — only the DITM header needs this, futures header
  hardcodes "NIFTY FUT") — land in `src/notifications/formatting.py` if that module has shipped
  by the time this task starts, otherwise colocate and flag for promotion (same judgment call
  `ROLL-7`/`ROLL-8` already make for their own label tables)
- Matching test file: `tests/unit/scripts/test_paper_3track_roll.py` (existing file — extend,
  not new, per `search_graph` before assuming)

**Before any code:**
```
get_code_snippet("_notify_roll")                        # confirm current message-build scope fresh
get_code_snippet("check_ditm_liquidity_gate")            # confirm still returns bool only (item 6 above)
search_graph("InstrumentLookup.get_next_contract_in_band")  # confirm returned dict still carries expiry/strike_price
```

**Tests:**
- One test per confirmed scenario in the reference script (`futures_clean_pass`,
  `futures_loss_backwardation`, `futures_gate_warn`, `futures_partial_roll`, `ditm_call_warn`,
  `ditm_call_profit_credit`, `ditm_call_partial_roll`) asserting the exact layout and correct
  escaping for its leg role
- `test_roll_notification_pnl_uses_avg_cost_not_avg_sell_price` — regression test for item 3's
  entry-basis correctness; a fixture `PaperPosition` with non-zero `avg_sell_price` but the
  real `avg_cost` basis must not leak into the P&L figure
- `test_futures_spread_label_contango_backwardation_flat` — three cases (`open > close`,
  `open < close`, `open == close`) assert `Contango`/`Backwardation`/`Flat`
- `test_ditm_spread_label_debit_credit_flat` — same three cases, asserts `Debit`/`Credit`/`Flat`
  (separate function/table from the futures one — regression test proving the two leg roles
  never share a label function)
- `test_ditm_gate_warn_has_no_reason_parenthetical` — regression test for item 6's explicit
  scope boundary; a WARN-state DITM roll's message must not contain a `(...)` reason suffix,
  proving a future edit doesn't silently half-implement the deferred gate-reason feature
- `test_roll_notification_escapes_underscore_strategy_name` — the regression test every message
  in this epic carries forward
- `test_roll_notification_partial_overrides_gate_line` — `partial=True` always produces the
  🚨 line regardless of `gate_passed`'s value, for both leg roles

**Financial-logic commit note:** the P&L computation is P&L-adjacent (uses `pos.avg_cost`
directly in a Telegram-facing figure) — real `@code-reviewer` against `git diff HEAD` required
per root `CLAUDE.md`'s AutoTrigger table.

**Commit:** `feat(scripts): migrate 3-track base-leg roll notification to Markdown + P&L`

---

## ROLL-10 — Proxy Delta CRITICAL Alert

**Not in the epic's original confirmed-callers list** — added 2026-08-10 via
`missing-message-workshop-prompt.md`/`message-format-workshop.md` (queue item 4, TODO.md).
Single status alert, no table, fires only on the CRITICAL proxy-delta breach state.

**Confirmed real source:** `scripts/dev/paper_track_snapshot.py::main`, lines 185-190
(confirmed via `search_graph` + direct read of the file, not the TODO.md grep excerpt alone):

```python
if track_name == STRATEGY_PROXY and snapshot.proxy_delta_alert:
    print(f"  ALERT  : Proxy Delta State -> {snapshot.proxy_delta_alert}")
    if "CRITICAL" in snapshot.proxy_delta_alert:
        await notifier.send(
            f"🚨 **CRITICAL**: Proxy Delta Monitor triggered: {snapshot.proxy_delta_alert}"
            f"\nDelta: {snapshot.greeks.net_delta:.2f}"
        )
```

Only the CRITICAL branch calls `notifier.send()` — the ALERT/WARNING/OK print() lines are
console-only and out of scope. The current call site already sends `**bold**` (legacy-Markdown
asterisks) with no `parse_mode` set at all — i.e. already silently broken (literal asterisks),
not a regression introduced by this migration.

**Known duplicate, flagged not fixed:** `scripts/strategies/three_track/paper_3track_snapshot.py::_run`
(~line 1639) sends a near-identical "Proxy Delta CRITICAL" alert independently from the same
`TrackSnapshot.proxy_delta_alert` field and the same `"CRITICAL" in ...` check — and it's the
real production EOD cron path, whereas `paper_track_snapshot.py` is the lower-stakes dev/manual
script. Not named in `backbone/`'s MD-4 file list or any other `ROLL-*` task. Added as TODO.md
queue item 10 for a future workshop session — out of scope for this task per the
missing-message-workshop-prompt's "do not batch" rule.

**Confirmed message structure (2026-08-10, `message-format-workshop.md` session — one
on-device round-trip via `--send`, reference implementation
`scratch/2026-08-10_proxy_delta_critical_alert_format.py`):**

```
🚨 CRITICAL: PROXY DELTA
📐 Current: \-0\.32 🔴
📉 Rule Breach: CRITICAL \(<0\.40, day 3 of 3\+\)
```

(Backslash escaping shown as actual MarkdownV2 source, as in every other confirmed block in
this file.)

**Elimination trail — two real findings, not cosmetic:**
1. **Escaping bug, found live:** the first draft only escaped the headline's literal `-`, not
   the `Delta:` line's formatted signed-float value (`-0.32`). Telegram 400'd:
   `Character '-' is reserved and must be escaped`. Fix: run `escape_markdown()` over the
   **entire** formatted numeric string, not just its sign character — a signed 2dp value also
   carries a `.` (also reserved). Every other numeric field in this epic already does this
   (`ROLL-1`'s Credit/Mark lines, etc.); this is the first message in the epic where a formatted
   *Greek* value specifically needed the same treatment, worth calling out for the real
   `format_greek()`/`escape_markdown()` call-site pairing once promoted from scratch.
2. **`🤖 Action: REQUIRED / PENDING / AUTO-HEDGING` proposed, then dropped.** No
   action/remediation-state field exists anywhere upstream of this alert —
   `ProxyDeltaMonitor.update_and_check` and `TrackSnapshot` compute no such value, and no
   auto-hedge mechanism is wired to proxy-delta breaches today. Rendering it would fabricate
   data — same anti-pattern `FMT-1b`/`ROLL-8` already rejected for their own severity/action
   fields. Confirmed with Animesh: revisit only once a real action signal exists.
3. **`📉 Rule Breach:` renders `proxy_delta_alert` verbatim, not split into separate
   threshold/day-count fields.** The threshold (`0.40`) and consecutive-day count aren't passed
   to this call site as their own values — only pre-baked into one string
   (`src/paper/track_snapshot.py::generate_track_snapshot`, ~line 349,
   `f"CRITICAL (<0.40, day {consecutive} of 3+)"`). Parsing them back out at render time would
   repeat the exact brittle string-split pattern `ROLL-7` rejected for `_check_reentry`'s
   `blocked_reason`. **Real implementation must first plumb `consecutive_days` as its own field**
   on `TrackSnapshot` (currently computed by `ProxyDeltaMonitor.update_and_check` then discarded
   after being folded into the string) before a structured `Rule Breach:` layout is possible —
   confirmed with Animesh: plan this data-plumbing at implementation time, same shape as
   `ROLL-0` was for the IC audit's Net Δ/θ. Until then, ship the verbatim string.

**Files to change:**
- `scripts/dev/paper_track_snapshot.py` — `main`'s CRITICAL-branch `notifier.send()` call
- `src/paper/track_snapshot.py` — `TrackSnapshot`/`generate_track_snapshot`, to add the
  `consecutive_days` field needed for finding 3 above (real scope, not deferred past this
  `ROLL-10` implementation — only deferred past this *format-confirmation* workshop session)
- Matching test file: `tests/unit/scripts/test_paper_track_snapshot.py` (new, or extend if one
  already exists — check via `search_graph` before assuming)

**Before any code:**
```
get_code_snippet("paper_track_snapshot.main")
get_code_snippet("ProxyDeltaMonitor.update_and_check")
get_code_snippet("generate_track_snapshot")
search_graph("TrackSnapshot")   # confirm current field list before adding consecutive_days
```

**Tests:**
- `test_critical_alert_escapes_signed_delta` — regression test for finding 1: a negative
  (`-0.32`) and positive (`+0.05`) `net_delta` both survive `escape_markdown()` fully (sign AND
  decimal point escaped), not just the headline's literal `-`
- `test_critical_alert_no_action_line` — regression test for finding 2: the constructed message
  never contains an `Action:`/🤖 line, proving the fabricated-data rejection stuck
- `test_critical_alert_rule_breach_is_verbatim` — `proxy_delta_alert` string appears escaped but
  otherwise unmodified in the `Rule Breach:` line, not parsed/reconstructed
- `test_critical_alert_only_fires_on_critical_state` — WARNING/OK states never call
  `notifier.send()` (existing behavior, must survive the port)
- `test_reentry_notice_escapes_underscore...` — N/A for this message (no identifier-shaped
  dynamic value carries an underscore here); the epic's standard underscore-survival regression
  test is not applicable and should not be force-added just for pattern-completeness

**Commit:** `feat(scripts): migrate proxy delta CRITICAL alert to MarkdownV2`

---

## ROLL-5 — Docs Close

**Files to change (targeted `Edit`, never `Write`):**
- `CONTEXT.md` — note the completed migration across all message types
- `DECISIONS.md` — close out the epic-level decision entry (from `backbone/` MD-5) with a note
  that rollout is complete
- `docs/plan/README.md` — mark `telegram-markdown-migration/` epic as shipped, matching the
  convention used for other archived epics in that table
- `TODOS.md` — final session log entry

**Also:** move `scratch/2026-08-07_ic_eod_audit_telegram_format.py` and
`scratch/2026-08-07_telegram_ic_comparison_format_repro.py` out of active scratch — they've
served their purpose as reference implementations now fully ported into `src/`/`scripts/`.
Per this project's scratch convention (dated throwaway files), leaving them in place is
harmless, but note in the commit message that they're now historical/superseded rather than
still-relevant references, so a future session doesn't mistake them for the current source of
truth.

**Commit:** `docs(notifications): close out Telegram Markdown migration epic`
