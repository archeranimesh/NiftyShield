# Overlay entry message — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: set `SHA:` on the task line + tick the box, update the story status
> summary in `docs/plan/README.md`, add one line to `TODOS.md` Session Log.

Depends on `unified-entry-message/` (UEM-1..3, shipped + archived) — this story assumes
`src/notifications/entry_message.py` with `EntryMessage` / `format_entry_message`,
`headline_label`, and optional `ivr`/`mode`/`expiry_type` already exists.

No DB schema change — no `schema.md`.

---

## OEM-1 — Sign-aware net line

**Files to change:**
- `src/notifications/entry_message.py` — `_credit_line` only. No field rename, no signature
  change to `format_entry_message`.
- `tests/unit/notifications/test_entry_message.py` — two new cases.

**Before any code (graph queries):**
- `get_code_snippet("_credit_line")` + `get_code_snippet("EntryMessage")` — confirm the
  exact current output string and that `net_credit: Decimal` is the field.
- `get_code_snippet("format_money")` — confirm it renders a leading `-` for negatives (it
  does; the point is to strip it and flip the label, not to change `format_money`).
- `search_code("Net credit")` — confirm the only renderer of that literal is `_credit_line`
  and nothing asserts on it outside `test_entry_message.py`.

**What to implement:**

1. `_credit_line`: if `msg.net_credit < 0`, label is `Net debit` and both interpolated values
   use `abs(msg.net_credit)` / `abs(msg.net_credit) * LOT_SIZE`; otherwise unchanged
   (`Net credit`, raw value). The `\=` escape and the `×{LOT_SIZE}` segment are identical
   either way. `net_credit == 0` takes the `Net credit` branch (byte-identical to today).
2. One-line docstring note on `_credit_line` + the module docstring: the field is a *signed*
   net premium — positive = credit received (IC / CSP / CC / short-call overlays), negative =
   debit paid (collar, PP re-entry); the label follows the sign.

**Tests:**
- Keep every existing assertion.
- **New** `test_net_debit_line_when_net_credit_negative` — `net_credit=Decimal("-25.00")`;
  assert the line is `💰 *Net debit:* ₹25\.00/lot  ×65 \= ₹1,625\.00` (no `-`, label flipped).
- **New** `test_net_credit_line_unchanged_for_zero` — `net_credit=Decimal("0")`; assert the
  line still reads `💰 *Net credit:* ₹0\.00/lot  ×65 \= ₹0\.00`.

**Commit:** `feat(notifications): sign-aware net credit/debit line in EntryMessage`

---

## OEM-2 — Collar re-entry entry card

**Files to change:**
- `src/strategy/collar_overlay_v1.py` — add a `_send_reentry_notification(...)` success
  card, called from `_reenter_collar` right after `self._store.record_trades(new_trades)`
  succeeds (~line 573, the `reenter_collar.recorded` log point).
- `tests/unit/strategy/test_collar_overlay_v1.py` — two cases.

**Before any code (graph queries — do not build `EntryMessage` / `LegRow` from memory):**
- `get_code_snippet("EntryMessage")` + `get_code_snippet("LegRow")` — exact fields.
- `get_code_snippet("CollarOverlayV1._reenter_collar")` — the success point, the shape of
  `new_trades`, what leg data (strike / price / delta / expiry) is on each.
- `get_code_snippet("CollarOverlayV1._send_reentry_failure_notification")` — mirror its
  `_notifier` dispatch chain (`send_notification` → `send_plain_message` → `send`) and its
  non-fatal `try/except` + `collar_overlay_v1.*_notify_failed` log.
- `get_code_snippet("format_entry_message")` + `search_graph("leg_role_label")` — the
  `overlay_collar_put` / `overlay_collar_call` labels are `"Collar Put"` / `"Collar Call"`.
- `get_code_snippet("format_leg_label")` — the instrument label helper the close card uses.

**What to implement:**

1. `_send_reentry_notification(self, new_trades, triggering_signal)` — returns `None`, guards
   `if self._notifier is None`. Build one `EntryMessage`:
   - `headline_label="Collar"`, `expiry_type=None`, `ivr=None`, `mode=None`.
   - `expiry` / `dte` from the re-entered legs (both share the monthly expiry;
     `dte = (expiry - market_today()).days`).
   - `spot` — the underlying the selection already fetched; if not in scope without a live
     call, log `collar_overlay_v1.reentry_card.skipped` (reason) and return — do **not** add
     a network call, do **not** pass `spot=None` (required field).
   - `legs`: `LegRow(role="Collar Put", instrument=<label>, delta=<put delta or None>,
     ltp=<put fill>, entry=<put fill>)` then the `"Collar Call"` row. Put first (send order).
   - `net_credit` = `call_sell_price - put_buy_price` as a signed `Decimal` (normally
     negative → OEM-1 renders `Net debit`).
2. Call it after the successful `record_trades`, in its own non-fatal `try/except Exception`
   logging `collar_overlay_v1.reentry_notify_failed` — a notify failure must never crash the
   tick or mask the successful record.
3. No change to `_send_reentry_failure_notification` or `_send_close_notification`.

**Tests (`tests/unit/strategy/test_collar_overlay_v1.py`, no network, no real DB):**
- `test_reentry_sends_collar_entry_card` — drive `_reenter_collar` with a stub broker/store
  so the record succeeds; spy `self._notifier.send_notification`; assert one call with a body
  containing `✅ *Collar Entry*`, one `[B]` and one `[S]` row, and a `💰 *Net debit:*` line.
- `test_reentry_notify_failure_is_non_fatal` — spy raises; assert `_reenter_collar` still
  returns normally and the `record_trades` spy saw the write.

**Commit:** `feat(strategy): Collar re-entry Telegram entry card via shared renderer`

---

## OEM-3 — CC + PP re-entry entry cards

**Files to change:**
- `src/strategy/cc_overlay_v1.py` — `✅ *CC Entry*`, one `[S]` call leg.
- `src/strategy/pp_overlay_v1.py` — `✅ *PP Entry*`, one `[B]` put leg (net debit).
- `src/strategy/reentry_mixin.py` — **only if** the re-entry-success record point is shared
  there rather than in each `apply_action`. Confirm first; prefer per-class if ambiguous.
- `tests/unit/strategy/test_cc_overlay_v1.py`, `tests/unit/strategy/test_pp_overlay_v1.py`.

**Before any code (graph queries):**
- `get_code_snippet("CCOverlayV1.apply_action")` + `get_code_snippet("PPOverlayV1.apply_action")`
  + `get_code_snippet("ReEntryMixin")` — find where a successful automated re-entry records
  the new leg. That is the single call site for the card.
- `get_code_snippet("CCOverlayV1._send_close_notification")` — mirror its dispatch + non-fatal
  pattern (same as OEM-2 for Collar).
- `get_code_snippet("EntryMessage")` + `get_code_snippet("LegRow")` — exact fields.
- `search_graph("leg_role_label")` — `overlay_cc` → `"Overlay CC"`, `overlay_pp` →
  `"Overlay PP"`; use the `role` string `build_leg_table` keys the badge off
  (`startswith("Short")` → `[S]`, else `[B]`), so pass `"Short Call"` for CC and
  `"Long Put"` for PP.

**What to implement:**

1. A `_send_reentry_notification` on each class (or one shared helper on `ReEntryMixin` if the
   record point is shared) with the same contract as OEM-2:
   - CC: `headline_label="CC"`, one `LegRow(role="Short Call", …)`, `net_credit` = the call
     sell price (positive → `Net credit`).
   - PP: `headline_label="PP"`, one `LegRow(role="Long Put", …)`, `net_credit` = negative of
     the put debit (→ `Net debit`).
   - `expiry` / `dte` / `spot` sourced as in OEM-2; skip-with-log if `spot` unavailable.
2. Called after the successful re-entry record, non-fatal `try/except`, log
   `<class>.reentry_notify_failed`.

**Tests (per class, no network, no real DB):**
- `test_reentry_sends_<cc|pp>_entry_card` — assert `✅ *CC Entry*` / `✅ *PP Entry*`, one leg
  row of the right badge, and the right net line (`Net credit` for CC, `Net debit` for PP).
- `test_reentry_notify_failure_is_non_fatal` — spy raises; re-entry still completes.

**Commit:** `feat(strategy): CC and PP re-entry Telegram entry cards via shared renderer`

---

## OEM-4 — Bootstrap message onto the shared renderer

**Files to change:**
- `scripts/strategies/three_track/paper_3track_overlay_entry.py` — the `if notifier:` block
  (~line 1538) that builds `📥 Overlay Entry — {TYPE} Bootstrap`.
- `tests/unit/scripts/test_paper_3track_overlay_entry.py` (or the existing test module for
  this script) — one case per overlay type.

**Before any code (graph queries):**
- Read the whole `if notifier:` block via `get_code_snippet` — the per-leg loop, the
  `⚠️ Gate Logged` append, the `asyncio.run(notifier.send(msg))` call.
- `get_code_snippet("EntryMessage")` + `get_code_snippet("LegRow")`.
- `search_code("format_month")` / `search_code("format_expiry")` — the bootstrap block uses
  `format_month`; the shared kv row uses `format_expiry`. Both come from the same expiry;
  pick `format_expiry` for the card (matches every other consumer).
- Confirm the `overlay_trades` entries carry strike / price and (if resolved) delta.

**What to implement:**

1. Replace the hand-rolled `lines = [...]` construction with:
   `card = format_entry_message(EntryMessage(headline_label=cfg.overlay_type.upper(), …))`
   — `"CC"` / `"PP"` / `"COLLAR"` from `cfg.overlay_type`, `expiry_type=None`, `ivr=None`,
   `mode=None`; one `LegRow` per `overlay_trades` entry (put → `"Long Put"` / `[B]`, call →
   `"Short Call"` / `[S]`); `net_credit` = signed sum of the leg premiums
   (sell positive, buy negative).
2. The `⚠️ Gate Logged: …` line, when `gate_violation is not None`, is appended to the
   rendered card string by the caller — `msg = card + "\n" + gate_line`. The renderer gains
   no `footer_note` field (keeps it lean; the gate line is a script concern).
3. `asyncio.run(notifier.send(msg))` in the existing non-fatal `try/except` — unchanged.

**Tests:**
- `test_bootstrap_card_<cc|pp|collar>` — run the `if notifier:` path with a spy notifier;
  assert `✅ *CC Entry*` / `✅ *PP Entry*` / `✅ *COLLAR Entry*`, the right leg count / badges,
  and (collar / pp) a `💰 *Net debit:*` line.
- `test_bootstrap_card_appends_gate_line` — with a `gate_violation`; assert the
  `⚠️ Gate Logged:` line follows the rendered card.

**Commit:** `refactor(3track): bootstrap entry message onto shared EntryMessage renderer`

---

## OEM-5 — Docs close

**Files to change:** `CONTEXT.md`, `src/notifications/CLAUDE.md`, `DECISIONS.md`,
`docs/plan/README.md`, `TODOS.md`. Targeted `Edit` only, never `Write`.

**What to implement:**

1. `CONTEXT.md` "What Exists" `src/notifications/` bullet — extend the `entry_message.py`
   description: `IC v1/v2 + CSP + CC + Collar/PP + 3track bootstrap`.
2. `src/notifications/CLAUDE.md` — note the net line is sign-aware (`Net credit` /
   `Net debit` by the sign of `net_credit`); overlay re-entry + bootstrap now use the shared
   renderer.
3. `DECISIONS.md` §P&L & Reporting — one dated line: overlay entries (Collar / CC / PP
   automated re-entry + three-track bootstrap) unified onto `format_entry_message`; net line
   sign-aware for debit structures; `nifty_track_comparison_v1` still deferred (not a credit
   structure).
4. `docs/plan/README.md` — move the `overlay-entry-message/` row to ✅ Shipped/Archived with
   the OEM SHAs; `TODOS.md` Feature Backlog line deleted, Session Log line added.
5. Archive: `git mv docs/plan/overlay-entry-message docs/archive/plan/overlay-entry-message`,
   per §Conventions *Completion → archive* — one commit.

**Commit:** `docs: close overlay-entry-message (OEM-1..5)`
