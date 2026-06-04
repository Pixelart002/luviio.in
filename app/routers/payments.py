"""
Payments Router — Security Hardened
====================================
IDEMPOTENCY + ANTI-FRAUD + RATE LIMITING + BRUTE FORCE PROTECTION

Security Layers:
  1. Rate Limiting — per endpoint, per IP, per user
  2. Brute Force Detection — consecutive failures trigger cooldown
  3. Amount Tampering Detection — Stripe amount vs DB amount
  4. PI Mismatch Detection — stored PI vs received PI
  5. Atomic DB Updates — TOCTOU safe
  6. Idempotency Keys — stripe level + DB level
  7. Webhook Signature Verification — Stripe's official verification
  8. IP Blacklisting — after threshold violations
  9. NEW: Pure Window Logger integrated for visual terminal trails
"""
import copy
import hashlib
import logging
import time
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.dependencies import get_current_user
from app.supabase_client import get_admin_supabase
from app.utils.stock import restore_stock
from app.services.events import get_event_bus, OrderPaidEvent, OrderFailedEvent

# ── Stripe key guard ──────────────────────────────────────────────────────────
if not settings.STRIPE_SECRET_KEY:
    raise RuntimeError("STRIPE_SECRET_KEY not set — payments disabled")

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["Payments"])

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)


# ══════════════════════════════════════════════════════════════════════════════
#  BRUTE FORCE PROTECTION SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

class BruteForceGuard:
    """
    In-memory brute force detection.
    Production: Replace with Redis for multi-instance support.
    """
    def __init__(
        self, 
        max_attempts: int = 5, 
        window_seconds: int = 300, 
        cooldown_seconds: int = 900
    ):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self.attempts: dict[str, list[float]] = defaultdict(list)
        self.blocked: dict[str, float] = {}
    
    def _cleanup(self):
        now = time.time()
        self.attempts = defaultdict(list, {
            k: [t for t in v if now - t < self.window_seconds]
            for k, v in self.attempts.items()
        })
        self.blocked = {k: v for k, v in self.blocked.items() if v > now}
    
    def _fingerprint(self, ip: str, user_id: str = "", endpoint: str = "") -> str:
        raw = f"{ip}:{user_id}:{endpoint}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    
    def is_blocked(self, ip: str, user_id: str = "", endpoint: str = "") -> bool:
        self._cleanup()
        fp = self._fingerprint(ip, user_id, endpoint)
        if fp in self.blocked:
            return True
        if ip in self.blocked:
            return True
        return False
    
    def record_attempt(self, ip: str, user_id: str = "", endpoint: str = "") -> bool:
        now = time.time()
        self._cleanup()
        
        fp = self._fingerprint(ip, user_id, endpoint)
        self.attempts[fp].append(now)
        self.attempts[ip].append(now)
        
        if len(self.attempts[fp]) > self.max_attempts:
            self.blocked[fp] = now + self.cooldown_seconds
            logger.warning(
                "BRUTE FORCE BLOCK | fp=%s ip=%s user=%s endpoint=%s attempts=%d cooldown=%ds",
                fp, ip, user_id, endpoint, len(self.attempts[fp]), self.cooldown_seconds
            )
            return True
        
        if len(self.attempts[ip]) > self.max_attempts * 3:
            self.blocked[ip] = now + self.cooldown_seconds * 2
            logger.warning(
                "BRUTE FORCE IP BLOCK | ip=%s attempts=%d cooldown=%ds",
                ip, len(self.attempts[ip]), self.cooldown_seconds * 2
            )
            return True
        
        return False
    
    def reset(self, ip: str, user_id: str = "", endpoint: str = ""):
        fp = self._fingerprint(ip, user_id, endpoint)
        self.attempts.pop(fp, None)
        self.blocked.pop(fp, None)


brute_force = BruteForceGuard(max_attempts=5, window_seconds=300, cooldown_seconds=900)


# ── Schemas ───────────────────────────────────────────────────────────────────

class PaymentIntentRequest(BaseModel):
    order_id: UUID

class PaymentIntentResponse(BaseModel):
    client_secret: str
    payment_intent_id: str

class ConfirmPaymentRequest(BaseModel):
    order_id: UUID
    payment_intent_id: str

class NotifyFailedRequest(BaseModel):
    order_id: UUID
    payment_intent_id: str
    error_message: str = Field(default="", max_length=500)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_id(current_user: dict[str, Any]) -> str:
    profile = current_user.get("profile")
    if isinstance(profile, dict) and "id" in profile:
        return str(profile["id"])
    if "id" in current_user:
        return str(current_user["id"])
    if "sub" in current_user:
        return str(current_user["sub"])
    raise HTTPException(401, "User ID not found in session")


def _amount_to_paise(amount: Any) -> int:
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _get_customer_email(sb: Any, customer_id: str) -> str:
    if not customer_id: return ""
    try:
        res = sb.table("users").select("email").eq("id", customer_id).limit(1).execute()
        if res and hasattr(res, "data") and res.data:
            return res.data[0].get("email", "")
        return ""
    except Exception:
        return ""


def _audit_log(action: str, user_id: str, ip: str, order_id: str = "", details: str = ""):
    logger.info(
        "AUDIT | action=%s user=%.8s ip=%s order=%.8s | %s",
        action, user_id, ip, order_id, details
    )


# ══════════════════════════════════════════════════════════════════════════════
#  POST /payments/create-intent
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/create-intent", response_model=PaymentIntentResponse)
@limiter.limit("10/minute")
def create_payment_intent(
    request: Request,
    payload: PaymentIntentRequest,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Create Stripe PaymentIntent with brute force protection"""
    sb = get_admin_supabase()
    user_id = _get_user_id(current)
    order_id = str(payload.order_id)
    client_ip = get_remote_address(request)
    
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Requesting Payment Intent for Order #{order_id[:8].upper()}")
    
    if brute_force.is_blocked(client_ip, user_id, "create_intent"):
        _audit_log("BLOCKED", user_id, client_ip, order_id, "brute_force_cooldown")
        raise HTTPException(429, "Too many attempts. Please try again later.")
    
    if hasattr(request.state, "actions"):
        request.state.actions.append("Passed Brute Force Guards")
    
    try:
        order_res = (
            sb.table("orders")
            .select("id, status, total_amount, stripe_payment_intent")
            .eq("id", order_id).eq("customer_id", user_id)
            .maybe_single().execute()
        )
    except Exception as exc:
        logger.error("DB error | order=%s: %s", order_id, exc)
        raise HTTPException(500, "Error fetching order")

    if not order_res or not order_res.data:
        brute_force.record_attempt(client_ip, user_id, "create_intent")
        _audit_log("NOT_FOUND", user_id, client_ip, order_id, "order not found or not owned")
        raise HTTPException(404, "Order not found")

    order = order_res.data
    if order["status"] != "pending":
        _audit_log("INVALID_STATUS", user_id, client_ip, order_id, f"status={order['status']}")
        raise HTTPException(409, f"Order not payable (status: {order['status']})")

    amount_paise = _amount_to_paise(order["total_amount"])
    existing_pi_id = order.get("stripe_payment_intent")

    if amount_paise < 50 * 100:
        raise HTTPException(400, "Order amount too low for payment processing")
    if amount_paise > 10_00_000 * 100:
        raise HTTPException(400, "Order amount exceeds maximum limit")

    try:
        if existing_pi_id:
            intent = stripe.PaymentIntent.retrieve(existing_pi_id)
            if intent.status in ("canceled", "succeeded"):
                if hasattr(request.state, "actions"):
                    request.state.actions.append("Recreating expired/invalid intent via Stripe API")
                idem_key = f"pi_v2_{order_id}_{existing_pi_id[-8:]}"
                intent = stripe.PaymentIntent.create(
                    amount=amount_paise, currency="inr",
                    metadata={"order_id": order_id, "user_id": user_id},
                    automatic_payment_methods={"enabled": True},
                    description=f"{settings.APP_NAME} — Order #{order_id[:8].upper()}",
                    idempotency_key=idem_key,
                )
                sb.table("orders").update({"stripe_payment_intent": intent.id}).eq("id", order_id).execute()
            else:
                if hasattr(request.state, "actions"):
                    request.state.actions.append("Re-using valid existing Stripe Payment Intent")
        else:
            if hasattr(request.state, "actions"):
                request.state.actions.append("Creating new intent via Stripe API")
            idem_key = f"pi_v1_{order_id}"
            intent = stripe.PaymentIntent.create(
                amount=amount_paise, currency="inr",
                metadata={"order_id": order_id, "user_id": user_id},
                automatic_payment_methods={"enabled": True},
                description=f"{settings.APP_NAME} — Order #{order_id[:8].upper()}",
                idempotency_key=idem_key,
            )
            sb.table("orders").update({"stripe_payment_intent": intent.id}).eq("id", order_id).execute()

    except stripe.error.IdempotencyError:
        raise HTTPException(409, "Payment intent conflict — please refresh")
    except stripe.error.CardError as exc:
        brute_force.record_attempt(client_ip, user_id, "create_intent")
        raise HTTPException(402, f"Card error: {exc.user_message}")
    except stripe.error.StripeError as exc:
        raise HTTPException(502, f"Payment provider error: {exc.user_message or 'Unknown'}")

    brute_force.reset(client_ip, user_id, "create_intent")
    _audit_log("INTENT_CREATED", user_id, client_ip, order_id, f"pi={intent.id}")
    
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Intent returned: {intent.id}")
        
    return {"client_secret": intent.client_secret, "payment_intent_id": intent.id}


# ══════════════════════════════════════════════════════════════════════════════
#  POST /payments/confirm
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/confirm")
@limiter.limit("10/minute")
def confirm_payment(
    request: Request,
    payload: ConfirmPaymentRequest,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Confirm payment with anti-fraud checks"""
    sb = get_admin_supabase()
    user_id = _get_user_id(current)
    order_id = str(payload.order_id)
    client_ip = get_remote_address(request)
    
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Starting fraud checks for Order #{order_id[:8].upper()}")

    if brute_force.is_blocked(client_ip, user_id, "confirm"):
        raise HTTPException(429, "Too many attempts. Please try again later.")
    
    order_res = (
        sb.table("orders")
        .select("id, status, total_amount, stripe_payment_intent, customer_id")
        .eq("id", order_id).eq("customer_id", user_id)
        .maybe_single().execute()
    )
    if not order_res or not order_res.data:
        brute_force.record_attempt(client_ip, user_id, "confirm")
        raise HTTPException(404, "Order not found")

    order = order_res.data
    if order["status"] == "paid":
        return {"status": "paid", "order_id": order["id"], "message": "Already paid"}
    if order["status"] != "pending":
        raise HTTPException(409, f"Cannot confirm '{order['status']}' order")

    try:
        intent = stripe.PaymentIntent.retrieve(payload.payment_intent_id)
        if hasattr(request.state, "actions"):
            request.state.actions.append("Successfully fetched actual status from Stripe")
    except stripe.error.StripeError as exc:
        brute_force.record_attempt(client_ip, user_id, "confirm")
        raise HTTPException(502, f"Verification failed: {exc.user_message}")

    if intent.status != "succeeded":
        brute_force.record_attempt(client_ip, user_id, "confirm")
        _audit_log("PAYMENT_NOT_SUCCEEDED", user_id, client_ip, order_id, f"stripe_status={intent.status}")
        raise HTTPException(400, f"Payment not completed. Status: {intent.status}")

    order_amount = float(order["total_amount"])
    stripe_amount = intent.amount / 100
    
    if abs(stripe_amount - order_amount) > 0.50:
        _audit_log("AMOUNT_MISMATCH", user_id, client_ip, order_id, f"db={order_amount} stripe={stripe_amount}")
        raise HTTPException(400, "Payment amount mismatch — contact support")
    
    if intent.currency.lower() != "inr":
        _audit_log("CURRENCY_MISMATCH", user_id, client_ip, order_id, f"currency={intent.currency}")
        raise HTTPException(400, "Invalid payment currency")
    
    stored_pi = order.get("stripe_payment_intent")
    if stored_pi and stored_pi != payload.payment_intent_id:
        _audit_log("PI_MISMATCH", user_id, client_ip, order_id, f"stored={stored_pi} received={payload.payment_intent_id}")
        raise HTTPException(400, "Payment intent mismatch")
        
    if hasattr(request.state, "actions"):
        request.state.actions.append("Anti-fraud validation passed (Amount, Currency, PI Match)")

    update_res = (
        sb.table("orders")
        .update({"status": "paid"})
        .eq("id", order["id"]).eq("status", "pending")
        .execute()
    )
    if not update_res or not update_res.data:
        return {"status": "paid", "order_id": order["id"], "message": "Already processed"}

    try:
        sb.table("payments").insert({
            "order_id": order["id"],
            "stripe_payment_intent_id": payload.payment_intent_id,
            "amount": stripe_amount, "currency": "INR",
            "status": "completed", "payment_method": "stripe",
        }).execute()
        if hasattr(request.state, "actions"):
            request.state.actions.append("Transaction log saved in payments table")
    except Exception:
        pass

    brute_force.reset(client_ip, user_id, "confirm")
    _audit_log("PAYMENT_CONFIRMED", user_id, client_ip, order_id, f"amount={stripe_amount}")
    
    try:
        paid_order = copy.copy(order); paid_order["status"] = "paid"
        email = current.get("profile", {}).get("email", "") or _get_customer_email(sb, order.get("customer_id", ""))
        get_event_bus().publish(OrderPaidEvent(order=paid_order, customer_email=email, customer_id=order.get("customer_id", "")))
        if hasattr(request.state, "actions"):
            request.state.actions.append("Dispatched background OrderPaidEvent")
    except Exception:
        pass

    return {"status": "paid", "order_id": order["id"], "message": "Payment confirmed"}


# ══════════════════════════════════════════════════════════════════════════════
#  POST /payments/notify-failed
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/notify-failed", status_code=200)
@limiter.limit("5/minute")
def notify_payment_failed(
    request: Request,
    payload: NotifyFailedRequest,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Record payment failure"""
    sb = get_admin_supabase()
    user_id = _get_user_id(current)
    order_id = str(payload.order_id)
    client_ip = get_remote_address(request)
    
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Recording payment failure for: {order_id[:8].upper()}")
    
    if brute_force.is_blocked(client_ip, user_id, "notify_failed"):
        raise HTTPException(429, "Too many attempts")

    order_res = (
        sb.table("orders")
        .select("id, status, customer_id, stripe_payment_intent")
        .eq("id", order_id).eq("customer_id", user_id)
        .maybe_single().execute()
    )
    if not order_res or not order_res.data:
        raise HTTPException(404, "Order not found")

    order = order_res.data
    if order["status"] != "pending":
        return {"message": "OK"}

    stored_pi = order.get("stripe_payment_intent")
    if not stored_pi or stored_pi != str(payload.payment_intent_id):
        brute_force.record_attempt(client_ip, user_id, "notify_failed")
        raise HTTPException(400, "Payment intent mismatch")

    reason = payload.error_message.strip() or "payment_failed"
    _audit_log("PAYMENT_FAILED", user_id, client_ip, order_id, reason)
    
    try:
        get_event_bus().publish(OrderFailedEvent(
            order=order, customer_email=_get_customer_email(sb, order.get("customer_id", "")),
            customer_id=order.get("customer_id", ""), reason=reason,
        ))
        if hasattr(request.state, "actions"):
            request.state.actions.append(f"Failure logged. Reason: {reason}")
    except Exception:
        pass

    return {"message": "OK"}


# ══════════════════════════════════════════════════════════════════════════════
#  POST /payments/webhook
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(None, alias="stripe-signature"),
) -> dict[str, str]:
    """Stripe webhook — signature verified"""
    body = await request.body()
    sb = get_admin_supabase()
    client_ip = get_remote_address(request)
    
    request.state.user_name = "Stripe Server"
    request.state.user_id = "WEBHOOK"

    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(500, "Webhook secret not configured")
    if not stripe_signature:
        raise HTTPException(400, "Missing stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload=body, 
            sig_header=stripe_signature, 
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
        if hasattr(request.state, "actions"):
            request.state.actions.append("Signature verified locally using Webhook Secret")
    except (ValueError, stripe.error.SignatureVerificationError):
        _audit_log("WEBHOOK_INVALID_SIG", "system", client_ip, "", "signature_verification_failed")
        raise HTTPException(400, "Invalid signature")

    event_type = event["type"]
    data_object = event["data"]["object"]
    pi_id = data_object.get("id")
    
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Event: {event_type} | PI: {pi_id}")
    
    logger.info("Webhook | type=%s pi=%s ip=%s", event_type, pi_id, client_ip)

    if event_type == "payment_intent.succeeded":
        order_res = (
            sb.table("orders")
            .select("id, status, total_amount, customer_id")
            .eq("stripe_payment_intent", pi_id).maybe_single().execute()
        )
        if not order_res or not order_res.data:
            return {"message": "OK"}

        order = order_res.data
        if order["status"] != "pending":
            return {"message": "OK"}

        update_res = (
            sb.table("orders")
            .update({"status": "paid"}).eq("id", order["id"]).eq("status", "pending").execute()
        )
        if not update_res or not update_res.data:
            return {"message": "OK"}

        _audit_log("WEBHOOK_PAID", "system", client_ip, order["id"], f"pi={pi_id}")
        
        try:
            sb.table("payments").insert({
                "order_id": order["id"], "stripe_payment_intent_id": pi_id,
                "amount": data_object.get("amount", 0) / 100,
                "currency": "INR", "status": "completed", "payment_method": "stripe",
            }).execute()
        except Exception:
            pass

        try:
            paid_order = copy.copy(order); paid_order["status"] = "paid"
            get_event_bus().publish(OrderPaidEvent(
                order=paid_order, customer_email=_get_customer_email(sb, order.get("customer_id", "")),
                customer_id=order.get("customer_id", ""),
            ))
        except Exception:
            pass

    elif event_type in ("payment_intent.payment_failed", "payment_intent.canceled"):
        order_res = (
            sb.table("orders")
            .select("id, status, customer_id, order_items(*)")
            .eq("stripe_payment_intent", pi_id).maybe_single().execute()
        )
        if not order_res or not order_res.data:
            return {"message": "OK"}

        order = order_res.data
        if order["status"] != "pending":
            return {"message": "OK"}

        sb.table("orders").update({"status": "cancelled"}).eq("id", order["id"]).execute()
        
        for item in order.get("order_items", []):
            if item.get("product_id"):
                restore_stock(sb, item["product_id"], item["quantity"], f"webhook_{event_type}")

        reason = "payment_canceled" if "canceled" in event_type else "payment_failed"
        _audit_log("WEBHOOK_FAILED", "system", client_ip, order["id"], reason)
        
        if hasattr(request.state, "actions"):
            request.state.actions.append(f"Auto-cancelled order and restored stock. Reason: {reason}")

    return {"message": "OK"}
