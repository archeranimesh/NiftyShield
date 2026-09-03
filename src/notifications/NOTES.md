# src/notifications — Reference Notes

> **Not auto-loaded.** Reference detail relocated out of `CLAUDE.md` (FIX-2,
> `docs/archive/plan/token-efficiency/fixed-overhead/`) so the auto-injected file carries only
> invariants and caller contracts. Read this when you need the history, the worked examples,
> or the full per-formatter enumeration behind a rule in `CLAUDE.md`.

---

## Message format — the removed `<pre>` wrap

`send()` posts `text` exactly as authored — it does not wrap the body in `<pre>`, a code
fence, or anything else. That paragraph in `CLAUDE.md` previously described an HTML `<pre>`
wrap that `TelegramNotifier.send()` performed under the old parse_mode; the wrap was removed
with the MarkdownV2 migration and the description was left behind — corrected 2026-08-25,
FMT-1.

The MarkdownV2 migration itself: `docs/plan/telegram-markdown-migration/`, MD-1 through
MD-7.3, completed 2026-08-25.

---

## Escaping — origin and the guard test

The unescaped-reserved-character failure mode (a send rejected with a 400 "can't parse
entities", silently swallowed by the non-fatal `send()` contract, so a bad message doesn't
crash the caller — it just never arrives) was the original `DELTA_WARN` bug class that
motivated the whole migration (`docs/plan/telegram-markdown-migration/`).

**Guard test:** `tests/unit/notifications/test_escaping_guard.py` (added MD-6, SHA `ce95bbd`)
statically walks `src/`/`scripts/` for `notifier.send(`/`send_plain_message(`/
`send_notification(` call sites and asserts every interpolated dynamic value is escaped via
`escape_markdown()`/`mdcode()` somewhere upstream. Pre-existing unescaped call sites that
predate the guard are tracked individually in its `_BASELINE_UNESCAPED` allowlist with a reason
string per entry — do not add a new entry to silence a newly-introduced unescaped call site;
fix the call site instead. Remove a call site's baseline entry in the same commit that fixes it
(`test_baseline_entries_are_still_unescaped` / `test_baseline_has_no_duplicate_or_unused_entries`
enforce this). Confirmed permanent won't-fix baseline entry: `scripts/dev/send_test_telegram.py`
(manual dev/debug utility, not a cron or strategy event path — Animesh, 2026-08-25).

All currently-known production call sites were audited and fixed under this epic (MD-3, MD-4.1–
4.3, MD-7.1–7.3): strategy close/roll notifications, the three reporting builders, both IC
entry-signal scripts (`send_notification` + `_gate_alert` paths), `pre_market_brief.py`,
`auto_close.py`, and `overlay_closer.py`. Any new `.send()`/`.send_plain_message()`/
`.send_notification()` call site added after 2026-08-25 is caught by the guard test at commit
time, not audited retroactively.

---

## Value formatters — full signatures and examples

Canonical per-parameter-type rules live in root `FORMATTING.md`; this is the module-level
narration of the code that implements them (formatting-rules epic, FMT-1..FMT-4,
`docs/plan/telegram-markdown-migration/formatting-rules/`). All return plain, unescaped text.

- **`format_money(value: Decimal) -> str`** — 2dp, comma thousands, `₹` prefix, sign before `₹`
  on negatives. Rejects `float` with `TypeError` — never silently coerces. `Decimal("82628")` ->
  `"₹82,628.00"`, `Decimal("-11.08")` -> `"-₹11.08"`.
- **`format_greek(value: float | None, *, width: int | None = None) -> str`** — 2dp, always
  signed, `"-"` placeholder for `None` (not-applicable, not zero). `0.28` -> `"+0.28"`. `width`
  right-aligns for `build_leg_table`'s reuse.
- **`format_strike(value: float | int) -> str`** — integer string, no decimal, no thousands
  separator (an identifier, not a quantity). Raises `ValueError` on a non-whole-number input.
- **`format_pct(value: float) -> str`** — 1dp; whole-number inputs print bare (`4` -> `"4%"`,
  not `"4.0%"`). `value` is a plain percentage number, `4` means 4%, not `0.04`.

## Table builders — full signatures and rationale

All wrap in a caller-supplied ` ```fenced block``` ` — none of these add the fence themselves,
so they stay reusable for plain console output too.

- **`build_kv_table(title, rows: list[tuple[str, str]]) -> str`** — bordered two-column
  label/value table. Width is always computed from the actual content
  (`max(len(x) for x in ...)`), never a hand-counted constant — this is the exact bug class
  that broke `build_comparison_report()`'s original fixed 20-char budget (see
  `formatting-rules/prompt.md`). Raises `ValueError` on empty `rows` — a titled table with
  nothing to show is a caller bug, not a valid empty table.
- **`build_side_by_side_kv_table(title_a, rows_a, title_b, rows_b) -> str`** — two `build_kv_table`
  outputs joined with `" | "`, shorter side blank-padded to stay aligned when row counts differ
  (the real Snapshot/P&L comparison case). Built on top of `build_kv_table` rather than
  reimplementing its width/border logic.
- **`build_leg_table(legs: list[LegRow]) -> str`** — position table: `[S]`/`[B]` badge (from
  whether `LegRow.role` starts with `"Short"`/`"Long"`), instrument, Δ, LTP, entry. LTP/Entry
  columns use a local 1dp format, **not** `format_money`'s 2dp — a locked-in exception (see
  `FORMATTING.md` §3) to fit numeric columns on a narrow mobile screen inside a fenced block; do
  not "fix" this into a `format_money()` call. Raises `ValueError` on empty `legs`.
- **`LegRow`** (frozen dataclass) — one input row for `build_leg_table`: `role`, `instrument`
  (pre-formatted, e.g. `"23000 PE"`), `delta: float | None`, `ltp: float`, `entry: float | None`.

**Known risk, not yet guarded in code:** any Unicode symbol with an emoji-presentation variant
(not just literal emoji) renders double-width on Telegram even inside a monospace fence and can
break column alignment — e.g. `▶`. Extends the emoji-breaks-alignment warning from literal
emoji to that wider glyph class. See `FORMATTING.md` (FMT-1e).

## Display-label lookups

ROLL-7, `docs/plan/telegram-markdown-migration/strategy-rollout/`.

- **`STRATEGY_LABELS` / `strategy_label(strategy_id) -> str`** — fuller-form human label for a
  raw `strategy_id` headline (`"paper_csp_nifty_v1"` -> `"CSP V1"`). Unmapped id raises
  `ValueError` — never falls back to the raw id. **Separate from** `scripts/eod_summary.py`'s
  `_STRATEGY_META` (narrow fenced-column abbreviations); the `id -> {short, long}`
  consolidation is flagged, not done.
- **`LEG_ROLE_LABELS` / `leg_role_label(leg_role) -> str`** — explicit `leg_role` -> label
  (`"covered_call"` -> `"Covered Call"`), not `.title()`. Unmapped role raises `ValueError`.
  Scoped to the roles reachable as `ReEntryMixin.reentry_leg_role`; extend the dict when a new
  caller needs a role. (The `STRATEGY_OVERLAY` umbrella id — shared by CC/Collar/PP at runtime
  — is resolved via leg_role by `reentry_mixin._reentry_headline_label`, not here.)

Tests: `tests/unit/notifications/test_formatting.py`.

---

## Instrument label formatting — origin

`docs/plan/telegram-leg-labels/` — raw `NSE_FO|65900` shown in an AUTO-CLOSE Telegram alert
with no way to identify the strike.
