# NiftyShield — New Story Scaffold Skill

> Invoke to start a new `docs/plan/` story or epic folder from `docs/plan/_TEMPLATE/`. Trigger phrases: "start a new story", "new plan folder", "scaffold a story", "/new-story". Thin wrapper around
> `scripts/dev/new_plan_folder.py` — the script does the work, this skill only gathers the inputs.

---

## Step 1 — Ask story vs. epic

If not already stated by the invoking message, `AskUserQuestion`:

- **Question:** "Story or epic?"
- **Options:** `Story` (one coherent goal, however many tasks) · `Epic` (two or more related stories shipped together — you'll scaffold the root now and each sub-story separately)

## Step 2 — Ask slug and title

- **Slug:** kebab-case, no date prefix (e.g. `risk-gamma-phase-a`). Validate against the pattern the script enforces before running it — lowercase letters, digits, single hyphens between words.
- **Title:** free text. If the user has none ready, let the script default to Title Case of the slug — do not block on this.
- **Epic sub-story only:** also ask which existing epic slug this belongs to (`--into <epic-slug>`).

## Step 3 — Run the script

```bash
python -m scripts.dev.new_plan_folder --story <slug> [--title "<Title>"] [--into <epic-slug>]
python -m scripts.dev.new_plan_folder --epic <slug> [--title "<Title>"]
```

A non-zero exit means the slug was invalid or the target already exists — report the stderr line verbatim, do not retry with a mangled slug.

## Step 4 — Report and hand off

Print the created path and its file list (the script's own stdout already has this). Then tell the user:

- For a **story**: fill in `prompt.md` (why it exists, scope guard), `tasks.md` (task ids + `| Owner | Model | Review | SHA |` lines), `stories.md` (per-task spec). Keep `schema.md.example` →
  `schema.md` only if the story changes DB schema — the script already dropped it by default.
- For an **epic**: fill in the root `prompt.md` (router — story order) and `README.md` (shared brief, scope decisions, story-status table), then run this skill again once per sub-story with `--into
  <epic-slug>`.
- Either way: `docs/plan/README.md` §Conventions has the full field-by-field spec if anything is unclear.

Do not write any story content yourself unless the user asks for that as a separate step — this skill's job ends at a clean scaffold.
