"""
Email Utility — Resend SDK v2.x
================================
FIXES:
  1. "to" must be a LIST — resend 2.x rejects plain string → ValidationError
  2. api_key set inside helper (no stale module-level state)
  3. Raises ValueError (not silently returns) when config missing, so caller
     can distinguish "skipped intentionally" from "crashed"
  4. exc_info=True on errors → full traceback in logs so you can debug

CHECKLIST before going live:
  ✓ RESEND_API_KEY in .env
  ✓ FROM_EMAIL domain verified in Resend dashboard
    (only onboarding@resend.dev works without verification, and only to
     the account owner's email — use that for local testing)
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── Internal helper ───────────────────────────────────────────────────────────
def _resend_client():
    """Return configured resend module or raise ValueError if not set up."""
    try:
        import resend
    except ImportError:
        raise ValueError("resend not installed — pip install resend")

    from app.config import settings
    if not settings.RESEND_API_KEY:
        raise ValueError("RESEND_API_KEY not set in .env")

    resend.api_key = settings.RESEND_API_KEY
    return resend


# ── 1 function = 1 feature ────────────────────────────────────────────────────
def send_order_confirmation(email: str, order: dict[str, Any]) -> None:
    """Send confirmation email after order is created."""
    try:
        resend = _resend_client()
        from app.config import settings

        order_id = str(order.get("id", ""))[:8].upper()
        city     = order.get("shipping_city", "")
        country  = order.get("shipping_country", "")
        total    = order.get("total_amount", "0")
        status   = str(order.get("status", "pending")).capitalize()

        params = {
            "from":    settings.FROM_EMAIL,
            "to":      [email],              # ← MUST be a list in resend v2
            "subject": f"Order #{order_id} confirmed — {settings.APP_NAME}",
            "html": f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:sans-serif;">
  <div style="max-width:520px;margin:40px auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08);">
    <div style="background:#0B1628;padding:28px 32px;">
      <h1 style="color:#00C5D4;font-size:22px;margin:0;letter-spacing:2px;">LUVIIO</h1>
    </div>
    <div style="padding:32px;">
      <h2 style="color:#0B1628;margin-top:0;">Order Confirmed ✓</h2>
      <p style="color:#555;">Your order has been placed successfully.</p>
      <table style="width:100%;border-collapse:collapse;margin:20px 0;">
        <tr style="border-bottom:1px solid #eee;">
          <td style="padding:10px 0;color:#888;font-size:13px;">Order ID</td>
          <td style="padding:10px 0;font-weight:700;text-align:right;">#{order_id}</td>
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
</body>
</html>
            """,
        }

        result = resend.Emails.send(params)
        logger.info("Confirmation email sent | to=%s order=%s resend_id=%s",
                    email, order.get("id"), getattr(result, "id", result))

    except ValueError as e:
        # Config not set — expected in dev without Resend key
        logger.warning("Email skipped: %s", e)
    except Exception as e:
        # Never crash the order — just log full traceback
        logger.error("send_order_confirmation failed | to=%s | %s",
                     email, e, exc_info=True)


def send_order_shipped(
    email: str,
    order: dict[str, Any],
    tracking_number: str | None,
) -> None:
    """Send shipment notification email."""
    try:
        resend = _resend_client()
        from app.config import settings

        order_id     = str(order.get("id", ""))[:8].upper()
        tracking_row = (
            f"<tr><td style='padding:10px 0;color:#888;font-size:13px;'>Tracking</td>"
            f"<td style='padding:10px 0;font-weight:700;text-align:right;'>{tracking_number}</td></tr>"
        ) if tracking_number else ""

        params = {
            "from":    settings.FROM_EMAIL,
            "to":      [email],              # ← MUST be a list in resend v2
            "subject": f"Your order #{order_id} has shipped! 🚚",
            "html": f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:sans-serif;">
  <div style="max-width:520px;margin:40px auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08);">
    <div style="background:#0B1628;padding:28px 32px;">
      <h1 style="color:#00C5D4;font-size:22px;margin:0;letter-spacing:2px;">LUVIIO</h1>
    </div>
    <div style="padding:32px;">
      <h2 style="color:#0B1628;margin-top:0;">Your order is on the way! 🚚</h2>
      <p style="color:#555;">Order <strong>#{order_id}</strong> has been shipped.</p>
      <table style="width:100%;border-collapse:collapse;margin:20px 0;">
        {tracking_row}
        <tr>
          <td style="padding:10px 0;color:#888;font-size:13px;">Estimated Delivery</td>
          <td style="padding:10px 0;text-align:right;">3–5 business days</td>
        </tr>
      </table>
    </div>
  </div>
</body>
</html>
            """,
        }

        result = resend.Emails.send(params)
        logger.info("Shipped email sent | to=%s order=%s resend_id=%s",
                    email, order.get("id"), getattr(result, "id", result))

    except ValueError as e:
        logger.warning("Email skipped: %s", e)
    except Exception as e:
        logger.error("send_order_shipped failed | to=%s | %s",
                     email, e, exc_info=True)