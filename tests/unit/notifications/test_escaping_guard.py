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
    ("scripts/signal_eod.py", 255): (
        "S5.5a — value is fully escaped inside the callee _format_outcome_notification() "
        "(the message-builder owns the MarkdownV2 boundary: escape_markdown() per dynamic "
        "value, literal * for bold), but this guard only inspects the immediate enclosing "
        "function (_notify_outcome), not the builder it calls — same shape as the morning_signal.py:218 entry. "
        "Line moved from 232 -> 255 by SOP-1/SOP-2's profit high/low addition (767c0bd, a73b6b6)."
    ),
    ("scripts/signal_eod.py", 464): (
        "S5.5d — report body is wrapped as a MarkdownV2 fenced code block inside the "
        "callee _format_report_message() (fence content only needs backslash/backtick "
        "escaping, never the general escape_markdown), but this guard only inspects the "
        "immediate enclosing function (_notify_report), not the builder it calls. "
        "Line moved from 441 -> 464 by SOP-1/SOP-2's profit high/low addition (767c0bd, a73b6b6)."
    ),
    (
        "scripts/dev/send_test_telegram.py",
        65,
    ): (
        "won't-fix (confirmed 2026-08-25, Animesh) - manual dev/debug utility invoked ad hoc "
        "by whoever's testing, not a cron or strategy event path; deliberately excluded from "
        "MD-7.1/MD-7.2/MD-7.3"
    ),
    ("scripts/eod_summary.py", 198): (
        "heuristic limitation, not a real gap - ROLL-6 migrated this (SHA on the task "
        "line); the message is built and fully escaped inside build_eod_summary_message() "
        "(escape_markdown() on every out-of-fence line), but this guard only inspects the "
        "immediate enclosing function (main), not the builder it calls - same shape as the "
        "paper_3track_snapshot.py:2030 entry. Line moved from 200 -> 198 by UXM's edits."
    ),
    ("scripts/healthcheck.py", 324): (
        "heuristic limitation, not a real gap - ROLL-11 migrated this (SHA on the task "
        "line); the message is built and fully escaped inside build_healthcheck_alert() "
        "(escape_markdown() on every label, status word, detail and the bracketed time), "
        "but this guard only inspects the immediate enclosing function (main), not the "
        "builder it calls - same shape as the scripts/eod_summary.py:198 entry"
    ),
    (
        "scripts/position_health_check.py",
        149,
    ): (
        "heuristic limitation, not a real gap - ROLL-12 migrated this; the message is built "
        "and fully escaped inside build_position_health_message(), but this guard only inspects "
        "the immediate enclosing function (main)"
    ),
    ("scripts/strategies/three_track/paper_3track_overlay_entry.py", 1333): (
        "ROLL-14 - format confirmed, real code not yet migrated (bootstrap-failure alert)"
    ),
    ("scripts/strategies/three_track/paper_3track_roll.py", 437): (
        "heuristic limitation, not a real gap - ROLL-9 migrated this (SHA on the task "
        "line); the message is built and fully escaped inside build_roll_notification() "
        "(escape_markdown() on every dynamic value + static punctuation), but this guard "
        "only inspects the immediate enclosing function (check_and_roll_leg), not the "
        "builder it calls - same shape as the scripts/eod_summary.py:198 entry"
    ),
    # base-expiry notifier.send (was line 511) - ROLL-15 (SHA 3855f8f) migrated it;
    # msg is now fully escaped (escape_markdown/mdcode on every value), so it is no
    # longer a baseline entry. Line numbers below shifted down by ROLL-15's edit.
    (
        "scripts/strategies/three_track/paper_3track_snapshot.py",
        769,
    ): "untracked gap - not named in any MD-*/ROLL-* task",
    (
        "scripts/strategies/three_track/paper_3track_snapshot.py",
        776,
    ): "untracked gap - not named in any MD-*/ROLL-* task",
    (
        "scripts/strategies/three_track/paper_3track_snapshot.py",
        1400,
    ): "ROLL-15/16 area - not itself named, untracked gap. Line moved from 1401 -> 1400 by ORD-2's edit.",
    (
        "scripts/strategies/three_track/paper_3track_snapshot.py",
        1426,
    ): "ROLL-15/16 area - not itself named, untracked gap. Line moved from 1427 -> 1426 by ORD-2's edit.",
    (
        "scripts/strategies/three_track/paper_3track_snapshot.py",
        1547,
    ): "untracked gap - not named in any MD-*/ROLL-* task. Line moved from 1548 -> 1547 by ORD-2's edit.",
    ("scripts/dev/paper_track_snapshot.py", 171): (
        "value escaped inside callee build_proxy_critical_alert() — guard inspects enclosing function only"
    ),
    ("scripts/strategies/three_track/paper_3track_snapshot.py", 2020): (
        "value escaped inside callee build_proxy_critical_alert() — guard inspects enclosing "
        "function only. Line moved from 2017 -> 2020 by ORD-3's edit."
    ),
    ("scripts/morning_signal.py", 181): (
        "S5.5c — value is fully escaped inside the callee _format_signal_notification() "
        "(the message-builder owns the MarkdownV2 boundary: escape_markdown() per dynamic "
        "value, literal * for bold), but this guard only inspects the immediate enclosing "
        "function (run), not the builder it calls — same shape as the scripts/eod_summary.py:198 entry. "
        "Line moved from 295 -> 181 by SEC-4's extraction of the pipeline body into "
        "src/signals/pipeline.py::run_morning_signal_pipeline."
    ),
    ("src/strategy/signal_track_v1.py", 378): (
        "SPT-3 — value is fully escaped inside the callee build_signal_entry_message() "
        "(the message-builder owns the MarkdownV2 boundary: escape_markdown() per dynamic "
        "value + literal * for bold, fenced table content passed through verbatim), but "
        "this guard only inspects the immediate enclosing function (open_signal_paper_entry), "
        "not the builder it calls — same shape as the scripts/morning_signal.py:282 entry. "
        "Line moved from 293 -> 379 by SPT-5's new imports/helpers above it."
    ),
    ("src/strategy/signal_track_v1.py", 645): (
        "SPT-5 — value is fully escaped inside the callee build_signal_exit_message() "
        "(same MarkdownV2-boundary shape as the SPT-3 entry above: escape_markdown() per "
        "dynamic value + literal * for bold, fenced table content passed through verbatim), "
        "but this guard only inspects the immediate enclosing function (_close_position), "
        "not the builder it calls."
    ),
    ("scripts/strategies/three_track/paper_3track_snapshot.py", 2066): (
        "ORD-3 - digest body is wrapped as a single MarkdownV2 fenced code block inside "
        "the callee _build_recovery_digest() (fence content is literal, no per-line/whole-"
        "string escape_markdown needed — same shape as the scripts/signal_eod.py:440 "
        "entry), but this guard only inspects the immediate enclosing function (_run), "
        "not the builder it calls. Line moved from 2063 -> 2066 by ORD-3's edit."
    ),
    ("scripts/record/record_paper_trade.py", 775): (
        "UEM-2 - heuristic limitation, not a real gap: the card is built by "
        "_build_entry_card() -> format_entry_message(), which escapes every "
        "interpolated value via escape_markdown() inside EntryMessage's own "
        "renderer (src/notifications/entry_message.py); this guard only "
        "inspects the immediate enclosing function (_send_entry_card_if_requested), "
        "not the builder it calls - same shape as the scripts/eod_summary.py:198 entry"
    ),
    ("scripts/record/record_paper_trade.py", 846): (
        "UXM-4 - heuristic limitation, not a real gap: the card is built by "
        "format_exit_message(), which escapes every interpolated value via "
        "escape_markdown() inside ExitMessage's own renderer "
        "(src/notifications/exit_message.py); this guard only inspects the "
        "immediate enclosing function (_send_close_card_if_requested), not the "
        "builder it calls - same shape as the scripts/eod_summary.py:198 entry. "
        "Line moved from 845 -> 846 by a later edit above it."
    ),
    ("src/strategy/collar_overlay_v1.py", 680): (
        "OEM-2 - heuristic limitation, not a real gap: the card is built by "
        "format_entry_message(), which escapes every interpolated value via "
        "escape_markdown() inside EntryMessage's own renderer "
        "(src/notifications/entry_message.py); this guard only inspects the "
        "immediate enclosing function (_send_reentry_notification), not the "
        "builder it calls - same shape as the scripts/record/record_paper_trade.py:775 entry. "
        "Line moved from 679 -> 680 by UXM-5's _send_close_notification rewrite above it."
    ),
    ("src/strategy/collar_overlay_v1.py", 682): (
        "OEM-2 - heuristic limitation, not a real gap: the card is built by "
        "format_entry_message(), which escapes every interpolated value via "
        "escape_markdown() inside EntryMessage's own renderer "
        "(src/notifications/entry_message.py); this guard only inspects the "
        "immediate enclosing function (_send_reentry_notification), not the "
        "builder it calls - same shape as the scripts/record/record_paper_trade.py:775 entry. "
        "Line moved from 681 -> 682 by UXM-5's _send_close_notification rewrite above it."
    ),
    ("src/strategy/cc_overlay_v1.py", 447): (
        "UXM-5 - heuristic limitation, not a real gap: the card is built by "
        "format_exit_message(), which escapes every interpolated value via "
        "escape_markdown() inside ExitMessage's own renderer "
        "(src/notifications/exit_message.py); this guard only inspects the "
        "immediate enclosing function (_send_close_notification), not the "
        "builder it calls - same shape as the scripts/record/record_paper_trade.py:846 entry"
    ),
    ("src/strategy/pp_overlay_v1.py", 470): (
        "UXM-5 - heuristic limitation, not a real gap: the card is built by "
        "format_exit_message(), which escapes every interpolated value via "
        "escape_markdown() inside ExitMessage's own renderer "
        "(src/notifications/exit_message.py); this guard only inspects the "
        "immediate enclosing function (_send_close_notification), not the "
        "builder it calls - same shape as the scripts/record/record_paper_trade.py:846 entry"
    ),
    ("src/strategy/collar_overlay_v1.py", 863): (
        "UXM-5 - heuristic limitation, not a real gap: the card is built by "
        "format_exit_message(), which escapes every interpolated value via "
        "escape_markdown() inside ExitMessage's own renderer "
        "(src/notifications/exit_message.py); this guard only inspects the "
        "immediate enclosing function (_send_close_notification), not the "
        "builder it calls - same shape as the scripts/record/record_paper_trade.py:846 entry"
    ),
    ("src/strategy/auto_close.py", 387): (
        "UXM-6 - heuristic limitation, not a real gap: the card is built by "
        "format_exit_message(), which escapes every interpolated value via "
        "escape_markdown() inside ExitMessage's own renderer "
        "(src/notifications/exit_message.py); this guard only inspects the "
        "immediate enclosing function (_send_close_notification), not the "
        "builder it calls - same shape as the scripts/record/record_paper_trade.py:846 entry. "
        "This is the daemon path's own _send_close_notification, unrelated to the "
        "MD-3-audited line 359 it replaced — that hand-built, pre-escaped string was "
        "removed by UXM-6's migration onto format_exit_message()."
    ),
    ("scripts/mvp_watch.py", 135): ("untracked gap - not named in any MD-*/ROLL-* task"),
    ("scripts/mvp_watch.py", 143): ("untracked gap - not named in any MD-*/ROLL-* task"),
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
    # UXM-5 moved cc_overlay_v1.py / pp_overlay_v1.py's close notification onto
    # format_exit_message() (escaping lives in the renderer, not this file), so
    # they no longer have an escaped call site of their own — dropped here.
    assert "src/strategy/auto_close.py" in escaped_files
    assert "src/strategy/collar_overlay_v1.py" in escaped_files


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
        ("src/strategy/collar_overlay_v1.py", 608),
        ("src/strategy/collar_overlay_v1.py", 610),
    ],
)
def test_md3_audited_close_notifications_stay_escaped(file_rel, line):
    """Regression pin for MD-3's audited call sites: they must stay escaped.

    A future edit that reworks one of these methods and drops the escaping call
    without touching this line number would otherwise slip past
    test_no_new_unescaped_send_call_sites (which only complains about *new*
    unescaped sites, not regressions on already-escaped ones at the same line).

    UXM-5 dropped the cc_overlay_v1.py / pp_overlay_v1.py close-notification
    entries and collar_overlay_v1.py's old 805 entry from this list: those
    methods no longer build their own escape_markdown()-wrapped string —
    escaping now happens inside format_exit_message() (see the corresponding
    _BASELINE_UNESCAPED entries for the new call sites this introduced). The
    collar_overlay_v1.py reentry-failure entries stay pinned, shifted
    607 -> 608 and 609 -> 610 by UXM-5's edit above them.

    UXM-6 removed the auto_close.py:359 entry from this pin too: that daemon
    close path's hand-built, pre-escaped string was replaced by a delegation
    to format_exit_message() (see the new src/strategy/auto_close.py:387
    _BASELINE_UNESCAPED entry above) — same shape as the UXM-5 drops.
    """
    sites = {(s.file, s.line): s for s in scan_call_sites()}
    site = sites.get((file_rel, line))
    assert site is not None, (
        f"expected a .send()/.send_plain_message() call at {file_rel}:{line}, found none"
    )
    assert site.escaped, f"{file_rel}:{line} lost its escaping-helper usage"
