import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.cron.registry import CRON_JOBS

# Importing tasks is zaroori taaki decorators run ho aur registry bhar jaye
import app.cron.tasks.order_tasks 

logger = logging.getLogger(__name__)

# AsyncIOScheduler FastAPI ke event loop ke sath perfectly kaam karta hai
cron_scheduler = AsyncIOScheduler()

def start_cron_jobs():
    logger.info(f"[CRON] Starting Scheduler. Found {len(CRON_JOBS)} tasks in registry.")
    
    for job in CRON_JOBS:
        # Job add karte time 'func' aur 'trigger' alag se pass karna hota hai
        kwargs = {k: v for k, v in job.items() if k not in ("func", "trigger")}
        cron_scheduler.add_job(job["func"], trigger=job["trigger"], **kwargs)
        
    cron_scheduler.start()
    logger.info("[CRON] 🚀 Background Scheduler is now ACTIVE.")