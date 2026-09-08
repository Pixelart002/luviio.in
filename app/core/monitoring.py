"""
Monitoring & Error Tracking Setup
=================================
Path: app/core/monitoring.py
"""
import os

import sentry_sdk

from app.core.config import settings


def init_sentry() -> None:
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn or settings.APP_ENV in {"development", "test", "local"}:
        return
    sentry_sdk.init(
        dsn=dsn,
        send_default_pii=False,
        traces_sample_rate=0.1,
        environment=settings.APP_ENV,
        release=os.getenv("APP_VERSION", "unknown"),
        include_local_variables=False,
    )
