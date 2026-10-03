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
entry)`. The math, registry and error types live in a **leaf package `src/payoff/`** that imports nothing from `src.strategy` or `src.notifications` (the dependency rule — enforced by a test in PC-2).
Which strategies get a chart is decided by an **explicit, opt-in registry** (`@register_payoff(name)` — PC-10): a strategy that is not registered gets no chart, and the sender logs a *warning* (wired
sites are expected to be registered, so silence would hide a wiring bug). Registrations are collected in **one explicit module, `src/strategy/payoff_registrations.py`** (PC-13), imported by every
wired site — never as an import side effect of a strategy module. All senders go through one non-raising entry point, `send_payoff_chart` (PC-11), which depends on a `PhotoSender` Protocol, not a
concrete gateway.

**Dependency rule (one-directional, no cycles):** `src.payoff` ← `src.notifications.payoff_chart` ← wired call sites; `src.payoff` ← `src.strategy.payoff_registrations` ← wired call sites.
`src.payoff` depends on nothing project-internal except `src.paper.models.PaperPosition` *types* under `TYPE_CHECKING` only (or on a local `Protocol` mirroring its fields — decide in PC-10).

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
- `src/payoff/__init__.py` — new leaf package (one-line comment is enough; required so the graph indexes it).
- `src/payoff/core.py` — new: `PayoffLeg`, `StrategyPayoff`, `compute_payoff`.
- `src/payoff/errors.py` — new: `PayoffError` (base), `InvalidLegsError(PayoffError, ValueError)`, `DuplicateRegistrationError(PayoffError)`, `RenderError(PayoffError)`, `SendError(PayoffError)` — the
  module-boundary exception hierarchy.
- `tests/unit/payoff/__init__.py`, `tests/unit/payoff/test_core.py`, `tests/unit/payoff/test_import_boundary.py` — new.

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
   - Raise `InvalidLegsError` on an empty leg list or an option leg with `strike is None` — a malformed leg set is a programming error at the adapter, not a runtime condition.
   - `Decimal` only; Google-style docstring; no I/O.
4. Do **not** special-case any strategy. IC, CSP, CC, Collar and everything later must fall out of the same scan.

**Tests:**
- `test_compute_payoff_iron_condor` — long 22800 PE / short 23000 PE / short 23500 CE / long 23700 CE, credit 120, qty 65 → max_profit 7800, max_loss −5200, breakevens 22880 / 23620, R:R 1.5.
- `test_compute_payoff_skewed_wings` — unequal wings → max_loss uses the wider wing.
- `test_compute_payoff_naked_short_call_unbounded_loss` — single short CE → `max_loss is None`, `rr_ratio is None`, one breakeven.
- `test_compute_payoff_long_call_unbounded_profit` — single long CE → `max_profit is None`.
- `test_compute_payoff_empty_legs` / `test_compute_payoff_option_without_strike` — `InvalidLegsError`.
- `test_payoff_package_import_boundary` — AST-walk every module under `src/payoff/` and assert no import of `src.strategy` or `src.notifications` (the automated dependency-direction check; runs
  offline).
- `test_compute_payoff_zero_net_premium` — no crash, breakevens still ordered.

**Commit:** `feat(strategy): add strategy-agnostic expiry payoff math (compute_payoff)`

---

## PC-3 — `expiry_pnl_at` + `expiry_pnl_series`

**Files to change / create:**
- `src/payoff/core.py` — add two functions.
- `tests/unit/payoff/test_core.py` — add cases.

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
- `tests/unit/payoff/test_acceptance.py` — new (tests only).

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

1. Build the figure with the object-oriented API — `from matplotlib.figure import Figure` + `FigureCanvasAgg` — **not `pyplot`**. `pyplot` keeps process-global figure state and is not thread-safe, and
   the render is CPU-bound work that must not block the event loop (see PC-11); a `Figure` owned by the call is safe to render off-thread and needs no `plt.close`.
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
   - Axis labels; y grid at 0. Render to `io.BytesIO` via `fig.savefig(buf, format="png", dpi=…, bbox_inches="tight")`; return `buf.getvalue()`. Wrap any matplotlib failure in `RenderError` (never
     leak a matplotlib exception type).
   - Theme-agnostic, single committed look (light background) — this is an image, not a web page.
3. Money / strike formatting for labels goes through the `FORMATTING.md` helpers in `src/notifications/formatting.py` (`format_money`, `format_strike`) — do not hand-format.
4. A structured log line per render (`payoff_chart.rendered`, with title + byte size) per `LOGGING.md`.

**Tests (Agg, no display):**
- `test_render_returns_png_bytes` — IC payoff → starts with `b"\x89PNG"`, len > 1 KB.
- `test_render_minimal` — only `payoff` passed → still valid PNG.
- `test_render_unbounded_structure` — naked short call payoff → valid PNG (no crash on `max_loss is None`).
- `test_render_full` — all optional args → valid PNG (smoke; no pixel assertions).
- `test_render_does_not_touch_pyplot` — `matplotlib.pyplot` figure registry stays empty after the call (`'matplotlib.pyplot' not in sys.modules` or `plt.get_fignums() == []`).

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
- `src/payoff/registry.py` — new: `PayoffContext`, the adapter Protocols, `PayoffRegistry`, module-level default registry + `register_payoff` / `get_adapter`, `DefaultPositionAdapter`.
- `tests/unit/payoff/test_registry.py` — new.

**Before any code:** `get_code_snippet("PaperPosition")`, `search_graph("InstrumentLookup")` and `get_code_snippet` on its strike-resolving method — the default adapter needs a strike per option
position. Confirm what a closed (flat) position and an unresolvable key look like (`option_type is None`). Decide how `src/payoff` refers to `PaperPosition` without importing `src.paper` at runtime
(`TYPE_CHECKING` import, or a small local `PositionLike` Protocol with the five fields it reads) — the leaf rule in the header forbids a runtime dependency on strategy / notifications and prefers none
on paper.

**What to implement:**

1. `PayoffContext` — frozen dataclass handed to an adapter: `positions: Sequence[PositionLike]`, `spot: Decimal | None`, `lot_size: int`, `strategy_name: str`, plus `extras: Mapping[str, object]`
   (default empty) for strategy-specific inputs.
2. Adapter Protocols, split by capability (ISP — no adapter implements a method it does not need):
   - `PayoffAdapter` — required: `def legs(self, ctx: PayoffContext) -> list[PayoffLeg]`.
   - `HasTitle` — `def title(self, ctx: PayoffContext) -> str`.
   - (`MarketAware` for the overlay is added by `chart-model-overlay/` MO-7 as a third small Protocol.) Callers detect optional capabilities with `isinstance(adapter, HasTitle)`
     (`@runtime_checkable`), never `hasattr` or a fat base class.
3. `PayoffRegistry` — a small class holding `dict[str, PayoffAdapter]` with `register(name, adapter)` (raises `DuplicateRegistrationError(PayoffError)` on a duplicate name; a second registration is a
   bug, never a silent override), `get(name) -> PayoffAdapter | None`, and `clear()` for test isolation. A module-level `DEFAULT_REGISTRY` plus thin `register_payoff(name, adapter=None)` (decorator or
   direct call) and `get_adapter(name)` wrappers keep the one-line registration ergonomics. **Consumers accept a `PayoffRegistry` parameter that defaults to `DEFAULT_REGISTRY`** (DIP — tests inject a
   fresh registry instead of mutating global state).
4. `DefaultPositionAdapter(lookup)` — **the instrument lookup is injected** through its constructor (a `StrikeResolver` Protocol: `def strike_for(self, instrument_key: str) -> Decimal | None`), never
   constructed inside. It builds one `PayoffLeg` per non-flat position: `kind = position.option_type`, `qty = position.net_qty` (already signed), `entry_price = avg_sell_price` for shorts / `avg_cost`
   for longs, `strike` from the resolver (`None` for EQ / FUT). Positions with `net_qty == 0` are skipped. A **partially resolved set aborts** — if any non-flat option position has `option_type is
   None` or no resolvable strike, raise `InvalidLegsError` (a payoff drawn from a subset of the legs would mislead); `send_payoff_chart` logs it and sends nothing.
5. Module docstring carries the three-line "how to register a strategy" recipe — PC-19 copies it into `src/strategy/CLAUDE.md`.

**Tests:**
- `test_register_and_get` / `test_get_unregistered_returns_none` / `test_duplicate_registration_raises`.
- `test_injected_registry_is_isolated` — a fresh `PayoffRegistry` does not see `DEFAULT_REGISTRY` entries.
- `test_default_adapter_builds_legs` — fixture positions (short PE, short CE, long PE, long CE) with a fake resolver → four `PayoffLeg`s with signed qty and correct entry price per side.
- `test_default_adapter_skips_flat` — flat positions dropped.
- `test_default_adapter_partial_resolution_raises` — one unresolved option leg → `InvalidLegsError`, no partial chart.
- `test_title_capability_detected` — adapter with `title()` satisfies `HasTitle`; one without does not.
- `test_decorator_registers_class` — decorator form returns the class unchanged.

**Commit:** `feat(payoff): add opt-in payoff registry with injected default adapter`

---

## PC-11 — `send_payoff_chart` entry point

**Files to change / create:**
- `src/notifications/payoff_chart.py` — add the async function and the `PhotoSender` Protocol.
- `tests/unit/notifications/test_payoff_chart.py` — add cases.

**What to implement:**

```python
class PhotoSender(Protocol):
    async def send_photo(self, png: bytes, caption: str = "") -> None: ...

async def send_payoff_chart(
    sender: PhotoSender,
    strategy_name: str,
    ctx: PayoffContext,
    *,
    registry: PayoffRegistry = DEFAULT_REGISTRY,
    dte: int | None = None,
    current_pnl: Decimal | None = None,
    margin: Decimal | None = None,
    caption: str = "",
) -> None:
```

- `registry.get(strategy_name)`; `None` → **log a warning** (`payoff_chart.unregistered`, with the strategy name) and return. Every wired call site is expected to be registered; silence would hide a
  wiring bug such as a missing `payoff_registrations` import.
- `adapter.legs(ctx)` → `compute_payoff` → title from `adapter.title(ctx)` when `isinstance(adapter, HasTitle)` → render → `await sender.send_photo(png, caption=caption)`. Empty legs → return without
  sending.
- **Render off the event loop.** `render_payoff_png` is CPU-bound (~0.5–1 s with the first-import cost) and this runs inside the 90-second `StrategyMonitor` tick: `await
  asyncio.to_thread(render_payoff_png, ...)` (safe because PC-5 uses the `Figure` API, not `pyplot`). `asyncio.to_thread` copies the current `contextvars` context, so the structlog correlation id
  carries into the worker (verified by a test below). If measurement ever shows the GIL contention matters, move to a `ProcessPoolExecutor` per `CLAUDE.md` async rules — note this in a comment. Wrap
  both the render and the send in `asyncio.wait_for` with explicit timeouts.
- Exception handling: catch `PayoffError` (expected: bad legs, render, send) and log at warning; catch bare `Exception` once at the outermost boundary, log with `logger.exception`
  (`payoff_chart.unexpected_failure`), and swallow. **Nothing raises into the caller.** This is the single choke point that keeps the feature non-fatal — call sites need no try/except of their own.

**Tests:**
- `test_send_happy_path` — injected fresh registry + fake adapter + fake `PhotoSender`; assert `send_photo` got PNG bytes.
- `test_send_unregistered_warns_and_noops` — gateway not called, no raise, warning logged.
- `test_send_empty_legs_is_noop` and `test_send_unresolved_legs_is_noop` (adapter raises `InvalidLegsError`).
- `test_send_swallows_render_error` — monkeypatch `render_payoff_png` to raise → returns, sender not called, warning logged.
- `test_send_swallows_send_error` — sender `send_photo` raises → returns.
- `test_send_times_out_cleanly` — a sender that never completes → returns after the timeout.
- `test_correlation_context_reaches_render_thread` — bind a structlog contextvar, assert a log line emitted inside the render worker still carries it.

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

## PC-13 — IC registration module (`payoff_registrations.py`)

**Files to change / create:**
- `src/strategy/payoff_registrations.py` — new: the **single explicit place** where strategies opt in, plus an idempotent `ensure_registered(registry=DEFAULT_REGISTRY)`.
- `tests/unit/strategy/test_payoff_registrations.py` — new.

**Before any code:** `get_code_snippet("IronCondorV1._compute_combined_pnl")` and the V2 mirror; check what the strategy `name` strings are (`search_code('strategy_name =')` in both files) — the
registry key must equal the `strategy_name` the call sites pass. Confirm whether the default positions adapter reproduces the four IC legs (it should — that is the point of the design).

**What to implement:** `ensure_registered()` registers `iron_condor_v1` and `iron_condor_v2` (default adapter if sufficient, else a thin IC adapter co-located here that takes strikes + entry credit
from the V1 / V2 position sets; add a `title()` producing `<strategy> · <expiry_type> · <dte>DTE`). It is idempotent (guards the duplicate-registration error) so every wired site can call it without
ordering concerns. **Registration is never an import side effect of a strategy module**: `src/strategy/__init__.py` imports `IronCondorV1` but not `IronCondorV2`, and the entry scripts import neither
strategy class, so import-time registration would silently skip V2 at entry. Each wired site (PC-14..18) calls `ensure_registered()` explicitly. This module is also the template future strategies
copy: one `registry.register("<strategy_name>")` line inside `ensure_registered`.

**Review:** `greeks-analyst` — blocking (IC credit definition).

**Tests:**
- `test_ensure_registered_resolves_ic_v1_and_v2` — fresh registry, both names resolve.
- `test_ensure_registered_is_idempotent` — calling twice does not raise.
- `test_every_wired_strategy_name_is_registered` — a parametrised list of the strategy names the wired sites pass (the single source of truth for PC-14..18) all resolve; adding a wired site without a
  registration fails this test.
- `test_ic_adapter_legs_match_entry_strikes` — fixture V1 and V2 position sets → four legs, correct signs, `net_premium` equals the entry credit × lot size.

**Commit:** `feat(strategy): register iron condors for payoff charts explicitly`

---

## PC-14 — Wire entry V1

**Files to change / create:**
- `scripts/strategies/ic/paper_ic_entry.py` — one additive call.

**Before any code:** `bash sed -n '740,800p' scripts/strategies/ic/paper_ic_entry.py` (the `net_credit` computation + `ICEntryMessage` build + Telegram send region). `trace_path` the send function.
Confirm where the fetched `OptionChain` (for `spot`, `dte`) and the opened positions are in scope; honour the PC-12 findings. Call `ensure_registered()` (PC-13) before sending; build the
`PayoffContext` with the injected strike resolver.

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
- `CONTEXT.md` — "What Exists": add `src/payoff/` (`core.py`, `registry.py`, `errors.py`), `src/strategy/payoff_registrations.py` and `src/notifications/payoff_chart.py` one-liners; note `send_photo`
  on the Telegram wrappers.
- `src/strategy/CLAUDE.md` — a "Registering a strategy for payoff charts" recipe (copy of the `src/payoff/registry.py` module docstring): the one-line `@register_payoff("<strategy_name>")`, when a
  custom `PayoffAdapter` is needed, and that registration is opt-in.
- `DECISIONS.md` — an entry dated the commit day: matplotlib added as a runtime dep for Telegram payoff charts; charts are additive follow-up photo sends; payoff math is strategy-agnostic with an
  opt-in registry; the `chart-model-overlay/` split and its `greeks-bs-fallback/` dependency.
- `TODOS.md` — a Session Log line; update the `## Feature Backlog` entry's `next:` to the first `chart-model-overlay/` task (or mark `chart-core/` done).
- `docs/plan/README.md` — flip the `strategy-payoff-charts/` epic row: `chart-core/` → ✅ with SHA.
- `docs/plan/strategy-payoff-charts/README.md` — **Stories** table status column; regenerate the "after" import-graph diagram (tests excluded) beside the design-time one.
- Re-index the graph: `mcp__codebase-memory-mcp__index_repository`.

**Tests:** none (docs). Run `python -m pytest tests/unit/ --tb=no -q` once to confirm the story left the suite green.

**Commit:** `docs(plan): close chart-core (strategy payoff charts on Telegram)`
