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
