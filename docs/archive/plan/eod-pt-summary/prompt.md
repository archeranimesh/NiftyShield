Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/eod-pt-summary/tasks.md` and find the first unchecked box. That is your
**only task** for this session. Do not look at any other unchecked item. One task.
Complete it fully. Stop.

**Origin:** A Cowork session (2026-08-13) iterated the shape of this report live in
`scratch/2026-08-13_eod_pt_summary.py` — cross-strategy open positions, a "closed
today" table, and a strategy-wise P&L/annualized-%-on-margin summary, confirmed
message-by-message with Animesh before this epic was written up. That script is the
reference implementation for every task below; read it before writing any code.

**Story spec:** Read the matching story in `docs/plan/eod-pt-summary/stories.md` for
the full spec, including the exact function names/signatures the scratch script
already validated.

**Known coordination point — read before starting PT-2:** `scripts/eod_summary.py`
is an existing production cron (already in scope of
`docs/plan/telegram-markdown-migration/README.md`'s ROLL-6, ""EOD Paper Summary""
message) that sends a coarser NAV-snapshot-based summary from `paper_nav_snapshots`.
This epic's report is a different, richer thing (live per-leg detail, closed-today,
margin/Ann.%) built off `PaperStore.get_positions()`/live broker LTP, not the nav
snapshot table. Do not assume it's a drop-in replacement without confirming with
Animesh — PT-2's story spec has the specific question to ask before touching
`scripts/eod_summary.py`. Also check `docs/plan/paper-ic-daily-snapshot/` (archived,
SNAP-4 built `scripts/reporting/paper_pnl_report.py`) for a second possibly-related
existing report before assuming this is greenfield.

**Graph-before-Read rule:** Never call `Read` on `src/` without first using the
graph. Order: `git log` → graph query → `search_code` → `sed -n` → `Read` (state
why).

**Non-fatal contract:** Every existing Telegram-sending script in this repo treats
send failures as non-fatal (log + continue, never raise past the caller). Any code
promoted from the scratch script must preserve that — the scratch script's
`_send_telegram_markdown()` already does this correctly; do not regress it while
porting.

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` first (e.g. `PaperPosition`, `PaperTrade`,
`MarginSnapshot`) — do not guess field names from the scratch script's local
tuples.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing. No network in tests — mock `BrokerClient` and
`TelegramGateway`/the raw `aiohttp` send call.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit —
do not draft it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to
`TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.
