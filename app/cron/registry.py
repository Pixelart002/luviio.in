import inspect
import logging
from functools import wraps
from typing import Any, Callable, Dict, List

from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)

CRON_JOBS: List[Dict[str, Any]] = []
CRON_LEASE_SECONDS = 3600


def _leased_job(func: Callable) -> Callable:
    """Wrap a cron task with a cross-worker PostgreSQL lease."""
    @wraps(func)
    async def runner(*args: Any, **kwargs: Any) -> Any:
        job_name = func.__name__
        token = None
        try:
            sb = await get_async_admin_supabase()
            result = await sb.rpc(
                "acquire_cron_job_lease",
                {"p_job_name": job_name, "p_lease_seconds": CRON_LEASE_SECONDS},
            ).execute()
            token = result.data
            if not token:
                logger.debug("[CRON] Skipping %s; another worker holds the lease", job_name)
                return None

            value = func(*args, **kwargs)
            return await value if inspect.isawaitable(value) else value
        except Exception:
            logger.exception("[CRON] Leased job %s failed", job_name)
            raise
        finally:
            if token:
                try:
                    sb = await get_async_admin_supabase()
                    await sb.rpc(
                        "release_cron_job_lease",
                        {"p_job_name": job_name, "p_lease_token": token},
                    ).execute()
                except Exception:
                    logger.exception("[CRON] Failed to release lease for %s", job_name)

    return runner


def cron_task(trigger: str = "interval", **kwargs: Any):
    """Register a scheduled job with cross-worker execution protection."""
    def decorator(func: Callable) -> Callable:
        leased_func = _leased_job(func)
        job_kwargs = dict(kwargs)
        if trigger == "interval" and "seconds" in job_kwargs:
            # Prevent every Uvicorn worker from waking on the same scheduler
            # tick. The PostgreSQL lease remains the execution authority.
            job_kwargs.setdefault("jitter", min(5, max(1, int(job_kwargs["seconds"] // 3))))
            job_kwargs.setdefault("coalesce", True)
            job_kwargs.setdefault("max_instances", 1)
            job_kwargs.setdefault("misfire_grace_time", 30)
        CRON_JOBS.append({
            "func": leased_func,
            "trigger": trigger,
            "id": func.__name__,
            "replace_existing": True,
            **job_kwargs,
        })
        logger.debug("[CRON REGISTRY] Registered task: %s", func.__name__)
        return leased_func

    return decorator
