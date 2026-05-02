#!/usr/bin/env python3
"""Submit a context-enriched design decision to the NiftyShield LLM council.

Builds a structured prompt from CONTEXT.md and optional domain templates, then
POSTs it to the running llm-council backend (tools/llm-council).  If the server
is not running, the assembled prompt is saved to docs/council/pending/ for manual
submission via the web UI at http://localhost:5173.

Usage:
    # Ask a backtest design question
    python scripts/ask_council.py \\
        --topic slippage-model \\
        --template backtest_methodology \\
        --question "Which slippage model is appropriate for NSE Bhavcopy backtesting?"

    # Include an additional file as context (repeatable)
    python scripts/ask_council.py \\
        --topic csp-delta \\
        --template strategy_parameters \\
        --context docs/strategies/csp_nifty_v1.md \\
        --question "Should the CSP entry delta be 0.20 or 0.25?"

    # Preview the assembled prompt without submitting
    python scripts/ask_council.py \\
        --topic foo \\
        --question "..." \\
        --dry-run
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths — resolved relative to project root so the script can be run from
# any working directory.
# ---------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).parent.parent
CONTEXT_MD: Path = PROJECT_ROOT / "CONTEXT.md"
TEMPLATES_DIR: Path = PROJECT_ROOT / "scripts" / "council_templates"
COUNCIL_DIR: Path = PROJECT_ROOT / "docs" / "council"
PENDING_DIR: Path = COUNCIL_DIR / "pending"

COUNCIL_URL: str = "http://localhost:8001"
CONTEXT_MAX_LINES: int = 200  # truncation guard for large files


# ---------------------------------------------------------------------------
# Pure helpers — tested without network or filesystem mocking
# ---------------------------------------------------------------------------


def read_context_file(path: Path, max_lines: int = CONTEXT_MAX_LINES) -> str:
    """Read a project file, truncating to max_lines with a note if needed.

    Args:
        path: Absolute path to the file.
        max_lines: Maximum lines to include before truncating.

    Returns:
        File content as a string, or a "[File not found]" note.
    """
    if not path.exists():
        return f"[File not found: {path.name}]"
    text = path.read_text()
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    truncated = "\n".join(lines[:max_lines])
    return f"{truncated}\n\n[... truncated at {max_lines} lines — full file: {path.name}]"


def load_template(templates_dir: Path, template_name: str) -> str:
    """Load a domain-specific prompt preamble from the templates directory.

    Args:
        templates_dir: Path to the council_templates directory.
        template_name: Filename stem (without .md extension).

    Returns:
        Template content, or empty string if the template does not exist.
    """
    path = templates_dir / f"{template_name}.md"
    if not path.exists():
        return ""
    return path.read_text().strip()


def build_prompt(
    question: str,
    context_md: Path,
    templates_dir: Path,
    template_name: Optional[str] = None,
    extra_files: Optional[list[Path]] = None,
) -> str:
    """Assemble the full context-enriched prompt string.

    Section order:
      1. NiftyShield project state (CONTEXT.md — always included)
      2. Additional context files (--context flags, in order given)
      3. Decision domain constraints (template — if specified)
      4. The council question

    Args:
        question: The design question to ask.
        context_md: Path to CONTEXT.md.
        templates_dir: Path to the council_templates directory.
        template_name: Optional domain template to include.
        extra_files: Optional list of additional context files.

    Returns:
        Assembled prompt string ready to POST to the council backend.
    """
    parts: list[str] = []

    parts.append("=== NIFTYSHIELD PROJECT STATE ===")
    parts.append(read_context_file(context_md))

    for f in extra_files or []:
        parts.append(f"=== ADDITIONAL CONTEXT: {f.name} ===")
        parts.append(read_context_file(f))

    if template_name:
        preamble = load_template(templates_dir, template_name)
        if preamble:
            parts.append("=== DECISION DOMAIN CONSTRAINTS ===")
            parts.append(preamble)

    parts.append("=== QUESTION FOR THE COUNCIL ===")
    parts.append(question)

    return "\n\n".join(parts)


def _slugify(topic: str) -> str:
    """Convert a topic label to a safe filename slug."""
    return topic.lower().replace(" ", "-")


def make_output_path(topic: str, council_dir: Path) -> Path:
    """Return the output path for a completed council decision file.

    Args:
        topic: Short topic label (e.g. "slippage-model").
        council_dir: Base docs/council/ directory.

    Returns:
        Path of the form docs/council/YYYY-MM-DD_<slug>.md
    """
    date = datetime.date.today().isoformat()
    return council_dir / f"{date}_{_slugify(topic)}.md"


def make_pending_path(topic: str, pending_dir: Path) -> Path:
    """Return the pending prompt file path for when the server is offline.

    Args:
        topic: Short topic label.
        pending_dir: docs/council/pending/ directory.

    Returns:
        Path of the form docs/council/pending/YYYY-MM-DD_<slug>_prompt.md
    """
    date = datetime.date.today().isoformat()
    return pending_dir / f"{date}_{_slugify(topic)}_prompt.md"


def format_decision(topic: str, prompt: str, result: dict) -> str:
    """Format a council API result as a markdown document.

    Args:
        topic: Short topic label used in the heading.
        prompt: The prompt that was submitted (truncated in output).
        result: The full JSON result from the council /message endpoint.

    Returns:
        Markdown string ready to write to docs/council/.
    """
    date = datetime.date.today().isoformat()
    stage3: dict = result.get("stage3", {})
    stage1: list[dict] = result.get("stage1", [])
    metadata: dict = result.get("metadata", {})

    lines: list[str] = [
        f"# Council Decision: {topic}",
        "",
        f"Date: {date}  ",
        f"Chairman: {stage3.get('model', 'unknown')}  ",
        f"Council members: {', '.join(r['model'] for r in stage1)}",
        "",
        "---",
        "",
        "## Stage 3 — Chairman Synthesis",
        "",
        stage3.get("response") or "*(no synthesis returned)*",
        "",
        "---",
        "",
        "## Stage 1 — Individual Responses",
        "",
    ]

    for entry in stage1:
        lines.append(f"### {entry['model']}")
        lines.append("")
        lines.append(entry.get("response") or "")
        lines.append("")

    agg: list[dict] = metadata.get("aggregate_rankings", [])
    if agg:
        lines += [
            "## Aggregate Rankings (Stage 2 Peer Review)",
            "",
        ]
        for rank in agg:
            lines.append(
                f"- {rank['model']}: avg rank {rank['average_rank']} "
                f"({rank['rankings_count']} votes)"
            )
        lines.append("")

    prompt_preview = prompt[:3000] + ("..." if len(prompt) > 3000 else "")
    lines += [
        "---",
        "",
        "## Prompt Sent (first 3000 chars)",
        "",
        "```",
        prompt_preview,
        "```",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Network — exercised via integration tests only, not unit tests
# ---------------------------------------------------------------------------


def council_is_running(url: str = COUNCIL_URL) -> bool:
    """Return True if the council backend responds on the health endpoint.

    Args:
        url: Base URL of the council backend.
    """
    try:
        urllib.request.urlopen(f"{url}/", timeout=3)
        return True
    except Exception:
        return False


def _post_json(url: str, payload: dict, timeout: float) -> dict:
    """POST a JSON payload and return the parsed response.

    Args:
        url: Full endpoint URL.
        payload: Dict to serialize as JSON body.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON response as a dict.

    Raises:
        urllib.error.URLError: On network or HTTP errors.
    """
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def run_council(prompt: str, url: str = COUNCIL_URL, timeout: float = 600.0) -> dict:
    """Create a council conversation and submit the prompt.

    Args:
        prompt: The full assembled prompt string.
        url: Base URL of the council backend.
        timeout: Seconds to wait for the council to complete all stages.
            Default 600 s (10 min). Raise to 900+ for large multi-context prompts.

    Returns:
        Full result dict with stage1, stage2, stage3, metadata keys.

    Raises:
        urllib.error.URLError: If any HTTP call fails.
    """
    conv = _post_json(f"{url}/api/conversations", {}, timeout=10.0)
    conv_id = conv["id"]
    return _post_json(
        f"{url}/api/conversations/{conv_id}/message",
        {"content": prompt},
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for ask_council.py."""
    parser = argparse.ArgumentParser(
        description="Submit a context-enriched question to the NiftyShield LLM council.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--topic",
        required=True,
        help="Short label used in the output filename (e.g. slippage-model).",
    )
    parser.add_argument(
        "--question",
        required=True,
        help="The design question to put to the council.",
    )
    parser.add_argument(
        "--template",
        choices=["data_architecture", "strategy_parameters", "backtest_methodology"],
        help="Domain preamble template to inject (see scripts/council_templates/).",
    )
    parser.add_argument(
        "--context",
        action="append",
        default=[],
        metavar="FILE",
        help="Additional project file to include as context (repeatable). "
             "Paths relative to project root.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the assembled prompt to stdout without submitting to the council.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        metavar="SECONDS",
        help="Seconds to wait for the council to complete all stages (default: 600). "
             "Raise to 900+ for large multi-context prompts.",
    )
    args = parser.parse_args()

    # Resolve and validate extra context files
    extra_files: list[Path] = []
    for raw in args.context:
        p = Path(raw)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        if not p.exists():
            print(f"ERROR: context file not found: {p}", file=sys.stderr)
            sys.exit(1)
        extra_files.append(p)

    prompt = build_prompt(
        question=args.question,
        context_md=CONTEXT_MD,
        templates_dir=TEMPLATES_DIR,
        template_name=args.template,
        extra_files=extra_files,
    )

    # Dry-run: just print the prompt for inspection
    if args.dry_run:
        print(prompt)
        return

    # Server offline: save prompt to pending/ for manual submission
    if not council_is_running():
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        pending_path = make_pending_path(args.topic, PENDING_DIR)
        pending_path.write_text(prompt)
        print(f"Council backend is not running at {COUNCIL_URL}.")
        print(f"  Start it:  cd tools/llm-council && ./start.sh")
        print(f"  Prompt saved to: {pending_path.relative_to(PROJECT_ROOT)}")
        print(f"  Re-run this command once the server is up.")
        sys.exit(0)

    # Submit to council
    timeout_min = args.timeout / 60
    print(f"Submitting '{args.topic}' to council… (timeout: {timeout_min:.0f} min)")
    try:
        result = run_council(prompt, timeout=args.timeout)
    except urllib.error.URLError as exc:
        print(f"ERROR: Council request failed: {exc}", file=sys.stderr)
        sys.exit(1)

    # Save decision
    COUNCIL_DIR.mkdir(parents=True, exist_ok=True)
    output_path = make_output_path(args.topic, COUNCIL_DIR)
    output_path.write_text(format_decision(args.topic, prompt, result))

    synthesis = result.get("stage3", {}).get("response", "")
    separator = "=" * 60
    print(f"\n{separator}")
    print(synthesis)
    print(f"{separator}")
    print(f"\nDecision saved to: {output_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
