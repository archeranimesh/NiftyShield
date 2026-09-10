# Unified entry message — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: set `SHA:` on the task line + tick the box, flip this sub-story's row in the
> epic `README.md` **Stories** table, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

Sub-story 1 of the `telegram-message-unification/` epic. No DB schema change — no `schema.md`.

---

## UEM-1 — Generalize the IC entry renderer

**Files to change / create:**
- `src/notifications/ic_entry_message.py` → **rename** to `src/notifications/entry_message.py` (`git mv`)
  — generalize model + renderer, drop all IC-specific naming.
- `scripts/strategies/ic/paper_ic_entry.py` — update import + `EntryMessage(...)` construction (~line 797).
- `scripts/strategies/ic/paper_ic_entry_v2.py` — same (~line 715).
- `tests/unit/notifications/test_ic_entry_message.py` → **rename** to `test_entry_message.py` (`git mv`)
  — update imports / names, keep every existing assertion, add a single-leg case.

**Before any code (graph queries — do not write model constructors from memory):**
- `get_code_snippet("ICEntryMessage")` and read the whole current `entry_message.py` module — every
  helper (`_headline` / `_kv_row` / `_credit_line`) and its exact output string.
- `get_code_snippet("LegRow")` + `get_code_snippet("build_leg_table")` — reused verbatim, confirm fields.
- `get_code_snippet("format_expiry")` + `get_code_snippet("format_money")` — kv row / credit line helpers.
- `trace_path("format_ic_entry_message")` — confirm exactly the two IC call sites, nothing else in `src/`.
- `search_code("ic_entry_message")` + `search_code("format_ic_entry_message")` + `search_code("ICEntryMessage")`
  — full reference sweep across `src/`, `scripts/`, `tests/`, `docs/` before the rename.

**What to implement:**

1. Rename the module with `git mv`. Rewrite the module docstring: it is now the shared entry-confirmation
   renderer for all paper strategies, IC being the first consumer; keep the ROLL-17 lineage pointer and
   the escaping-boundary note (fenced block emitted literally, every interpolated value pre-escaped).
2. `ICEntryMessage` → `EntryMessage`. Fields:
   - `headline_label: str` — **new**, replaces the `"v2" in strategy_name` derivation. Caller passes
     `"IC v1"` / `"IC v2"` / `"CSP"` / `"CC"`. `_headline` becomes `f"✅ *{escape_markdown(label)} Entry* — ..."`
     with the trailing `— {expiry_type}` segment emitted only when `expiry_type is not None`.
   - `expiry: date`, `dte: int`, `spot: float`, `net_credit: Decimal` — stay **required**.
   - `ivr: float | None = None`, `mode: str | None = None`, `expiry_type: str | None = None` — optional.
     `_kv_row` builds its segment list conditionally: always `DTE` / `Nifty` / `Exp`; `IVR` only when
     `ivr is not None`. Document why `ivr` was relaxed from ROLL-17's required (CSP entry via the recorder
     has no IVR in scope) — a short comment on the field + a line in the module docstring.
   - `legs: list[LegRow]` — unchanged type; docstring drops "the four IC legs", now "1..N legs in send
     order". `build_leg_table` already raises on empty, so no new guard.
   - Drop `strategy_name` entirely (its only use was the v1/v2 marker, now `headline_label`).
3. `format_ic_entry_message` → `format_entry_message(msg: EntryMessage) -> str`. Body unchanged except
   the optional `*Mode:*` line already guards on `msg.mode is not None` — keep that.
4. Migrate both IC call sites: `ICEntryMessage(` → `EntryMessage(`, drop `strategy_name=...`, add
   `headline_label="IC v1"` (`paper_ic_entry.py`) / `headline_label="IC v2"` (`paper_ic_entry_v2.py`).
   `paper_ic_entry_v2.py` already passes `mode=None` — leave it. Update the `from src.notifications...`
   import lines in both.
5. No shim / alias for the old names — the reference sweep in the pre-step covers every caller.

**Tests (`tests/unit/notifications/test_entry_message.py`, no network, no real DB):**
- Keep all current assertions, renamed. `test_headline_marker_from_strategy_name` becomes
  `test_headline_uses_headline_label` — assert `"IC v2"` label renders `✅ *IC v2 Entry* — monthly`.
- `test_net_credit_line_uses_format_money_both_sides` — unchanged logic.
- **New** `test_single_leg_no_ivr_omits_ivr_segment` — build an `EntryMessage` with one short-put
  `LegRow`, `ivr=None`, `expiry_type=None`, `headline_label="CSP"` (the CC card uses the same shape,
  `headline_label="CC"` + a `"Short Call"` leg); assert the kv row has no `IVR:` and
  the headline has no `—` segment, and `build_leg_table` renders exactly one `[S]` row.
- **New** `test_ivr_present_renders_ivr_segment` — same but `ivr=0.14`; assert `*IVR:* 0\.14` present.

**Commit:** `refactor(notifications): generalize IC entry renderer to EntryMessage`

---

## UEM-2 — Lean CSP / CC entry card from the shared recorder

**Files to change / create:**
- `scripts/record/record_paper_trade.py` — add `--notify` flag; on a successful open, build an
  `EntryMessage` and send it via `TelegramNotifier`. One card path serves both CSP and CC — they share
  the recorder; only `headline_label` and the leg `role` differ, and both are derived (not hand-passed).
- `tests/unit/scripts/test_record_paper_trade.py` — new or extended; four cases below.

**Before any code (graph queries):**
- Read the whole `record_paper_trade.py` `main()` / arg-parse flow via `get_code_snippet` — find where a
  successful **open** (SELL, `--close` not set, not a roll-close) is confirmed (~line 900+, after
  `store` write, the `net qty` branch). The card fires only on the genuine open path.
- `get_code_snippet("EntryMessage")` — the UEM-1 field list.
- `get_code_snippet("TelegramNotifier")` + `search_graph("NotifierProtocol")` — the `send_notification`
  signature and how existing callers construct it from `settings` (mirror `paper_ic_entry.py`'s
  `TelegramGateway` block, but use `TelegramNotifier` — no approval/callback needed for a plain card).
- `search_graph("STRATEGY_CSP")` + `search_graph("STRATEGY_CC_OVERLAY")` + `get_code_snippet` on both
  constants — confirm the CSP and CC-overlay strategy ids the recorder receives via `--strategy` (the CC
  id is what `scripts/strategies/cc_calibration/paper_cc_entry.py` prints).
- `search_code("format_expiry")` — reuse for the expiry the recorder already resolved.
- `trace_path("record_trade")` in `scripts/record/record_paper_trade.py` — confirm nothing else imports
  its internals such that adding a flag / a helper breaks a caller.

**What to implement:**

1. Add `--notify` (store_true, default False) to the arg parser, help: "send a Telegram entry card on a
   successful open (no-op on close / roll)".
2. New module-level helper `_build_entry_card(...)` (10–20 lines): takes the resolved strike / opt-type /
   expiry date / dte / spot / credit / lot fill and returns `format_entry_message(EntryMessage(...))`
   with `expiry_type=None`, `ivr=None`, `mode=None`, one `LegRow(role=<"Short Put" for a PE, "Short Call"
   for a CE>, instrument=f"{int(strike)} {opt_type}", delta=<delta if resolved else None>, ltp=<fill>,
   entry=<fill>)`. `headline_label` is `"CSP"` when `--strategy` is the CSP id and `"CC"` when it is the
   CC-overlay id — a small dict / `if`, never string-parsing the strategy name. `net_credit` = the
   per-unit sell price as `Decimal`.
   - Instrument label per `src/notifications/CLAUDE.md` §"Instrument Label Formatting" — if a
     `format_option_label` / `format_strike` helper is the sanctioned form there, use it, don't hand-roll.
3. At the confirmed-open point, `if args.notify and <this is an open, not a close>:` build the card, then
   the send in a `try/except Exception` that logs `logger.warning("telegram.send_failed", error=...)`
   and proceeds — never fail the recording because Telegram is down. Match the existing non-fatal
   pattern in `csp_nifty_v1._send_notification` / `paper_ic_entry.py`.
4. Guard: if `--close` (or the roll-close path) is set, `--notify` is a silent no-op — an entry card on a
   close is wrong. Do not emit a "position closed" card here; that is out of scope.
5. `spot` / `dte`: use values the recorder already computes for its entry-gate / price-drift checks. If
   `dte` is not already in scope, derive it from `expiry - date.today()` (`.days`). If spot is not in
   scope without a live call, pass the underlying the drift check already fetched; if genuinely
   unavailable offline, omit by making the card builder tolerate `spot=None` is **not** allowed
   (`spot` is required) — instead skip the card with a `logger.info("entry_card.skipped", reason=...)`.
   Prefer reusing an already-fetched value over adding a network call.

**Tests (`tests/unit/scripts/test_record_paper_trade.py`, no network, no real DB):**
- `test_notify_flag_sends_csp_entry_card_on_open` — patch `TelegramNotifier.send_notification` with a
  spy, run the open path with `--notify`, assert it was awaited once with a body containing
  `✅ *CSP Entry*` and one `[S]` leg row.
- `test_notify_flag_sends_cc_entry_card_on_open` — same but `--strategy` = the CC-overlay id with a CE
  strike; assert the body contains `✅ *CC Entry*` and one `[S]` `… CE` row.
- `test_notify_send_failure_is_non_fatal` — spy raises `RuntimeError`; assert the recorder still exits 0
  and the trade write happened (store spy saw the insert).
- `test_no_notify_flag_sends_nothing` — run the open path without `--notify`; assert the notifier was
  never constructed / never called.

**Commit:** `feat(paper): CSP / CC entry Telegram card from record_paper_trade --notify`

---

## UEM-3 — Docs close

**Files to change:** `CONTEXT.md`, `src/notifications/CLAUDE.md`, `DECISIONS.md`,
`docs/plan/telegram-message-unification/README.md`, `TODOS.md`. Targeted `Edit` only, never `Write`.

**What to implement:**

1. `CONTEXT.md` "What Exists" `src/notifications/` bullet — `ic_entry_message.py (IC entry ...)` →
   `entry_message.py (shared lean entry-confirmation renderer — IC v1/v2 + CSP + CC, UEM-1/2)`.
2. `src/notifications/CLAUDE.md` — update any reference to `ic_entry_message` / `format_ic_entry_message`
   to the new names; add a one-line note that the renderer is strategy-agnostic (`headline_label`) and
   the kv row omits `IVR` when absent.
3. `DECISIONS.md` §P&L & Reporting — one dated line: shared entry renderer + CSP / CC entry card via
   `record_paper_trade --notify` (`headline_label` from `--strategy`); `ivr` relaxed to optional vs
   ROLL-17 (CSP / CC have no IVR at record time); PP / collar / three-track bootstrap / track-comparison
   deferred.
4. `docs/plan/telegram-message-unification/README.md` — flip the `unified-entry-message/` row in the
   **Stories** table to ✅ with the closing SHA; add a Session Log line to `TODOS.md`. Do **not** touch
   the `docs/plan/README.md` epic row or archive anything — the whole epic archives at UXM-8.

**Commit:** `docs: close unified-entry-message sub-story (UEM-1..3)`
