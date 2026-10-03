"""Module-boundary exception hierarchy for ``src.payoff``."""


class PayoffError(Exception):
    """Base class for all payoff-chart errors."""


class InvalidLegsError(PayoffError, ValueError):
    """Raised when a leg set is empty or a leg is malformed."""


class DuplicateRegistrationError(PayoffError):
    """Raised when a strategy name is registered twice."""


class RenderError(PayoffError):
    """Raised when chart rendering fails."""


class SendError(PayoffError):
    """Raised when sending a rendered chart fails."""
