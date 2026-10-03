"""Dependency-direction check: src.payoff is a leaf package."""

import ast
from pathlib import Path

import src.payoff

_FORBIDDEN = ("src.strategy", "src.notifications")


def test_payoff_package_import_boundary():
    root = Path(src.payoff.__file__).parent
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert not name.startswith(_FORBIDDEN), f"{path.name} imports {name}"
