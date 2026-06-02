"""
Luviio Settings — Production Grade
====================================
Central configuration using Pydantic Settings.
Reads from .env file + environment variables.

Pricing Strategy:
  ✅ Cart → DB pricing_config table (live, admin-updatable)
  ✅ Orders → settings.py fallback (DB migration pending)
  
  Fallback values match DB defaults — consistency guaranteed.
"""
import os
from decimal import Decimal
from typing import List

from pydantic import field_validator, ValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env and environment variables."""

    # ══════════════════════════════════════════════════════════════════════════
    #  APP
    # ══════════════════════════════════════════════════════════════════════════
    APP_NAME: str = "luviio"
    APP_ENV: str = "production"
    DEBUG: bool = False

    # ══════════════════════════════════════════════════════════════════════════
    #  SUPABASE
    # ══════════════════════════════════════════════════════════════════════════
    SB_URL: str = ""
    SB_KEY: str = ""
    SB_SERVICE_ROLE_KEY: str = ""

    # ══════════════════════════════════════════════════════════════════════════
    #  STRIPE
    # ══════════════════════════════════════════════════════════════════════════
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # ══════════════════════════════════════════════════════════════════════════
    #  RESEND (EMAIL)
    # ══════════════════════════════════════════════════════════════════════════
    RESEND_API_KEY: str = ""
    FROM_EMAIL: str = "Luviio <orders@luviio.in>"

    # ══════════════════════════════════════════════════════════════════════════
    #  VAPID (PUSH NOTIFICATIONS)
    # ══════════════════════════════════════════════════════════════════════════
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_CLAIM_EMAIL: str = "mailto:admin@luviio.in"

    # ══════════════════════════════════════════════════════════════════════════
    #  CORS
    # ══════════════════════════════════════════════════════════════════════════
    ALLOWED_ORIGINS: str = (
        "https://luviio.in,"
        "https://www.luviio.in,"
        "http://localhost:7700,"
        "http://127.0.0.1:7700,"
        "https://my-frontend-c4s409o9f-pixelart002s-projects.vercel.app"
    )

    # ══════════════════════════════════════════════════════════════════════════
    #  RATE LIMITING
    # ══════════════════════════════════════════════════════════════════════════
    RATE_LIMIT_PER_MINUTE: int = 60

    # ══════════════════════════════════════════════════════════════════════════
    #  PRICING — FALLBACK VALUES (DB pricing_config table is primary source)
    # ══════════════════════════════════════════════════════════════════════════
    # 
    # 📌 NOTE: Cart uses LIVE pricing from DB (pricing_config table)
    #          Orders still use these settings via get_default_pricing()
    #          Future: Orders will also use DB pricing_config
    #
    # These must match the DEFAULT values in pricing_config table seed:
    #   INSERT INTO pricing_config (tax_rate, shipping_flat, shipping_threshold, ...)
    #   VALUES (18.0, 99.0, 999.0, ...);
    #
    SHIPPING_THRESHOLD: Decimal = Decimal("999.00")   # Free shipping above ₹999
    SHIPPING_FLAT: Decimal = Decimal("99.00")          # Flat shipping fee
    TAX_RATE: Decimal = Decimal("0.18")                # 18% GST

    # ══════════════════════════════════════════════════════════════════════════
    #  VALIDATORS
    # ══════════════════════════════════════════════════════════════════════════

    @field_validator("SB_URL", "SB_KEY", "SB_SERVICE_ROLE_KEY", 
                     "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET")
    @classmethod
    def require_keys_in_production(cls, v: str, info: ValidationInfo) -> str:
        """Critical keys must be set in production"""
        app_env = info.data.get("APP_ENV", "production")
        if app_env != "development" and not v:
            raise ValueError(
                f"{info.field_name} must be set in production environment"
            )
        return v

    # ══════════════════════════════════════════════════════════════════════════
    #  COMPUTED PROPERTIES
    # ══════════════════════════════════════════════════════════════════════════

    @property
    def cors_origins(self) -> List[str]:
        """
        Strict CORS origins — prevents wildcard issues.
        Koyeb environment variables cannot override this.
        """
        return [
            "https://luviio.in",
            "https://www.luviio.in",
            "http://localhost:7700",
            "http://127.0.0.1:7700",
            "https://my-frontend-c4s409o9f-pixelart002s-projects.vercel.app",
        ]

    @property
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.APP_ENV == "development"

    @property
    def stripe_configured(self) -> bool:
        """Check if Stripe keys are properly set"""
        return bool(self.STRIPE_SECRET_KEY and self.STRIPE_WEBHOOK_SECRET)

    @property
    def email_configured(self) -> bool:
        """Check if email (Resend) is configured"""
        return bool(self.RESEND_API_KEY and self.FROM_EMAIL)

    @property
    def push_configured(self) -> bool:
        """Check if push notifications (VAPID) are configured"""
        return bool(self.VAPID_PUBLIC_KEY and self.VAPID_PRIVATE_KEY)

    # ══════════════════════════════════════════════════════════════════════════
    #  PYDANTIC CONFIG
    # ══════════════════════════════════════════════════════════════════════════

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",          # Ignore unknown env vars
        validate_default=True,   # Validate default values too
    )


# ── Singleton ─────────────────────────────────────────────────────────────────
settings = Settings()