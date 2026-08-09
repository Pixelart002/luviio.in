"""
WhatsApp Order Alerts Handler
=============================
Path: app/events/handlers/whatsapp_alerts.py
"""
import logging
from app.events.bus import get_event_bus, OrderPaidEvent
from app.integrations.whatsapp.client import notify_team

logger = logging.getLogger(__name__)

async def handle_order_paid_whatsapp(event: OrderPaidEvent) -> None:
    """
    Listens for Paid orders and dispatches a WhatsApp alert to the team.
    Runs asynchronously via the Event Bus threadpool/task system.
    """
    try:
        order = event.order
        short_id = order.get("order_number") or str(order.get("id", ""))[:8].upper()
        amount = order.get("total_amount", 0.0)
        customer_name = order.get("shipping_name") or order.get("billing_name") or "A Customer"
        items_count = len(order.get("order_items") or [])
        
        # Format the WhatsApp Message
        msg = (
            f"🚨 *NEW ORDER RECEIVED!* 🚨\n\n"
            f"📦 *Order ID:* #{short_id}\n"
            f"👤 *Customer:* {customer_name}\n"
            f"🛒 *Items:* {items_count}\n"
            f"💰 *Total Paid:* ₹{amount}\n\n"
            f"👉 *View details in Admin Panel:*\n"
            f"https://luviio.in/admin.html"
        )
        
        # Trigger WhatsApp API
        await notify_team(msg)
        
    except Exception as e:
        logger.error(f"[WHATSAPP HANDLER] Failed to generate alert for Order {short_id}: {e}")

# Register the handler to the bus
def register_whatsapp_handlers():
    bus = get_event_bus()
    bus.subscribe(OrderPaidEvent, handle_order_paid_whatsapp)
    logger.info("✅ WhatsApp Alerts Handler registered to Event Bus.")