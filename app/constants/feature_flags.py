import os

class FeatureFlags:
    NEW_CHECKOUT = "NEW_CHECKOUT"
    CRYPTO_PAYMENTS = "CRYPTO_PAYMENTS"
    ADVANCED_ANALYTICS = "ADVANCED_ANALYTICS"
    PUSH_NOTIFICATIONS = "PUSH_NOTIFICATIONS"

def is_feature_enabled(flag: str, default: bool = False) -> bool:
    """
    Checks if a feature is enabled via environment variables.
    """
    val = os.getenv(flag)
    if val is None:
        return default
    return str(val).lower() in ("true", "1", "yes", "on")