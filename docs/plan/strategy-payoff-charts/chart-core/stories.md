# Chart Core — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the epic `README.md` **Stories** table, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

No DB schema change anywhere in this story — no `schema.md`.

**Shared facts (verified 2026-09-09; registry design added 2026-10-03, do not re-derive):**

- `OptionLeg` — `src/models/options.py:20`, frozen Pydantic. Fields: `strike: Decimal`, `ltp: Decimal`, `bid: Decimal`, `ask: Decimal`, `oi: int`, `volume: int`, and `delta/gamma/theta/vega/iv:
  Decimal | None`. `iv` is annualised %, and a genuine Upstox `0.0` arrives as `Decimal("0")`, not `None`.
- `OptionChain` — `src/models/options.py:71`. `underlying_spot: Decimal`, `expiry: date`, `strikes: dict[Decimal, OptionChainStrike]`. No DTE field — callers compute `dte = (chain.expiry -
  market_today()).days`.
- `PaperPosition` — `src/paper/models.py:115`, frozen. `strategy_name`, `leg_role`, `net_qty` (+long / −short), `avg_cost` (BUY avg), `avg_sell_price` (SELL avg), `instrument_key`, `entry_date`,
  `option_type: "PE"|"CE"|"FUT"|"EQ"|None` (resolved lazily via `InstrumentLookup`; `None` for flat legs and unresolvable keys). The strike is **not** a field — it comes from the instrument lookup.
- `LegSpec` — `src/strategy/protocol.py:12`: `instrument_key`, `action BUY|SELL`, `quantity`, `leg_role`, `price | None`.
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

**Design in one paragraph.** Payoff math is strategy-agnostic: a strategy is a list of `PayoffLeg`s (strike, kind, signed qty, entry price) and expiry P&L is the sum of per-leg `qty · (intrinsic −
entry)`. Which strategies get a chart is decided by an **explicit, opt-in registry** (`@register_payoff(name)` — PC-10): an unregistered strategy gets no chart and no error. Iron Condors register
themselves in this epic (PC-13); every future strategy adds one registration line (and an adapter only if the default positions-derived one is not enough). All senders go through one non-raising entry
point, `send_payoff_chart` (PC-11).

---

## PC-1 — Scaffold the epic folder

**Files to change / create:**
- `docs/plan/strategy-payoff-charts/README.md`, `prompt.md` — epic index + router.
- `docs/plan/strategy-payoff-charts/chart-core/{prompt,tasks,stories}.md` — this story.
- `docs/plan/strategy-payoff-charts/chart-model-overlay/{prompt,tasks,stories}.md` — sub-story B.
- `TODOS.md` — add a pointer-only line under `## Feature Backlog`.
- `docs/plan/README.md` — add an epic entry under `## Active Epics`.

**What to implement:** copy the `_TEMPLATE/epic/` + two `_TEMPLATE/story/` shapes, fill them from the approved plan. No `schema.md`. Run `python -m scripts.dev.hooks.check_story_structure --all` (or
the path mode) and confirm this folder is clean. (Epic originally scaffolded as `ic-payoff-charts/`; renamed and re-scoped to any strategy on 2026-10-03 — the PC-1 SHA predates the rename.)

**Tests:** none (docs only).

**Commit:** `docs(plan): scaffold strategy-payoff-charts epic (chart-core + chart-model-overlay)`

---

## PC-2 — `PayoffLeg`, `StrategyPayoff`, `compute_payoff`

**Files to change / create:**
- `src/strategy/payoff.py` — new module (package `src/strategy/` already has `__init__.py`).
- `tests/unit/strategy/test_payoff.py` — new.

**Before any code (graph queries):**
- `get_code_snippet("OptionLeg")`, `get_code_snippet("PaperPosition")` — exact field names for the leg inputs.
- `search_code("LOT_SIZE")` — confirm the constant's home and value.

**What to implement:**

1. `PayoffLeg` — `@dataclass(frozen=True)`: `kind: Literal["CE","PE","FUT","EQ"]`, `strike: Decimal | None` (`None` for FUT / EQ — the leg is linear in spot), `qty: int` (signed: + long, − short, in
   **units**, i.e. lots already multiplied by lot size), `entry_price: Decimal` (per unit), `role: str = ""` (free-form label, e.g. `short_put`; carried for the overlay's per-leg IV lookup).
2. `StrategyPayoff` — `@dataclass(frozen=True)`: `legs: tuple[PayoffLeg, ...]`, `net_premium: Decimal` (rupees; **+ credit / − debit**, = −Σ `qty · entry_price`), `max_profit: Decimal | None`,
   `max_loss: Decimal | None` (negative; `None` ⇒ **unbounded** on that side), `breakevens: tuple[Decimal, ...]` (ascending), `rr_ratio: Decimal | None` (`None` when either side is unbounded or
   `max_loss == 0`), `key_spots: tuple[Decimal, ...]` (every strike, ascending — used by the renderer for verticals and x-range).
3. `compute_payoff(legs: Sequence[PayoffLeg]) -> StrategyPayoff`:
   - Expiry P&L at settlement `S` is `Σ qty · (payoff_kind(S) − entry_price)` with `payoff_kind` = `max(S−K,0)` (CE), `max(K−S,0)` (PE), `S` (FUT / EQ). It is **piecewise linear** with kinks only at
     the option strikes.
   - Evaluate P&L at `S = 0`, at every strike, and read the **slope past the highest strike** (`Σ qty` over CE, FUT, EQ legs). Slope > 0 ⇒ `max_profit = None` (unbounded up); slope < 0 ⇒ `max_loss =
     None` (unbounded up-side loss). Downside is bounded by `S = 0` (spot cannot go negative), so `max_loss` / `max_profit` on that side come from the value at 0.
   - Otherwise `max_profit = max(values)`, `max_loss = min(values)` over `{0} ∪ strikes`; a bounded side where the extremum is ≥ 0 / ≤ 0 respectively still returns the number (a risk-free structure is
     legal, just unusual).
   - `breakevens`: linearly interpolate every sign change between consecutive evaluation points (including the segment past the top strike when its slope crosses zero). Exact zeros are included once.
   - Raise `ValueError` on an empty leg list or an option leg with `strike is None` — a malformed leg set is a programming error at the adapter, not a runtime condition.
   - `Decimal` only; Google-style docstring; no I/O.
4. Do **not** special-case any strategy. IC, CSP, CC, Collar and everything later must fall out of the same scan.

**Tests:**
- `test_compute_payoff_iron_condor` — long 22800 PE / short 23000 PE / short 23500 CE / long 23700 CE, credit 120, qty 65 → max_profit 7800, max_loss −5200, breakevens 22880 / 23620, R:R 1.5.
- `test_compute_payoff_skewed_wings` — unequal wings → max_loss uses the wider wing.
- `test_compute_payoff_naked_short_call_unbounded_loss` — single short CE → `max_loss is None`, `rr_ratio is None`, one breakeven.
- `test_compute_payoff_long_call_unbounded_profit` — single long CE → `max_profit is None`.
- `test_compute_payoff_empty_legs` / `test_compute_payoff_option_without_strike` — `ValueError`.
- `test_compute_payoff_zero_net_premium` — no crash, breakevens still ordered.

**Commit:** `feat(strategy): add strategy-agnostic expiry payoff math (compute_payoff)`

---

## PC-3 — `expiry_pnl_at` + `expiry_pnl_series`

**Files to change / create:**
- `src/strategy/payoff.py` — add two functions.
- `tests/unit/strategy/test_payoff.py` — add cases.

**What to implement:**

1. `expiry_pnl_at(payoff: StrategyPayoff, spot: Decimal) -> Decimal` — the per-leg sum from PC-2 evaluated at `spot`, in rupees. This is the single source of truth; `compute_payoff` should call it for
   its kink evaluation so the two cannot drift.
2. `expiry_pnl_series(payoff: StrategyPayoff, lo: Decimal, hi: Decimal, n: int) -> tuple[list[Decimal], list[Decimal]]` — `n` evenly spaced spots in `[lo, hi]` (endpoints exact) and `expiry_pnl_at`
   for each. Default plotting range is the renderer's concern, not this function's.

**Tests:**
- `test_expiry_pnl_at_plateau` — IC, spot midway between shorts → `max_profit`.
- `test_expiry_pnl_at_deep_otm` — spot below the long put → `max_loss`.
- `test_expiry_pnl_at_breakeven` — spot == a breakeven → ≈ 0 (within a paisa).
- `test_expiry_pnl_at_unbounded_tail` — naked short call far above the strike keeps falling linearly.
- `test_expiry_pnl_series_length` — `len(spots) == len(pnls) == n`, endpoints exact.

**Commit:** `feat(strategy): add expiry P&L point + series helpers for any strategy`

---

## PC-4 — Acceptance matrix

**Files to change / create:**
- `tests/unit/strategy/test_payoff_acceptance.py` — new (tests only).

**What to implement:** four named, hand-computed fixtures, each asserting `max_profit`, `max_loss`, `breakevens` and a spot-by-spot `expiry_pnl_at` spot-check. Put the arithmetic in a comment above
each fixture so a reader can verify it without running anything.

1. **Iron Condor** — the PC-2 symmetric case, plus a V2-style wide-wing case.
2. **Cash-Secured Put** — short 1 lot PE, no hedge: `max_profit = premium`, `max_loss = −(K − premium)·qty` (bounded by spot → 0), one breakeven `K − premium`.
3. **Covered Call** — long NiftyBees/FUT-equivalent EQ leg + short CE: `max_profit = (K − S0 + premium)·qty`, `max_loss` at spot 0, one breakeven; confirms the EQ/FUT linear leg.
4. **Collar** — EQ long + long PE + short CE: both sides bounded, two kinks, mixed leg kinds in one structure.

This task exists to prove the "any strategy" claim before any rendering or wiring is built on it. If a fixture needs a change to `compute_payoff`, fix PC-2/PC-3 in this commit and say so in the
message.

**Commit:** `test(strategy): acceptance matrix for generic payoff math (IC, CSP, CC, Collar)`

---

## PC-5 — `render_payoff_png` (chart body) + matplotlib dep

**Files to change / create:**
- `src/notifications/payoff_chart.py` — new module.
- `requirements.txt` — add `matplotlib` (pin a recent stable major, e.g. `matplotlib>=3.8`).
- `tests/unit/notifications/test_payoff_chart.py` — new.

**Before any code:** `get_code_snippet("StrategyPayoff")` for the exact field list PC-2 shipped.

**What to implement:**

1. `import matplotlib; matplotlib.use("Agg")` at module top, before `pyplot`.
2. `render_payoff_png(payoff: StrategyPayoff, *, spot: Decimal | None = None, current_pnl: Decimal | None = None, dte: int | None = None, margin: Decimal | None = None, title: str = "") -> bytes`:
   - x-range: from `min(key_spots) − 1.5·span` to `max(key_spots) + 1.5·span` where `span = max(key_spots) − min(key_spots)` (fallback `0.1·spot` / `0.1·strike` when there is a single strike). Include
     `spot` in the range when given. Never extend below 0.
   - Payoff line from `expiry_pnl_series` (PC-3), ~200 points. Segment above P&L = 0 drawn green, below drawn red (masked arrays).
   - Fill green where P&L > 0 and light-red where P&L < 0 — **derived from the series, not from the strategy shape**, so any structure (including unbounded ones) is handled.
   - Vertical dashed lines at every breakeven (labelled) and at each short-option strike (long strikes unlabelled, lighter).
   - If `spot` given: solid vertical line, labelled `Nifty Spot : <spot>`.
   - If `current_pnl` given: a marker dot at `(spot, current_pnl)` (needs `spot` too), labelled like Stockmock's `Target P&L : <₹> (<%>)` where % is `current_pnl / margin` when available else
     `current_pnl / max_profit` (omit the % when `max_profit is None`).
   - Title: `title` as passed — the caller supplies strategy name + expiry + DTE.
   - Axis labels; y grid at 0. Render to `io.BytesIO` via `fig.savefig(buf, format="png", dpi=…, bbox_inches="tight")`; `plt.close(fig)`; return `buf.getvalue()`.
   - Theme-agnostic, single committed look (light background) — this is an image, not a web page.
3. Money / strike formatting for labels goes through the `FORMATTING.md` helpers in `src/notifications/formatting.py` (`format_money`, `format_strike`) — do not hand-format.
4. A structured log line per render (`payoff_chart.rendered`, with title + byte size) per `LOGGING.md`.

**Tests (Agg, no display):**
- `test_render_returns_png_bytes` — IC payoff → starts with `b"\x89PNG"`, len > 1 KB.
- `test_render_minimal` — only `payoff` passed → still valid PNG.
- `test_render_unbounded_structure` — naked short call payoff → valid PNG (no crash on `max_loss is None`).
- `test_render_full` — all optional args → valid PNG (smoke; no pixel assertions).
- `test_render_closes_figure` — `plt.get_fignums()` empty after the call.

**Commit:** `feat(notifications): render strategy expiry payoff chart to PNG (matplotlib)`

---

## PC-6 — Stat strip

**Files to change / create:**
- `src/notifications/payoff_chart.py` — extend `render_payoff_png`.
- `tests/unit/notifications/test_payoff_chart.py` — add cases.

**What to implement:** a header/footer text band (Stockmock's top bar) showing `Max Profit`, `Max Loss`, `R:R` (from `payoff.rr_ratio`), `Net Credit` or `Net Debit` (sign of `net_premium`),
`Breakevens` as `<b1> (<±x%>) – <b2> (<±y%>)` (one entry per breakeven, any count; % is distance from `spot`, omitted when `spot` is `None`), and `Est. Margin` **only** when `margin` is non-`None`. A
`None` max profit / max loss renders as `Unlimited`; a `None` R:R is omitted. Use `fig.text` or a dedicated top axes. All values via the `FORMATTING.md` helpers.

**Tests:**
- `test_stat_strip_without_margin` — `margin=None` → still a PNG.
- `test_stat_strip_with_margin` — `margin` passed → PNG renders.
- `test_stat_strip_unbounded_side` — naked short call → renders `Unlimited`, no crash (assert via a text-capture hook only if cheap; otherwise smoke).

**Commit:** `feat(notifications): add stat strip to strategy payoff chart`

---

## PC-7 — `TelegramNotifier.send_photo`

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

## PC-8 — `TelegramGateway.send_photo`

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

## PC-9 — Message-budget fix for multi-photo runs

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

## PC-10 — Payoff registry (opt-in) + default adapter

**Files to change / create:**
- `src/strategy/payoff_registry.py` — new.
- `tests/unit/strategy/test_payoff_registry.py` — new.

**Before any code:** `get_code_snippet("PaperPosition")`, `search_graph("InstrumentLookup")` and `get_code_snippet` on its strike-resolving method — the default adapter needs a strike per option
position. Confirm what a closed (flat) position and an unresolvable key look like (`option_type is None`).

**What to implement:**

1. `PayoffContext` — frozen dataclass handed to an adapter: `positions: Sequence[PaperPosition]`, `spot: Decimal | None`, `lot_size: int`, `strategy_name: str`, plus a free-form `extras: Mapping[str,
   object] = {}` for strategy-specific inputs.
2. `PayoffAdapter` — `Protocol`: `def legs(self, ctx: PayoffContext) -> list[PayoffLeg]` (required) and an optional `def title(self, ctx: PayoffContext) -> str`.
3. `register_payoff(name: str, adapter: PayoffAdapter | None = None)` — usable as a decorator on a strategy class (`@register_payoff("csp_nifty_v1")`, default adapter) or called directly with an
   adapter instance. `ValueError` on a duplicate name (a second registration is a bug, never a silent override).
4. `get_adapter(name: str) -> PayoffAdapter | None` — `None` for an unregistered strategy. **Opt-in is the contract:** nothing is registered implicitly.
5. `DefaultPositionAdapter` — builds one `PayoffLeg` per non-flat position: `kind = position.option_type`, `qty = position.net_qty` (already signed), `entry_price = avg_sell_price` for shorts /
   `avg_cost` for longs, `strike` from the instrument lookup (`None` for EQ / FUT). Positions with `option_type is None` or `net_qty == 0` are skipped and logged at debug; if that leaves no legs the
   adapter returns `[]` (the entry point then sends nothing).
6. Module docstring carries the three-line "how to register a strategy" recipe — PC-19 copies it into `src/strategy/CLAUDE.md`.

**Tests:**
- `test_register_and_get` / `test_get_unregistered_returns_none` / `test_duplicate_registration_raises`.
- `test_default_adapter_builds_legs` — fixture positions (short PE, short CE, long PE, long CE) → four `PayoffLeg`s with signed qty and correct entry price per side.
- `test_default_adapter_skips_flat_and_unresolved` — flat and `option_type=None` positions dropped, no raise.
- `test_decorator_registers_class` — decorator form returns the class unchanged.

**Commit:** `feat(strategy): add opt-in payoff registry with default positions adapter`

---

## PC-11 — `send_payoff_chart` entry point

**Files to change / create:**
- `src/notifications/payoff_chart.py` — add the async function.
- `tests/unit/notifications/test_payoff_chart.py` — add cases.

**What to implement:**

```python
async def send_payoff_chart(
    gateway,                 # anything with async send_photo(png, caption="")
    strategy_name: str,
    ctx: PayoffContext,
    *,
    dte: int | None = None,
    current_pnl: Decimal | None = None,
    margin: Decimal | None = None,
    title: str = "",
    caption: str = "",
) -> None:
```

- `get_adapter(strategy_name)`; `None` → log at debug and return (an unregistered strategy is normal, not an error).
- `adapter.legs(ctx)` → `compute_payoff` → `render_payoff_png(..., spot=ctx.spot, ...)` → `await gateway.send_photo(png, caption=caption)`. Empty legs → return without sending.
- Wrap the whole body so **nothing raises** into the caller: a compute error, a render error, or a send error is logged (`payoff_chart.send_failed`) and swallowed. This is the single choke point that
  keeps the feature non-fatal — every call site then needs no try/except of its own.
- CPU-bound `render_*` call: acceptable inline for now (one small figure); note in a comment that if it ever shows up in the monitor tick it moves to a `ProcessPoolExecutor` per `CLAUDE.md` async
  rules. Wrap the gateway await in `asyncio.wait_for` (explicit timeout, per `CLAUDE.md` async rules).

**Tests:**
- `test_send_happy_path` — registered fake adapter + fake gateway; assert `send_photo` got PNG bytes.
- `test_send_unregistered_is_noop` — gateway not called, no raise.
- `test_send_empty_legs_is_noop`.
- `test_send_swallows_render_error` — monkeypatch `render_payoff_png` to raise → returns, gateway not called, warning logged.
- `test_send_swallows_send_error` — gateway `send_photo` raises → returns.

**Commit:** `feat(notifications): add send_payoff_chart non-raising entry point`

---

## PC-12 — Hook audit (read-only)

**Files to change / create:** none in `src/` or `scripts/`. Append a **Findings** block under this heading in this file, and adjust the PC-14..18 specs below if the finding changes them.

**Question to answer:** is there a single choke point every strategy already passes through at *open*, *EOD* and *close* — so that registering a strategy is enough and no per-script wiring is needed?
Candidates to read via the graph (`trace_path`, `search_graph`): `PaperExecutor` (open / close persistence), `StrategyMonitor` action dispatch (`apply_action`), the shared close-confirmation renderer
in `src/notifications/exit_message.py`, the shared entry renderer `entry_message.py`, and `src/reporting/eod_pt_summary.py` (cross-strategy EOD).

**Decision to record:** per lifecycle point (open / EOD / close), either "central hook = X, one wiring edit covers every registered strategy" or "no central hook, wire per call site". PC-14..18 are
written for the per-call-site fallback; if a central hook exists for a point, collapse that point's tasks into one wiring task there and say so here.

**Commit:** `docs(plan): record payoff-chart hook audit findings`

---

## PC-13 — IC adapter + explicit registration

**Files to change / create:**
- `src/strategy/ic_nifty_v1.py`, `src/strategy/ic_nifty_v2.py` — an adapter and `register_payoff(...)` call per strategy (module level or decorator).
- `tests/unit/strategy/test_ic_payoff_adapter.py` — new.

**Before any code:** `get_code_snippet("IronCondorV1._compute_combined_pnl")` and the V2 mirror; check what the strategy `name` strings are (`search_code('strategy_name =')` in both files) — the
registry key must equal the `strategy_name` the call sites pass.

**What to implement:** IC is the first (and, in this epic, only) registered strategy. If the `DefaultPositionAdapter` reproduces the four IC legs correctly, register with the default and add no
adapter code (that is the point of the design); otherwise write a thin IC adapter that takes the four strikes + entry credit from the V1 / V2 position sets. Add a `title()` producing `<strategy> ·
<expiry_type> · <dte>DTE`. Registering is explicit and lives next to the strategy class, which is the template future strategies copy.

**Review:** `greeks-analyst` — blocking (strategy classes, IC credit definition).

**Tests:**
- `test_ic_v1_registered` / `test_ic_v2_registered` — `get_adapter` resolves both names.
- `test_ic_adapter_legs_match_entry_strikes` — fixture V1 and V2 position sets → four legs, correct signs, `net_premium` equals the entry credit × lot size.

**Commit:** `feat(strategy): register iron condors for payoff charts`

---

## PC-14 — Wire entry V1

**Files to change / create:**
- `scripts/strategies/ic/paper_ic_entry.py` — one additive call.

**Before any code:** `bash sed -n '740,800p' scripts/strategies/ic/paper_ic_entry.py` (the `net_credit` computation + `ICEntryMessage` build + Telegram send region). `trace_path` the send function.
Confirm where the fetched `OptionChain` (for `spot`, `dte`) and the opened positions are in scope; honour the PC-12 findings.

**What to implement:** immediately after the existing `ICEntryMessage` text send, `await send_payoff_chart(gateway, strategy_name, PayoffContext(positions=…, spot=chain.underlying_spot,
lot_size=LOT_SIZE, strategy_name=…), dte=(chain.expiry - market_today()).days)`. No `current_pnl` (fresh entry), no `margin` (not captured yet). Guard on the gateway being non-`None` exactly as the
text send does.

**Tests:** an entry-script test likely already exists — extend it (or add one) to assert `send_photo` is invoked once after the text send, against a fixture chain. No network.

**Commit:** `feat(scripts): attach payoff chart to IC v1 entry message`

---

## PC-15 — Wire entry V2

Identical to PC-14 for `scripts/strategies/ic/paper_ic_entry_v2.py` (`net_credit` at `:701`; V2 derives wing width rather than reading a config points value — the legs come from the adapter, so no
strike plumbing is needed). `bash sed -n '660,720p' scripts/strategies/ic/paper_ic_entry_v2.py` first.

**Commit:** `feat(scripts): attach payoff chart to IC v2 entry message`

---

## PC-16 — Wire EOD snapshot

**Files to change / create:**
- `scripts/strategies/ic/paper_ic_snapshot.py` — additive, inside `process_variant`.

**Before any code:** `bash sed -n '258,320p' scripts/strategies/ic/paper_ic_snapshot.py` and `bash sed -n '420,470p' …` (the `_compute_combined_pnl` call + `nifty_spot` + `dte` + the per-variant
report send at ~line 705). `get_code_snippet("IronCondorV1._compute_combined_pnl")` for the exact return tuple. Confirm `process_variant` returns `None` for a variant with no open position (skip the
photo then).

**What to implement:** after `await notifier.send_notification(r)` for a variant that has an open position, compute `current_pnl = (entry_credit - combined_mark) * LOT_SIZE`, fetch `margin =
store.get_margin_snapshot(strategy_name, entry_date)` (use the position's entry date — `get_margin_snapshot` keys on `(strategy_name, entry_date)`), then `await send_payoff_chart(notifier,
strategy_name, ctx, dte=dte, current_pnl=current_pnl, margin=margin.final_margin if margin else None, title=…)`. One photo per open variant.

**Review:** `greeks-analyst` (touches `paper_ic_snapshot.py` + option-chain-derived values) — blocking.

**Tests:** extend the snapshot test — seed one open V1 variant + one variant with no position; assert exactly one `send_photo`, after the text report.

**Commit:** `feat(scripts): attach payoff chart per variant to IC EOD audit`

---

## PC-17 — Wire close V1

**Files to change / create:**
- `src/strategy/ic_nifty_v1.py` — additive, inside `_send_close_notification`.

**Before any code:** `get_code_snippet("IronCondorV1._send_close_notification")` and `get_code_snippet("IronCondorV1._compute_combined_pnl")`. Confirm what's in scope at the close call
(`ic_nifty_v1.py:737-777`): the `market`/`chain`, the closed trades, the `strategy_name`, `self._store`, `self._notifier`. Note the positions are **already flat** at this point — the context needs the
pre-close positions (reconstruct from the closed trades or capture before close); decide from the code and record the choice in the commit body.

**What to implement:** after `await self._notifier.send_notification(text)` (and only when `self._notifier is not None` and trades were closed), `await send_payoff_chart(self._notifier, self.name,
ctx, dte=…, current_pnl=net_pnl)` with `spot` from the chain in scope and `current_pnl` from the realized P&L already computed for the message. Margin from `self._store.get_margin_snapshot` if
available.

**Review:** `greeks-analyst` — blocking (strategy class, financial logic). Financial-logic commit → the **real** `@code-reviewer` subagent, not a persona.

**Tests:** extend the V1 close test — simulate a `CLOSE_FULL`, assert close text then a photo; `self._notifier = None` → no photo, no crash; empty `closed_trades` → nothing.

**Commit:** `feat(strategy): attach payoff chart to IC v1 close notification`

---

## PC-18 — Wire close V2

Identical to PC-17 for `src/strategy/ic_nifty_v2.py`'s `_send_close_notification` mirror. `get_code_snippet("IronCondorV2._send_close_notification")` first — V2's `__init__` arg order and combined-P&L
helper differ from V1.

**Review:** `greeks-analyst` — blocking; real `@code-reviewer`.

**Commit:** `feat(strategy): attach payoff chart to IC v2 close notification`

---

## PC-19 — Docs close

**Files to change / create (targeted `Edit` only, never `Write`):**
- `CONTEXT.md` — "What Exists": add `src/strategy/payoff.py`, `src/strategy/payoff_registry.py` and `src/notifications/payoff_chart.py` one-liners; note `send_photo` on the Telegram wrappers.
- `src/strategy/CLAUDE.md` — a "Registering a strategy for payoff charts" recipe (copy of the `payoff_registry.py` module docstring): the one-line `@register_payoff("<strategy_name>")`, when a custom
  `PayoffAdapter` is needed, and that registration is opt-in.
- `DECISIONS.md` — an entry dated the commit day: matplotlib added as a runtime dep for Telegram payoff charts; charts are additive follow-up photo sends; payoff math is strategy-agnostic with an
  opt-in registry; the `chart-model-overlay/` split and its `greeks-bs-fallback/` dependency.
- `TODOS.md` — a Session Log line; update the `## Feature Backlog` entry's `next:` to the first `chart-model-overlay/` task (or mark `chart-core/` done).
- `docs/plan/README.md` — flip the `strategy-payoff-charts/` epic row: `chart-core/` → ✅ with SHA.
- `docs/plan/strategy-payoff-charts/README.md` — **Stories** table status column.
- Re-index the graph: `mcp__codebase-memory-mcp__index_repository`.

**Tests:** none (docs). Run `python -m pytest tests/unit/ --tb=no -q` once to confirm the story left the suite green.

**Commit:** `docs(plan): close chart-core (strategy payoff charts on Telegram)`
