"""
Payments Router — Enterprise Grade
====================================
Path: app/api/v1/routers/payments.py

Architecture Upgrades:
  1. ALL Supabase DB logic delegated to PaymentRepository.
  2. Stripe SDK removed! Delegated to PaymentRegistry.
  3. Schemas strict mapping to DTOs.
"""
import copy
import hashlib
import logging
import time
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from slowapi import Limiter
from slowapi.util import get_remote_address

# 🔥 ARCHITECTURE IMPORTS
from app.core.dependencies import get_current_user
from app.repositories.payment_repo import PaymentRepository
from app.services.stock import restore_stock
from app.services.events import get_event_bus, OrderPaidEvent, OrderFailedEvent
from app.integrations.payments.registry import get_payment_provider
from app.api.schemas.payment_dto import (
    PaymentIntentRequest, PaymentIntentResponse, 
    ConfirmPaymentRequest, NotifyFailedRequest
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["Payments"])
limiter = Limiter(key_func=get_remote_address)

# ══════════════════════════════════════════════════════════════════════════════
#  BRUTE FORCE PROTECTION SYSTEM (Remains in Router/Security Layer)
# ══════════════════════════════════════════════════════════════════════════════

class BruteForceGuard:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 300, cooldown_seconds: int = 900):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self.attempts: dict[str, list[float]] = defaultdict(list)
        self.blocked: dict[str, float] = {}
    
    def _cleanup(self):
        now = time.time()
        self.attempts = defaultdict(list, {k: [t for t in v if now - t < self.window_seconds] for k, v in self.attempts.items()})
        self.blocked = {k: v for k, v in self.blocked.items() if v > now}
    
    def _fingerprint(self, ip: str, user_id: str = "", endpoint: str = "") -> str:
        return hashlib.sha256(f"{ip}:{user_id}:{endpoint}".encode()).hexdigest()[:16]
    
    def is_blocked(self, ip: str, user_id: str = "", endpoint: str = "") -> bool:
        self._cleanup()
        fp = self._fingerprint(ip, user_id, endpoint)
        return fp in self.blocked or ip in self.blocked
    
    def record_attempt(self, ip: str, user_id: str = "", endpoint: str = "") -> bool:
        now = time.time()
        self._cleanup()
        fp = self._fingerprint(ip, user_id, endpoint)
        self.attempts[fp].append(now); self.attempts[ip].append(now)
        
        if len(self.attempts[fp]) > self.max_attempts:
            self.blocked[fp] = now + self.cooldown_seconds
            return True
        if len(self.attempts[ip]) > self.max_attempts * 3:
            self.blocked[ip] = now + self.cooldown_seconds * 2
            return True
        return False
    
    def reset(self, ip: str, user_id: str = "", endpoint: str = ""):
        fp = self._fingerprint(ip, user_id, endpoint)
        self.attempts.pop(fp, None); self.blocked.pop(fp, None)

brute_force = BruteForceGuard()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_id(current_user: dict[str, Any]) -> str:
    profile = current_user.get("profile")
    if isinstance(profile, dict) and "id" in profile: return str(profile["id"])
    if "id" in current_user: return str(current_user["id"])
    if "sub" in current_user: return str(current_user["sub"])
    raise HTTPException(401, "User ID not found in session")

def _amount_to_paise(amount: Any) -> int:
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

def _audit_log(action: str, user_id: str, ip: str, order_id: str = "", details: str = ""):
    logger.info("AUDIT | action=%s user=%.8s ip=%s order=%.8s | %s", action, user_id, ip, order_id, details)

# ══════════════════════════════════════════════════════════════════════════════
#  POST /payments/create-intent
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/create-intent", response_model=PaymentIntentResponse)
@limiter.limit("10/minute")
def create_payment_intent(request: Request, payload: PaymentIntentRequest, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    repo = PaymentRepository()
    payment_service = get_payment_provider("stripe")
    user_id = _get_user_id(current)
    order_id = str(payload.order_id)
    client_ip = get_remote_address(request)
    
    if brute_force.is_blocked(client_ip, user_id, "create_intent"):
        _audit_log("BLOCKED", user_id, client_ip, order_id, "brute_force_cooldown")
        raise HTTPException(429, "Too many attempts. Please try again later.")
    
    order = repo.get_order_for_payment(order_id, user_id)
    if not order:
        brute_force.record_attempt(client_ip, user_id, "create_intent")
        _audit_log("NOT_FOUND", user_id, client_ip, order_id, "order not found")
        raise HTTPException(404, "Order not found")

    if order["status"] != "pending":
        raise HTTPException(409, f"Order not payable (status: {order['status']})")

    amount_paise = _amount_to_paise(order["total_amount"])
    if amount_paise < 50 * 100 or amount_paise > 10_00_000 * 100:
        raise HTTPException(400, "Order amount out of bounds")

    existing_pi_id = order.get("stripe_payment_intent")

    try:
        if existing_pi_id:
            intent = payment_service.retrieve_intent(existing_pi_id)
            if intent["status"] in ("canceled", "succeeded"):
                idem_key = f"pi_v2_{order_id}_{existing_pi_id[-8:]}"
                intent = payment_service.create_payment_intent(amount_paise, "inr", order_id, user_id, idem_key)
                repo.update_order_pi(order_id, intent["id"])
        else:
            idem_key = f"pi_v1_{order_id}"
            intent = payment_service.create_payment_intent(amount_paise, "inr", order_id, user_id, idem_key)
            repo.update_order_pi(order_id, intent["id"])

    except Exception as exc:
        brute_force.record_attempt(client_ip, user_id, "create_intent")
        raise HTTPException(502, f"Payment provider error")

    brute_force.reset(client_ip, user_id, "create_intent")
    _audit_log("INTENT_CREATED", user_id, client_ip, order_id, f"pi={intent['id']}")
        
    return {"client_secret": intent["client_secret"], "payment_intent_id": intent["id"]}


# ══════════════════════════════════════════════════════════════════════════════
#  POST /payments/confirm
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/confirm")
@limiter.limit("10/minute")
def confirm_payment(request: Request, payload: ConfirmPaymentRequest, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    repo = PaymentRepository()
    payment_service = get_payment_provider("stripe")
    user_id = _get_user_id(current)
    order_id = str(payload.order_id)
    client_ip = get_remote_address(request)
    
    if brute_force.is_blocked(client_ip, user_id, "confirm"): raise HTTPException(429, "Too many attempts.")
    
    order = repo.get_order_for_payment(order_id, user_id)
    if not order:
        brute_force.record_attempt(client_ip, user_id, "confirm")
        raise HTTPException(404, "Order not found")

    if order["status"] == "paid": return {"status": "paid", "order_id": order["id"], "message": "Already paid"}
    if order["status"] != "pending": raise HTTPException(409, f"Cannot confirm '{order['status']}' order")

    try:
        intent = payment_service.retrieve_intent(payload.payment_intent_id)
    except Exception as exc:
        brute_force.record_attempt(client_ip, user_id, "confirm")
        raise HTTPException(502, "Verification failed")

    if intent["status"] != "succeeded":
        brute_force.record_attempt(client_ip, user_id, "confirm")
        raise HTTPException(400, f"Payment not completed. Status: {intent['status']}")

    order_amount = float(order["total_amount"])
    stripe_amount = intent["amount"] / 100
    
    if abs(stripe_amount - order_amount) > 0.50:
        raise HTTPException(400, "Payment amount mismatch — contact support")
    
    if intent["currency"].lower() != "inr":
        raise HTTPException(400, "Invalid payment currency")
    
    if order.get("stripe_payment_intent") != payload.payment_intent_id:
        raise HTTPException(400, "Payment intent mismatch")

    if not repo.update_order_status(order["id"], "paid", "pending"):
        return {"status": "paid", "order_id": order["id"], "message": "Already processed"}

    repo.create_payment_record(order["id"], payload.payment_intent_id, stripe_amount, "INR", "completed", "stripe")
    brute_force.reset(client_ip, user_id, "confirm")
    
    paid_order = copy.copy(order); paid_order["status"] = "paid"
    email = current.get("profile", {}).get("email") or repo.get_customer_email(order.get("customer_id", ""))
    
    try: get_event_bus().publish(OrderPaidEvent(order=paid_order, customer_email=email, customer_id=order.get("customer_id", "")))
    except Exception: pass

    return {"status": "paid", "order_id": order["id"], "message": "Payment confirmed"}


# ══════════════════════════════════════════════════════════════════════════════
#  POST /payments/notify-failed
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/notify-failed", status_code=200)
@limiter.limit("5/minute")
def notify_payment_failed(request: Request, payload: NotifyFailedRequest, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    repo = PaymentRepository()
    user_id = _get_user_id(current)
    order_id = str(payload.order_id)
    client_ip = get_remote_address(request)
    
    if brute_force.is_blocked(client_ip, user_id, "notify_failed"): raise HTTPException(429, "Too many attempts")

    order = repo.get_order_for_payment(order_id, user_id)
    if not order or order["status"] != "pending": return {"message": "OK"}

    if order.get("stripe_payment_intent") != payload.payment_intent_id:
        brute_force.record_attempt(client_ip, user_id, "notify_failed")
        raise HTTPException(400, "Payment intent mismatch")

    reason = payload.error_message.strip() or "payment_failed"
    _audit_log("PAYMENT_FAILED", user_id, client_ip, order_id, reason)
    
    try:
        get_event_bus().publish(OrderFailedEvent(
            order=order, customer_email=repo.get_customer_email(order.get("customer_id", "")),
            customer_id=order.get("customer_id", ""), reason=reason,
        ))
    except Exception: pass

    return {"message": "OK"}


# ══════════════════════════════════════════════════════════════════════════════
#  POST /payments/webhook
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str | None = Header(None, alias="stripe-signature")) -> dict[str, str]:
    body = await request.body()
    client_ip = get_remote_address(request)
    repo = PaymentRepository()
    payment_service = get_payment_provider("stripe")

    if not stripe_signature: raise HTTPException(400, "Missing stripe-signature")

    try:
        event = payment_service.verify_webhook(body, stripe_signature)
    except ValueError:
        _audit_log("WEBHOOK_INVALID_SIG", "system", client_ip, "", "signature_verification_failed")
        raise HTTPException(400, "Invalid signature")

    event_type, pi_id = event["type"], event["pi_id"]
    logger.info("Webhook | type=%s pi=%s ip=%s", event_type, pi_id, client_ip)

    if event_type == "payment_intent.succeeded":
        order = repo.get_order_by_pi(pi_id)
        if not order or order["status"] != "pending": return {"message": "OK"}

        if not repo.update_order_status(order["id"], "paid", "pending"): return {"message": "OK"}

        repo.create_payment_record(order["id"], pi_id, event["amount"] / 100, "INR", "completed", "stripe")
        
        try:
            paid_order = copy.copy(order); paid_order["status"] = "paid"
            get_event_bus().publish(OrderPaidEvent(
                order=paid_order, customer_email=repo.get_customer_email(order.get("customer_id", "")), customer_id=order.get("customer_id", "")
            ))
        except Exception: pass

    elif event_type in ("payment_intent.payment_failed", "payment_intent.canceled"):
        order = repo.get_order_by_pi(pi_id)
        if not order or order["status"] != "pending": return {"message": "OK"}

        repo.update_order_status(order["id"], "cancelled", "pending")
        
        # We need raw Supabase client for stock restoration since it relies on atomic DB functions
        from app.core.supabase import get_admin_supabase
        sb = get_admin_supabase()
        for item in order.get("order_items", []):
            if item.get("product_id"): restore_stock(sb, item["product_id"], item["quantity"], f"webhook_{event_type}")

    return {"message": "OK"}