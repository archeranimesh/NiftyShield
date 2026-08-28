#!/usr/bin/env bash
# SessionStart hook — flags root state docs that have fallen behind src/ changes.
#
# For each tracked state doc, counts commits touching src/ or scripts/ since the
# doc was last modified. Docs over their threshold are listed on one line so the
# staleness is visible at session start and gets addressed during Step 5a.
#
# Informational only — always exits 0. "Behind code" is a proxy for "possibly
# stale", not proof: a doc can be current without recent edits. Thresholds are
# deliberately loose to avoid crying wolf. Uses "last commit that touched the
# file" as the freshness signal — zero-maintenance, no stamp lines in the docs.

set -uo pipefail

git rev-parse --git-dir >/dev/null 2>&1 || exit 0

# file:threshold — src/|scripts/ commits since the doc's last change that trip the flag.
# Thresholds tuned per how often the doc legitimately changes: CONTEXT.md / TODOS.md every
# session (tight); CONTEXT_TREE.md / DB_REGISTRY.md / README.md only on new modules / tables /
# public-surface shifts (loose — RDO-10 #5 raised these from 35/40 to kill false positives).
DOCS="
CONTEXT.md:15
TODOS.md:15
docs/plan/README.md:35
DECISIONS.md:40
PLANNER.md:40
CONTEXT_TREE.md:60
DB_REGISTRY.md:60
README.md:60
"

now=$(date +%s)
stale=""
while IFS=: read -r file threshold; do
    [ -z "$file" ] && continue
    [ -f "$file" ] || continue
    last=$(git log -1 --format=%H -- "$file" 2>/dev/null || true)
    [ -z "$last" ] && continue
    count=$(git log --oneline "$last"..HEAD -- src/ scripts/ 2>/dev/null | wc -l | tr -d ' ')
    if [ "${count:-0}" -gt "$threshold" ]; then
        ts=$(git log -1 --format=%ct -- "$file" 2>/dev/null || echo "$now")
        days=$(( (now - ts) / 86400 ))
        stale="${stale}  · ${file} (${count} src commits, ${days}d)"$'\n'
    fi
done <<EOF
$DOCS
EOF

if [ -n "$stale" ]; then
    printf '%s\n%s' "⚠ state docs may be behind code — verify/refresh during Step 5a:" "$stale"
fi

exit 0
