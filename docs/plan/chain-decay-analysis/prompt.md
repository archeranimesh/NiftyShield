Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/chain-decay-analysis/tasks.md` and find the first unchecked box. That is your **only
task** for this session. Do not look at any other unchecked item. One task. Complete it fully.
Stop.

**Story spec:** Read the matching story in `docs/plan/chain-decay-analysis/stories.md` for the
full spec.

**Background:** Animesh wants to know, empirically, whether intraday option premium moves track
what delta predicts, or whether there's a meaningful residual — and separately, whether some
strikes decay faster than theta alone would explain. The data to answer this already exists:
`data/historical/option_chain/intraday/{year}/{month}/{day}/upstox_{HHMM}_{label}.parquet`,
written every 5 minutes during market hours since 2026-06-01 (confirmed via Cowork session
2026-08-06 — 42 trading days present as of that date), via `ChainWriter`/`ChainReader`
(`src/backtest/chain_writer.py`, `src/backtest/chain_reader.py`). Full chain, all strikes, both
sides, not filtered by liquidity — confirmed by row-level cross-check against a live diagnostic
pull the same session (monthly and quarterly bucket rows matched exactly on strike, ltp, oi, iv).

**Scope for this story: monthly bucket only.** The yearly bucket has a confirmed, persistent,
unresolved zero-Greeks defect (`docs/plan/greeks-bs-fallback/`, GF-1 findings) — delta/gamma/
theta/vega/iv all exactly 0.0 on every yearly strike as of 2026-08-06, three weeks after first
confirmed. Do not attempt this analysis on the yearly bucket; the Greeks needed for the
delta-decomposition math don't exist there yet (pending that story's GF-2..GF-5). Quarterly is a
plausible second pass once monthly is validated, but is not this story's Task 1 scope — quarterly
also has known degenerate-Greeks rows on deep-OTM illiquid strikes (pinned delta ±1.0, all other
Greeks 0.0 — same pattern documented in `greeks-bs-fallback/stories.md` GF-1) that this story's
strike-filtering logic must exclude regardless of which bucket it runs against.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first using the
graph. Order: `git log` → graph query (`search_graph`/`get_code_snippet`/`trace_path`) →
`search_code` → `sed -n` → `Read` (state why the graph was insufficient).

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` first (e.g. `OptionChain`, `OptionChainStrike`) — do not
write fixtures from memory.

**This is read-only analysis over already-captured historical data — no live capital path, no
new capture pipeline.** It does not touch strike selection, entry/exit signals, or any paper
trade execution. Standard code-reviewer gate applies (any `.py` under `src/`/`scripts/`/`tests/`),
but this is NOT financial-logic-gated the way `greeks-bs-fallback/` is — no `@greeks-analyst`
subagent required, since nothing here feeds live/paper trading decisions. If a later story wires
this analysis's output into an actual strategy decision, that story inherits the financial-logic
gate; this one does not.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing. New tests use static/synthetic fixture chains — no network,
no dependency on the real Parquet store existing at test time.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft
it and stop.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.
