"""Custom exceptions for the broker client layer.

Hierarchy:
    BrokerError
    ├── AuthenticationError       — token expired, invalid credentials, OAuth failure
    ├── RateLimitError            — 429 or rate limit threshold hit (retryable)
    ├── DataFetchError            — market data fetch failed (retryable)
    │   └── LTPFetchError        — LTP batch request failed entirely
    ├── OrderRejectedError        — exchange/broker rejected the order (terminal)
    │   └── InsufficientMarginError — not enough margin (terminal)
    └── InstrumentNotFoundError   — invalid instrument key (terminal)
"""


class BrokerError(Exception):
    """Base exception for all broker client errors."""


class AuthenticationError(BrokerError):
    """Token expired, invalid credentials, or OAuth failure."""


class RateLimitError(BrokerError):
    """429 or rate limit threshold hit — retryable."""


class DataFetchError(BrokerError):
    """Market data fetch failed — retryable."""


class LTPFetchError(DataFetchError):
    """LTP batch request returned no data at all.

    Raised when the API response is empty or the HTTP request fails
    for every instrument in a batch. Callers should treat this as a
    hard failure and not proceed with stale/zero prices.
    """


class OrderRejectedError(BrokerError):
    """Exchange or broker rejected the order — terminal."""


class InsufficientMarginError(OrderRejectedError):
    """Not enough margin to place the order — terminal."""


class InstrumentNotFoundError(BrokerError):
    """Invalid instrument key — terminal."""
