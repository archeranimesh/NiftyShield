#!/usr/bin/env python3
"""Attribute a Claude Code session transcript's tokens by bucket.

Parses a session JSONL transcript and reports where its tokens went: the
first-turn system-prompt write, an on-disk estimate of the resident project
docs (``CLAUDE.md`` / ``AGENTS.md`` / ``MEMORY.md``), tool results grouped by
tool name, subagent report payloads returned into the main thread, subagent
internal token usage (real account cost that never enters main context), and
the assistant's own output.

Token accounting is a mix of real API numbers and a documented heuristic
where no real number exists in the transcript:

- ``system_prompt`` — real: the first assistant turn's
  ``usage.cache_creation_input_tokens`` (the whole initial prefix: harness
  preamble + tool schemas + whatever docs the harness injected at the time).
  This is reported once per session even though the same content is resident
  every turn.
- ``project_docs`` — estimated: chars/4 over the *current* on-disk
  ``CLAUDE.md`` + ``AGENTS.md`` + ``MEMORY.md``. The transcript does not store
  the text actually injected at session-start time, so this is a present-day
  approximation, not a historical measurement — it will drift for old
  transcripts if those files have since changed. It is independent of
  ``system_prompt`` (not a subtraction from it) to keep each transcript
  record contributing to exactly one bucket. Module-level ``CLAUDE.md`` files
  that auto-inject when a ``src/`` directory is touched are not included —
  detecting which ones fired for a given session would need per-turn tool
  argument inspection this tool does not do.
- ``tool_results:<tool>`` — estimated: chars/4 over each ``tool_result``
  block's content, grouped by the tool name resolved from the matching
  ``tool_use`` block earlier in the transcript.
- ``subagent_reports`` — estimated: chars/4 over the ``<result>...</result>``
  text of each ``<task-notification>`` delivered to the main thread.
- ``subagent_internal`` — real: the ``<subagent_tokens>`` figure in that same
  ``<task-notification>`` — tokens spent inside the subagent's own context
  that never entered the main session but are real account cost.
- ``assistant_text`` — real: ``usage.output_tokens`` summed across every
  assistant record.

Usage::

    python -m scripts.dev.token_audit <transcript-path-or-session-id>
    python -m scripts.dev.token_audit <transcript-path-or-session-id> --json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

import structlog

from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.dev.token_audit"
logger = structlog.get_logger(_SCRIPT_NAME)

_CHARS_PER_TOKEN = 4
_PROJECT_DOC_NAMES = ("CLAUDE.md", "AGENTS.md")
_RESULT_RE = re.compile(r"<result>(.*?)</result>", re.DOTALL)
_SUBAGENT_TOKENS_RE = re.compile(r"<subagent_tokens>(\d+)</subagent_tokens>")

_BUCKET_NOTES = {
    "system_prompt": "real, first-turn cache write (preamble + tool schemas + injected docs)",
    "project_docs": "estimated, chars/4 over current on-disk CLAUDE.md+AGENTS.md+MEMORY.md",
    "subagent_reports": "estimated, chars/4 over <result> text",
    "subagent_internal": "real, <subagent_tokens> from task-notification",
    "assistant_text": "real, usage.output_tokens",
}
_TOOL_RESULT_NOTE = "estimated, chars/4 over tool_result content"


@dataclass(frozen=True)
class Record:
    """One token-bearing unit extracted from (or derived alongside) a transcript.

    Args:
        index: Line number the record came from, or -1 for a synthetic
            record (currently only ``project_docs``) not tied to one line.
        kind: Bucket key, except for ``"tool_result"`` which is grouped by
            ``label`` into ``tool_results:<label>`` by :func:`attribute`.
        label: Tool name for a ``tool_result``; a short static tag otherwise.
        tokens: Token count for this record.
        estimated: ``True`` if ``tokens`` is a chars/4 heuristic rather than
            a real API/harness-reported number.
    """

    index: int
    kind: str
    label: str
    tokens: int
    estimated: bool


def resolve_transcript(arg: str) -> Path:
    """Resolve ``arg`` to a transcript JSONL path.

    Args:
        arg: An explicit file path, or a Claude Code session id to locate
            under ``~/.claude/projects/``.

    Returns:
        The resolved path.

    Raises:
        FileNotFoundError: ``arg`` is neither an existing file nor a session
            id that resolves to exactly one ``<arg>.jsonl`` under the
            projects root.
        ValueError: ``arg`` resolves to more than one transcript.
    """
    direct = Path(arg)
    if direct.is_file():
        return direct

    root = Path.home() / ".claude" / "projects"
    matches = list(root.rglob(f"{arg}.jsonl")) if root.is_dir() else []
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"session id {arg!r} is ambiguous: {len(matches)} matches under {root}")
    raise FileNotFoundError(
        f"could not resolve {arg!r} as a transcript file or a session id under {root}"
    )


def _tool_result_text(content: object) -> str:
    """Flatten a ``tool_result`` block's ``content`` field to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            else:
                parts.append(json.dumps(block))
        return "".join(parts)
    return json.dumps(content)


def _estimate_tokens(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


def parse_records(path: Path, *, repo_root: Path | None = None) -> list[Record]:
    """Parse a transcript JSONL into token-bearing :class:`Record`\\ s.

    Args:
        path: Transcript JSONL path (from :func:`resolve_transcript`).
        repo_root: Directory to look for ``CLAUDE.md`` / ``AGENTS.md`` /
            ``MEMORY.md`` in when estimating the ``project_docs`` bucket. If
            omitted, uses the ``cwd`` field of the first record that has one,
            falling back to the current working directory.

    Returns:
        Every extracted record, plus one synthetic ``project_docs`` record.
    """
    records: list[Record] = []
    tool_names: dict[str, str] = {}
    seen_first_assistant = False
    inferred_root: Path | None = None

    with path.open(encoding="utf-8") as f:
        for index, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue

            if inferred_root is None and isinstance(raw.get("cwd"), str):
                inferred_root = Path(raw["cwd"])

            record_type = raw.get("type")
            message = raw.get("message") if isinstance(raw.get("message"), dict) else {}
            content = message.get("content")

            if record_type == "assistant":
                for block in content or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_id = block.get("id")
                        if isinstance(tool_id, str):
                            tool_names[tool_id] = block.get("name", "unknown")

                usage = message.get("usage") or {}
                if not seen_first_assistant:
                    seen_first_assistant = True
                    prefix_tokens = usage.get("cache_creation_input_tokens", 0)
                    if prefix_tokens:
                        records.append(
                            Record(
                                index, "system_prompt", "first_turn_prefix", prefix_tokens, False
                            )
                        )
                output_tokens = usage.get("output_tokens", 0)
                if output_tokens:
                    records.append(
                        Record(index, "assistant_text", "assistant", output_tokens, False)
                    )

            elif record_type == "user":
                if isinstance(content, str) and "<task-notification>" in content:
                    result_match = _RESULT_RE.search(content)
                    if result_match:
                        tokens = _estimate_tokens(result_match.group(1))
                        records.append(Record(index, "subagent_reports", "subagent", tokens, True))
                    usage_match = _SUBAGENT_TOKENS_RE.search(content)
                    if usage_match:
                        records.append(
                            Record(
                                index,
                                "subagent_internal",
                                "subagent",
                                int(usage_match.group(1)),
                                False,
                            )
                        )
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            tool_use_id = block.get("tool_use_id")
                            name = tool_names.get(tool_use_id, "unknown")
                            text = _tool_result_text(block.get("content", ""))
                            tokens = _estimate_tokens(text)
                            if tokens:
                                records.append(Record(index, "tool_result", name, tokens, True))

    docs_root = repo_root or inferred_root or Path.cwd()
    records.append(
        Record(-1, "project_docs", "docs", estimate_project_docs_tokens(docs_root), True)
    )
    return records


def estimate_project_docs_tokens(repo_root: Path) -> int:
    """Estimate resident project-doc size: ``CLAUDE.md`` + ``AGENTS.md`` + ``MEMORY.md``.

    Args:
        repo_root: Project directory. ``MEMORY.md`` is looked up at the
            Claude Code memory path derived from this directory
            (``~/.claude/projects/<slug>/memory/MEMORY.md``, matching the
            harness's own path-slugging convention).

    Returns:
        chars/4 token estimate over whichever of the three files exist.
    """
    total_chars = 0
    for name in _PROJECT_DOC_NAMES:
        doc_path = repo_root / name
        if doc_path.is_file():
            total_chars += len(doc_path.read_text(encoding="utf-8", errors="ignore"))

    slug = str(repo_root).replace("/", "-")
    memory_path = Path.home() / ".claude" / "projects" / slug / "memory" / "MEMORY.md"
    if memory_path.is_file():
        total_chars += len(memory_path.read_text(encoding="utf-8", errors="ignore"))

    return total_chars // _CHARS_PER_TOKEN


def attribute(records: list[Record]) -> dict[str, int]:
    """Fold records into buckets, keyed by bucket name.

    Args:
        records: Records from :func:`parse_records` (or hand-built ones).

    Returns:
        Bucket name -> summed tokens. ``tool_result`` records are grouped
        into ``tool_results:<label>``; every other kind is its own bucket.
    """
    buckets: dict[str, int] = {}
    for record in records:
        key = f"tool_results:{record.label}" if record.kind == "tool_result" else record.kind
        buckets[key] = buckets.get(key, 0) + record.tokens
    return buckets


def _note_for(bucket: str) -> str:
    if bucket.startswith("tool_results:"):
        return _TOOL_RESULT_NOTE
    return _BUCKET_NOTES.get(bucket, "")


def render_table(buckets: dict[str, int]) -> str:
    """Render buckets as a compact table, largest bucket first."""
    rows = sorted(buckets.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(buckets.values())
    width = max((len(name) for name in buckets), default=6)
    lines = [f"{'bucket':<{width}}  {'tokens':>8}  note"]
    for name, tokens in rows:
        lines.append(f"{name:<{width}}  {tokens:>8}  {_note_for(name)}")
    lines.append(f"{'TOTAL':<{width}}  {total:>8}")
    return "\n".join(lines)


def render_json(buckets: dict[str, int]) -> str:
    """Render buckets as a JSON object with bucket totals and the grand total."""
    return json.dumps(
        {"buckets": buckets, "total": sum(buckets.values())}, indent=2, sort_keys=True
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Attribute a Claude Code session transcript's tokens by bucket."
    )
    parser.add_argument(
        "transcript",
        help="Transcript JSONL path, or a session id to resolve under ~/.claude/projects/",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON instead of the compact table"
    )
    args = parser.parse_args()

    path = resolve_transcript(args.transcript)
    buckets = attribute(parse_records(path))

    print(render_json(buckets) if args.json else render_table(buckets))
    logger.info("token_audit_complete", transcript=str(path), total_tokens=sum(buckets.values()))


if __name__ == "__main__":
    setup_logging()
    main()
