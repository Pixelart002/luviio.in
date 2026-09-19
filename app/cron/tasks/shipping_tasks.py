"""Scheduled shipment synchronization and post-delivery follow-ups."""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from app.cron.registry import cron_task
from app.core.supabase import get_async_admin_supabase
from app.domains.shipping.provider_repository import ShippingProviderRepository
from app.domains.shipping.provider_service import ShippingProviderService
from app.integrations.email.registry import get_email_provider
from app.integrations.push.webpush_impl import send_push_to_user

logger = logging.getLogger(__name__)
repo = ShippingProviderRepository()
service = ShippingProviderService()

@cron_task(minutes=10)
async def synchronize_active_shipments() -> None:
    rows = await repo.list_recent(limit=200)
    active = [r for r in rows if r.get("provider_key") == "shiprocket" and r.get("tracking_number") and str(r.get("status") or "").lower() not in {"delivered","cancelled","canceled","rto","rto_delivered"}]
    for row in active:
        try:
            await service.sync_tracking(str(row["id"]))
        except Exception as exc:
            logger.warning("[CRON] shipment sync failed id=%s: %s", str(row.get("id"))[:8], exc)

@cron_task(hours=1)
async def send_post_delivery_followups() -> None:
    sb = await get_async_admin_supabase()
    cutoff_review = datetime.now(timezone.utc) - timedelta(hours=24)
    cutoff_care = datetime.now(timezone.utc) - timedelta(hours=72)
    rows = await repo.list_recent(limit=200)
    email = get_email_provider("resend")
    for row in rows:
        delivered_at = row.get("delivered_at")
        if not delivered_at:
            continue
        try:
            delivered = datetime.fromisoformat(str(delivered_at).replace("Z", "+00:00"))
        except ValueError:
            continue
        order_res = await sb.table("orders").select("order_number,customer_id,shipping_email").eq("id", row["order_id"]).maybe_single().execute()
        order = order_res.data if order_res else None
        if not order or not order.get("shipping_email"):
            continue
        metadata = dict(row.get("metadata") or {})
        oid = str(order.get("order_number") or "")
        if delivered <= cutoff_review and not metadata.get("review_followup_sent_at"):
            try:
                sent = await email.send_review_followup(str(order["shipping_email"]), oid)
                if sent:
                    metadata["review_followup_sent_at"] = datetime.now(timezone.utc).isoformat()
                    await repo.update(str(row["id"]), {"metadata": metadata})
                    if order.get("customer_id"):
                        await send_push_to_user(order["customer_id"], title="How was your order?", body=f"Share your experience with order #{oid}.", icon="/icons/ri-star-line.png", url=f"/orders/{oid}")
            except Exception:
                logger.exception("[CRON] review follow-up failed order=%s", oid)
        if delivered <= cutoff_care and not metadata.get("care_followup_sent_at"):
            try:
                sent = await email.send_delivery_care_followup(str(order["shipping_email"]), oid)
                if sent:
                    metadata["care_followup_sent_at"] = datetime.now(timezone.utc).isoformat()
                    await repo.update(str(row["id"]), {"metadata": metadata})
                    if order.get("customer_id"):
                        await send_push_to_user(order["customer_id"], title="Need help with your order?", body=f"Need anything with order #{oid}? We're here to help.", icon="/icons/ri-customer-service-2.png", url=f"/orders/{oid}")
            except Exception:
                logger.exception("[CRON] care follow-up failed order=%s", oid)
