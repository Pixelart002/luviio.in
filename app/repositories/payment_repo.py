"""Deprecated compatibility import for the payments repository.

Canonical ownership: ``app.domains.payments.repository``.
Keep this module temporarily for external/legacy imports during the domain
migration; new application code must import from the payments domain.
"""

from app.domains.payments.repository import AsyncPaymentRepository

__all__ = ["AsyncPaymentRepository"]
