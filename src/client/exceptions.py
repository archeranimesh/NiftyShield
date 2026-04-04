"""Custom exceptions for the broker client layer.

Hierarchy:
    BrokerError
    └── DataFetchError          — market data fetch failed (retryable)
        └── LTPFetchError       — LTP batch request failed entirely
"""


class BrokerError(Exception):
    """Base exception for all broker client errors."""


class DataFetchError(BrokerError):
    """Market data fetch failed — retryable."""


class LTPFetchError(DataFetchError):
    """LTP batch request returned no data at all.

    Raised when the API response is empty or the HTTP request fails
    for every instrument in a batch. Callers should treat this as a
    hard failure and not proceed with stale/zero prices.
    """
