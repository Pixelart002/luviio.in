"""
Email Service — Resend Integration (Async Threadpool Fixed)
===========================================================
Architecture Layer: External Integrations
Path: app/integrations/email/resend_impl.py
"""
import base64
import logging
import os
from html import escape

import resend
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
resend.api_key = os.environ.get("RESEND_API_KEY", "")

FROM = os.environ.get("FROM_EMAIL", "Luviio <orders@luviio.in>")
APP  = os.environ.get("APP_NAME", "Luviio")
BASE_URL = os.environ.get("APP_URL", "https://luviio.in")

# ── Brand Colors & Assets ─────────────────────────────────────────────────────
BG_DARK    = "#080808"
BG_SURFACE = "#0d0c0a"
GOLD       = "#c9a55e"
TEXT       = "#f0ece4"
TEXT_MUTED = "#7a7368"
BORDER     = "#1e1c18"
DEFAULT_HERO_GIF = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExcGZ4bHhkM2M5bndkZnJ5a3gxeThwbWxnNnc4c2h1bnV4ZHl4b3V4eSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/3o7aCRZYNerX4ovPwI/giphy.gif"

def _email_template(title: str, content: str, preheader: str = "", hero_image: str = "") -> str:
    hero_html = ""
    if hero_image:
        hero_html = f"""
        <tr>
            <td align="center" style="padding: 0; background-color: {BG_DARK}; border-bottom: 1px solid {BORDER};">
                <img src="{hero_image}" alt="Luviio Premium" width="540" style="display: block; width: 100%; max-width: 540px; height: auto; border: 0;" />
            </td>
        </tr>
        """
    return f"""
<!DOCTYPE html>
<html lang="en" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta name="color-scheme" content="dark">
  <title>{title}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;700&family=Playfair+Display:wght@600;700&display=swap');
    body, table, td, a {{ -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
    table, td {{ mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
    img {{ -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }}
  </style>
</head>
<body style="margin: 0; padding: 0; background-color: {BG_DARK}; font-family: 'DM Sans', Arial, sans-serif; color: {TEXT};">
  <div style="display:none;max-height:0;overflow:hidden;font-size:0px;color:transparent;">
    {preheader or title} &zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;
  </div>
  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: {BG_DARK};">
    <tr>
      <td align="center" style="padding: 40px 10px;">
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 540px; background-color: {BG_SURFACE}; border-radius: 16px; border: 1px solid {BORDER}; overflow: hidden;">
          <tr>
            <td align="center" style="background-color: {BG_DARK}; padding: 32px 36px; border-bottom: 1px solid {GOLD};">
              <h1 style="color: {GOLD}; font-family: 'Playfair Display', Georgia, serif; font-size: 28px; margin: 0; letter-spacing: 4px; font-weight: 700;">
                LUVIIO
              </h1>
              <p style="color: {TEXT_MUTED}; font-size: 11px; margin: 6px 0 0; letter-spacing: 2px; text-transform: uppercase;">
                Hardware • Sanitary • Drainage
              </p>
            </td>
          </tr>
          {hero_html}
          <tr>
            <td style="padding: 36px;">
              <h2 style="color: {TEXT}; font-family: 'Playfair Display', Georgia, serif; font-size: 20px; margin: 0 0 16px; font-weight: 600;">
                {title}
              </h2>
              {content}
            </td>
          </tr>
          <tr>
            <td align="center" style="background-color: {BG_DARK}; padding: 24px 36px; border-top: 1px solid {BORDER};">
              <p style="color: {TEXT_MUTED}; font-size: 11px; margin: 0 0 8px; line-height: 1.6;">
                © 2026 Luviio. All rights reserved.<br>
                <a href="{BASE_URL}" style="color: {GOLD}; text-decoration: none;">{BASE_URL.replace('https://', '')}</a>
              </p>
              <p style="color: {TEXT_MUTED}; font-size: 10px; margin: 0;">
                This is an automated message from Luviio. Please do not reply directly.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

# 🔥 FIX: Threadpool dispatcher to stop blocking the main Async Loop
async def _async_safe_send(params: dict, log_context: str) -> bool:
    if not resend.api_key:
        logger.warning(f"[EMAIL SKIPPED] Missing RESEND_API_KEY. Context: {log_context}")
        return False
    try:
        # Pushing sync I/O into a threadpool so it doesn't block the ASGI loop
        await run_in_threadpool(resend.Emails.send, params)
        logger.info(f"[EMAIL SENT] {log_context}")
        return True
    except Exception as e:
        logger.error(f"[EMAIL FAILED] {log_context} : {e}")
        return False

async def send_welcome_email(to: str, name: str) -> None:
    name = (name or "there").strip()
    safe_name = _esc(name)
    content = f"""
      <p style="color:{TEXT_MUTED};line-height:1.8;font-size:14px;margin:0 0 20px;">Hi <strong style="color:{TEXT};">{safe_name}</strong>, welcome to Luviio.</p>
      <p style="color:{TEXT_MUTED};line-height:1.8;font-size:14px;margin:0 0 20px;">Your Luviio account is ready. Explore hardware, sanitary and drainage essentials selected for everyday projects and professional requirements.</p>
      <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
        <tr>
          <td align="center" style="padding: 28px 0;">
            <a href="{BASE_URL}/shop" style="display:inline-block;padding:14px 36px;background-color:{GOLD};color:{BG_DARK};border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;letter-spacing:0.5px;">Start Shopping →</a>
          </td>
        </tr>
      </table>
      <div style="background-color:{BG_DARK};border-radius:10px;padding:16px 20px;margin:20px 0;">
        <p style="color:{TEXT_MUTED};font-size:12px;margin:0;line-height:1.6;">
          <strong style="color:{GOLD};">Secure Checkout</strong> with trusted payment processing<br>
          <strong style="color:{GOLD};">Order Updates</strong> by email and notifications<br>
          <strong style="color:{GOLD};">Pan-India Delivery</strong> where available
        </p>
      </div>
      <p style="color:{TEXT_MUTED};font-size:11px;margin:24px 0 0;line-height:1.6;">If you didn't create this account, you can safely ignore this email.</p>
    """
    params: resend.Emails.SendParams = {
        "from": FROM, 
        "to": [to], 
        "subject": f"Welcome to {APP}, {name}", 
        "html": _email_template(title=f"Welcome, {name}!", content=content, preheader=f"Your {APP} account is ready — explore hardware, sanitary and drainage products", hero_image="")
    }
    await _async_safe_send(params, f"welcome to={to}")

async def send_order_confirmation(to: str, order: dict | None) -> None:
    order = order or {}
    oid = _order_ref(order)
    total = order.get("total_amount", 0)
    status = str(order.get("status", "pending")).capitalize()
    location_parts = [p for p in [order.get("shipping_city", ""), order.get("shipping_state", ""), order.get("shipping_country", "IN")] if p]
    location = ", ".join(location_parts) if location_parts else "—"
    
    item_rows = ""
    for item in order.get("order_items", []):
        item_rows += f"""<tr><td style="padding:10px 0;border-bottom:1px solid {BORDER};color:{TEXT};font-size:13px;">{item.get('product_name', 'Product')}<span style="color:{TEXT_MUTED};font-size:11px;"> × {item.get('quantity', 1)}</span></td><td align="right" style="padding:10px 0;border-bottom:1px solid {BORDER};font-weight:600;color:{GOLD};font-size:13px;">₹{float(item.get('subtotal', 0)):.2f}</td></tr>"""
    
    content = f"""
      <p style="color:{TEXT_MUTED};line-height:1.8;font-size:14px;margin:0 0 20px;">Your order has been confirmed and is being processed.</p>
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:{BG_DARK};border-radius:10px;margin:20px 0;"><tr><td style="padding:20px 24px;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
        <tr><td style="padding:6px 0;color:{TEXT_MUTED};font-size:12px;width:100px;">Order No.</td><td style="padding:6px 0;color:{TEXT};font-size:14px;font-weight:700;font-family:monospace;">#{oid}</td></tr>
        <tr><td style="padding:6px 0;color:{TEXT_MUTED};font-size:12px;">Status</td><td style="padding:6px 0;color:{GOLD};font-size:13px;font-weight:600;">{status}</td></tr>
        <tr><td style="padding:6px 0;color:{TEXT_MUTED};font-size:12px;">Ships to</td><td style="padding:6px 0;color:{TEXT};font-size:13px;">{location}</td></tr>
        <tr><td style="padding:6px 0;color:{TEXT_MUTED};font-size:12px;">Total</td><td style="padding:6px 0;color:{GOLD};font-size:18px;font-weight:700;">₹{float(total):,.2f}</td></tr>
      </table></td></tr></table>
      <h3 style="color:{TEXT};font-size:13px;margin:20px 0 10px;text-transform:uppercase;letter-spacing:1px;">Order Items</h3>
      <table role="presentation" style="width:100%;border-collapse:collapse;">{item_rows}</table>
      <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td align="center" style="padding: 28px 0 0;"><a href="{BASE_URL}/orders.html" style="display:inline-block;padding:12px 28px;border:1px solid {GOLD};color:{GOLD};border-radius:8px;text-decoration:none;font-weight:600;font-size:13px;">Track Your Order →</a></td></tr></table>
      <p style="color:{TEXT_MUTED};font-size:11px;margin:24px 0 0;line-height:1.6;">You'll receive another email when your order ships. For any queries, reply to <a href="mailto:support@luviio.in" style="color:{GOLD};text-decoration:none;">support@luviio.in</a></p>
    """
    params: resend.Emails.SendParams = {
        "from": FROM, 
        "to": [to], 
        "subject": f"Order {oid} confirmed — {APP}", 
        "html": _email_template(title="Order Confirmed", content=content, preheader=f"Order #{oid} — ₹{float(total):,.2f} — Status: {status}")
    }
    await _async_safe_send(params, f"order_confirmation to={to} order={oid}")

async def send_order_shipped(to: str, order: dict | None, tracking_number: str | None) -> None:
    order = order or {}
    oid = str(order.get("id", ""))[:8].upper()
    tracking = tracking_number or "Will be updated soon"
    tracking_section = f"""<div style="background-color:{BG_DARK};border:1px solid {GOLD};border-radius:10px;padding:20px 24px;margin:20px 0;text-align:center;"><p style="color:{TEXT_MUTED};font-size:11px;margin:0 0 8px;text-transform:uppercase;letter-spacing:1px;">Tracking Number</p><p style="color:{GOLD};font-size:20px;font-weight:700;margin:0;font-family:monospace;letter-spacing:2px;">{tracking}</p></div>""" if tracking_number else ""
    content = f"""
      <p style="color:{TEXT_MUTED};line-height:1.8;font-size:14px;margin:0 0 20px;">Great news! Your order <strong style="color:{TEXT};">#{oid}</strong> is on its way to you! 🚚</p>
      {tracking_section}
      <div style="background-color:{BG_DARK};border-radius:10px;padding:16px 20px;margin:20px 0;"><p style="color:{TEXT_MUTED};font-size:12px;margin:0;line-height:1.8;"><strong style="color:{GOLD};">📦 Estimated Delivery:</strong> 3-5 business days<br><strong style="color:{GOLD};">📍 Shipping to:</strong> {order.get('shipping_city', '—')}, {order.get('shipping_country', 'IN')}</p></div>
      <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td align="center" style="padding: 28px 0 0;"><a href="{BASE_URL}/orders.html" style="display:inline-block;padding:12px 28px;background-color:{GOLD};color:{BG_DARK};border-radius:8px;text-decoration:none;font-weight:700;font-size:13px;">View Order Status →</a></td></tr></table>
    """
    params: resend.Emails.SendParams = {
        "from": FROM, 
        "to": [to], 
        "subject": f"Order #{oid} Shipped! 🚚 — {APP}", 
        "html": _email_template(title="Your Order is on the Way! 🚚", content=content, preheader=f"Order #{oid} shipped — tracking: {tracking}")
    }
    await _async_safe_send(params, f"shipped to={to} order={oid}")

async def send_payment_success(
    to: str,
    order: dict | None,
    invoice_pdf: bytes | None = None,
    invoice_number: str | None = None,
) -> None:
    order = order or {}
    oid = _order_ref(order)
    total = _money(order.get("total_amount"))
    invoice_no = str(invoice_number or order.get("invoice_number") or "").strip()
    customer_name = _esc(
        order.get("shipping_name")
        or order.get("billing_name")
        or "Customer"
    )

    item_rows = ""
    for item in order.get("order_items") or []:
        product_name = _esc(
            item.get("product_name")
            or item.get("name")
            or "Product"
        )
        qty = max(1, int(_money(item.get("quantity")) or 1))
        line_total = _money(
            item.get("line_total")
            if item.get("line_total") is not None
            else item.get("subtotal")
        )
        item_rows += f"""
          <tr>
            <td style="padding:11px 0;border-bottom:1px solid {BORDER};color:{TEXT};font-size:13px;">
              {product_name}
              <span style="color:{TEXT_MUTED};font-size:11px;"> × {qty}</span>
            </td>
            <td align="right" style="padding:11px 0;border-bottom:1px solid {BORDER};color:{GOLD};font-size:13px;font-weight:700;">
              ₹{line_total:,.2f}
            </td>
          </tr>
        """

    if not item_rows:
        item_rows = f"""
          <tr>
            <td colspan="2" style="padding:12px 0;color:{TEXT_MUTED};font-size:12px;">
              Your purchased items are listed in the attached invoice PDF.
            </td>
          </tr>
        """

    invoice_row = (
        f'<tr><td style="padding:6px 0;color:{TEXT_MUTED};font-size:12px;">Invoice No.</td>'
        f'<td style="padding:6px 0;color:{TEXT};font-size:13px;font-weight:700;font-family:monospace;">{_esc(invoice_no or "—")}</td></tr>'
    )
    attachment_note = (
        '<div style="margin:18px 0 0;padding:12px 14px;background-color:#12100d;border:1px solid #2b251d;border-radius:10px;'
        f'color:{TEXT_MUTED};font-size:12px;line-height:1.6;">Your invoice PDF is attached to this email.</div>'
        if invoice_pdf
        else
        '<div style="margin:18px 0 0;padding:12px 14px;background-color:#12100d;border:1px solid #2b251d;border-radius:10px;'
        f'color:{TEXT_MUTED};font-size:12px;line-height:1.6;">Your order has been recorded successfully. Your invoice is also available from your order details.</div>'
    )

    content = f"""
      <p style="color:{TEXT_MUTED};line-height:1.8;font-size:14px;margin:0 0 18px;">
        Hi <strong style="color:{TEXT};">{customer_name}</strong>, your payment has been received and your order is confirmed.
      </p>

      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
             style="background-color:{BG_DARK};border:1px solid {BORDER};border-radius:12px;margin:0 0 20px;">
        <tr>
          <td style="padding:20px 22px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
              <tr>
                <td style="padding:6px 0;color:{TEXT_MUTED};font-size:12px;width:110px;">Order No.</td>
                <td style="padding:6px 0;color:{TEXT};font-size:14px;font-weight:700;font-family:monospace;">{_esc(oid)}</td>
              </tr>
              {invoice_row}
              <tr>
                <td style="padding:6px 0;color:{TEXT_MUTED};font-size:12px;">Payment</td>
                <td style="padding:6px 0;color:{GOLD};font-size:13px;font-weight:700;">Paid</td>
              </tr>
              <tr>
                <td style="padding:8px 0 0;color:{TEXT_MUTED};font-size:12px;">Amount</td>
                <td style="padding:8px 0 0;color:{GOLD};font-size:20px;font-weight:700;">₹{total:,.2f}</td>
              </tr>
            </table>
          </td>
        </tr>
      </table>

      <h3 style="color:{TEXT};font-size:12px;margin:0 0 9px;text-transform:uppercase;letter-spacing:1.4px;">Items in your order</h3>
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;">
        {item_rows}
      </table>

      {attachment_note}

      <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
        <tr>
          <td align="center" style="padding:26px 0 4px;">
            <a href="{BASE_URL}/orders.html"
               style="display:inline-block;padding:13px 30px;background-color:{GOLD};color:{BG_DARK};border-radius:8px;text-decoration:none;font-weight:700;font-size:13px;">
              View Order
            </a>
          </td>
        </tr>
      </table>

      <p style="color:{TEXT_MUTED};font-size:11px;margin:18px 0 0;line-height:1.7;">
        Need help? Contact <a href="mailto:support@luviio.in" style="color:{GOLD};text-decoration:none;">support@luviio.in</a>.
      </p>
    """

    attachments = []
    if invoice_pdf:
        attachments.append({
            "filename": f"Luviio_Invoice_{invoice_no or oid}.pdf",
            "content": base64.b64encode(invoice_pdf).decode("ascii"),
        })

    params: resend.Emails.SendParams = {
        "from": FROM,
        "to": [to],
        "subject": f"Payment confirmed • Order {oid} — {APP}",
        "html": _email_template(
            title="Payment confirmed",
            content=content,
            preheader=f"Order {oid} is confirmed — ₹{total:,.2f} paid successfully",
            hero_image="",
        ),
    }
    if attachments:
        params["attachments"] = attachments

    await _async_safe_send(params, f"payment_success to={to} order={oid} attachment={'yes' if attachments else 'no'}")


async def send_cart_reminder_email(to: str, name: str, items: list) -> None:
    name = (name or "there").strip()
    item_rows = ""
    total_value = 0.0
    for item in items:
        prod = item.get("products") or {}
        qty, price = item.get("quantity", 1), float(item.get("price_snapshot", 0))
        subtotal = price * qty
        total_value += subtotal
        image_url = prod.get("image_url", "")
        image_cell = f'<img src="{image_url}" width="40" style="width:40px;height:auto;border-radius:6px;display:block;" alt="">' if image_url else ""
        item_rows += f"""<tr><td style="padding:10px 8px;border-bottom:1px solid {BORDER};width:50px;">{image_cell}</td><td style="padding:10px 8px;border-bottom:1px solid {BORDER};color:{TEXT};font-size:13px;">{prod.get("name", "Product")}<span style="color:{TEXT_MUTED};font-size:11px;"> × {qty}</span></td><td align="right" style="padding:10px 8px;border-bottom:1px solid {BORDER};color:{GOLD};font-size:13px;font-weight:600;">₹{subtotal:.2f}</td></tr>"""
    
    content = f"""
      <p style="color:{TEXT_MUTED};line-height:1.8;font-size:14px;margin:0 0 20px;">Hi <strong style="color:{TEXT};">{name}</strong>, your cart is waiting! Complete your purchase before these items sell out.</p>
      <table role="presentation" style="width:100%;border-collapse:collapse;">
        <tr><th colspan="2" style="border-bottom:2px solid {GOLD};padding:8px;text-align:left;font-size:10px;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:1px;">Product</th><th style="border-bottom:2px solid {GOLD};padding:8px;text-align:right;font-size:10px;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:1px;">Price</th></tr>
        {item_rows}
        <tr><td colspan="3" align="right" style="padding:12px 8px;"><span style="color:{TEXT_MUTED};font-size:12px;">Total: </span><span style="color:{GOLD};font-size:16px;font-weight:700;">₹{total_value:.2f}</span></td></tr>
      </table>
      <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td align="center" style="padding: 28px 0 0;"><a href="{BASE_URL}/cart" style="display:inline-block;padding:14px 36px;background-color:{GOLD};color:{BG_DARK};border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;">Complete Your Order →</a></td></tr></table>
      <p style="color:{TEXT_MUTED};font-size:11px;margin:20px 0 0;line-height:1.6;text-align:center;">Items in your cart are not reserved and may sell out.</p>
    """
    params: resend.Emails.SendParams = {
        "from": FROM, 
        "to": [to], 
        "subject": f"You left something behind, {name}! 🛒 — {APP}", 
        "html": _email_template(title="Your Cart is Waiting 🛒", content=content, preheader=f"Hi {name}, you have {len(items)} item(s) in your cart — complete your order")
    }
    await _async_safe_send(params, f"cart_reminder to={to} items={len(items)}")