"""Domain errors for the Nifty positional calendar strategy."""


class CalendarError(Exception):
    """Base exception for all calendar strategy errors."""


class InvalidStructureError(CalendarError):
    """Raised when a calendar structure violates structural invariant rules."""


class MissingGreeksError(CalendarError):
    """Raised when a calendar leg is missing required Greeks (delta, vega, iv)."""
