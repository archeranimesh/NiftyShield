# NiftyShield — Plan Loop Skill

> Invoke whenever Animesh asks to run a `docs/plan/` story, epic or `tasks.md` as a loop. Trigger phrases: "loop execution of docs/plan/…", "run this story in a loop", "loop through the tasks",
> "execute chart-core like gamma-near-expiry", "/loop" aimed at a plan folder. Goal: one fixed, token-lean process for every loop run — a fresh worker subagent per task, a 45-minute gap between tasks,
> a scripted docs close, and hard stop rules — so the main session stays small and the run is the same every time.

---

## Defaults (apply without asking)

| Setting | Default | Override only if Animesh says so |
|---|---|---|
| Gap between tasks | **45 minutes** (`ScheduleWakeup` `delaySeconds: 2700`) | any other gap he names |
| Implementer | **Claude** (a worker subagent) for every task, whatever the `Owner:` tag says | "pause at Antigravity tasks" |
| Stop at | story complete, or any stop rule below | "one task per wake-up, wait for me" |

Ask a question only if the target folder is ambiguous. Everything else is decided by this table; state the settings in one line and start.

## Why this shape

Running every task in the main session accumulates specs, code, test output and subagent reports for the whole epic; late tasks run worse for it. Here the **main session only orchestrates** — a few
hundred tokens per tick — and each task runs in a fresh `general-purpose` worker. Subagents may spawn subagents (3 layers by default, `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, per the sub-agents docs),
so the worker runs the `test-runner` and `code-reviewer` gates itself. Never `fork` the worker: a fork clones the whole conversation, which defeats the point.

Do **not** use `CronCreate` for the gap: `*/45 * * * *` fires at :00 and :45, giving alternating 45- and 15-minute gaps. `ScheduleWakeup` gives an exact gap.

## Procedure — one tick

1. **Locate the work.** Read the story's `tasks.md` header (`**Open: …**`). If it says `none`, the story is complete → go to *Finish*.
2. **Spawn one worker** (`general-purpose`, never `fork`) with the prompt template below. Fill in the story folder only; the worker re-derives everything else from the files.
3. **Read only the worker's report** (≤10 lines). Do not read its transcript or re-run its checks.
4. **Decide.** Report starts with `STOP:` → call `ScheduleWakeup` with `stop: true`, tell Animesh the reason, end. Otherwise → `ScheduleWakeup` (`delaySeconds: 2700`, `prompt` = the original `/loop`
   input verbatim, prefixed `/loop `), write a two-line status for Animesh (task closed, SHAs, next task, wake time), end the turn.

Never poll the worker or any subagent; the harness notifies on completion.

## Worker prompt template

> You are closing exactly ONE task of the NiftyShield plan story `<story folder>`. Work in `/Users/abhadra/myWork/myCode/python/NiftyShield`. Follow `CLAUDE.md`.
>
> 1. Read `CONTEXT.md` and state `CONTEXT.md ✓`. Read the story `prompt.md`, `tasks.md`, and the first unchecked task's section in `stories.md`. Do only that task. Implement it yourself
>    regardless of the
>    `Owner:` tag. Graph before Read for `src/` and `scripts/` (Rule 0); tests are mandatory; follow the task's "Before any code" step.
> 2. Run targeted tests and `ruff check` / `ruff format` on what you touched while developing.
> 3. Gates, each as a subagent you spawn yourself: `test-runner` (full `tests/unit/`, once, after edits are done), `code-reviewer` (before the code commit), plus any reviewer the task's
>    `Review:` tag names
>    (e.g. `greeks-analyst`). Tell every gate subagent it is read-only — no edits, no index/stash-mutating git commands. Resolve every CRITICAL/ERROR; fix cheap WARNINGs, document deferred ones.
> 4. Commit the code: `git add <specific files>`, imperative subject ≤60 chars, a `Why:` body, the attribution line from the session. Run `git log --oneline -1` and keep the SHA.
> 5. Close the docs with `python -m scripts.dev.close_task <tasks.md> --task <ID> --sha <SHA> --summary "<one line>"`. Fix by hand anything it flags `CHECK BY HAND`. Run
>    `python -m scripts.dev.reflow_md` on any other `.md` you edited. Commit the docs (`docs(plan): close <ID>, point epic at <next>`).
> 6. Report in ≤10 lines: task id, both SHAs, full-suite counts, review findings (counts + anything deferred), and anything Animesh must decide.
>
> **Stop without committing anything further** and begin your report with `STOP:` if: a test is red, a CRITICAL/ERROR finding cannot be resolved, the task needs a council-worthy decision
> (CLAUDE.md Step 2b:
> load-bearing, two defensible approaches, multi-discipline), or the spec and the code disagree in a way the spec cannot settle. Do not work around it.

## Stop rules (mirrors the worker's)

Red test · unresolved CRITICAL/ERROR review finding · council-worthy decision · spec/code conflict. A red test stops the run even if it looks unrelated to the task — report it and let Animesh decide
(once it was a midnight-IST date-boundary flake that passed hours later). Never skip a gate to keep the loop moving.

## Finish

Story complete: run the `session-close` subagent per `CLAUDE.md` Step 5d (a fresh `general-purpose` subagent, not `fork`), do the epic's "Completion → archive" convention from `docs/plan/README.md`
§Conventions only if **both** sub-stories are done, call `ScheduleWakeup` with `stop: true`, and summarise the run for Animesh. If he stops the loop early, do the same stop call and note that Step 5d
was skipped.

## Related

`scripts/dev/close_task.py` (deterministic docs close) · `/work` (single task, interactive) · `protocol-reference` §3 (Antigravity handoff, used only when Animesh routes a task there) · `CLAUDE.md`
Steps 3–5.
