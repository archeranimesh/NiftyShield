# NiftyShield — Weekly Audit Skill

> Invoke on demand to check whether recent sessions missed a Claude Code feature (graph
> tools, subagents/forks, skills, bash-output aggregation) that would have helped.
> Trigger phrases: "weekly audit", "feature audit", "run the weekly audit"
>
> Goal: cheap, aggregate-first review. Read `session_audit.jsonl` rows (small, structured,
> written by `.claude/skills/session-close/SKILL.md` Step 4c) before ever touching a raw
> transcript. Only drill into a specific session's `.jsonl` when the aggregate flags it as
> ambiguous — most of the answer should come from the log alone.
>
> **On-demand only.** Not wired to cron or `/loop` — invoke manually when you want a check.
> This is deliberately the cheapest version: prove the value before committing to a
> recurring schedule.

---

## Step 1 — Read the log

```bash
python -m scripts.dev.session_audit_log read --since <YYYY-MM-DD, default: 7 days ago>
```

If the file doesn't exist yet or returns zero rows, report "No sessions logged since
`<date>` — nothing to audit yet." and stop. Do not fall back to scanning raw transcripts to
manufacture a result.

---

## Step 2 — Aggregate

Over the returned rows, compute:

- Totals: `graph_calls`, `raw_read_violations`, `bash_output_violations`, `subagent_spawns`,
  `suggestions_count`, summed across the window.
- Which `skills_invoked` appeared at all, and which sessions invoked none.
- Any session with `raw_read_violations > 0` or `bash_output_violations > 0` but
  `suggestions_count == 0` — a violation the same session's own `session-close` run didn't
  turn into a suggestion, worth a second look.
- Any session with zero `subagent_spawns` and zero `skills_invoked` — a plain, un-tooled
  session; not inherently a problem, but worth naming if it recurs across the window.

This covers the majority of what's actionable from the log alone — no transcript read
needed for a clean week.

---

## Step 3 — Drill into flagged sessions only

For each session flagged in Step 2 (violation with no matching suggestion; recurring
un-tooled pattern), extract detail from that one session's transcript using the same
targeted `jq` extraction `session-close` Step 1 uses — never a raw `Read` of the transcript:

```bash
jq -r 'select(.type=="assistant") | .message.content[]? | select(.type=="tool_use") |
  "\(.name)\t\((.input.file_path // .input.qualified_name // .input.query //
  .input.pattern // .input.subagent_type // .input.skill //
  (.input.command|tostring))[0:120])"' ~/.claude/projects/*/<session_id>.jsonl
```

Only do this for flagged sessions — the point of Step 1/2 is to make this the exception,
not the default path.

---

## Step 4 — Report

Print a one-screen report. No file writes — this is a review surface, not a state mutator;
if a pattern looks worth tracking long-term, name it and let the user decide whether to feed
it into `suggestions.md` by hand.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WEEKLY AUDIT — since <YYYY-MM-DD> — <N> sessions
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TOTALS
  Graph calls:              <N>
  Rule 0 violations:        <N>
  Rule 1 violations:        <N>
  Subagent spawns:          <N>
  Suggestions logged:       <N>

SKILLS INVOKED THIS WINDOW
  <skill>: <count of sessions>, ...
  Sessions with no skill/subagent use: <N> / <total>

FLAGGED SESSIONS
  <session_id> (<date>): <one-line reason + one-line finding from Step 3 drill-in>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If nothing was flagged: "Clean window — no missed-feature signal in <N> sessions."
