import fcntl
import logging
import os
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Import task modules so their decorators populate CRON_JOBS.
import app.cron.tasks.coupon_tasks  # noqa: F401,E402
import app.cron.tasks.event_tasks  # noqa: F401,E402
import app.cron.tasks.order_tasks  # noqa: F401,E402
import app.cron.tasks.shipping_tasks  # noqa: F401,E402
from app.cron.registry import CRON_JOBS

logger = logging.getLogger(__name__)

cron_scheduler = AsyncIOScheduler()
_scheduler_lock_file: Optional[object] = None
_scheduler_lock_path = "/tmp/luviio-cron-scheduler.lock"


def _acquire_scheduler_lock() -> bool:
    """Allow exactly one worker in this container to own the APScheduler."""
    global _scheduler_lock_file

    if _scheduler_lock_file is not None:
        return True

    lock_file = None
    try:
        lock_file = open(_scheduler_lock_path, "a+")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _scheduler_lock_file = lock_file
        return True
    except (BlockingIOError, OSError):
        if lock_file is not None:
            try:
                lock_file.close()
            except OSError:
                pass
        return False


def _release_scheduler_lock() -> None:
    global _scheduler_lock_file
    if _scheduler_lock_file is None:
        return

    try:
        fcntl.flock(_scheduler_lock_file.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        _scheduler_lock_file.close()
    except OSError:
        pass
    _scheduler_lock_file = None


def start_cron_jobs() -> bool:
    """Start APScheduler in one worker per container, not once per Gunicorn worker."""
    if cron_scheduler.running:
        return True

    if not _acquire_scheduler_lock():
        logger.info("Scheduler skipped | another worker owns the container scheduler lock")
        return False

    logger.info("Scheduler starting | tasks=%s pid=%s", len(CRON_JOBS), os.getpid())

    try:
        for job in CRON_JOBS:
            kwargs = {k: v for k, v in job.items() if k not in ("func", "trigger")}
            cron_scheduler.add_job(job["func"], trigger=job["trigger"], **kwargs)

        cron_scheduler.start()
        logger.info("Scheduler started | tasks=%s pid=%s", len(CRON_JOBS), os.getpid())
        return True
    except Exception:
        _release_scheduler_lock()
        raise


def stop_cron_jobs() -> None:
    """Stop APScheduler and release the per-container ownership lock."""
    if cron_scheduler.running:
        cron_scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped | pid=%s", os.getpid())
    _release_scheduler_lock()
