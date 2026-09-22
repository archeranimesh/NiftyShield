# Chart Core — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the epic `README.md` **Stories** table, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

No DB schema change anywhere in this story — no `schema.md`.

**Shared facts (verified 2026-09-09, do not re-derive):**

- `OptionLeg` — `src/models/options.py:20`, frozen Pydantic. Fields: `strike: Decimal`, `ltp: Decimal`, `bid: Decimal`, `ask: Decimal`, `oi: int`, `volume: int`, and `delta/gamma/theta/vega/iv:
  Decimal | None`. `iv` is annualised %, and a genuine Upstox `0.0` arrives as `Decimal("0")`, not `None`.
- `OptionChain` — `src/models/options.py:71`. `underlying_spot: Decimal`, `expiry: date`, `strikes: dict[Decimal, OptionChainStrike]`. No DTE field — callers compute `dte = (chain.expiry -
  market_today()).days`.
- `ICEntryMessage` — `src/notifications/ic_entry_message.py`. Carries `strategy_name`, `expiry_type`, `expiry`, `ivr`, `dte`, `spot`, `net_credit`, `mode`, and `legs: list[LegRow]`. `LegRow` is
  defined in `src/notifications/formatting.py`.
- `net_credit` per lot (points) is computed inline as `(short_put.mid + short_call.mid) - (long_put.mid + long_call.mid)` — `paper_ic_entry.py:783`, `paper_ic_entry_v2.py:701`.
- `IronCondorV1._compute_combined_pnl(market, positions) -> (combined_mark, entry_credit)` — `src/strategy/ic_nifty_v1.py:1244`; V2 has its own mirror. `combined_mark` is the cost to close (Σ short
  LTP − Σ long LTP). Used by both `paper_ic_snapshot.py:process_variant` (~line 442) and the close path.
- `LOT_SIZE = 65` (existing constant in the IC scripts / configs).
- `MarginSnapshot` — `src/paper/models.py:179`, frozen dataclass: `strategy_name`, `entry_date`, `required_margin: Decimal`, `final_margin: Decimal`, `captured_at`. Read via
  `PaperStore.get_margin_snapshot(strategy_name, entry_date) -> MarginSnapshot | None` (`src/paper/store.py:2183`). `final_margin` is the ROI denominator. Absent at entry.
- `TelegramNotifier` — `src/notifications/telegram.py`. Raw `aiohttp` POST to `https://api.telegram.org/bot{token}/sendMessage`, `parse_mode=MarkdownV2`, a per-session message budget (default 10).
  `TelegramGateway` — `src/notifications/telegram_gateway.py` — wraps it (`send_notification`, `send_plain_message`, `send_approval_request`).
- `_send_close_notification` — `src/strategy/ic_nifty_v1.py:777` and the `ic_nifty_v2.py` mirror. MarkdownV2 string via `self._notifier.send_notification(text)`; returns early if `self._notifier is
  None` or `closed_trades` is empty. `self._notifier` is a `TelegramGateway` injected at construction (`scripts/monitor_daemon.py`).

---

## PC-1 — Scaffold the epic folder

**Files to change / create:**
- `docs/plan/ic-payoff-charts/README.md`, `prompt.md` — epic index + router.
- `docs/plan/ic-payoff-charts/chart-core/{prompt,tasks,stories}.md` — this story.
- `docs/plan/ic-payoff-charts/chart-model-overlay/{prompt,tasks,stories}.md` — sub-story B.
- `TODOS.md` — add a pointer-only line under `## Feature Backlog`.
- `docs/plan/README.md` — add an epic entry under `## Active Epics`.

**What to implement:** copy the `_TEMPLATE/epic/` + two `_TEMPLATE/story/` shapes, fill them from the approved plan (`~/.claude/plans/is-it-possible-to-glowing-hollerith.md`). No `schema.md`. Run
`python -m scripts.dev.hooks.check_story_structure --all` (or the path mode) and confirm this folder is clean.

**Tests:** none (docs only). `check_story_structure.py` + `check_checkbox_consistency.py` must not flag the new folder.

**Commit:** `docs(plan): scaffold ic-payoff-charts epic (chart-core + chart-model-overlay)`

---

## PC-2 — `ICPayoff` + `compute_ic_payoff`

**Files to change / create:**
- `src/strategy/payoff.py` — new module (package `src/strategy/` already has `__init__.py`).
- `tests/unit/strategy/test_payoff.py` — new.

**Before any code (graph queries):**
- `get_code_snippet("OptionLeg")` and `get_code_snippet("LegRow")` — exact field names for the leg inputs.
- `get_code_snippet("ICEntryMessage")` — how legs/strikes are exposed at the entry call site.
- `search_code("LOT_SIZE")` — confirm the constant's home and value.

**What to implement:**

1. `@dataclass(frozen=True)` `ICPayoff` with `Decimal` fields: `short_put`, `long_put`, `short_call`, `long_call`, `net_credit` (per-lot points), `lot_size: int`, `max_profit`, `max_loss` (negative),
   `lower_breakeven`, `upper_breakeven`, `rr_ratio`.
2. `compute_ic_payoff(*, short_put, long_put, short_call, long_call, net_credit, lot_size)` `-> ICPayoff`:
   - `put_wing = short_put - long_put`, `call_wing = long_call - short_call`.
   - `max_profit = net_credit * lot_size`.
   - `max_loss = -(max(put_wing, call_wing) - net_credit) * lot_size` (the wider wing is the
     capital-at-risk side; a skewed IC risks more on one side).
   - `lower_breakeven = short_put - net_credit`, `upper_breakeven = short_call + net_credit`.
   - `rr_ratio = abs(max_profit / max_loss)` when `max_loss != 0`, else `Decimal("0")`.
   - Assert `long_put < short_put < short_call < long_call` (raise `ValueError` otherwise —
     a malformed IC is a programming error at the call site, not a runtime condition).
   - Google-style docstring, full type hints, `Decimal` only.
3. A small `from_legs(legs, net_credit, lot_size)` classmethod or free helper that pulls the four strikes + short/long role from a `list[LegRow]` (or the strategy's leg objects — pick whichever the
   call sites actually hold; document the choice).

**Tests:**
- `test_compute_ic_payoff_symmetric` — 23000/22800 put wing, 23500/23700 call wing, credit 120, lot 65 → assert max_profit 7800, max_loss −5200, breakevens 22880 / 23620, R:R 1.5.
- `test_compute_ic_payoff_skewed_wings` — unequal wings → max_loss uses the wider wing.
- `test_compute_ic_payoff_credit_ge_wing` — credit ≥ wing → max_loss ≥ 0 (degenerate but no crash, no divide error), breakevens still ordered.
- `test_compute_ic_payoff_bad_strike_order` — strikes out of order → `ValueError`.

**Commit:** `feat(strategy): add IC payoff math (ICPayoff, compute_ic_payoff)`

---

## PC-3 — `expiry_pnl_at` + `expiry_pnl_series`

**Files to change / create:**
- `src/strategy/payoff.py` — add two functions.
- `tests/unit/strategy/test_payoff.py` — add cases.

**What to implement:**

1. `expiry_pnl_at(payoff: ICPayoff, spot: Decimal) -> Decimal` — piecewise-linear IC P&L at expiry for a settlement `spot`: flat `max_profit` between the short strikes, sloping down through each wing,
   flat `max_loss` beyond each long strike. Return rupees (already `* lot_size`).
2. `expiry_pnl_series(payoff: ICPayoff, lo: Decimal, hi: Decimal, n: int) -> tuple[list[Decimal], list[Decimal]]` — `n` evenly spaced spot points in `[lo, hi]` and `expiry_pnl_at` for each. Used by
   the renderer for the payoff line. Default plotting range is the renderer's concern, not this function's.

**Tests:**
- `test_expiry_pnl_at_plateau` — spot midway between shorts → `max_profit`.
- `test_expiry_pnl_at_deep_otm` — spot below `long_put` → `max_loss`.
- `test_expiry_pnl_at_breakeven` — spot == `lower_breakeven` → ≈ 0 (within a paisa).
- `test_expiry_pnl_series_length` — `len(spots) == len(pnls) == n`, endpoints exact.

**Commit:** `feat(strategy): add IC expiry P&L point + series helpers`

---

## PC-4 — `render_expiry_payoff_png` (chart body) + matplotlib dep

**Files to change / create:**
- `src/notifications/payoff_chart.py` — new module.
- `requirements.txt` — add `matplotlib` (pin a recent stable major, e.g. `matplotlib>=3.8`).
- `tests/unit/notifications/test_payoff_chart.py` — new.

**Before any code:** `get_code_snippet("ICPayoff")` for the exact field list PC-2 shipped.

**What to implement:**

1. `import matplotlib; matplotlib.use("Agg")` at module top, before `pyplot`.
2. `render_expiry_payoff_png(payoff: ICPayoff, *, spot: Decimal | None = None, current_pnl: Decimal | None = None, dte: int | None = None, title: str = "") -> bytes`:
   - x-range: `short_put - 1.5*wing` … `short_call + 1.5*wing` (wing = wider of the two).
   - Payoff line from `expiry_pnl_series` (PC-3), ~200 points. Segment above P&L = 0 drawn
     green, below drawn red (two `plot` calls or a masked array).
   - Fill: green between the breakevens where P&L > 0; light-red/pink in the two loss zones.
   - Vertical dashed lines at `lower_breakeven`, `upper_breakeven`, `short_put`, `short_call`
     (label the breakevens).
   - If `spot` given: solid vertical line at `spot`, labelled `Nifty Spot : <spot>`.
   - If `current_pnl` given: a marker dot at `(spot, current_pnl)` (needs `spot` too),
     labelled like Stockmock's `Target P&L : <₹> (<%>)` where % is `current_pnl / margin`
     when available else `current_pnl / max_profit`.
   - Title: `title` or `f"{payoff ...}"` — caller passes strategy name + expiry + DTE.
   - Axis labels; y grid at 0. Render to `io.BytesIO` via `fig.savefig(buf, format="png",
     dpi=…, bbox_inches="tight")`; `plt.close(fig)`; return `buf.getvalue()`.
   - Theme-agnostic, single committed look (light background) — this is an image, not a web
     page.
3. Money / strike formatting for labels goes through the `FORMATTING.md` helpers in `src/notifications/formatting.py` (`format_money`, `format_strike`) — do not hand-format.
4. A structured log line per render (`payoff_chart.rendered`, with strategy + byte size) per `LOGGING.md`.

**Tests (Agg, no display):**
- `test_render_returns_png_bytes` — result starts with `b"\x89PNG"`, len > 1 KB.
- `test_render_minimal` — only `payoff` passed (no spot / pnl / dte) → still valid PNG.
- `test_render_full` — all optional args → valid PNG (smoke; no pixel assertions).
- `test_render_closes_figure` — `plt.get_fignums()` empty after the call.

**Commit:** `feat(notifications): render IC expiry payoff chart to PNG (matplotlib)`

---

## PC-5 — Stat strip

**Files to change / create:**
- `src/notifications/payoff_chart.py` — extend `render_expiry_payoff_png`.
- `tests/unit/notifications/test_payoff_chart.py` — add a case.

**What to implement:** a header/footer text band on the figure (Stockmock's top bar) showing `Max Profit`, `Max Loss`, `R:R` (from `payoff.rr_ratio`), `Net Credit` (`payoff.net_credit * lot_size`),
`Breakevens` as `<lower> (<-x%>) – <upper> (<+y%>)` where % is distance from `spot` (omit the % when `spot` is `None`), and `Est. Margin` **only** when a new optional `margin: Decimal | None = None`
arg is passed non-`None`. Use `fig.text` or a dedicated top axes. All values via the `FORMATTING.md` helpers.

**Tests:**
- `test_stat_strip_without_margin` — render with `margin=None`; assert the function still returns a PNG (no crash on the missing stat). Optionally assert via a text-capture hook that "Est. Margin" is
  not rendered — only if cheap; otherwise a smoke test is enough.
- `test_stat_strip_with_margin` — `margin` passed → PNG renders.

**Commit:** `feat(notifications): add stat strip to IC payoff chart`

---

## PC-6 — `TelegramNotifier.send_photo`

**Files to change / create:**
- `src/notifications/telegram.py` — add the method.
- `tests/unit/notifications/test_telegram_photo.py` — new.

**Before any code:** `get_code_snippet("TelegramNotifier")` — the exact `__init__` fields (token, chat id, budget counter name), how `send` builds its `aiohttp` request and handles non-200, and how
the budget is decremented / checked.

**What to implement:**

`async def send_photo(self, png: bytes, *, caption: str = "") -> None`:
- Budget check identical to `send` (if the per-session cap is hit, log and return — do not raise).
- `aiohttp.FormData`: `chat_id`, `photo` (the bytes, filename `payoff.png`, `content_type="image/png"`), and `caption` + `parse_mode="MarkdownV2"` when `caption`.
- POST to `https://api.telegram.org/bot{token}/sendPhoto`.
- Non-200 or a client exception → structured warning log (`telegram.send_photo.failed`), return normally. Never raise (non-fatal send contract, `src/notifications/CLAUDE.md`).
- Decrement the budget on a successful send, matching `send`.

**Tests (mock `aiohttp`, no network):**
- `test_send_photo_posts_multipart` — assert the URL ends `/sendPhoto` and the form carries `chat_id`, `photo`, `caption`.
- `test_send_photo_non_200_is_non_fatal` — mocked 400 → no raise, warning logged.
- `test_send_photo_respects_budget` — exhaust the budget → the call is a no-op, no POST.

**Commit:** `feat(notifications): add sendPhoto support to TelegramNotifier`

---

## PC-7 — `TelegramGateway.send_photo`

**Files to change / create:**
- `src/notifications/telegram_gateway.py` — add the method.
- `src/notifications/protocol.py` — add `send_photo` to `NotificationGateway` **only if** a type-checked caller (the close path) needs it — check with `trace_path` first.
- `tests/unit/notifications/test_telegram_photo.py` — add a case.

**Before any code:** `get_code_snippet("TelegramGateway")` and `get_code_snippet("NotificationGateway")`; `trace_path("_send_close_notification")` to see whether the strategy classes hold a
`TelegramGateway` concretely or the `NotificationGateway` protocol.

**What to implement:** `async def send_photo(self, png: bytes, caption: str = "") -> None` delegating to `self._notifier.send_photo(png, caption=caption)`, wrapped so a failure is logged and swallowed
(match `send_notification`'s error handling exactly).

**Tests:**
- `test_gateway_send_photo_delegates` — mock the notifier, assert the pass-through.
- `test_gateway_send_photo_non_fatal` — notifier raises → gateway does not.

**Commit:** `feat(notifications): add send_photo to TelegramGateway`

---

## PC-8 — Message-budget fix for multi-photo runs

**Files to change / create:**
- `src/notifications/telegram.py` **or** `scripts/strategies/ic/paper_ic_snapshot.py` — whichever is cleaner (decide after reading both).
- the matching test file.

**Before any code:** `get_code_snippet` for the budget field on `TelegramNotifier` and how `paper_ic_snapshot.py` constructs its `TelegramGateway` (~line 598). Confirm the real per-run message count:
up to `len(CONFIGS) + len(CONFIGS_V2)` variants → that many text messages + that many photos.

**What to implement:** the smallest change that guarantees the EOD run's text reports and their photos all send. Options, in preference order:
1. Count photos against a separate counter (or not at all) so text is never starved.
2. Let `paper_ic_snapshot.py` construct the notifier with an explicit higher budget sized to `2 * (len(CONFIGS) + len(CONFIGS_V2)) + slack`. Do not remove the budget mechanism — it exists to cap
   runaway sends.

**Tests:**
- `test_eod_run_sends_all_text_and_photos` — simulate N variants, assert 2N sends succeed.
- `test_budget_still_caps_runaway` — a pathological caller still hits a ceiling.

**Commit:** `fix(notifications): stop payoff photos starving the EOD text budget`

---

## PC-9 — Shared `build_and_send_ic_payoff` helper

**Files to change / create:**
- `src/notifications/payoff_chart.py` — add the async helper.
- `tests/unit/notifications/test_payoff_chart.py` — add cases.

**What to implement:**

```python
async def build_and_send_ic_payoff(
    gateway,                 # anything with async send_photo(png, caption="")
    *,
    short_put, long_put, short_call, long_call,   # Decimal strikes
    net_credit: Decimal,
    lot_size: int,
    spot: Decimal | None = None,
    dte: int | None = None,
    current_pnl: Decimal | None = None,
    margin: Decimal | None = None,
    title: str = "",
    caption: str = "",
) -> None:
```

- `compute_ic_payoff(...)` → `render_expiry_payoff_png(...)` → `await gateway.send_photo(png, caption=caption)`.
- Wrap the whole body so **nothing raises** into the caller: a compute error, a render error, or a send error is logged (`payoff_chart.send_failed`) and swallowed. This is the single choke point that
  keeps the feature non-fatal — the three call sites then need no try/except of their own.
- CPU-bound `render_*` call: acceptable inline for now (one small figure); note in a comment that if it ever shows up in the monitor tick it moves to a `ProcessPoolExecutor` per `CLAUDE.md` async
  rules.

**Tests:**
- `test_build_and_send_happy_path` — fake gateway records the call; assert `send_photo` got PNG bytes.
- `test_build_and_send_swallows_render_error` — monkeypatch `render_*` to raise → helper returns, gateway not called, warning logged.
- `test_build_and_send_swallows_send_error` — gateway `send_photo` raises → helper returns.

**Commit:** `feat(notifications): add build_and_send_ic_payoff wiring helper`

---

## PC-10 — Wire entry V1

**Files to change / create:**
- `scripts/strategies/ic/paper_ic_entry.py` — one additive call.

**Before any code:** `bash sed -n '740,800p' scripts/strategies/ic/paper_ic_entry.py` (the `net_credit` computation + `ICEntryMessage` build + Telegram send region). `trace_path` the send function.
Confirm where the four strikes and the fetched `OptionChain` (for `spot`, `dte`) are in scope.

**What to implement:** immediately after the existing `ICEntryMessage` text send, call `await build_and_send_ic_payoff(gateway, short_put=…, long_put=…, short_call=…, long_call=…,
net_credit=net_credit, lot_size=LOT_SIZE, spot=chain.underlying_spot, dte=(chain.expiry - market_today()).days, title=f"{strategy_name} · {expiry_type} · {dte}DTE")`. No `current_pnl` (fresh entry),
no `margin` (not captured yet). Guard on the gateway being non-`None` exactly as the text send does.

**Tests:** an entry-script test likely already exists — extend it (or add one) to assert `send_photo` is invoked once after the text send, against a fixture chain. No network.

**Commit:** `feat(scripts): attach payoff chart to IC v1 entry message`

---

## PC-11 — Wire entry V2

Identical to PC-10 for `scripts/strategies/ic/paper_ic_entry_v2.py` (`net_credit` at `:701`; V2 derives wing width rather than reading a config points value — take the strikes from the selected legs).
`bash sed -n '660,720p' scripts/strategies/ic/paper_ic_entry_v2.py` first.

**Commit:** `feat(scripts): attach payoff chart to IC v2 entry message`

---

## PC-12 — Wire EOD snapshot

**Files to change / create:**
- `scripts/strategies/ic/paper_ic_snapshot.py` — additive, inside `process_variant`.

**Before any code:** `bash sed -n '258,320p' scripts/strategies/ic/paper_ic_snapshot.py` and `bash sed -n '420,470p' …` (the `_compute_combined_pnl` call + `nifty_spot` + `dte` + the per-variant
report send at ~line 705). `get_code_snippet("IronCondorV1._compute_combined_pnl")` for the exact return tuple. Confirm `process_variant` returns `None` for a variant with no open position (skip the
photo then).

**What to implement:** after `await notifier.send_notification(r)` for a variant that has an open position, resolve the four leg strikes from the open positions (short/long put/call), compute
`current_pnl = (entry_credit - combined_mark) * LOT_SIZE`, fetch `margin = store.get_margin_snapshot(strategy_name, snap_date-or-entry_date)` (use the position's entry date — `get_margin_snapshot`
keys on `(strategy_name, entry_date)`), then `await build_and_send_ic_payoff(notifier, …, spot=nifty_spot, dte=dte, current_pnl=current_pnl, margin=margin.final_margin if margin else None, title=…)`.
One photo per open variant.

**Review:** `greeks-analyst` (touches `paper_ic_snapshot.py` + option-chain-derived values) — blocking.

**Tests:** extend the snapshot test — seed one open V1 variant + one variant with no position; assert exactly one `send_photo`, after the text report.

**Commit:** `feat(scripts): attach payoff chart per variant to IC EOD audit`

---

## PC-13 — Wire close V1

**Files to change / create:**
- `src/strategy/ic_nifty_v1.py` — additive, inside `_send_close_notification`.

**Before any code:** `get_code_snippet("IronCondorV1._send_close_notification")` and `get_code_snippet("IronCondorV1._compute_combined_pnl")`. Confirm what's in scope at the close call
(`ic_nifty_v1.py:737-777`): the `market`/`chain`, the closed trades, the `strategy_name`, `self._store`, `self._notifier`.

**What to implement:** after `await self._notifier.send_notification(text)` (and only when `self._notifier is not None` and trades were closed), compute the payoff from the position's four strikes +
entry credit, get `spot` from the chain in scope, `current_pnl` from the realized P&L already computed for the message (`net_pnl`), and `await self._notifier.send_photo(png)` via
`build_and_send_ic_payoff`. `dte` from `self._config` / the position expiry. Margin from `self._store.get_margin_snapshot` if available.

**Review:** `greeks-analyst` — blocking (strategy class, financial logic). Financial-logic commit → the **real** `@code-reviewer` subagent, not a persona.

**Tests:** extend the V1 close test — simulate a `CLOSE_FULL`, assert close text then a photo; `self._notifier = None` → no photo, no crash; empty `closed_trades` → nothing.

**Commit:** `feat(strategy): attach payoff chart to IC v1 close notification`

---

## PC-14 — Wire close V2

Identical to PC-13 for `src/strategy/ic_nifty_v2.py`'s `_send_close_notification` mirror. `get_code_snippet("IronCondorV2._send_close_notification")` first — V2's `__init__` arg order and combined-P&L
helper differ from V1.

**Review:** `greeks-analyst` — blocking; real `@code-reviewer`.

**Commit:** `feat(strategy): attach payoff chart to IC v2 close notification`

---

## PC-15 — Docs close

**Files to change / create (targeted `Edit` only, never `Write`):**
- `CONTEXT.md` — "What Exists": add `src/strategy/payoff.py` and `src/notifications/payoff_chart.py` one-liners; note `send_photo` on the Telegram wrappers.
- `DECISIONS.md` — an entry dated the commit day: matplotlib added as a runtime dep for Telegram payoff charts; charts are additive follow-up photo sends; the `chart-model-overlay/` split and its
  `greeks-bs-fallback/` dependency.
- `TODOS.md` — a Session Log line; update the `## Feature Backlog` entry's `next:` to the first `chart-model-overlay/` task (or mark `chart-core/` done).
- `docs/plan/README.md` — flip the `ic-payoff-charts/` epic row: `chart-core/` → ✅ with SHA.
- `docs/plan/ic-payoff-charts/README.md` — **Stories** table status column.
- Re-index the graph: `mcp__codebase-memory-mcp__index_repository`.

**Tests:** none (docs). Run `python -m pytest tests/unit/ --tb=no -q` once to confirm the story left the suite green.

**Commit:** `docs(plan): close chart-core (IC payoff charts on Telegram)`
