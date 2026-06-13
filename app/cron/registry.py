import logging
from typing import Callable, List, Dict, Any

logger = logging.getLogger(__name__)

# Ye list humari registry hai jisme saari jobs store hongi
CRON_JOBS: List[Dict[str, Any]] = []

def cron_task(trigger: str = "interval", **kwargs):
    """
    Decorator for Registry Pattern.
    Example: @cron_task(minutes=15)
    """
    def decorator(func: Callable):
        job_config = {
            "func": func,
            "trigger": trigger,
            "id": func.__name__,
            "replace_existing": True,
            **kwargs
        }
        CRON_JOBS.append(job_config)
        logger.debug(f"[CRON REGISTRY] Registered task: {func.__name__}")
        return func
    return decorator