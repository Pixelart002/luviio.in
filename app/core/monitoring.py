"""
Monitoring & Error Tracking Setup
=================================
Path: app/core/monitoring.py
"""
import sentry_sdk
from app.core.config import settings

def init_sentry():
    """Initialize Sentry for error tracking."""
    sentry_sdk.init(
        dsn="https://8d98c50d41677e226c0ad55b901fab20@o4511499364270080.ingest.us.sentry.io/4511499512446976",
        send_default_pii=True,           # Adds user data like IP and request headers
        traces_sample_rate=1.0,          # 100% performance monitoring
        environment=settings.APP_ENV,    # Tags errors with production/development
    )