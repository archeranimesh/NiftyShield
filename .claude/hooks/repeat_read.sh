#!/usr/bin/env bash
# PreToolUse(Read|Edit|Write) hook — warns on a re-Read of a path already read
# this session with no intervening Edit/Write on it.
#
# Exit 0 always — warn only, never block. Logic + tests:
#   scripts/dev/hooks/check_repeat_read.py
#
# Seen paths live in a session-scoped file keyed by PPID (the Claude Code PID,
# same scheme as guard_src_reads.sh). Stale files are reaped after a day.

set -uo pipefail

SEEN="/tmp/niftyshield-seen-reads-$PPID"
find /tmp -maxdepth 1 -name 'niftyshield-seen-reads-*' -mtime +1 -delete 2>/dev/null || true

cat | python3 scripts/dev/hooks/check_repeat_read.py "$SEEN" 2>/dev/null || true

exit 0
