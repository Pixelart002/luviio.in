import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Import task modules so their decorators populate CRON_JOBS.
import app.cron.tasks.event_tasks  # noqa: F401,E402
import app.cron.tasks.order_tasks  # noqa: F401,E402
from app.cron.registry import CRON_JOBS

logger = logging.getLogger(__name__)

cron_scheduler = AsyncIOScheduler()


def start_cron_jobs():
    logger.info(f"[CRON] Starting Scheduler. Found {len(CRON_JOBS)} tasks in registry.")

    for job in CRON_JOBS:
        kwargs = {k: v for k, v in job.items() if k not in ("func", "trigger")}
        cron_scheduler.add_job(job["func"], trigger=job["trigger"], **kwargs)

    cron_scheduler.start()
    logger.info("[CRON] 🚀 Background Scheduler is now ACTIVE.")
