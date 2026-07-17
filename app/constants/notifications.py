"""
Push Notification & Email Content SSOT
======================================
Path: app/constants/notifications.py
"""
import os

_ICON_BASE = os.environ.get("PUSH_ICON_BASE_URL", "/icons").rstrip("/")

class PushIcons:
    NEW_ORDER = f"{_ICON_BASE}/ri-shopping-bag-3.png"
    PAID      = f"{_ICON_BASE}/ri-checkbox-circle.png"
    FAILED    = f"{_ICON_BASE}/ri-close-circle.png"
    CANCELLED = f"{_ICON_BASE}/ri-forbid-2.png"
    SHIPPED   = f"{_ICON_BASE}/ri-truck.png"
    DELIVERED = f"{_ICON_BASE}/ri-mail-check.png"
    REFUNDED  = f"{_ICON_BASE}/ri-refund-2.png"
    LOW_STOCK = f"{_ICON_BASE}/ri-alert.png"

class PushTemplates:
    URL_ORDERS = "/orders.html"
    URL_CART   = "/cart.html"
    URL_ADMIN  = "/admin.html"

    ADMIN_ORDER_TITLE = "New Order #{oid}"
    ADMIN_ORDER_BODY  = "₹{amt} — needs processing"
    
    PAID_TITLE    = "Payment Confirmed ✓"
    PAID_BODY     = "Order #{oid} confirmed. We're preparing it now."
    
    FAILED_TITLE  = "Payment Failed — Order #{oid}"
    FAILED_BODY   = "Your payment could not be processed. Please try again."
    
    CANCEL_TITLE  = "Order #{oid} Cancelled"
    CANCEL_BODY   = "Your order was successfully cancelled."
    
    SHIPPED_TITLE = "Order #{oid} Shipped!"
    SHIPPED_BODY  = "Your order is on the way."
    SHIPPED_TRACKING = " Tracking: {tracking}"
    
    DELIVERED_TITLE = "Order #{oid} Delivered!"
    DELIVERED_BODY  = "Your order has arrived. Enjoy!"
    
    REFUNDED_TITLE  = "Refund Initiated — Order #{oid}"
    REFUNDED_BODY   = "Your refund has been processed."
    
    LOW_STOCK_TITLE = "Low Stock — {name}"
    LOW_STOCK_BODY  = "Only {stock} left (threshold: {threshold})"