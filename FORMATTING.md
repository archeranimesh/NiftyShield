# Telegram Message Formatting Standard

> Why this exists: value formatting was decided independently inside eighteen `scratch/`
> message-format workshop scripts between 2026-08-07 and 2026-08-13. Money alone ships in five
> different shapes across them (`₹82,628.00`, `₹82,628`, `82,628.00`, `+11,024`, `-3k`), percentages in four, and
> `-` currently means "not applicable" in one table and "zero" in another. Each choice was
> defensible where it was made; none of them were made against a common rule. This file is that
> rule set.
>
> **Scope:** any value rendered into a Telegram message body. **Authority:** this file governs.
> `formatting-rules/` FMT-2/FMT-3 implement it; `strategy-rollout/` ROLL-* consume it. Where a
> scratch script and this file disagree, this file wins and §8 names who reconciles.
>
> Origin: `docs/plan/telegram-markdown-migration/formatting-rules/` FMT-1.
> Transport and escaping helpers: `src/notifications/CLAUDE.md`.

---

## 1. The one rule

**Every value rendered into a Telegram message is formatted by a named formatter in
`src/notifications/formatting.py`. A message never inlines its own `f"{value:,.2f}"`. A context
that genuinely needs different output declares a named override in §5 and documents it in its own
docstring — it never post-processes a formatter's output.**

The failure this prevents is not ugliness. It is two messages about the same position quoting the
same number differently, and nobody being able to tell which one is rounded.

---

## 2. The two axes

Every rule in §3 falls out of two questions. Answer them first when a new parameter type appears;
the format usually follows without a fresh decision.

**Prose or fence?** Text outside a fenced code block is read left to right — drop noise (a
trailing `.0`, a redundant `+`). Text inside a fenced block is read as a column — every cell in a column carries
the same precision and the same width, or it stops being a column. This is why the same percentage
prints `3%` in a sentence and `+3.0%` in a table cell, and it is not an inconsistency.

**Identifier or quantity?** A strike (`23000`), a DTE (`18`), a lot count (`4`) *name* a thing. A
price, a P&L, a share count *measure* a thing. Identifiers take no thousands separator and no
decimals — a comma in `23,000 PE` reads as punctuation, not magnitude. Quantities take a separator
once they can exceed 999.

---

## 3. Canonical rules

| Parameter type | Format | Example | Formatter |
|---|---|---|---|
| Money — default (prose, kv lines) | `Decimal`, 2dp, `,` thousands, `₹` prefix, **sign before the `₹`** | `₹86.68` · `₹82,628.00` · `-₹11.08` | `format_money(v)` |
| Money — explicit positive sign | as above, plus a leading `+` on positives | `+₹7,812.50` · `-₹393.00` | `format_money(v, signed=True)` (FMT-1f) |
| Strike price | integer, no decimal, **no thousands separator** | `23000` | `format_strike(v)` — identifier |
| Index / spot level | integer, thousands separator | `24,571` | quantity |
| Greeks (Δ, Γ, Θ, ν) | 2dp, **always signed**; `-` when the leg has no value | `+0.28` · `-0.03` · `-` | `format_greek(v)` |
| IVR | 2dp, unitless, unsigned | `0.16` | 0.0–1.0 per `compute_ivr` |
| DTE, open-leg count, lot count | bare integer, no separator | `18` · `4` | cannot exceed 999 |
| Share / unit quantity | integer, thousands separator, sign preserved | `-5,735` | can exceed 999 (NIFTYBEES) |
| Percent — prose | 1dp, trailing `.0` dropped on whole numbers, `%` suffix, unsigned | `3%` · `2.7%` · `0.2%` | `format_pct(v)` |
| Percent — prose, signed | as above, plus a leading `+` on positives | `+3%` · `-1.4%` | `format_pct_signed(v)` |
| Percent — **inside a fenced table column** | **always 1dp, always signed** | `+3.0%` · `-1.4%` | width discipline (§2) |
| LTP / Entry — prose | money default | `₹9.30` | `format_money(v)` |
| LTP / Entry — **inside `build_leg_table`** | 1dp, no `₹` | `9.3` | locked override, §5 |
| Expiry date | `%d %b %y`, **uppercase, leading zero kept** | `25 AUG 26` · `07 JUL 26` | `format_expiry(v)` |

**Money is `Decimal`, never `float`.** A `float` argument raises `TypeError` — it does not silently
coerce. Project Data Layer rule (root `CLAUDE.md`); the whole point is that a rounding artefact
never reaches a message that a capital decision is read off.

**Correction to FMT-1's original table (2026-08-25):** its money row gave `₹82,628` as an example
of its own 2dp rule. The rule stands, the example was wrong — `Decimal("82628")` renders
`₹82,628.00`. Margin happening to be whole rupees in practice is not a special case.

**Expiry — resolved 2026-08-25 (Animesh).** FMT-1's original row specified `25 Aug 26` / `5 Aug 26`
(title case, `strftime("%d %b %y").lstrip("0")`). Superseded by a single rule matching the shipped
`format_option_label()` (`src/instruments/lookup.py`, TL-1), for three reasons: that function is
already live in Telegram messages via TL-2/TL-3; a variable-width day field misaligns any fenced
column carrying an expiry, which is exactly what §2 exists to prevent; and two renderings of the
same date inside one message reads as a bug to the person on the receiving end. `%-d` remains
banned (platform-dependent, fails on some Windows builds) — moot now, since the leading zero is
kept and nothing is stripped.

> **Carry-forward for `ROLL-1`:** its confirmed header and
> `scratch/2026-08-07_ic_eod_audit_v2_telegram_format.py::format_expiry` still emit `25 Aug 26`.
> Both need updating when ROLL-1's real port lands. Not changed here — FMT-1 is docs-only and
> ROLL-1 is another task's scope.

---

## 4. Missing, unresolved, and zero are three different things

| State | Meaning | Renders as |
|---|---|---|
| Not applicable | the field has no meaning for this row — e.g. a long wing with no captured delta | `-` |
| Unresolved | the field should have a value but the source did not supply one — LTP fetch failed, BOD lookup missed | `N/A` |
| Zero | a real, measured zero | the formatter's normal output — `₹0.00`, `+0.00`, `0%` |

Collapsing "unresolved" into "not applicable" is how a silent data-fetch failure gets read as a
deliberate blank. Keep them apart.

**Open conflict — FMT-1d.** FMT-1d renders *zero* as `-` inside the multi-strategy summary table,
which collides with `-` meaning *not applicable* above. Inside any table adopting that convention,
an unresolved value must render `N/A` and a not-applicable value must not appear in that column at
all — otherwise one glyph carries two meanings in one column. FMT-1d's spec does not currently say
this; whoever implements it resolves it explicitly rather than picking whichever is convenient at
the call site.

---

## 5. Context overrides — the registry

An override is legitimate **only when a fenced table's width budget forces it**. "It looked nicer"
is not a reason. Every override must (a) appear in this table, (b) be documented in its own
function's docstring as an override of the §3 default, and (c) be implemented as its own local
format — never `format_money(...)`'s output with the `₹` stripped or the decimals re-rounded.

| Context | What changes | Spec | Status |
|---|---|---|---|
| `build_leg_table` LTP/Entry columns | 1dp, no `₹` | FMT-1 (locked 2026-08-07) | specified, not yet real code |
| Multi-strategy summary table (8+ rows, 3+ numeric cols) | signed integer, no `₹` per cell, zero as `-` | FMT-1d | specified, not yet real code |
| IC V1-vs-V2 monthly comparison table | money at **0dp** with `₹`, `N/A` for `None` | `scratch/2026-08-07_ic_monthly_comparison_telegram_format.py` | **unregistered — reconcile at ROLL-2** |
| EOD PT summary table | money at 2dp, no `₹` | `scratch/2026-08-13_eod_pt_summary.py` | **unregistered — reconcile at PT-1's ROLL task** |
| Daily-snapshot waterfall | `k` abbreviation for \|value\| ≥ 1000 (`-3k`) | `scratch/2026-08-08_daily_snapshot_waterfall_format.py` | **unregistered — no ROLL task; format decision deferred 2026-08-11** |

---

## 6. Escaping contract

**Formatters return display strings, not MarkdownV2-safe strings.** Escaping happens at the call
site, never inside a formatter.

Nearly every formatter above can emit a MarkdownV2-reserved character: `.` from any 2dp value, `-`
from a negative or a placeholder, `+` from a signed value, `(` `)` from a parenthesised label. The
reserved set is `` _*[]()~`>#+-=|{}.! `` — ordinary numeric punctuation, not just markup.

- **Inside a fence** — pass formatter output through verbatim. Telegram parses no entities
  inside a fence; escaping there prints literal backslashes.
- **Outside a fence** — wrap the formatter's output in `escape_markdown()` (or `mdcode()` when the
  value is conceptually an identifier) before interpolating it into the template.

Worked example: `format_money(Decimal("-11.08"))` returns `-₹11.08`. Outside a fence the caller
sends `escape_markdown(...)` → `\-₹11\.08`, which renders as `-₹11.08`. Sent unescaped, the leading
`-` opens a reserved entity, Telegram rejects the whole message with a 400, and
`TelegramNotifier.send()`'s non-fatal contract swallows it — the message simply never arrives. That
is the `DELTA_WARN` bug class one layer up.

Why not escape inside the formatter: it would double-escape every fenced-table cell and every value
a caller already wrapped in `mdcode()`. Same reasoning that keeps `TelegramNotifier.send()` from
auto-escaping (`src/notifications/CLAUDE.md`). One escaping boundary, at the call site, enforced by
`tests/unit/notifications/test_escaping_guard.py`.

---

## 7. Characters inside a fence

Full rule: FMT-1e (`formatting-rules/stories.md`) — a symbol with a Unicode emoji-presentation
variant renders double-width on Telegram even inside a fence, and breaks column alignment
identically to a literal emoji. Confirmed data points so far:

| Glyph | Status |
|---|---|
| `▶` U+25B6 | **breaks alignment** — renders with its emoji-presentation glyph. Use `>`. |
| `Δ` U+0394 | in use as a fenced column header since ROLL-1 (2026-08-07); no break observed |
| `₹` U+20B9 | only ever used *outside* a fence. Width inside one is **unverified** — FMT-1d drops it from cells for width budget, not for safety. Do not assume. |

Note for FMT-1e: its rule as drafted is "only plain ASCII inside a fence", which would outlaw the
`Δ` header already shipped in ROLL-1's confirmed layout. FMT-1e should either carve `Δ` out
explicitly after an on-device check, or change ROLL-1's header — not leave the contradiction
standing.

---

## 8. Known divergences (audit, 2026-08-25)

Every formatter defined in `scratch/*_format.py` as of this date, checked against §3.

| Source | Helper | Divergence | Reconciled by |
|---|---|---|---|
| `2026-08-07_ic_monthly_comparison` | `format_money` | 0dp, not 2dp | ROLL-2 |
| `2026-08-07_ic_monthly_comparison` | `format_pct_signed` | none — adopted into §3 | — |
| `2026-08-07_ic_monthly_comparison` | `format_delta` | none | — |
| `2026-08-07_ic_eod_audit_v2` | `format_money`, `format_greek`, `format_strike`, `format_pct` | none | — |
| `2026-08-07_ic_eod_audit_v2` | `format_chg_pct` | none — matches §3's fenced-column percent rule | — |
| `2026-08-07_ic_eod_audit_v2` | `format_expiry` | title case + `lstrip("0")` — superseded by §3 | ROLL-1 |
| `2026-08-08_eod_paper_summary` | `_fmt_table_money` | registered override (FMT-1d) | FMT-1d |
| `2026-08-08_daily_snapshot_waterfall` | `_fmt_k` | `k` abbreviation, unregistered | §5 — no owning task |
| `2026-08-10_3track_roll_notification` | `format_money(signed=)` | none — adopted into §3 (FMT-1f) | — |
| `2026-08-10` / `2026-08-11` proxy-delta alerts | `_fmt_greek` | none | — |
| `2026-08-13_eod_pt_summary` | `_fmt_money` | 2dp without `₹`, unregistered override | PT-1's ROLL task |
| `2026-08-13_eod_pt_summary` | `_fmt_pct` | **2dp, not 1dp** | PT-1's ROLL task |
| `2026-08-13_eod_pt_summary` | `_fmt_qty` | none — adopted into §3 as the share-quantity rule | — |
| `2026-08-13_eod_pt_summary` | `_fmt_expiry_label` | none — matches §3 | — |

**Reference-implementation correction (verified 2026-08-25).** `formatting-rules/prompt.md` and
FMT-3's spec both name `_kv_table` and `_side_by_side_kv` as "working, user-validated reference
implementations" in `scratch/2026-08-07_ic_eod_audit_telegram_format.py`. **They do not exist.**
That file contains only `_leg_table`; neither name appears anywhere in `scratch/`, `src/`, or
`scripts/`. FMT-3 must therefore design `build_kv_table` / `build_side_by_side_kv_table` rather
than port them, or start from the nearest real analogue — `build_compare_table` in
`scratch/2026-08-07_ic_monthly_comparison_telegram_format.py`. Do not open FMT-3 expecting a port.

---

## 9. Column widths are computed, never counted

Every column width in every table builder is `max(len(x) for x in ...)` over the actual header and
cell strings. Never a literal constant.

`build_comparison_report()` (`scripts/strategies/ic/paper_ic_monthly_comparison.py`) hand-counted a
20-character label budget and broke silently the first time a label — `Realized (inception)` —
exceeded it. Fixed in TGFMT-1 (SHA `a69d817`); the rule exists so it is not re-introduced by the
next builder.

---

## 10. Changing this file

Prefer adding a row to editing one. Changing an existing rule invalidates every already-confirmed
`ROLL-*` message that used it — name the affected ones in the commit body, the way §3's expiry
change names ROLL-1.
