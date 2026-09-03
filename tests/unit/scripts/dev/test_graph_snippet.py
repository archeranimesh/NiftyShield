"""Tests for scripts.dev.graph_snippet."""

from __future__ import annotations

from scripts.dev.graph_snippet import strip_fingerprint_fields

_RAW_SNIPPET = {
    "name": "aggregate_delta",
    "qualified_name": "pkg.mod.Cls.aggregate_delta",
    "source": "def aggregate_delta(self): ...",
    "signature": "(self, paper_positions, nifty_spot)",
    "return_type": "PortfolioDelta",
    "docstring": "Compute aggregate portfolio delta.",
    "callers": 26,
    "fp": "02732deb01379367048a19610009c825",  # pragma: allowlist secret
    "sp": "3,1,0,0,0,1,9,44,9",
    "bt": "nifty_spot Decimal ValueError lot_size options_delta",
}


def test_strips_fingerprint_fields() -> None:
    out = strip_fingerprint_fields(_RAW_SNIPPET)
    assert "fp" not in out
    assert "sp" not in out
    assert "bt" not in out


def test_preserves_source_and_signature() -> None:
    out = strip_fingerprint_fields(_RAW_SNIPPET)
    assert out["source"] == _RAW_SNIPPET["source"]
    assert out["signature"] == _RAW_SNIPPET["signature"]
    assert out["docstring"] == _RAW_SNIPPET["docstring"]
    assert out["callers"] == 26


def test_noop_when_fields_absent() -> None:
    clean = {"name": "x", "source": "pass"}
    assert strip_fingerprint_fields(clean) == clean
