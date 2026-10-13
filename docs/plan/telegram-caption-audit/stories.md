
# Telegram Message Caption-Fit Audit — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

---

## TCA-1 — Inventory Telegram message types

**Files to change / create:**
- `docs/plan/telegram-caption-audit/findings.md` — new; inventory table (no code files touched)

**Before any code (graph queries):**
- `search_graph("send")` scoped to `src/notifications/`, then `trace_path("TelegramNotifier.send")` and `trace_path("TelegramGateway.send_photo")` for every caller
- `search_code("notifier.send|gateway.send|send_payoff_chart")` over `src/` and `scripts/` to catch call sites the graph misses
- Read `src/notifications/CLAUDE.md` and `FORMATTING.md` for the formatter and escaping contract

**What to do:**

1. List every distinct message type (snapshot, entry, exit, roll, alert, error, daily summary, etc.), not every call site. Group call sites that share one formatter.
2. Per type record: trigger, entry script or strategy, formatter function, parse mode, and whether `send_payoff_chart` fires alongside it today.
3. Note any message that already goes through `send_photo` with a caption.

**Tests:** none. Read-only.

**Commit:** `docs(plan): inventory Telegram message types`

---

## TCA-2 — Measure rendered lengths

**Files to change / create:**
- `docs/plan/telegram-caption-audit/findings.md` — add measured lengths per type
- `scratch/<name>.py` — optional throwaway measurement script, named per `SCRATCH.md`; not committed unless SCRATCH.md says to promote

**Before any code:**
- `get_code_snippet` on each formatter found in TCA-1, and on the model it consumes, so fixture construction is not written from memory
- Locate existing fixtures and tests that already render each message (`tests/unit/notifications/`, `tests/fixtures/`)

**What to do:**

1. For each type, render the final escaped MarkdownV2 string using existing fixtures, for a small case (e.g. 2-leg), typical (4-leg IC) and worst case (max legs, long symbols, large P&L figures).
2. Record length in characters after escaping, and also after entity parsing (strip backslashes and markup) since Telegram's 1024 limit counts parsed text. Record both so the verdict is defensible.
3. Where no fixture exists, say so in findings rather than inventing numbers.

**Tests:** none. No network, no real DB, no real token.

**Commit:** `docs(plan): measure Telegram message lengths`

---

## TCA-3 — Verdicts and recommendations

**Files to change / create:**
- `docs/plan/telegram-caption-audit/findings.md` — verdict column, summary counts, recommendations section

**What to do:**

1. Verdict per type: fits as caption (parsed length ≤ 1024 at worst case), fits with trimming (typical fits, worst case does not), or needs split (photo with short caption plus follow-up text).
2. For each trimmed or split type, propose the caption content (headline, strategy, expiry, P&L) and what moves to the follow-up message.
3. State the totals and the open risks from `prompt.md` Perspectives not covered. Do not implement; end with a proposed shape for the follow-up story and ask Animesh to review.

**Tests:** none.

**Commit:** `docs(plan): add Telegram caption-fit verdicts`
