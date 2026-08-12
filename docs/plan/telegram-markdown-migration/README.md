# Telegram Markdown Migration — Epic Index

Spawned from a Cowork session (2026-08-07) prototyping a nicer IC EOD audit Telegram message.
The prototype (`scratch/2026-08-07_ic_eod_audit_telegram_format.py`) proved Markdown parse_mode
gets real bold + a copyable fenced code block in the same message — something HTML parse_mode
cannot do (nested `<b>` inside `<pre>` isn't reliably rendered by Telegram's HTML parser; see
that script's module docstring for the full elimination trail across HTML/plain/raw-HTML
attempts). That prototype also surfaced a real bug class: a lone `_` in dynamic text
(`DELTA_WARN`) opens an unclosed `_italic_` entity in Markdown and 400s the send — silently,
since `TelegramNotifier.send()` swallows exceptions by contract (non-fatal notifications).

**Revised 2026-08-07: target is `parse_mode=MarkdownV2`, not legacy `Markdown` v1** (the
prototype used legacy Markdown; `backbone/stories.md`'s header note explains the switch —
MarkdownV2's larger reserved-character set removes the "smart" entity-pairing ambiguity that
caused the `DELTA_WARN` bug in the first place, and is Telegram's actively-recommended mode).
This also means `backbone/` MD-3/MD-4's audit-and-fix pass covers more ground than originally
scoped: MarkdownV2 reserves ordinary prose punctuation (`.`/`(`/`)`/`-`/`!`) in addition to
markup characters, so static message *templates* need escaping too, not just dynamic values.

**Scope decision (confirmed with Animesh, 2026-08-07):** replace `TelegramNotifier`'s default
parse mode globally — not an opt-in second method. This is the higher-blast-radius option:
every existing caller of `send_plain_message()` / `TelegramNotifier.send()` was written for
HTML+`<pre>` (auto-escaped, wrapped) and has never been audited for Markdown special
characters in its dynamic content. Confirmed real callers via the code graph (not assumed):

- 7 strategy classes' `_send_close_notification` — `src/strategy/auto_close.py`,
  `csp_nifty_v1.py`, `cc_overlay_v1.py`, `collar_overlay_v1.py`, `ic_nifty_v1.py`,
  `ic_nifty_v2.py`, `pp_overlay_v1.py`
- `TelegramGateway.send_approval_request` — interactive keyboard, auth-sensitive
- `scripts/strategies/ic/paper_ic_snapshot.py` — the actual EOD audit cron
- `scripts/strategies/ic/paper_ic_monthly_comparison.py` — its hand-counted-width table bug
  was **already fixed** (`docs/plan/telegram-ic-comparison-formatting/` TGFMT-1, SHA
  `a69d817`) — see "A known coordination point" below; this epic's ROLL-2 builds on that fix,
  does not redo it
- `scripts/strategies/three_track/paper_3track_snapshot.py`
- ~~`scripts/reporting/paper_pnl_report.py`~~ — **removed 2026-08-12, miscategorized.** It is
  CLI-only (stdout, `--json`/plain-text), no `TelegramNotifier`/`TelegramGateway` call exists
  anywhere in its history (single commit `04687f1`, SNAP-4). It was never a real confirmed
  caller despite being listed as one above — see `TODO.md`'s "Correction (2026-08-12)" section.

**Added 2026-08-08 (message-format-workshop.md session, EOD Paper Summary):**
`scripts/eod_summary.py` was missing from the confirmed-callers list above — it sends the daily
"NiftyShield EOD Paper Summary" message via raw HTML parse_mode directly (not
`TelegramNotifier.send()`), so it fell outside the original audit scope entirely. It is now in
scope: `strategy-rollout/` ROLL-6 covers its migration to `TelegramNotifier.send()` +
MarkdownV2. `backbone/`'s audit-and-fix pass should be re-checked against this file if it has
already landed by the time ROLL-6 starts — do not assume it was covered.

**All Telegram messages migrate** (not just IC) — confirmed with Animesh. `strategy-rollout/`
sequences the actual format migration by risk tier; `backbone/` only changes the transport
(parse mode) and makes existing plain-text messages safe under it, it does not change how any
message looks yet.

---

## Priority order

| Tier | Folder | What it does | Depends on |
|---|---|---|---|
| **P0 — transport change, must land first** | `backbone/` | Switch `TelegramNotifier.send()` from HTML+`<pre>` to Markdown parse_mode; audit + fix every existing caller's dynamic-value interpolation so nothing silently 400s post-switch | none |
| **P1 — reusable formatting layer** | `formatting-rules/` | Canonical decimal/alignment spec per parameter type (money, Greeks, strikes, %); promote the scratch script's table-builder helpers into real tested `src/notifications/` code | `backbone/` (needs the escaping helper it defines) |
| **P2 — actual message migrations, staged by risk** | `strategy-rollout/` | Migrate each message family to the new bold/table format, IC audit first (lowest stakes, already prototyped) through approval requests last (highest stakes, coordinate with `telegram-approval-auth-fix`) | `backbone/` + `formatting-rules/` |

Do not start `formatting-rules/` before `backbone/`'s escaping helper exists — every formatting
helper that interpolates a dynamic value needs it. Do not start `strategy-rollout/` before both
are done.

## Supersession — `telegram-ic-comparison-formatting/`

That story's TGFMT-1 (the `build_comparison_report()` alignment fix) is shipped and stays as
history. **TGFMT-2 through TGFMT-9 are superseded by this epic**, marked as such in that
folder's `tasks.md` (2026-08-07) — they planned the same generalized table-helper +
`auto_close.py` retrofit + CLAUDE.md standard this epic's `formatting-rules/` and
`strategy-rollout/` already cover, just under the old HTML parse_mode instead of Markdown.
Two still-open feature asks from that story (TGFMT-2's Legs row, TGFMT-3's Bkd/Flt
month-inception P&L split) are carried forward into `strategy-rollout/` ROLL-2's scope, not
dropped — see that task's spec for the full carry-forward detail.

## A known coordination point

`docs/plan/full-repo-review-followups/telegram-approval-auth-fix/` touches
`TelegramGateway.send_approval_request` — the same method `strategy-rollout/ROLL-4` touches.
**Checked 2026-08-07: its only task (T1) is already shipped (SHA `5cafc3c`)** — the outer
`docs/plan/README.md` epic-summary line still says "Not started," which is stale; do not trust
that line, `tasks.md` inside the story folder is the source of truth. No live coordination
needed as of this writing, but re-check `tasks.md` there before starting ROLL-4 in case new
tasks were added since.

---

## Improvement backlog (added 2026-08-12, Cowork design-review session)

Four process/design improvements identified during a plan review, sequenced by urgency — not
listed order. Each has a model recommendation for the owning agent. Re-read this section before
picking up any of the four; do not assume listed order is execution order.

1. **MD-6 (new task) — static-scan escaping guard.** Owner: Claude, Model: Sonnet. Closes the
   only real correctness gap of the four: `backbone/`'s escaping discipline
   (`mdcode()`/`escape_markdown()` on every dynamic value) is currently hand-maintained with no
   compiler/CI check — the same failure shape as the original `DELTA_WARN` bug. Add a test that
   walks `src/`/`scripts/` for `notifier.send(`/`send_plain_message(` call sites and asserts
   every interpolated value passed through the escaping helpers somewhere upstream. **Resequence
   this task in `backbone/tasks.md` to land right after MD-2** (not after MD-5 where it's
   currently positioned) — it needs to exist before `formatting-rules/`/`strategy-rollout/`
   start generating the bulk of new `send()` call sites, so it catches mistakes as they're
   introduced instead of requiring a forensic sweep later. **Status: not yet resequenced or
   drafted — next up.**
2. **FMT-1 design-gate treatment.** Owner: Claude, Model: Opus (for the spec-writing pass
   itself, not just a post-hoc review). Already routed in `formatting-rules/tasks.md` — FMT-1 is
   the highest-leverage doc in the epic (every downstream formatter and roughly half of
   `strategy-rollout/` inherits its decisions), so it gets the stronger model at write-time, not
   just at commit-review time. **Status: routing recorded, ready to execute whenever `FMT-1`'s
   session runs — no further plan edit needed.**
3. **ROLL-7–16 parallelization restructure.** Owner: Claude, Model: Sonnet. `ROLL-7` through
   `ROLL-16` are each blocked only on "`backbone/` + `formatting-rules/` complete," not on each
   other (`ROLL-15`/`ROLL-16` are the one pair that must stay sequential — both touch
   `paper_3track_snapshot.py`). Dependency notes are already annotated inline in
   `strategy-rollout/tasks.md`; formalizing this into explicit parallel "waves" for actual
   multi-session execution is lower urgency — it only pays off once `backbone/` +
   `formatting-rules/` are fully landed and those sessions are about to start. **Status:
   dependency notes recorded, wave-grouping restructure not yet done.**
4. **FMT-1b–1e session bundle.** Owner: Claude or Antigravity (either fine), Model: Sonnet.
   Pure session-count housekeeping — collapse four already-fully-specced, non-overlapping
   doc-only tasks into one session instead of four. Zero risk, zero urgency. **Status: bundling
   note recorded in `formatting-rules/tasks.md`, not yet executed.**

---

## Message-by-message format iteration

`message-format-workshop.md` (this directory) is a **reusable** prompt, not tied to one task —
use it every time you want to iterate a specific Telegram message's format live (paste a
before/after, or ask for a suggestion), confirm it on-device via a scratch script, and have the
confirmed result written back into `strategy-rollout/stories.md`/`tasks.md`. This is how ROLL-1
(IC EOD audit) was actually produced; use it for ROLL-2 onward instead of writing a message's
final format directly into `stories.md` without a live-confirmed reference script.

## Conventions

Same as `docs/plan/README.md` — each folder has `prompt.md` (session entry point), `tasks.md`
(first-unchecked-box protocol), `stories.md` (implementation spec).

**Central entry point (added 2026-08-12):** `prompt.md` in this directory (the epic root) picks
the right folder for you — P0 `backbone/` → P1 `formatting-rules/` → P2 `strategy-rollout/`,
first unchecked box, with the Owner/Model/Review routing check built in. Use it instead of
manually picking a folder-level `prompt.md`; it reads the folder-level one for you once it's
found the task. The folder-level `prompt.md` files still exist and still work standalone — the
central one is a router in front of them, not a replacement.
