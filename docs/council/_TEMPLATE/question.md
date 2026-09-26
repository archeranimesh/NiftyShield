<!-- Copy to tmp/q<N>_<topic-slug>.md. Delete this comment and every other HTML comment
before submitting. Keep prose lines filled to ≤200 chars (see reflow_md, MEMORY.md). -->

# <One-line topic — matches tasks.md / bugs.md wording>

## System Context

<!-- What exists today, cited with exact file:line references (pull these from the graph,
Rule 0 — search_graph / get_code_snippet, not a cold Read). State the module(s) involved,
the relevant model(s)/field(s), and the call sites that touch the behaviour in question. -->

**Bug / trigger (if applicable):** <!-- BUG-### or story id, filed/opened date, one-line
description of what surfaced the need for this decision. -->

## Mechanics of the problem

<!-- Concrete, cited walk-through of why this is load-bearing: what breaks, what silently
does the wrong thing, and under what conditions. This is the section a council model reads
to understand the failure mode without any other context. -->

## Relevant existing machinery

<!-- Bullet list of the exact classes/functions/scripts that any answer must go through,
each with a file:line or file reference. -->

**Already decided / out of scope for the council:**

| Parameter | Decision |
|---|---|
| <!-- prior decision that must NOT be re-litigated --> | <!-- where it's recorded --> |

## The decision to resolve

### Option A — <name>

<!-- Concrete mechanics: what changes, what stays, what it costs. -->

### Option B — <name>

<!-- Concrete mechanics: what changes, what stays, what it costs. -->

<!-- Add Option C only if a third approach is genuinely distinct — don't force a third
option to exist. -->

## Q1 — <precise question tied to Option A vs B>

<!-- One focused question per numbered heading. Each should be answerable independently
where possible; note dependencies between them explicitly if not. -->

## Q2 — <follow-on question, e.g. data source / detection / retrofit scope>

---

## Required Council Output Format

```
## Summary Table

| Decision | Recommendation |
|----------|---------------|
| <row per Q above> | |

## Design Rationale
[Why the recommended option is correct given the specific constraints named above.]

## Data Model / Schema Detail
[If the decision touches storage: exact schema/field changes. Otherwise: exact command
or call-site changes and every field/module they touch.]

## Historical Data Handling
[Only if existing data is affected — omit this section otherwise.]

## Dissenting Notes
[Panel disagreements, particularly on the primary option split.]
```
