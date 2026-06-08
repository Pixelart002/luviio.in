"""
Monitoring & Error Tracking Setup
=================================
Path: app/core/monitoring.py
"""
import sentry_sdk
from app.core.config import settings

def init_sentry():
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN if hasattr(settings, "SENTRY_DSN") else "https://8d98c50d41677e226c0ad55b901fab20@o4511499364270080.ingest.us.sentry.io/4511499512446976",
        send_default_pii=True,
        traces_sample_rate=1.0,
        environment=settings.APP_ENV,
    )