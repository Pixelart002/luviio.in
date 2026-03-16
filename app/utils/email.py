import logging
from typing import Any

logger = logging.getLogger(__name__)


def send_order_confirmation(email: str, order: dict[str, Any]) -> None:
    """Order create hone pe confirmation email bhejo."""
    try:
        import resend
        from app.config import settings

        if not settings.RESEND_API_KEY:
            logger.warning("RESEND_API_KEY not set — skipping order confirmation email")
            return

        resend.api_key = settings.RESEND_API_KEY
        order_id_short = str(order.get("id", ""))[:8].upper()

        resend.Emails.send({
            "from": settings.FROM_EMAIL,
            "to": email,
            "subject": f"Order #{order_id_short} confirmed — {settings.APP_NAME}",
            "html": f"""
                <h2>Order Confirmed!</h2>
                <p>Order ID: <strong>#{order_id_short}</strong></p>
                <p>Total: <strong>₹{order.get('total_amount', '0')}</strong></p>
                <p>Status: {order.get('status', 'pending').capitalize()}</p>
                <hr>
                <p style="color:#888;font-size:12px">
                  Shipping to: {order.get('shipping_city', '')}, {order.get('shipping_country', '')}
                </p>
            """,
        })
        logger.info("Order confirmation email sent to %s for order %s", email, order.get("id"))
    except Exception as e:
        # Email failure should never break the order flow
        logger.error("Failed to send order confirmation email: %s", e)


def send_order_shipped(email: str, order: dict[str, Any], tracking_number: str | None) -> None:
    """Order ship hone pe notification email bhejo."""
    try:
        import resend
        from app.config import settings

        if not settings.RESEND_API_KEY:
            return

        resend.api_key = settings.RESEND_API_KEY
        order_id_short = str(order.get("id", ""))[:8].upper()
        tracking_info = f"Tracking: <strong>{tracking_number}</strong>" if tracking_number else ""

        resend.Emails.send({
            "from": settings.FROM_EMAIL,
            "to": email,
            "subject": f"Order #{order_id_short} has shipped!",
            "html": f"""
                <h2>Your order is on the way!</h2>
                <p>Order ID: <strong>#{order_id_short}</strong></p>
                {tracking_info}
            """,
        })
    except Exception as e:
        logger.error("Failed to send shipped email: %s", e)