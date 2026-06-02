"""
Email Service — Resend Integration
===================================
Single-responsibility email functions for transactional emails.
Uses Resend (resend.com) for reliable delivery.

Email Types:
  • Welcome — account creation confirmation
  • Order Confirmation — payment received
  • Order Shipped — tracking info
  • Cart Reminder — abandoned cart recovery

Design:
  • 1 function = 1 email type (Single Responsibility)
  • Consistent Luviio branding across all emails
  • Safe NoneType handling throughout
  • Structured logging with email IDs
  • Graceful failure — never crash the caller

Setup:
  RESEND_API_KEY=re_xxxxx        # Required
  FROM_EMAIL=Luviio <noreply@luviio.in>  # Must be verified domain
  APP_NAME=Luviio                 # Optional, defaults to "Luviio"
"""
import os
import logging
from typing import Any

import resend

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
resend.api_key = os.environ.get("RESEND_API_KEY", "")

FROM = os.environ.get("FROM_EMAIL", "Luviio <onboarding@resend.dev>")
APP  = os.environ.get("APP_NAME", "Luviio")
BASE_URL = os.environ.get("APP_URL", "https://luviio.in")

# ── Brand Colors ──────────────────────────────────────────────────────────────
BG_DARK    = "#080808"
BG_SURFACE = "#0d0c0a"
GOLD       = "#c9a55e"
TEXT       = "#f0ece4"
TEXT_MUTED = "#7a7368"
BORDER     = "#1e1c18"
ACCENT     = "#c9a55e"  # Gold accent


# ══════════════════════════════════════════════════════════════════════════════
#  EMAIL TEMPLATE WRAPPER
# ══════════════════════════════════════════════════════════════════════════════

def _email_template(title: str, content: str, preheader: str = "") -> str:
    """
    Consistent Luviio-branded email wrapper.
    All emails share this layout — change once, update everywhere.
    """
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark">
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:{BG_DARK};font-family:'DM Sans',-apple-system,sans-serif;color:{TEXT};">
  
  <!-- Preheader (shows in inbox preview) -->
  <div style="display:none;max-height:0;overflow:hidden;">{preheader or title}</div>
  
  <!-- Main Container -->
  <div style="max-width:540px;margin:40px auto;background:{BG_SURFACE};border-radius:16px;overflow:hidden;border:1px solid {BORDER};">
    
    <!-- Header -->
    <div style="background:{BG_DARK};padding:32px 36px;border-bottom:1px solid {GOLD};text-align:center;">
      <h1 style="color:{GOLD};font-family:'Playfair Display',serif;font-size:28px;margin:0;letter-spacing:4px;font-weight:700;">
        LUVIIO
      </h1>
      <p style="color:{TEXT_MUTED};font-size:11px;margin:6px 0 0;letter-spacing:2px;text-transform:uppercase;">
        Premium Bath & Sanitation
      </p>
    </div>
    
    <!-- Content -->
    <div style="padding:36px;">
      <h2 style="color:{TEXT};font-family:'Playfair Display',serif;font-size:20px;margin:0 0 16px;font-weight:600;">
        {title}
      </h2>
      
      {content}
    </div>
    
    <!-- Footer -->
    <div style="background:{BG_DARK};padding:24px 36px;border-top:1px solid {BORDER};text-align:center;">
      <p style="color:{TEXT_MUTED};font-size:11px;margin:0 0 8px;line-height:1.6;">
        © 2026 Luviio. All rights reserved.<br>
        <a href="{BASE_URL}" style="color:{GOLD};text-decoration:none;">{BASE_URL.replace('https://', '')}</a>
      </p>
      <p style="color:{TEXT_MUTED};font-size:10px;margin:0;">
        This is an automated message from Luviio. Please do not reply directly.
      </p>
    </div>
    
  </div>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════════════════════
#  SAFE SEND HELPER
# ══════════════════════════════════════════════════════════════════════════════

def _safe_send(params: dict, log_context: str) -> bool:
    """
    Send email with error handling and logging.
    Returns True if sent successfully, False otherwise.
    Never raises — caller continues regardless.
    """
    if not resend.api_key:
        logger.warning("Resend API key not configured — skipping email | context=%s", log_context)
        return False
    
    try:
        email = resend.Emails.send(params)
        email_id = email.get("id") if isinstance(email, dict) else getattr(email, "id", "unknown")
        logger.info("Email sent | %s id=%s", log_context, email_id)
        return True
    except Exception as e:
        logger.error("Email failed | %s | %s", log_context, e, exc_info=True)
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  EMAIL FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def send_welcome_email(to: str, name: str) -> None:
    """Send welcome email after successful registration."""
    name = (name or "there").strip()
    
    content = f"""
      <p style="color:{TEXT_MUTED};line-height:1.8;font-size:14px;margin:0 0 20px;">
        Hi <strong style="color:{TEXT};">{name}</strong>, welcome to Luviio! 👋
      </p>
      <p style="color:{TEXT_MUTED};line-height:1.8;font-size:14px;margin:0 0 20px;">
        Your account has been created successfully. Explore our curated collection 
        of premium bath and sanitation products — crafted for those who appreciate quality.
      </p>
      
      <div style="text-align:center;margin:28px 0;">
        <a href="{BASE_URL}/shop"
           style="display:inline-block;padding:14px 36px;
                  background:{GOLD};color:{BG_DARK};border-radius:8px;
                  text-decoration:none;font-weight:700;font-size:14px;
                  letter-spacing:0.5px;transition:all 0.3s;">
          Start Shopping →
        </a>
      </div>
      
      <div style="background:{BG_DARK};border-radius:10px;padding:16px 20px;margin:20px 0;">
        <p style="color:{TEXT_MUTED};font-size:12px;margin:0;line-height:1.6;">
          <strong style="color:{GOLD};">✨ Free Shipping</strong> on orders above ₹999<br>
          <strong style="color:{GOLD};">🔒 Secure Checkout</strong> via Stripe<br>
          <strong style="color:{GOLD};">🚚 Pan-India Delivery</strong> in 3-5 business days
        </p>
      </div>
      
      <p style="color:{TEXT_MUTED};font-size:11px;margin:24px 0 0;line-height:1.6;">
        If you didn't create this account, you can safely ignore this email.
      </p>
    """
    
    params: resend.Emails.SendParams = {
        "from": FROM,
        "to": [to],
        "subject": f"Welcome to {APP}, {name}! 🎉",
        "html": _email_template(
            title=f"Welcome, {name}!",
            content=content,
            preheader=f"Your {APP} account is ready — start shopping premium bath products",
        ),
    }
    _safe_send(params, f"welcome to={to}")


def send_order_confirmation(to: str, order: dict[str, Any] | None) -> None:
    """Send order confirmation after successful payment."""
    order = order or {}
    
    oid     = str(order.get("id", ""))[:8].upper()
    total   = order.get("total_amount", 0)
    status  = str(order.get("status", "pending")).capitalize()
    city    = order.get("shipping_city", "")
    state   = order.get("shipping_state", "")
    country = order.get("shipping_country", "IN")
    
    # Build location string
    location_parts = [p for p in [city, state, country] if p]
    location = ", ".join(location_parts) if location_parts else "—"
    
    # Build items table
    items = order.get("order_items", [])
    item_rows = ""
    for item in items:
        item_rows += f"""
        <tr style="border-bottom:1px solid {BORDER};">
          <td style="padding:10px 0;color:{TEXT};font-size:13px;">
            {item.get('product_name', 'Product')}
            <span style="color:{TEXT_MUTED};font-size:11px;"> × {item.get('quantity', 1)}</span>
          </td>
          <td style="padding:10px 0;text-align:right;font-weight:600;color:{GOLD};font-size:13px;">
            ₹{float(item.get('subtotal', 0)):.2f}
          </td>
        </tr>"""
    
    content = f"""
      <p style="color:{TEXT_MUTED};line-height:1.8;font-size:14px;margin:0 0 20px;">
        Your order has been confirmed and is being processed.
      </p>
      
      <!-- Order Details Card -->
      <div style="background:{BG_DARK};border-radius:10px;padding:20px 24px;margin:20px 0;">
        <table style="width:100%;border-collapse:collapse;">
          <tr>
            <td style="padding:6px 0;color:{TEXT_MUTED};font-size:12px;width:100px;">Order ID</td>
            <td style="padding:6px 0;color:{TEXT};font-size:14px;font-weight:700;font-family:monospace;">#{oid}</td>
          </tr>
          <tr>
            <td style="padding:6px 0;color:{TEXT_MUTED};font-size:12px;">Status</td>
            <td style="padding:6px 0;color:{GOLD};font-size:13px;font-weight:600;">
              <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{GOLD};margin-right:6px;"></span>
              {status}
            </td>
          </tr>
          <tr>
            <td style="padding:6px 0;color:{TEXT_MUTED};font-size:12px;">Ships to</td>
            <td style="padding:6px 0;color:{TEXT};font-size:13px;">{location}</td>
          </tr>
          <tr>
            <td style="padding:6px 0;color:{TEXT_MUTED};font-size:12px;">Total</td>
            <td style="padding:6px 0;color:{GOLD};font-size:18px;font-weight:700;">₹{float(total):,.2f}</td>
          </tr>
        </table>
      </div>
      
      <!-- Items Table -->
      <h3 style="color:{TEXT};font-size:13px;margin:20px 0 10px;text-transform:uppercase;letter-spacing:1px;">Order Items</h3>
      <table style="width:100%;border-collapse:collapse;">
        {item_rows}
      </table>
      
      <div style="text-align:center;margin:28px 0 0;">
        <a href="{BASE_URL}/orders.html"
           style="display:inline-block;padding:12px 28px;
                  border:1px solid {GOLD};color:{GOLD};border-radius:8px;
                  text-decoration:none;font-weight:600;font-size:13px;">
          Track Your Order →
        </a>
      </div>
      
      <p style="color:{TEXT_MUTED};font-size:11px;margin:24px 0 0;line-height:1.6;">
        You'll receive another email when your order ships. For any queries, 
        reply to <a href="mailto:support@luviio.in" style="color:{GOLD};">support@luviio.in</a>
      </p>
    """
    
    params: resend.Emails.SendParams = {
        "from": FROM,
        "to": [to],
        "subject": f"Order #{oid} Confirmed — {APP} ✓",
        "html": _email_template(
            title="Order Confirmed ✓",
            content=content,
            preheader=f"Order #{oid} — ₹{float(total):,.2f} — Status: {status}",
        ),
    }
    _safe_send(params, f"order_confirmation to={to} order={oid}")


def send_order_shipped(to: str, order: dict[str, Any] | None, tracking_number: str | None) -> None:
    """Send shipping confirmation with tracking info."""
    order = order or {}
    
    oid = str(order.get("id", ""))[:8].upper()
    tracking = tracking_number or "Will be updated soon"
    
    tracking_section = f"""
    <div style="background:{BG_DARK};border:1px solid {GOLD};border-radius:10px;padding:20px 24px;margin:20px 0;text-align:center;">
      <p style="color:{TEXT_MUTED};font-size:11px;margin:0 0 8px;text-transform:uppercase;letter-spacing:1px;">Tracking Number</p>
      <p style="color:{GOLD};font-size:20px;font-weight:700;margin:0;font-family:monospace;letter-spacing:2px;">{tracking}</p>
    </div>""" if tracking_number else ""
    
    content = f"""
      <p style="color:{TEXT_MUTED};line-height:1.8;font-size:14px;margin:0 0 20px;">
        Great news! Your order <strong style="color:{TEXT};">#{oid}</strong> is on its way to you! 🚚
      </p>
      
      {tracking_section}
      
      <div style="background:{BG_DARK};border-radius:10px;padding:16px 20px;margin:20px 0;">
        <p style="color:{TEXT_MUTED};font-size:12px;margin:0;line-height:1.8;">
          <strong style="color:{GOLD};">📦 Estimated Delivery:</strong> 3-5 business days<br>
          <strong style="color:{GOLD};">📍 Shipping to:</strong> {order.get('shipping_city', '—')}, {order.get('shipping_country', 'IN')}
        </p>
      </div>
      
      <div style="text-align:center;margin:28px 0 0;">
        <a href="{BASE_URL}/orders.html"
           style="display:inline-block;padding:12px 28px;
                  background:{GOLD};color:{BG_DARK};border-radius:8px;
                  text-decoration:none;font-weight:700;font-size:13px;">
          View Order Status →
        </a>
      </div>
    """
    
    params: resend.Emails.SendParams = {
        "from": FROM,
        "to": [to],
        "subject": f"Order #{oid} Shipped! 🚚 — {APP}",
        "html": _email_template(
            title="Your Order is on the Way! 🚚",
            content=content,
            preheader=f"Order #{oid} shipped — tracking: {tracking}",
        ),
    }
    _safe_send(params, f"shipped to={to} order={oid}")


def send_cart_reminder_email(to: str, name: str, items: list) -> None:
    """
    Send abandoned cart reminder.
    Called from: cart.py admin remind endpoint.
    """
    name = (name or "there").strip()
    
    # Build item rows
    item_rows = ""
    total_value = 0.0
    for item in items:
        prod = item.get("products") or {}
        prod_name = prod.get("name", "Product")
        qty = item.get("quantity", 1)
        price = float(item.get("price_snapshot", 0))
        subtotal = price * qty
        total_value += subtotal
        
        # Get image URL if available
        image_url = prod.get("image_url", "")
        image_cell = f'<img src="{image_url}" style="width:40px;height:50px;object-fit:cover;border-radius:6px;" alt="">' if image_url else ""
        
        item_rows += f"""
        <tr style="border-bottom:1px solid {BORDER};">
          <td style="padding:10px 8px;">{image_cell}</td>
          <td style="padding:10px 8px;color:{TEXT};font-size:13px;">
            {prod_name}
            <span style="color:{TEXT_MUTED};font-size:11px;"> × {qty}</span>
          </td>
          <td style="padding:10px 8px;text-align:right;color:{GOLD};font-size:13px;font-weight:600;">
            ₹{subtotal:.2f}
          </td>
        </tr>"""
    
    content = f"""
      <p style="color:{TEXT_MUTED};line-height:1.8;font-size:14px;margin:0 0 20px;">
        Hi <strong style="color:{TEXT};">{name}</strong>, your cart is waiting! 
        Complete your purchase before these items sell out.
      </p>
      
      <!-- Items -->
      <table style="width:100%;border-collapse:collapse;">
        <tr style="border-bottom:2px solid {GOLD};">
          <th style="padding:8px;text-align:left;font-size:10px;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:1px;"></th>
          <th style="padding:8px;text-align:left;font-size:10px;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:1px;">Product</th>
          <th style="padding:8px;text-align:right;font-size:10px;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:1px;">Price</th>
        </tr>
        {item_rows}
        <tr>
          <td colspan="3" style="padding:12px 8px;text-align:right;">
            <span style="color:{TEXT_MUTED};font-size:12px;">Total: </span>
            <span style="color:{GOLD};font-size:16px;font-weight:700;">₹{total_value:.2f}</span>
          </td>
        </tr>
      </table>
      
      <div style="text-align:center;margin:28px 0 0;">
        <a href="{BASE_URL}/cart"
           style="display:inline-block;padding:14px 36px;
                  background:{GOLD};color:{BG_DARK};border-radius:8px;
                  text-decoration:none;font-weight:700;font-size:14px;">
          Complete Your Order →
        </a>
      </div>
      
      <p style="color:{TEXT_MUTED};font-size:11px;margin:20px 0 0;line-height:1.6;text-align:center;">
        Items in your cart are not reserved and may sell out.
      </p>
    """
    
    params: resend.Emails.SendParams = {
        "from": FROM,
        "to": [to],
        "subject": f"You left something behind, {name}! 🛒 — {APP}",
        "html": _email_template(
            title="Your Cart is Waiting 🛒",
            content=content,
            preheader=f"Hi {name}, you have {len(items)} item(s) in your cart — complete your order",
        ),
    }
    _safe_send(params, f"cart_reminder to={to} items={len(items)}")