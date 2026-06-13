import logging
import datetime
from app.cron.registry import cron_task
from app.repositories.cart_repo import AsyncCartRepository

logger = logging.getLogger(__name__)

@cron_task(minutes=15)
async def unlock_orphaned_carts():
    """
    Finds carts locked for more than 30 minutes and unlocks them.
    Runs every 15 minutes.
    """
    logger.info("[CRON] Running orphaned cart cleanup job...")
    repo = AsyncCartRepository()
    
    # 30 minute pehle ka time nikalo
    cutoff_time = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)
    ).isoformat()
    
    try:
        # Wo carts dhoondo jo Locked hain AND 30 min se update nahi hue
        res = await repo.admin_sb.table("carts").update({"locked": False}) \
            .eq("locked", True) \
            .lt("updated_at", cutoff_time).execute()
            
        unlocked_count = len(res.data) if res and res.data else 0
        if unlocked_count > 0:
            logger.info(f"[CRON] ✅ Successfully unlocked {unlocked_count} orphaned cart(s).")
        else:
            logger.debug("[CRON] No orphaned carts found.")
            
    except Exception as e:
        logger.error(f"[CRON] ❌ Failed to run orphaned cart cleanup: {e}", exc_info=True)