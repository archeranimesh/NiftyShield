Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/telegram-leg-labels/tasks.md` and find the first unchecked box. That is your
**only task** for this session. Do not look at any other unchecked item. One task.
Complete it fully. Stop.

**Origin:** Live Telegram alert `AUTO-CLOSE FAILED — paper_nifty_spot / overlay_collar_call`
showed the leg as raw `NSE_FO|65900` — unreadable without a manual BOD lookup. Confirmed
these are Upstox's real numeric instrument keys (not symbol-embedded strings — see
`src/risk/CLAUDE.md` note "real Upstox keys are numeric-only"), so no regex on the key
itself can recover strike/expiry/type. The only path to a human label is resolving through
`InstrumentLookup.get_by_key()` against the offline BOD JSON.

**Story spec:** Read the matching story in `docs/plan/telegram-leg-labels/stories.md` for
the full spec.

**Hard constraint — do not violate:** Only *prose* Telegram/log message text gets the
human label. Any line that is a literal CLI command to be copy-pasted and executed
(e.g. `python -m scripts.record.record_paper_trade ... --key NSE_FO|44498 ...`) must keep
the raw `instrument_key` unchanged — that is the exact string the script's `--key` flag
expects. Never reformat text inside a `cmd = [...]` list or an f-string that is printed as
an executable command.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first using
the graph. Order: `git log` → `search_graph`/`get_code_snippet` → `search_code` →
`sed -n` → `Read` (state why the graph was insufficient).

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` first — do not write BOD instrument dict fixtures
from memory; confirm field names (`trading_symbol`, `instrument_type`, `strike_price`,
`expiry`, `segment`) against `format_results()` in `src/instruments/lookup.py` first.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not
draft it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.
