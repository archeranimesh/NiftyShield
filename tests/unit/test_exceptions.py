"""Unit tests for the exception hierarchy in src/client/exceptions.py.

All tests are offline — no imports beyond src.client.exceptions.
One test per hierarchy relationship (8 total).
"""

from src.client.exceptions import (
    AuthenticationError,
    BrokerError,
    DataFetchError,
    InstrumentNotFoundError,
    InsufficientMarginError,
    LTPFetchError,
    OrderRejectedError,
    RateLimitError,
)


def test_authentication_error_is_broker_error() -> None:
    """AuthenticationError must be catchable as BrokerError."""
    assert isinstance(AuthenticationError("token expired"), BrokerError)


def test_rate_limit_error_is_broker_error() -> None:
    """RateLimitError must be catchable as BrokerError."""
    assert isinstance(RateLimitError("429"), BrokerError)


def test_data_fetch_error_is_broker_error() -> None:
    """DataFetchError must be catchable as BrokerError."""
    assert isinstance(DataFetchError("fetch failed"), BrokerError)


def test_ltp_fetch_error_is_data_fetch_error() -> None:
    """LTPFetchError must be catchable as DataFetchError."""
    assert isinstance(LTPFetchError("no data"), DataFetchError)


def test_ltp_fetch_error_is_broker_error() -> None:
    """LTPFetchError must be catchable as BrokerError (transitive)."""
    assert isinstance(LTPFetchError("no data"), BrokerError)


def test_order_rejected_error_is_broker_error() -> None:
    """OrderRejectedError must be catchable as BrokerError."""
    assert isinstance(OrderRejectedError("rejected"), BrokerError)


def test_insufficient_margin_error_is_order_rejected_error() -> None:
    """InsufficientMarginError must be catchable as OrderRejectedError."""
    assert isinstance(InsufficientMarginError("no margin"), OrderRejectedError)


def test_insufficient_margin_error_is_broker_error() -> None:
    """InsufficientMarginError must be catchable as BrokerError (transitive)."""
    assert isinstance(InsufficientMarginError("no margin"), BrokerError)


def test_instrument_not_found_error_is_broker_error() -> None:
    """InstrumentNotFoundError must be catchable as BrokerError."""
    assert isinstance(InstrumentNotFoundError("bad key"), BrokerError)
