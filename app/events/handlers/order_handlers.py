"""
Order Event Handlers
====================
Customer-facing and admin reactions to order-related events.
"""
import logging
import os
from typing import Any

from app.events.bus import (
    LowStockEvent,
    OrderCreatedEvent,
    OrderFailedEvent,
    OrderPaidEvent,
    OrderShippedEvent,
    OrderStatusChangedEvent,
)
from app.integrations.email.registry import get_email_provider
from app.integrations.push.webpush_impl import broadcast_push_to_admins, send_push_to_user

logger = logging.getLogger(__name__)

_ICON_BASE: str = os.environ.get("PUSH_ICON_BASE_URL", "/icons").rstrip("/")


class _Icon:
    NEW_ORDER = f"{_ICON_BASE}/ri-shopping-bag-3.png"
    PAID = f"{_ICON_BASE}/ri-checkbox-circle.png"
    FAILED = f"{_ICON_BASE}/ri-close-circle.png"
    CANCELLED = f"{_ICON_BASE}/ri-forbid-2.png"
    SHIPPED = f"{_ICON_BASE}/ri-truck.png"
    DELIVERED = f"{_ICON_BASE}/ri-mail-check.png"
    REFUNDED = f"{_ICON_BASE}/ri-refund-2.png"
    LOW_STOCK = f"{_ICON_BASE}/ri-alert.png"


class _Copy:
    URL_ORDERS = "/orders.html"
    URL_CART = "/cart.html"
    URL_ADMIN = "/admin.html"

    # Admin notifications
    ADMIN_ORDER_TITLE = "New order received"
    ADMIN_ORDER_BODY = "₹{amt} order #{oid} is ready for processing."

    # Customer notifications
    PAID_PUSH_TITLE = "Your order is confirmed 🎉"
    PAID_PUSH_BODY = "Order #{oid} is confirmed. We're getting it ready for you."

    FAILED_PUSH_TITLE = "Payment needs another try"
    FAILED_PUSH_BODY = "We couldn't complete your payment. Your items are safe — you can try again anytime."

    CANCEL_PUSH_TITLE = "Your order was cancelled"
    CANCEL_PUSH_BODY = "Your order has been cancelled successfully. Your items are back in your cart."

    PAYMENT_CANCELLED_TITLE = "Payment cancelled"
    PAYMENT_CANCELLED_BODY = "No worries — your payment was cancelled. Your items are safely saved in your cart."

    SHIPPED_PUSH_TITLE = "Your order is on the way 🚚"
    SHIPPED_PUSH_BODY = "Great news! Your order #{oid} has been shipped and is on its way to you."
    SHIPPED_TRACKING = " Tracking: {tracking}"

    DELIVERED_TITLE = "Your order has arrived 📦"
    DELIVERED_BODY = "Order #{oid} has been delivered. We hope you love your purchase!"

    REFUNDED_TITLE = "Your refund is on its way"
    REFUNDED_BODY = "Your refund for order #{oid} has been initiated successfully."

    LOW_STOCK_TITLE = "Low stock alert — {name}"
    LOW_STOCK_BODY = "Only {stock} left (threshold: {threshold})."


def _safe_oid(order: dict[str, Any]) -> str:
    return str(order.get("order_number") or order.get("id") or "UNKNOWN")[:14].upper()


async def handle_new_order_admin_push(event: OrderCreatedEvent) -> None:
    oid = _safe_oid(event.order or {})
    amt = (event.order or {}).get("total_amount", 0)
    await broadcast_push_to_admins(
        title=_Copy.ADMIN_ORDER_TITLE,
        body=_Copy.ADMIN_ORDER_BODY.format(oid=oid, amt=amt),
        icon=_Icon.NEW_ORDER,
        url=_Copy.URL_ADMIN,
    )


async def handle_paid_email(event: OrderPaidEvent) -> None:
    if not event.customer_email or not event.order:
        return
    logger.info("[HOOK:EMAIL] Triggering Payment Success Email for %s", event.customer_email)
    email_provider = get_email_provider("resend")
    try:
        await email_provider.send_payment_success(event.customer_email, event.order)
    except Exception:
        logger.error("[HOOK:EMAIL] Failed to send payment email", exc_info=True)
        raise


async def handle_paid_push(event: OrderPaidEvent) -> None:
    order = event.order or {}
    uid = event.customer_id or order.get("customer_id", "")
    if uid:
        await send_push_to_user(
            uid,
            title=_Copy.PAID_PUSH_TITLE,
            body=_Copy.PAID_PUSH_BODY.format(oid=_safe_oid(order)),
            icon=_Icon.PAID,
            url=_Copy.URL_ORDERS,
        )


async def handle_failed_push(event: OrderFailedEvent) -> None:
    order = event.order or {}
    uid = event.customer_id or order.get("customer_id", "")
    if not uid:
        return

    raw_id = str(order.get("id", ""))
    is_cart = "SESSION" in raw_id
    oid = _safe_oid(order)

    if event.reason == "payment_canceled":
        title = _Copy.PAYMENT_CANCELLED_TITLE if is_cart else _Copy.CANCEL_PUSH_TITLE.format(oid=oid)
        body = _Copy.PAYMENT_CANCELLED_BODY if is_cart else _Copy.CANCEL_PUSH_BODY
        icon = _Icon.CANCELLED
    elif event.reason == "payment_failed":
        title = _Copy.FAILED_PUSH_TITLE
        body = _Copy.FAILED_PUSH_BODY
        icon = _Icon.FAILED
    else:
        title = "We couldn't complete your checkout"
        body = "Something went wrong while processing your payment. Your items are still safe in your cart."
        icon = _Icon.FAILED

    logger.info("[HOOK:PUSH] Sending customer payment notification to %s: %s", uid, title)
    await send_push_to_user(uid, title=title, body=body, icon=icon, url=_Copy.URL_CART)


async def handle_shipped_push(event: OrderShippedEvent) -> None:
    order = event.order or {}
    uid = event.customer_id or order.get("customer_id", "")
    if not uid:
        return

    body = _Copy.SHIPPED_PUSH_BODY.format(oid=_safe_oid(order))
    if event.tracking_number:
        body += _Copy.SHIPPED_TRACKING.format(tracking=event.tracking_number)

    await send_push_to_user(
        uid,
        title=_Copy.SHIPPED_PUSH_TITLE,
        body=body,
        icon=_Icon.SHIPPED,
        url=_Copy.URL_ORDERS,
    )


async def handle_status_push(event: OrderStatusChangedEvent) -> None:
    config = {
        "delivered": (_Copy.DELIVERED_TITLE, _Copy.DELIVERED_BODY, _Icon.DELIVERED),
        "refunded": (_Copy.REFUNDED_TITLE, _Copy.REFUNDED_BODY, _Icon.REFUNDED),
        "cancelled": (_Copy.CANCEL_PUSH_TITLE, _Copy.CANCEL_PUSH_BODY, _Icon.CANCELLED),
    }
    cfg = config.get(event.new_status)
    if not cfg:
        return

    title_tpl, body, icon = cfg
    await send_push_to_user(
        event.customer_id,
        title=title_tpl.format(oid=_safe_oid(event.order or {})),
        body=body.format(oid=_safe_oid(event.order or {})),
        icon=icon,
        url=_Copy.URL_ORDERS,
    )


async def handle_low_stock_push(event: LowStockEvent) -> None:
    await broadcast_push_to_admins(
        title=_Copy.LOW_STOCK_TITLE.format(name=event.product_name),
        body=_Copy.LOW_STOCK_BODY.format(stock=event.stock, threshold=event.threshold),
        icon=_Icon.LOW_STOCK,
        url=_Copy.URL_ADMIN,
    )
