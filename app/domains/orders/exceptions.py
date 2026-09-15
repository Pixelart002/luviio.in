"""Domain exceptions for order persistence and business boundaries."""


class OrderRepositoryError(Exception):
    """Raised when the order repository cannot complete a persistence operation."""
