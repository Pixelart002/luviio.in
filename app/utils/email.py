import os
import logging
from typing import Any

import resend

logger = logging.getLogger(__name__)

# ── Set API key from env (exactly like official docs) ─────────────────────────
resend.api_key = os.environ.get("RESEND_API_KEY", "")

# ── Sender — set FROM_EMAIL env var to your verified domain ──────────────────
# e.g. FROM_EMAIL=Luviio <noreply@yourdomain.com>
FROM = os.environ.get("FROM_EMAIL", "Luviio <onboarding@resend.dev>")
APP  = os.environ.get("APP_NAME",   "Luviio")


# ── 1 function = 1 email type ─────────────────────────────────────────────────

def send_welcome_email(to: str, name: str) -> None:
    name = name or "there"
    params: resend.Emails.SendParams = {
        "from":    FROM,
        "to":      [to],
        "subject": f"Welcome to {APP}! 🎉",
        "html": f"""
<!DOCTYPE html><html>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:sans-serif;">
<div style="max-width:520px;margin:40px auto;background:#fff;border-radius:10px;overflow:hidden;">
  <div style="background:#0B1628;padding:28px 32px;">
    <h1 style="color:#00C5D4;font-size:22px;margin:0;letter-spacing:2px;">{APP.upper()}</h1>
  </div>
  <div style="padding:32px;">
    <h2 style="color:#0B1628;margin-top:0;">Welcome, {name}! 👋</h2>
    <p style="color:#555;line-height:1.7;">
      Your account has been created successfully.<br>
      Explore our premium bath sanitation products.
    </p>
    <a href="https://luviio.in/shop"
       style="display:inline-block;margin-top:20px;padding:12px 28px;
              background:#0B1628;color:#fff;border-radius:8px;
              text-decoration:none;font-weight:600;letter-spacing:1px;">
      Shop Now →
    </a>
    <p style="color:#aaa;font-size:12px;margin-top:28px;">
      If you didn't create this account, ignore this email.
    </p>
  </div>
</div>
</body></html>""",
    }
    try:
        email = resend.Emails.send(params)
        logger.info("Welcome email sent | to=%s id=%s", to, email.get("id"))
    except Exception as e:
        logger.error("Welcome email failed | to=%s | %s", to, e, exc_info=True)


def send_order_confirmation(to: str, order: dict[str, Any]) -> None:
    oid     = str(order.get("id", ""))[:8].upper()
    total   = order.get("total_amount", "0")
    status  = str(order.get("status", "pending")).capitalize()
    city    = order.get("shipping_city", "")
    country = order.get("shipping_country", "")

    params: resend.Emails.SendParams = {
        "from":    FROM,
        "to":      [to],
        "subject": f"Order #{oid} confirmed — {APP}",
        "html": f"""
<!DOCTYPE html><html>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:sans-serif;">
<div style="max-width:520px;margin:40px auto;background:#fff;border-radius:10px;overflow:hidden;">
  <div style="background:#0B1628;padding:28px 32px;">
    <h1 style="color:#00C5D4;font-size:22px;margin:0;letter-spacing:2px;">{APP.upper()}</h1>
  </div>
  <div style="padding:32px;">
    <h2 style="color:#0B1628;margin-top:0;">Order Confirmed ✓</h2>
    <p style="color:#555;">Your order has been placed successfully.</p>
    <table style="width:100%;border-collapse:collapse;margin:20px 0;">
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:10px 0;color:#888;font-size:13px;">Order ID</td>
        <td style="padding:10px 0;font-weight:700;text-align:right;">#{oid}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:10px 0;color:#888;font-size:13px;">Total</td>
        <td style="padding:10px 0;font-weight:700;color:#00b0be;text-align:right;">₹{total}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:10px 0;color:#888;font-size:13px;">Status</td>
        <td style="padding:10px 0;text-align:right;">{status}</td>
      </tr>
      <tr>
        <td style="padding:10px 0;color:#888;font-size:13px;">Ships to</td>
        <td style="padding:10px 0;text-align:right;">{city}{', ' + country if country else ''}</td>
      </tr>
    </table>
    <p style="color:#aaa;font-size:12px;margin-bottom:0;">
      You'll receive another email when your order ships.
    </p>
  </div>
</div>
</body></html>""",
    }
    try:
        email = resend.Emails.send(params)
        logger.info("Order confirmation sent | to=%s order=%s id=%s", to, order.get("id"), email.get("id"))
    except Exception as e:
        logger.error("Order confirmation failed | to=%s | %s", to, e, exc_info=True)


def send_order_shipped(to: str, order: dict[str, Any], tracking_number: str | None) -> None:
    oid          = str(order.get("id", ""))[:8].upper()
    tracking_row = (
        f"<tr><td style='padding:10px 0;color:#888;font-size:13px;'>Tracking</td>"
        f"<td style='padding:10px 0;font-weight:700;text-align:right;'>{tracking_number}</td></tr>"
    ) if tracking_number else ""

    params: resend.Emails.SendParams = {
        "from":    FROM,
        "to":      [to],
        "subject": f"Your order #{oid} has shipped! 🚚",
        "html": f"""
<!DOCTYPE html><html>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:sans-serif;">
<div style="max-width:520px;margin:40px auto;background:#fff;border-radius:10px;overflow:hidden;">
  <div style="background:#0B1628;padding:28px 32px;">
    <h1 style="color:#00C5D4;font-size:22px;margin:0;letter-spacing:2px;">{APP.upper()}</h1>
  </div>
  <div style="padding:32px;">
    <h2 style="color:#0B1628;margin-top:0;">Your order is on the way! 🚚</h2>
    <p style="color:#555;">Order <strong>#{oid}</strong> has been shipped.</p>
    <table style="width:100%;border-collapse:collapse;margin:20px 0;">
      {tracking_row}
      <tr>
        <td style="padding:10px 0;color:#888;font-size:13px;">Estimated Delivery</td>
        <td style="padding:10px 0;text-align:right;">3–5 business days</td>
      </tr>
    </table>
  </div>
</div>
</body></html>""",
    }
    try:
        email = resend.Emails.send(params)
        logger.info("Shipped email sent | to=%s order=%s id=%s", to, order.get("id"), email.get("id"))
    except Exception as e:
        logger.error("Shipped email failed | to=%s | %s", to, e, exc_info=True)