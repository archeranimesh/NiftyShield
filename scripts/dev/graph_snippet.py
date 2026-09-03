#!/usr/bin/env python3
"""Fetch a ``get_code_snippet`` result with the fingerprint bloat stripped.

``codebase-memory-mcp``'s ``get_code_snippet`` returns three fields the model
never consumes: ``fp`` (a ~512-char hex fingerprint), ``bt`` (a flat token bag
of every identifier in the body) and ``sp`` (a numeric shape vector). Together
they are ~244 tokens per call — ~20% of a typical snippet result — and they sit
resident in the context prefix for every subsequent turn.

This wrapper shells out to the MCP server's own CLI (``codebase-memory-mcp cli
get_code_snippet``), drops those three keys, and prints the rest as indented
JSON. Rule 0's "Need a symbol?" step points here instead of the raw MCP tool.

The real fix belongs upstream (a compact/fields mode on the server); see the
issue linked in ``docs/plan/token-efficiency/fixed-overhead/stories.md`` FIX-4.

``print`` here is the CLI output contract (indented JSON on stdout), not a log
line — so this script declares no structlog logger, matching ``reflow_md.py``.

Usage::

    python -m scripts.dev.graph_snippet <qualified_name>
    python -m scripts.dev.graph_snippet <qualified_name> --neighbors
    python -m scripts.dev.graph_snippet <qualified_name> --project <id>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any

_DEFAULT_PROJECT = "Users-abhadra-myWork-myCode-python-NiftyShield"
_FINGERPRINT_FIELDS = ("fp", "sp", "bt")


def strip_fingerprint_fields(snippet: dict[str, Any]) -> dict[str, Any]:
    """Return ``snippet`` without the consumer-unusable fingerprint keys.

    Args:
        snippet: A parsed ``get_code_snippet`` result object.

    Returns:
        A new dict with ``fp`` / ``sp`` / ``bt`` removed; all other keys
        (``source``, ``signature``, ``docstring``, ``callers`` …) preserved.
    """
    return {k: v for k, v in snippet.items() if k not in _FINGERPRINT_FIELDS}


def _run_cli(qualified_name: str, project: str, include_neighbors: bool) -> dict[str, Any]:
    """Invoke the MCP server CLI and return the parsed snippet object.

    Raises:
        RuntimeError: If the CLI process fails or times out, the payload
            shape is unrecognised, or the server reports an error (e.g.
            symbol not found — the message is forwarded verbatim).
    """
    payload = {
        "qualified_name": qualified_name,
        "project": project,
        "include_neighbors": include_neighbors,
    }
    try:
        proc = subprocess.run(
            ["codebase-memory-mcp", "cli", "get_code_snippet", json.dumps(payload)],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("codebase-memory-mcp cli timed out after 30s") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"codebase-memory-mcp cli failed: {proc.stderr.strip()}")
    try:
        envelope = json.loads(proc.stdout)
        text = envelope["content"][0]["text"]
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        raise RuntimeError(f"unexpected CLI payload: {exc!r}") from exc
    if envelope.get("isError"):
        raise RuntimeError(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"snippet body was not JSON: {exc!r}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(
        description="get_code_snippet without the fp/sp/bt fingerprint fields."
    )
    parser.add_argument("qualified_name", help="Full qualified_name from search_graph")
    parser.add_argument(
        "--project", default=_DEFAULT_PROJECT, help="Graph project id (default: this repo)"
    )
    parser.add_argument(
        "--neighbors", action="store_true", help="Pass include_neighbors=true to the server"
    )
    args = parser.parse_args()

    try:
        snippet = _run_cli(args.qualified_name, args.project, args.neighbors)
    except RuntimeError as exc:
        sys.exit(f"graph_snippet: {exc}")
    print(json.dumps(strip_fingerprint_fields(snippet), indent=2))


if __name__ == "__main__":
    main()
