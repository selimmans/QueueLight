"""Shared exception classes for Queue Light.

Adapted from Clove's bookings exception hierarchy — simplified for Queue Light's
narrower domain.
"""


class QueueError(Exception):
    """Base exception for all Queue Light domain errors."""
    default_message = "A queue error occurred."

    def __init__(self, message: str = "", detail: str = ""):
        self.message = message or self.default_message
        self.detail = detail
        super().__init__(self.message)


class RuleViolationError(QueueError):
    """Raised when a business rule is violated (bad transition, invalid state, etc.)."""
    default_message = "This action is not allowed."


class InvalidTransitionError(QueueError):
    """Raised when a status transition is not in ALLOWED_TRANSITIONS."""
    default_message = "This status transition is not permitted."


class BusinessInactiveError(QueueError):
    """Raised when a customer tries to join an inactive business's queue."""
    default_message = "This queue is not currently accepting customers."
