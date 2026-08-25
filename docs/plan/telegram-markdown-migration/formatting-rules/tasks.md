# Telegram Markdown Migration — Formatting Rules — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/telegram-markdown-migration/formatting-rules/stories.md`.

> **Routing (added 2026-08-12, Cowork design-review session):** `Owner` is who implements —
> `Claude` for judgment-call/exploratory work, `Antigravity` for mechanical multi-file work with
> an unambiguous spec. `Model` is the model the owner should run at. `Review` is the mandatory
> gate per root `CLAUDE.md`'s Agent AutoTrigger table. Routing is a recommendation to
> re-confirm at session start, not a hard override of the AutoTrigger table.

---

- [x] **FMT-1** — Write the decimal/alignment formatting spec (per-parameter-type rules) —
      docs only, no code | Blocked by: none | SHA: c252bf3 — shipped as root `FORMATTING.md`
      | Owner: Claude | Model: **Opus (design review recommended before finalizing)** |
      Review: n/a — this is the highest-leverage doc in the epic; every downstream formatter
      (`FMT-2`/`FMT-3`) and roughly half of `strategy-rollout/` inherits its decisions. A mistake
      here propagates silently through ~16 `ROLL-*` tasks. Worth the stronger model on the
      spec-writing pass itself, not just at the code-review gate.
- [x] **FMT-1f** — Document the signed-money override (`format_money(value, signed=True)`) +
      Contango/Backwardation (futures roll) vs. Debit/Credit (option-premium roll) spread
      labels — docs only, no code (implementation lands with whichever `ROLL-*` task promotes
      these into real code) | Blocked by: FMT-1 | **Added 2026-08-25 — fully specced in
      `stories.md` since the `ROLL-9` workshop session (2026-08-10) but had no line here, so the
      first-unchecked-box protocol could never reach it; the `format_money(signed=True)` row
      was folded into `FORMATTING.md` §3 as part of FMT-1's session, the two spread-label rows
      were not, they need this task to land in real docs.**
      | Owner: Claude | Model: Sonnet | Review: none — bundle with FMT-1b/1c/1d/1e per the epic
      improvement notes
- [x] **FMT-1b** — Add `pnl_emoji`/`alert_emoji` dynamic status-emoji helpers + tests
      (presence/sign-based, not substring-matched — see stories.md for the rejected design) |
      Blocked by: FMT-1, `backbone/` MD-1
      | Owner: Claude | Model: Sonnet | Review: none — bundle this session with FMT-1c/1d/1e
      (see epic improvement notes); each has an explicit implementation-time judgment call, not
      Antigravity material
- [x] **FMT-1c** — Add IC EOD audit timeframe color/emoji header + hashtag
      (`weekly`/`monthly`/`leaps`/`yearly` × V1/V2 — color+emoji encode timeframe only, version
      is a separate text badge; hashtag must not be code-span-wrapped) | Blocked by: FMT-1,
      `backbone/` MD-1 — file location (IC-specific vs. `src/notifications/formatting.py`) is an
      implementation-time judgment call, see stories.md
      | Owner: Claude | Model: Sonnet | Review: none — bundle with FMT-1b/1d/1e
- [x] **FMT-1d** — Document the multi-strategy summary table money exception (signed integer,
      no `₹` per cell, zero-as-`-`) + `Flt`/`Bkd` terminology + bucket-grouping/totals-first
      table convention — docs only, no code (implementation lands with `ROLL-6`'s table
      builder) | Blocked by: FMT-1
      | Owner: Claude | Model: Sonnet | Review: none — bundle with FMT-1b/1c/1e
- [x] **FMT-1e** — Document the monospace-table emoji-presentation-glyph risk (extends FMT-3's
      emoji-breaks-alignment warning to any Unicode symbol with an emoji-presentation variant,
      not just literal emoji — e.g. `▶` renders double-width on Telegram even inside a fence) —
      docs only, no code | Blocked by: FMT-1
      | Owner: Claude | Model: Sonnet | Review: none — bundle with FMT-1b/1c/1d
- [ ] **FMT-2** — Add `src/notifications/formatting.py` value formatters
      (`format_money`, `format_greek`, `format_strike`, `format_pct`) + tests |
      Blocked by: FMT-1, `backbone/` MD-1
      | Owner: Antigravity | Model: n/a | Review: none — clean formatter functions, exhaustive
      spec, mechanical
- [ ] **FMT-3** — Add table-builder helpers (`build_kv_table`, `build_side_by_side_kv_table`,
      `build_leg_table`) to the same module + tests | Blocked by: FMT-2
      | Owner: Claude | Model: Sonnet | Review: none, but keep a human/Claude judgment pass on
      width computation — this is where the original hand-counted-width bug lived
      (`build_comparison_report()`), don't fully delegate the alignment logic
- [ ] **FMT-4** — Docs close: `src/notifications/CLAUDE.md`, `CONTEXT.md`, `TODOS.md` |
      Blocked by: FMT-3
      | Owner: Antigravity | Model: n/a | Review: none (docs only)
