"""Static-scan guard: MarkdownV2 escaping discipline on Telegram send call sites.

MD-6 (docs/plan/telegram-markdown-migration/backbone/tasks.md): the escaping
discipline `escape_markdown()`/`mdcode()` from `src/notifications/markdown.py`
is hand-maintained, not compiler-checked. This is the same failure class as the
original `DELTA_WARN` bug that started the epic — a dynamic value interpolated
into message text without escaping silently 400s the send (swallowed by the
non-fatal `TelegramNotifier.send()` contract, so it fails invisibly rather than
loudly). This guard walks `src/` and `scripts/` for call sites of
`.send(...)` / `.send_plain_message(...)` (the two names named in MD-6's spec;
`.send_notification(...)` and `.send_approval_request(...)` were already
covered call-by-call in MD-4.1-4.3 and are out of this guard's literal scope)
and flags any call whose first argument is not a bare string literal unless the
enclosing function also calls `escape_markdown()`/`mdcode()` somewhere in its
body.

Design notes (recorded because "what counts as escaped" is a judgment call,
per MD-6's Review note):

- This is a single-function-scope heuristic, not real data-flow analysis. It
  proves "this function shows escaping discipline somewhere," not "this exact
  value passed through an escaping call." That's a deliberate trade: false
  negatives (an escaping call present but not actually applied to the value
  reaching `.send()`) are possible; the guard's job is to catch the *absence*
  of escaping discipline in a function that sends dynamic text, which is the
  actual shape of every bug this epic has found so far.
- A call whose enclosing function is itself named `send`/`send_plain_message`
  (i.e. we're inside `TelegramNotifier`/`TelegramGateway`'s own passthrough
  implementation, forwarding an already-built `text` parameter one layer
  down) is excluded — escaping is the message-builder's responsibility, not
  the transport layer's; flagging the passthrough itself is a guaranteed
  false positive with no useful action.
- A call whose sole argument is a plain `ast.Constant` string (no dynamic
  value at all) is excluded — nothing to escape.

Baseline: as of this task (2026-08-25), the codebase has 29 real call sites
that fail the check above. All 29 are messages `strategy-rollout/`'s ROLL-*
tasks have already format-confirmed-but-not-yet-implemented in real code, or
gaps this scan itself surfaced that were not previously tracked anywhere in
the epic (see per-entry notes). They are NOT new mistakes introduced by this
task, and fixing them is out of scope for MD-6 (a guard test, not an
audit-and-fix task) and out of scope for one-task-per-session. They are
tracked explicitly below so this guard can ship today without blocking on
unrelated work, while still catching any *new* unescaped call site from this
point forward.

Maintenance contract: remove a baseline entry in the same commit that lands
its real escaping fix (a ROLL-* implementation, or a new MD-*/gap fix) — do
not leave stale entries. `test_baseline_entries_are_still_unescaped` fails
loudly if an entry no longer reproduces (line moved, or already fixed),
forcing the baseline to be updated rather than silently rotting.
"""

from __future__ import annotations

import ast
import pathlib
from dataclasses import dataclass

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCAN_DIRS = ("src", "scripts")
EXCLUDE_PARTS = {"tests", "test", "scratch", "__pycache__"}
TARGET_METHODS = {"send", "send_plain_message"}
ESCAPING_HELPERS = {"escape_markdown", "mdcode"}


@dataclass(frozen=True)
class CallSite:
    """One `.send()`/`.send_plain_message()` call site with a dynamic argument."""

    file: str
    line: int
    method: str
    enclosing_function: str
    escaped: bool


def _iter_py_files():
    for d in SCAN_DIRS:
        base = REPO_ROOT / d
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if EXCLUDE_PARTS & set(path.parts):
                continue
            yield path


def _enclosing_function(tree: ast.AST, target: ast.Call) -> ast.AST | None:
    """Return the nearest FunctionDef/AsyncFunctionDef containing `target`, if any."""
    stack: list[ast.AST] = []
    found: list[ast.AST | None] = [None]

    class _Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):  # noqa: N802 - ast visitor naming
            stack.append(node)
            self.generic_visit(node)
            stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):  # noqa: N802 - ast visitor naming
            if node is target:
                found[0] = stack[-1] if stack else None
            self.generic_visit(node)

    _Visitor().visit(tree)
    return found[0]


def _arg_is_dynamic(node: ast.AST | None) -> bool:
    """False only for a bare string literal - i.e. nothing that needs escaping."""
    if node is None:
        return False
    return not (isinstance(node, ast.Constant) and isinstance(node.value, str))


def _has_escaping_call(scope: ast.AST) -> bool:
    for node in ast.walk(scope):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in ESCAPING_HELPERS:
            return True
        if isinstance(func, ast.Attribute) and func.attr in ESCAPING_HELPERS:
            return True
    return False


def scan_call_sites() -> list[CallSite]:
    """Walk src/ and scripts/ for .send()/.send_plain_message() call sites.

    Returns every call site with a dynamic (non-literal-string) first argument,
    flagging whether the enclosing function shows escaping-helper usage.
    """
    sites: list[CallSite] = []
    for path in _iter_py_files():
        try:
            source = path.read_text()
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        rel = str(path.relative_to(REPO_ROOT))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr not in TARGET_METHODS:
                continue
            if not node.args or not _arg_is_dynamic(node.args[0]):
                continue
            fn = _enclosing_function(tree, node)
            if fn is not None and fn.name in TARGET_METHODS:
                # Transport-layer passthrough (TelegramNotifier/TelegramGateway's
                # own send()/send_plain_message() implementation) - the caller,
                # not this forwarding layer, owns escaping.
                continue
            scope = fn if fn is not None else tree
            sites.append(
                CallSite(
                    file=rel,
                    line=node.lineno,
                    method=node.func.attr,
                    enclosing_function=fn.name if fn else "<module>",
                    escaped=_has_escaping_call(scope),
                )
            )
    return sites


# Known-unescaped call sites as of MD-6 (2026-08-25). Each is either a message
# `strategy-rollout/` has format-confirmed but not yet implemented in real code
# (ROLL-* reference given), or a gap this scan surfaced that no prior MD-*/ROLL-*
# task names (flagged "untracked gap" - worth a future task, not this one).
# (file, line): reason
_BASELINE_UNESCAPED: dict[tuple[str, int], str] = {
    (
        "scripts/dev/paper_track_snapshot.py",
        167,
    ): "ROLL-10 - format confirmed, real code not yet migrated",
    (
        "scripts/dev/send_test_telegram.py",
        65,
    ): (
        "won't-fix (confirmed 2026-08-25, Animesh) - manual dev/debug utility invoked ad hoc "
        "by whoever's testing, not a cron or strategy event path; deliberately excluded from "
        "MD-7.1/MD-7.2/MD-7.3"
    ),
    ("scripts/eod_summary.py", 114): "ROLL-6 - format confirmed, real code not yet migrated",
    ("scripts/healthcheck.py", 254): "ROLL-11 - format confirmed, real code not yet migrated",
    ("scripts/portfolio/daily_snapshot.py", 739): (
        "untracked gap - TODO.md item 9 kept current format as-is (2026-08-11 decision); "
        "MD-4's file list never actually included this file despite that note flagging it "
        "for re-check"
    ),
    (
        "scripts/position_health_check.py",
        135,
    ): "ROLL-12 - format confirmed, real code not yet migrated",
    (
        "scripts/strategies/three_track/paper_3track_entry.py",
        940,
    ): "ROLL-13 - format confirmed, real code not yet migrated",
    ("scripts/strategies/three_track/paper_3track_overlay_entry.py", 1307): (
        "ROLL-14 - format confirmed, real code not yet migrated (bootstrap-failure alert)"
    ),
    (
        "scripts/strategies/three_track/paper_3track_overlay_entry.py",
        1547,
    ): "ROLL-14 - format confirmed, real code not yet migrated",
    (
        "scripts/strategies/three_track/paper_3track_roll.py",
        321,
    ): "ROLL-9 - format confirmed, real code not yet migrated",
    (
        "scripts/strategies/three_track/paper_3track_snapshot.py",
        511,
    ): "untracked gap - not named in any MD-*/ROLL-* task",
    (
        "scripts/strategies/three_track/paper_3track_snapshot.py",
        729,
    ): "untracked gap - not named in any MD-*/ROLL-* task",
    (
        "scripts/strategies/three_track/paper_3track_snapshot.py",
        736,
    ): "untracked gap - not named in any MD-*/ROLL-* task",
    (
        "scripts/strategies/three_track/paper_3track_snapshot.py",
        1361,
    ): "ROLL-15/16 area - not itself named, untracked gap",
    (
        "scripts/strategies/three_track/paper_3track_snapshot.py",
        1387,
    ): "ROLL-15/16 area - not itself named, untracked gap",
    (
        "scripts/strategies/three_track/paper_3track_snapshot.py",
        1508,
    ): "untracked gap - not named in any MD-*/ROLL-* task",
    (
        "scripts/strategies/three_track/paper_3track_snapshot.py",
        1984,
    ): "untracked gap - not named in any MD-*/ROLL-* task",
    ("scripts/strategies/three_track/paper_3track_snapshot.py", 2030): (
        "heuristic limitation, not a real gap - value is escaped inside the callee "
        "_build_recovery_digest() (MD-4.2 scope) but this guard only inspects the "
        "immediate enclosing function (_run), not callees"
    ),
    ("src/strategy/monitor.py", 367): "ROLL-8 - format confirmed, real code not yet migrated",
    ("src/strategy/reentry_mixin.py", 210): "ROLL-7 - format confirmed, real code not yet migrated",
}


def test_scan_finds_the_known_escaped_call_sites():
    """Sanity check the scanner itself: it must still see already-escaped sites.

    Guards against a path/rglob change silently making the scan a no-op (which
    would make every other test in this file vacuously pass).
    """
    sites = scan_call_sites()
    assert sites, "scanner found zero .send()/.send_plain_message() call sites - scan is broken"
    escaped_files = {s.file for s in sites if s.escaped}
    # MD-3's audited close-notification methods - known escaped as of this task.
    assert "src/strategy/auto_close.py" in escaped_files
    assert "src/strategy/cc_overlay_v1.py" in escaped_files
    assert "src/strategy/pp_overlay_v1.py" in escaped_files


def test_no_new_unescaped_send_call_sites():
    """Every unescaped dynamic .send()/.send_plain_message() call site must be
    a documented, pre-existing entry in `_BASELINE_UNESCAPED` - not a new one.
    """
    sites = scan_call_sites()
    unescaped = {(s.file, s.line): s for s in sites if not s.escaped}
    undocumented = {k: v for k, v in unescaped.items() if k not in _BASELINE_UNESCAPED}
    assert not undocumented, (
        "New unescaped Telegram send call site(s) found - dynamic values must be "
        "wrapped with escape_markdown()/mdcode() from src/notifications/markdown.py "
        "before merging, or (if this is genuinely deferred work) added to "
        "_BASELINE_UNESCAPED in tests/unit/notifications/test_escaping_guard.py with "
        "a reason:\n"
        + "\n".join(
            f"  {f}:{line} ({v.method}, in {v.enclosing_function})"
            for (f, line), v in sorted(undocumented.items())
        )
    )


def test_baseline_entries_are_still_unescaped():
    """Baseline entries must still reproduce, so the baseline can't rot silently.

    If a line moved or was already fixed, this fails - forcing the entry to be
    removed (fixed) or corrected (moved), rather than left as permanent noise.
    """
    sites = scan_call_sites()
    unescaped = {(s.file, s.line) for s in sites if not s.escaped}
    stale = sorted(k for k in _BASELINE_UNESCAPED if k not in unescaped)
    assert not stale, (
        "Baseline entries no longer reproduce (fixed, or line moved) - remove/update "
        "them in _BASELINE_UNESCAPED:\n" + "\n".join(f"  {f}:{line}" for f, line in stale)
    )


def test_baseline_has_no_duplicate_or_unused_entries():
    """Every baseline key must correspond to a real (file, line) pair the scan visits."""
    sites = scan_call_sites()
    all_call_site_keys = {(s.file, s.line) for s in sites}
    orphaned = sorted(k for k in _BASELINE_UNESCAPED if k not in all_call_site_keys)
    assert not orphaned, (
        "Baseline entries reference call sites the scanner no longer finds at all "
        "(not just 'now escaped') - the file/line was moved, deleted, or refactored:\n"
        + "\n".join(f"  {f}:{line}" for f, line in orphaned)
    )


@pytest.mark.parametrize(
    "file_rel, line",
    [
        ("src/strategy/auto_close.py", 347),
        ("src/strategy/cc_overlay_v1.py", 382),
        ("src/strategy/pp_overlay_v1.py", 394),
        ("src/strategy/collar_overlay_v1.py", 601),
        ("src/strategy/collar_overlay_v1.py", 603),
        ("src/strategy/collar_overlay_v1.py", 726),
    ],
)
def test_md3_audited_close_notifications_stay_escaped(file_rel, line):
    """Regression pin for MD-3's audited call sites: they must stay escaped.

    A future edit that reworks one of these methods and drops the escaping call
    without touching this line number would otherwise slip past
    test_no_new_unescaped_send_call_sites (which only complains about *new*
    unescaped sites, not regressions on already-escaped ones at the same line).
    """
    sites = {(s.file, s.line): s for s in scan_call_sites()}
    site = sites.get((file_rel, line))
    assert site is not None, (
        f"expected a .send()/.send_plain_message() call at {file_rel}:{line}, found none"
    )
    assert site.escaped, f"{file_rel}:{line} lost its escaping-helper usage"
