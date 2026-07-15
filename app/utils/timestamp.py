"""
Timestamp Utility
=================
Path: app/utils/timestamp.py
"""
import datetime
import logging
from typing import Any

logger = logging.getLogger(__name__)

def ts_to_iso(val: Any) -> str | None:
    """
    Safely converts Unix timestamp (int/float) to a readable ISO-8601 UTC date string.
    Usage:
        from app.utils.timestamp import ts_to_iso
        formatted_date = ts_to_iso(1784091623)
    """
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            return datetime.datetime.fromtimestamp(val, tz=datetime.timezone.utc).isoformat()
        return str(val)
    except Exception as e:
        logger.debug("Timestamp conversion fallback: %s", e)
        return str(val) if val is not None else None