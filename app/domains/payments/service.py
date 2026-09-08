"""
Payment Service -- Enterprise Orchestration (With Atomic GST & HSN Snapshots)
=============================================================================
Path: app/domains/payments/service.py

Architecture & Fixes:
  * Cart Lifecycle: Cart is cleared immediately upon successful atomic order creation & stock reservation.
  * Self-Healing Retry Logic: Auto-generates fresh Stripe intents for unlinked/canceled orders.
  * Atomic GST & HSN Snapshots: Locks exact legal inventory prices & tax rates at checkout.
  * Enterprise Snapshots: Captures full B2B/B2C Shipping & Billing address telemetry natively.
  * Idempotent Checkout: Prevents double-charging via UUID-based idempotency keys.
  * Null Intent Guard: Prevents 502 Bad Gateway crashes when Stripe ID is None or Empty in DB.
  * Payment Method Tracking: Extracts 'card', 'upi', etc. from Stripe Intents & Webhooks.
"""
import logging
import time
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException, status
from nanoid import generate
from starlette.concurrency import run_in_threadpool

from app.constants.payment_messages import PaymentMessages, PaymentRules, PaymentSecurityMessages
from app.domains.payments.repository import AsyncPaymentRepository
from app.domains.pricing.service import get_pricing_from_config
from app.enums.order_status import OrderStatus
from app.events.bus import OrderCreatedEvent, OrderFailedEvent, OrderPaidEvent, get_event_bus
from app.integrations.payments.registry import get_payment_provider
from app.permissions.policies.payment_policies import PaymentPolicy

logger = logging.getLogger(__name__)

class PaymentService:
    def __init__(self) -> None:
        self.repo = AsyncPaymentRepository()
        self.provider = get_payment_provider("stripe")

    # Existing implementation continues unchanged.
