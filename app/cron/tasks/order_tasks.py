##import logging
#from datetime import datetime, timedelta, timezone
#from app.cron.registry import cron_task
#from app.repositories.payment_repo import AsyncPaymentRepository
#from app.integrations.payments.registry import get_payment_provider

#logger = logging.getLogger(__name__)

#@cron_task(minutes=15)
#async def cleanup_pending_orders():
#    logger.info("[CRON] Running pending order verification...")
#    repo = AsyncPaymentRepository()
#    payment_service = get_payment_provider("stripe")
    
    # 15 minute pehle ka time
#    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    
    # DB se pending orders fetch karo
#    res = await repo.admin_sb.table("orders").select("*").eq("status", "pending").lt("created_at", cutoff.isoformat()).execute()
    
#    for order in res.data or []:
#        try:
 #           pi_id = order.get("stripe_payment_intent")
#            if not pi_id: continue
            
            # Stripe se status check karo
 #           intent = await payment_service.retrieve_intent(pi_id)
            
 #           if intent["status"] == "succeeded":
  #              await repo.update_order_status(order["id"], "paid", pi_id)
 #               logger.info(f"[CRON] Order {order['id']} recovered to PAID status.")
#            elif intent["status"] in ["canceled", "processing"] and intent["status"] != "succeeded":
                # Isko failed mark karke stock restore karo
 #               await repo.update_order_status(order["id"], "failed")
#                await repo.restore_stock_for_order(order["id"])
#                logger.info(f"[CRON] Order {order['id']} marked FAILED and stock restored.")
                
#        except Exception as e:
#            logger.error(f"[CRON] Error verifying order {order['id']}: {e}")