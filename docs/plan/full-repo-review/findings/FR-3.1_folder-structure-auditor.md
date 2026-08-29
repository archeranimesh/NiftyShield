# FR-3.1 — Full Folder Structure & Taxonomy Review

**Persona: Folder Structure Auditor.** Run as: **Sonnet**, Date: 2026-07-05.

**Scope read:** full repo directory tree (`find . -type d`, VCS/cache/build noise excluded),
targeted `ls`/`find` on every subfolder named below, `git log --oneline` on flagged path pairs,
`git ls-files` on `scratch/`/`tmp/` to check VCS-tracking status, `.gitignore`, `pyproject.toml`
`[tool.pytest.ini_options]`, `docs/council/README.md`, `docs/archive/plan/README.md`,
`CONTEXT_TREE.md` (grepped, not read in full — no `data/` section found). Depended on
`findings/FR-3_systems-architect.md` for F8/F9 and the `docs/archive/council/`+`docs/archive/plan/`
listings rather than re-deriving them. No other file contents read except one-line greps to confirm
flagged items are not false positives (per task scope).

---

## 1. Full directory tree sorted into four buckets

### Code — `src/`, `scripts/`, `tests/`

`src/`: `auth`, `backtest`, `client`, `council`, `dhan`, `gamma`, `instruments`, `intraday`,
`market_calendar` (+`market_calendar/data`), `mf`, `models`, `notifications`, `nuvama`, `paper`,
`portfolio` (+`portfolio/strategies/finideas`), `risk`, `strategy`, `utils` (+`niftyshield.egg-info`,
a build artifact, not a package).

`scripts/`: `council` (+`council_templates`), `dev`, `intraday`, `lookup`, `pipeline`, `portfolio`,
`record`, `seed`, `strategies` (+`cc_calibration`, `csp`, `ic`, `three_track`).

`tests/`: `fixtures` (+`amfi`, `responses/{bhavcopy,historical_candles,market_quote,option_chain,
orders}`, `vix`), `unit` (+`auth`, `backtest`, `council`, `dhan`, `gamma`, `instruments`, `intraday`,
`market_calendar`, `mf`, `notifications`, `nuvama`, `paper`, `portfolio`, `risk`, `scripts`,
`strategies` (+`ic`), `strategy`, `utils`).

### Docs-active — `docs/plan/`, `docs/council/`, `docs/bugs/`, root markdown

`docs/plan/`: `backtest-eval-core`, `broker-abstraction` (+`stories`), `dev-foundation`
(+`code-health`), `full-repo-review` (+`findings`), `historical-data-abstraction` (+`stories`),
`mvp`, `options_income`, `paper-exit-codification`, `paper-store-position-granularity`,
`risk-gamma-phase-a`, `signals`, `signals-eval-core`, `telegram-leg-labels`, `variance-gate`.
`docs/council/` (active/pending decisions only — no `archive/` subfolder present here, see F10).
`docs/bugs/`. Root markdown (19 files): `AGENTS.md`, `ANTIGRAVITY.md`, `BACKTEST_PLAN.md`,
`BACKTEST_PLAN_PHASE1.md`, `BUGS.md`, `CLAUDE.md`, `CONTEXT.md`, `CONTEXT_TREE.md`, `DECISIONS.md`,
`GLOSSARY.md`, `INSTRUCTION.md`, `LITERATURE.md`, `LOGGING.md`, `MISSION.md`, `PLANNER.md`,
`README.md`, `REFERENCES.md`, `REVIEW.md`, `TODOS.md`.

Two directories that don't fit cleanly in any of the task's four named buckets but are
"docs-active" by nature: `docs/instructions/` (`3track.md`, `csp_nifty_v1.md`, `paper_trade.md`,
`prompt.md`) and `docs/viz/` (`3track_comparison.html`) — see F15. `docs/strategies/`
(`regime_probe.pine`, cited live in `CONTEXT.md`) also lives outside the four named buckets;
placed here since `CONTEXT.md` treats it as active research tooling, not archive.

### Docs-archive — all of `docs/archive/`

Confirmed 12 top-level entries (2 files + 10 subfolders), only 2 of which FR-3 sampled
(`council/`, `plan/`):

- `BACKTEST_PLAN_ARCHIVE.md`, `TODOS_ARCHIVE.md` (loose files, not folders)
- `analysis/` (2 files, flat)
- `antigravity/` (2 files, flat)
- `council/` (`data_architecture/`, `misc/`, `research/`, `strategy/` — FR-3 sampled this)
- `covered-call-overlay/` (flat: `ARCHIVED.md`, `prompt.md`, `schema.md`, `stories.md`, `tasks.md`)
- `ic-e2e/` (flat + `stories/` subfolder, `_DEPRECATED.md` marker)
- `ic-full/` (flat + `stories/` subfolder, no deprecation marker)
- `ic-multi-expiry/` (flat + `stories/` subfolder, `_DEPRECATED.md` marker)
- `ic-nifty-v2/` (flat: `prompt.md`, `stories.md`, `tasks.md` — no `stories/` subfolder, no
  deprecation marker; the seed issue's subject)
- `plan/` (FR-3 sampled this; see F13 below for a correction to FR-3's framing)
- `process/` (2 files, flat)
- `research/` (3 files, flat)
- `reviews/` (4 files, flat)
- `strategies/` (4 files + `archive/` subfolder containing 1 more file)

### Config-and-data — `data/`, `.github/`, root config files

`data/` (gitignored, structure-only): `historical/ohlc/india_vix/{2016..2026}`,
`historical/option_chain/{eod,intraday}/2026/{06,07}[/DD]`, `instruments/`, `market_holidays/`,
`nuvama/{instruments,logs}`, `offline/{chain_snapshots,chain_snapshots_5min,options_ohlcv}/...`,
`paper/`, `portfolio/`, `samples/truedata/{1min,tick}`. `.github/workflows/ci.yml` (single file,
no other `.github/` subfolders). Root config: `pyproject.toml`, `Makefile`,
`.pre-commit-config.yaml`. Also present at repo root but not covered by the task's three
config-and-data examples: `config/` (single file, `logrotate.conf` — not gitignored, not
mentioned in `CONTEXT.md`/`CONTEXT_TREE.md` at all), `scratch/` and `tmp/` (see F16),
`tools/llm-council/` (external tool source, has its own `backend/`, `frontend/{public,src/
{assets,components}}`, `data/conversations/` — this is the actual council service `scripts/
council/ask_council.py` and `docs/council/README.md` both refer to).

---

## 2. `src/`↔`scripts/` pairing sweep (not just the FR-3 seed pairs)

Cross-referencing `src/` top-level packages against `scripts/` top-level directories:

| `src/` | `scripts/` | Relationship |
|---|---|---|
| `auth` | — | no collision |
| `backtest` | — | no collision |
| `client` | — | no collision |
| **`council`** | **`council`** | **exact-name collision — FR-3 F9, confirmed still holds** |
| `dhan` | — | no collision (scripts live under `scripts/intraday/dhan_intraday_tracker.py`, not a `scripts/dhan/` dir) |
| `gamma` | — | no collision (script is `scripts/pipeline/gamma_daily_watch.py`) |
| `instruments` | — | no collision (`scripts/lookup/instrument_lookup.py` — different dir name, and singular/plural doesn't even apply since it's nested under `lookup/`) |
| **`intraday`** | **`intraday`** | **exact-name collision — FR-3 F9, confirmed still holds** |
| `market_calendar` | — | no collision |
| `mf` | — | no collision (`scripts/seed/seed_mf_holdings.py`) |
| `models` | — | no collision |
| `notifications` | — | no collision |
| `nuvama` | — | no collision (`scripts/dev/probe_nuvama_schema.py`, `scripts/intraday/nuvama_intraday_tracker.py`) |
| `paper` | — | no collision (paper scripts are scattered across `scripts/strategies/`, `scripts/portfolio/paper_snapshot.py`, `scripts/daemon/` per `CONTEXT.md`) |
| **`portfolio`** | **`portfolio`** | **exact-name collision — new finding, not in FR-3, see F10a below** |
| `risk` | — | no collision |
| **`strategy`** | **`strategies`** | **singular/plural — FR-3 F8, confirmed still holds** |
| `utils` | — | no collision |

### F10a — [WARNING, new — FR-3 did not catch this pairing] `src/portfolio/` vs. `scripts/portfolio/` — exact-name collision

`src/portfolio/` (`formatting.py`, `service.py`, `store.py`, `strategies/`, `summary.py`,
`tracker.py` — the P&L model/store/tracker layer) vs. `scripts/portfolio/` (`daily_snapshot.py`,
`morning_nav.py`, `paper_snapshot.py`, `roll_leg.py` — the cron entrypoint scripts that call into
the `src/portfolio/` layer). This is the same shape as FR-3's F9 (`intraday`, `council`) — an
exact name shared by a library layer and its CLI/cron layer, no plural or lexical disambiguator —
and arguably carries **higher stakes than either F9 pair**, since `src/portfolio/` and
`scripts/portfolio/` are both on the critical path for live P&L (`daily_snapshot.py` is the EOD
cron; `roll_leg.py` executes rolls). `git log --oneline` on both paths (10 most recent commits
sampled) shows the same informal disambiguator FR-3 found for `strategy`/`strategies` — commit
prefixes consistently read `fix(portfolio): ...` for `src/portfolio/` changes and
`fix(scripts): ...` for `scripts/portfolio/` changes (e.g. `13b7285 refactor(scripts): move
portfolio scripts to scripts/portfolio/` is the commit that created this exact pairing
deliberately) — so, as with F8/F9, no confirmed misdirected edit in sampled history. Applying
FR-3's own decision matrix: **rating WARNING, not CRITICAL/ERROR** (same reasoning as F9 — the
name is otherwise apt for what each side does, and the informal commit-prefix convention has held
so far), but recommend it be added to the same `CONTEXT_TREE.md` disambiguating-note fix FR-3
proposed for F8/F9, rather than treated as a separate, smaller issue — three same/near-same-name
`src/`↔`scripts/` pairs sharing one root cause (the repo's convention of mirroring module names
between library and entrypoint layers, with no lexical marker) is a taxonomy pattern, not three
unrelated one-offs, and the fix (one `CONTEXT_TREE.md` section listing all three pairs together)
should be authored as such.

**No further src/↔scripts/ collisions found** beyond the four now enumerated (`council`,
`intraday`, `portfolio`, `strategy`/`strategies`) — this sweep is exhaustive over `src/`'s 17
top-level packages, not sampled.

---

## 3. Docs-archive structural check

### F10 — [ERROR, sharpens FR-3 F5] `docs/council/README.md`'s stated taxonomy is stale in a way
that also fails to name 10 of `docs/archive/`'s 12 top-level entries

FR-3's F5 already flagged that `docs/council/README.md` documents `docs/council/archive/
{strategy,risk,research}/` (a path that does not exist) when the real path is
`docs/archive/council/{strategy,risk,data_architecture,misc}/` — 2 undocumented categories
(`data_architecture`, `misc`) within that one folder. This task's wider sweep shows the drift is
larger than F5's framing suggests: `docs/council/README.md` is the *only* doc in the repo that
attempts to describe `docs/archive/`'s shape at all, and it describes exactly one of `docs/
archive/`'s 12 top-level entries (`council/`, and even that one incompletely). The other 11 —
`BACKTEST_PLAN_ARCHIVE.md`, `TODOS_ARCHIVE.md`, `analysis/`, `antigravity/`,
`covered-call-overlay/`, `ic-e2e/`, `ic-full/`, `ic-multi-expiry/`, `ic-nifty-v2/`, `plan/`
(FR-3 sampled this one but no doc names it as part of a taxonomy either — `docs/archive/
plan/README.md` documents `plan/`'s *internal* conventions, not its place among the other 11
siblings), `process/`, `research/`, `reviews/`, `strategies/` — have **no taxonomy document at
all**, active or stale. Rated ERROR (not CRITICAL): nobody is being actively misdirected by a
wrong path today the way F5's dead `docs/plan/variance-gate/prompt.md:18` link does, but a fresh
agent asked "where would X archived strategy doc live" has zero authoritative doc to consult for
9 of the 10 archive subfolders, and would have to enumerate the directory itself (as this task
did) rather than trust any README. **Recommendation:** `docs/council/README.md` should either be
narrowed to only describe `docs/archive/council/`'s own shape (drop the "docs/archive/" framing
implication) and a new top-level `docs/archive/README.md` should be written describing the full
12-entry taxonomy, or (cheaper) `docs/archive/plan/README.md` gets a short preamble note
clarifying it only governs `plan/`'s internal shape, not the archive root's — either way, this is
a docs-only fix, no rename.

### F11 — [WARNING] `ic-e2e/`, `ic-full/`, `ic-multi-expiry/`, `ic-nifty-v2/` are a *pattern* of
top-level archive entries that break the `docs/archive/plan/<story>/` nesting convention, not the
isolated one-off FR-3's seed issue implied

FR-3's seed issue asked whether `docs/archive/ic-nifty-v2/`'s placement (top-level, not nested
under `docs/archive/plan/`) is a one-off. It is not: `ic-e2e/`, `ic-full/`, and `ic-multi-expiry/`
are the same shape — each has a `prompt.md` + `tasks.md` + `stories/` (or `stories.md`) triad
identical to a `docs/archive/plan/<story>/` entry, but sits as a `docs/archive/` top-level sibling
instead. Two of the four (`ic-e2e/`, `ic-multi-expiry/`) carry an explicit `_DEPRECATED.md`
marker file that `docs/archive/plan/`'s convention doesn't use anywhere else in the sampled
listing — suggesting these four may predate the current `docs/archive/plan/<story>/` convention
entirely (an earlier "IC-prefixed top-level archive" era that was never backfilled into `plan/`
when the newer convention was adopted), rather than four independent placement mistakes. This
reframes the finding from "one folder is misplaced" to "an entire earlier archiving convention
was superseded but never migrated" — **higher information value than FR-3's framing, same
WARNING severity** (no confirmed misdirected read found; `git log --grep` on all four shows
commits scoped correctly to their actual paths). **Recommendation:** worth a one-line note in
`docs/archive/plan/README.md`'s (or the new `docs/archive/README.md` per F10) conventions section
acknowledging this predates-the-convention set exists and won't be retroactively moved — cheaper
than migrating four already-archived, already-dead trees for no operational benefit.

### F12 — [INFO, refines FR-3's loose-file framing] `docs/archive/plan/`'s 9 loose files split
into two sub-patterns, not one undifferentiated group

FR-3 and `stories.md`'s seed issue both describe the 9 loose files in `docs/archive/plan/`
(alongside its 7 proper story folders) as a single "loose vs. folder" inconsistency. Checking
each loose file's name against `docs/archive/plan/README.md`'s own stated file-naming convention
(`<phase>_<task>_<slug>.md`, sourced from `BACKTEST_PLAN.md` checkbox numbers) shows they split
cleanly into two groups:

- **Conforms to the documented convention** (pre-dates the folder convention, README's own
  "Initial story files created (2026-04-17)" section explicitly names these as archived
  individually): `0_3_finideas_roll.md`, `1_5b_analytics_module.md`, `1_10_dhan_chain_client.md`.
  These are *not* drift — the README documents exactly why they're loose files, by name.
- **Does not conform, and not named in the README's inventory section**: `PAPER_TRADING_PLAN.md`,
  `mvp_tracker.md`, `story_audit_remediation.md`, `story_paper_impl_tasks.md`,
  `story_risk_gamma_phase_a.md`, `variance_gate.md`, `paper_3track_overlay.md`,
  `paper_3track_roll.md`. `variance_gate.md` *is* mentioned elsewhere in the README's "Initial
  story files" section as archived — so 1 of these 8 is at least referenced, even if not in the
  phase-numbered convention. The remaining 7 have no naming-convention conformance and no
  README mention at all.

This is genuinely two different situations, not one: the first group is documented, intentional,
pre-convention archival (no action needed); the second group (7 files) is the real unaddressed
drift the seed issue was pointing at. Rated INFO because none of these 7 files are live —
they're already archived and nothing currently reads them per any doc checked — but flagging the
split for precision, since FR-9's roadmap should scope any fix to the 7, not all 9.

---

## 4. Docs-active / Config-and-data orphan and referenced-but-missing checks

### F13 — [INFO] No referenced-but-missing directories found in Docs-active or Config-and-data

Checked every directory path named in `CONTEXT.md`, `CONTEXT_TREE.md` (grepped for `data/`,
`docs/`, `src/`, `scripts/` path mentions), and `pyproject.toml` against the actual tree:
`pyproject.toml`'s `testpaths = ["tests/unit"]` matches where tests actually live (confirmed —
`tests/unit/` exists and holds all test files; `tests/fixtures/` is correctly excluded from
`testpaths` since fixtures aren't collected as tests). `data/`'s structure as described inline in
`CONTEXT.md` (`data/portfolio/portfolio.sqlite`, `data/historical/ohlc/india_vix/`) matches what's
on disk. No dead directory references found in this bucket — contrast with FR-3's F5, which found
a dead *file* link (`docs/plan/variance-gate/prompt.md:18` → nonexistent
`docs/council/2026-05-02_...md`) in the adjacent Docs-active/Docs-archive boundary.

### F14 — [WARNING] `data/` has no dedicated structural documentation anywhere — `CONTEXT_TREE.md`
has zero `data/` section

Grepping `CONTEXT_TREE.md` for any `data/`-rooted heading or section returns nothing — the file
that's explicitly supposed to be "load when adding new modules or doing a full structural survey"
(per `CONTEXT.md`'s own pointer) documents `src/`/`scripts/` file-by-file but has no equivalent
for `data/`, even though `data/` has 6 top-level subtrees with non-obvious partitioning logic
(`historical/` split by `ohlc`/`option_chain`, `offline/` as a separate parallel tree for
snapshot/OHLCV data, `nuvama/` nested under `data/` alongside `paper/` and `portfolio/` — the
relationship between `data/nuvama/` and `src/nuvama/` isn't documented anywhere either). `CONTEXT.
md`'s "Live Data" section documents *facts about* specific paths (`portfolio.sqlite`'s tables,
when `mf_nav_snapshots` was last wiped) but never the directory shape itself. Rated WARNING, not
ERROR: `data/` is gitignored, so this isn't a "doc references a path that doesn't exist" problem —
it's a genuine documentation gap for a tree that's grown to 6 subtrees + partition-by-date nesting
without ever getting a `CONTEXT_TREE.md` entry. **Recommendation:** add a `data/` section to
`CONTEXT_TREE.md` mirroring the `src/`/`scripts/` treatment — one line per top-level subtree
stating what it holds and which module writes to it.

### F15 — [WARNING] `config/`, `docs/instructions/`, `docs/viz/` — three small directories with no
documentation anywhere and, for two of the three, no inbound reference from any other doc

- `config/` — single file (`logrotate.conf`), not gitignored, not mentioned in `CONTEXT.md`,
  `CONTEXT_TREE.md`, `README.md`, or `TODOS.md` in any grep. No doc says what rotates the logs it
  configures or that this directory exists.
- `docs/instructions/` — 4 files (`3track.md`, `csp_nifty_v1.md`, `paper_trade.md`, `prompt.md`).
  `git log` shows active history (`b6b5889 docs(council-refactor): add BUG-6 realized P&L
  cross-cycle bug + 3-track overlay analysis rules` is a relatively recent, substantive commit
  touching this folder) — this is not dead content, but no root doc (`CONTEXT.md`, `README.md`,
  `docs/plan/README.md`) links to it or explains its relationship to `docs/plan/`'s story-file
  convention or `docs/strategies/`'s Pine Script tooling. A fresh reader has no way to discover
  `docs/instructions/` exists except by listing the tree.
- `docs/viz/` — single file (`3track_comparison.html`), zero inbound references found via grep
  across all root markdown and `docs/plan/`. Either a genuinely orphaned one-off visualization
  artifact or a legitimate live tool nobody links to — cannot distinguish without opening the
  file, which is out of this task's directory-listing-only scope. Flagging as the clearest
  candidate for either a doc link or removal.

Rated WARNING across all three: none of these cause active harm today (nothing points at a wrong
path), but all three represent the same failure mode as F14 at smaller scale — directories that
exist, have real content, and are invisible to anyone navigating from the documented entry points.

### F16 — [WARNING] `scratch/` is tracked in git; the functionally identical `tmp/` is gitignored
— inconsistent VCS treatment of two directories serving the same purpose

`.gitignore` contains `tmp/` (and separately `/data/`, `logs/`, `logs/snapshot.log`) but has no
entry for `scratch/`. `git ls-files scratch/` confirms all 8 files in `scratch/` are tracked
(`2026-05-28_exit-philosophy_council.sh`, `..._question.md`, `2026-06-02_watchlist-design_council.
sh`, `..._question.md`, `council_ping.sh`, `council_ping_question.md`, and — most notably —
`diff.patch` and `git_diff.diff`, i.e. committed git-diff output files sitting in version
control). `git ls-files tmp/` returns nothing — `tmp/`'s 20+ files (council question drafts,
`check_live_delta.py`, `full_diff.txt`) are correctly untracked. Both directories hold the exact
same *kind* of content — ad hoc council-question scratch files and diff dumps — which means this
isn't a case of one directory legitimately needing version control and the other not; it's the
same workflow (drafting a council question, saving the diff for reference) landing in two
different places with two different (and inconsistent) VCS outcomes, apparently by which
directory name the person or agent happened to type that day. Rated WARNING, not ERROR: no
evidence this has caused a wrong-directory *read*, but `diff.patch`/`git_diff.diff` being
permanently committed is exactly the kind of repo-hygiene rot that compounds silently.
**Recommendation:** either add `scratch/` to `.gitignore` (matching `tmp/`'s treatment, if
scratch content was never meant to be permanent) and remove the 8 already-tracked files in a
follow-up commit, or — if `scratch/`'s tracked status is deliberate (some of these files may be
referenced as historical council-prompt provenance) — rename `tmp/` to something that doesn't
imply the two are interchangeable, and document the distinction. This task does not have enough
context (file-content-level) to pick between the two; flagging as `NEEDS-OPUS-REVIEW` per the
escalation path in `stories.md` only if the resolution turns out to require deciding whether any
of the 8 tracked files are load-bearing provenance — on a first pass this looks like a pure
repo-hygiene call, not one, so leaving as WARNING/Sonnet-resolvable pending confirmation.

---

## 5. Findings summary table

| ID | Severity | Bucket | Finding |
|---|---|---|---|
| F10 | ERROR | Docs-archive | `docs/council/README.md` is the only doc attempting to describe `docs/archive/`'s shape, and covers 1 of 12 top-level entries (incompletely) — sharpens FR-3's F5 |
| F10a | WARNING | Code | `src/portfolio/` ↔ `scripts/portfolio/` exact-name collision — new pairing FR-3 didn't enumerate; same risk class as F8/F9, arguably higher stakes (P&L critical path) |
| F11 | WARNING | Docs-archive | `ic-e2e/`, `ic-full/`, `ic-multi-expiry/`, `ic-nifty-v2/` are a 4-member pattern of pre-convention top-level archive dirs, not an isolated `ic-nifty-v2` misplacement |
| F12 | INFO | Docs-archive | `docs/archive/plan/`'s 9 loose files split into 3 documented-pre-convention (no drift) + 6 truly-undocumented (real drift, narrower than FR-3/seed implied) |
| F13 | INFO | Docs-active/Config | No referenced-but-missing directories found — `pyproject.toml` `testpaths`, `data/` inline paths in `CONTEXT.md` all check out |
| F14 | WARNING | Config-and-data | `data/`'s 6-subtree structure has zero coverage in `CONTEXT_TREE.md` despite that file's stated purpose |
| F15 | WARNING | Docs-active | `config/`, `docs/instructions/`, `docs/viz/` — undocumented, unlinked-from-root-docs directories with real (not dead) content |
| F16 | WARNING | Config-and-data | `scratch/` tracked in git (including committed diff files) while functionally identical `tmp/` is gitignored — inconsistent VCS treatment of the same workflow |

F12 detail: FR-3/seed implied 8 loose files lack any mention; `variance_gate.md` is referenced, so the real count is 7.

**Confirmed still holding from FR-3:** F8 (`src/strategy/` vs `scripts/strategies/`) and F9
(`src/intraday/`↔`scripts/intraday/`, `src/council/`↔`scripts/council/`) — no new evidence found
that changes FR-3's WARNING rating or no-rename recommendation for either.

**Severity distribution this task added:** 0 CRITICAL, 1 ERROR (F10), 6 WARNING (F10a, F11, F14,
F15, F16, plus F8/F9 reconfirmed), 2 INFO (F12, F13). No CRITICAL findings — nothing here rises to
FR-1's "misdirects capital or a live-trading decision" bar; the highest-impact items (F10, F10a)
are navigation/discoverability risks in the docs-archive index layer and one additional same-name
code pairing, consistent in kind (not volume) with what FR-3 already found.

---

## 6. Docs-archive follow-up decision (mandatory)

Comparing Docs-archive findings (F10, F11, F12 — 1 ERROR + 1 WARNING + 1 INFO, across 3 distinct
sub-issues) against the other three buckets (Code: F8/F9/F10a — 3 WARNING; Docs-active: F15 — 1
WARNING; Config-and-data: F13/F14/F16 — 2 WARNING + 1 INFO): Docs-archive findings are **not**
materially larger in volume than Code's, and the one ERROR-rated finding (F10) is resolvable
entirely at the structural/naming level — it does not require reading file *contents* to close
(the fix is "write or narrow a taxonomy doc," not "reconcile conflicting claims inside archived
files," which is the kind of content-dependent work that would be genuinely out of this task's
scope). F11's four-folder pattern is likewise closable with a one-line documentation note, no
content read required beyond the directory listings already gathered here.

**Conclusion: no dedicated `docs/archive/`-only follow-up story is warranted.** Docs-archive
findings were comparable in volume and severity to Code and Config-and-data, and none of them
require the content-level reading that would justify scoping a separate pass — all three
(F10, F11, F12) are fixable as documentation/taxonomy edits using only what this structural sweep
already surfaced. If a future review does want to go deeper into `docs/archive/`'s 144 files
(FR-3's original point — content, not structure), that would be a different task shape entirely
(a provenance/content-drift check, closer to FR-3's own Fable-assigned cross-document tracing
than to this Folder Structure Auditor's directory-listing pass) and should be scoped as such if
FR-9's roadmap decides it's worth the budget — but that is a recommendation contingent on future
priorities, not a finding that Docs-archive's *structure* needs a dedicated follow-up now.

---

## Closing block

> State the persona you reviewed as (Folder Structure Auditor). Name at least one perspective
> this review did not cover that a different persona would have caught — write "none identified"
> explicitly if genuinely nothing comes to mind, do not omit this section.

**Persona reviewed as:** Folder Structure Auditor.

**Perspective not covered:** A **security/secrets-hygiene persona checking what's actually inside
the tracked-but-shouldn't-be `scratch/` files (F16).** This review flagged that `scratch/diff.patch`
and `scratch/git_diff.diff` are committed git-diff artifacts, but stayed at the directory-listing
level per this task's explicit scope (no file-content reads except one-line false-positive checks)
— it did not open either file to check whether the diffs they capture ever touched anything
sensitive (a `.env`-adjacent config snippet, a token accidentally pasted into a council-question
draft file like `scratch/council_ping_question.md`). `CLAUDE.md`'s own Security section
("Never commit API keys, secrets, or tokens... `.env` in `.gitignore` always") is exactly the
policy a security-focused pass would check these 8 tracked files against, and this task's
structural remit stopped one layer short of that check. Recommend FR-9 either fold this into a
`code-reviewer`/security-scan pass over `scratch/`'s tracked contents specifically, or flag it as
its own narrow follow-up if the full-repo-review epic doesn't already have a dedicated security
persona covering committed-scratch-file exposure (FR-6, if it exists in this epic's persona
lineup, is the natural home — this task did not read FR-6's own findings file to check for
overlap, since FR-6 wasn't named as a dependency).
