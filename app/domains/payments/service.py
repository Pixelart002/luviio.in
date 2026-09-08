from __future__ import annotations

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
    pass
