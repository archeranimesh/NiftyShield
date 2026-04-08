"""Composition root for broker client instantiation.

This is the **only** module in ``src/`` that imports concrete broker client
implementations (``UpstoxLiveClient``, ``MockBrokerClient``).  All other
modules receive a ``BrokerClient`` via constructor injection — they must
never import concrete client classes directly.
"""

from __future__ import annotations

import os
from typing import Any, Final

from src.client.mock_client import MockBrokerClient
from src.client.protocol import BrokerClient
from src.client.upstox_live import UpstoxLiveClient

VALID_ENVS: Final = ("prod", "sandbox", "test")


def create_client(env: str, **kwargs: Any) -> BrokerClient:
    """Instantiate the correct broker client for the target environment.

    This is the single composition root — the only place that knows which
    concrete implementation to wire.  Call it at application startup (or in
    test ``conftest.py``) and inject the returned instance everywhere else.

    Args:
        env: Target environment.  Must be one of ``VALID_ENVS``:

            * ``"prod"``    — :class:`UpstoxLiveClient` reading
              ``UPSTOX_ANALYTICS_TOKEN`` from env (or pass ``token=``).
            * ``"sandbox"`` — :class:`UpstoxLiveClient` reading
              ``UPSTOX_SANDBOX_TOKEN`` from env (or pass ``token=``).
            * ``"test"``    — :class:`MockBrokerClient` (offline, no token).

        **kwargs: Forwarded to the chosen client constructor.

            * ``prod`` / ``sandbox``: ``token`` (``str | None``)
            * ``test``:  ``fixtures_dir`` (``Path | None``),
              ``initial_margin`` (``float``, default ``500_000.0``)

    Returns:
        A :class:`BrokerClient` instance.

    Raises:
        ValueError: If *env* is not one of ``VALID_ENVS``.
    """
    if env == "prod":
        return UpstoxLiveClient(token=kwargs.get("token"))

    if env == "sandbox":
        token = kwargs.get("token") or os.getenv("UPSTOX_SANDBOX_TOKEN")
        return UpstoxLiveClient(token=token)

    if env == "test":
        return MockBrokerClient(
            fixtures_dir=kwargs.get("fixtures_dir"),
            initial_margin=kwargs.get("initial_margin", 500_000.0),
        )

    raise ValueError(f"Unknown env '{env}'. Valid values: {VALID_ENVS}")
