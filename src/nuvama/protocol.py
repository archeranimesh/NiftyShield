"""NuvamaClient protocol — abstracts Nuvama APIConnect SDK behind a 2-method interface.

All callers accept NuvamaClient instead of the concrete APIConnect class,
enabling offline testing via MockNuvamaClient without importing the SDK.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class NuvamaClient(Protocol):
    """Minimal protocol over the Nuvama APIConnect SDK.

    Only Holdings() and NetPosition() are used across the codebase.
    Marking runtime_checkable allows isinstance(obj, NuvamaClient) checks,
    which tests use to verify MockNuvamaClient satisfies the protocol.
    """

    def Holdings(self) -> str:  # noqa: N802
        """Return raw Holdings() response as a JSON string."""
        ...

    def NetPosition(self) -> str:  # noqa: N802
        """Return raw NetPosition() response as a JSON string."""
        ...
