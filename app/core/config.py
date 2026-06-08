"""
Luviio Settings — Production Grade
====================================
Path: app/core/config.py

Central configuration using Pydantic Settings.
Reads from .env file + environment variables.
"""
from typing import List
from pydantic import field_validator, ValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # ── APP ────────────────────────────────────────────────────────
    APP_NAME: str = "luviio"
    APP_ENV: str = "production"
    DEBUG: bool = False

    # ── SUPABASE ───────────────────────────────────────────────────
    SB_URL: str = ""
    SB_KEY: str = ""
    SB_SERVICE_ROLE_KEY: str = ""

    # ── STRIPE ─────────────────────────────────────────────────────
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # ── RESEND (EMAIL) ─────────────────────────────────────────────
    RESEND_API_KEY: str = ""
    FROM_EMAIL: str = "Luviio <orders@luviio.in>"

    # ── VAPID (PUSH NOTIFICATIONS) ─────────────────────────────────
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_CLAIM_EMAIL: str = "mailto:admin@luviio.in"

    # ── CORS ───────────────────────────────────────────────────────
    ALLOWED_ORIGINS: str = (
        "https://luviio.in,"
        "https://www.luviio.in,"
        "http://localhost:7700,"
        "http://127.0.0.1:7700,"
        "https://my-frontend-c4s409o9f-pixelart002s-projects.vercel.app"
    )

    # ── RATE LIMITING ──────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60

    # ── VALIDATORS ─────────────────────────────────────────────────
    @field_validator(
        "SB_URL", "SB_KEY", "SB_SERVICE_ROLE_KEY",
        "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
    )
    @classmethod
    def require_keys_in_production(cls, v: str, info: ValidationInfo) -> str:
        app_env = info.data.get("APP_ENV", "production")
        if app_env != "development" and not v:
            raise ValueError(f"{info.field_name} is required in production")
        return v

    # ── COMPUTED PROPERTIES ────────────────────────────────────────
    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool: return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool: return self.APP_ENV == "development"

    @property
    def stripe_configured(self) -> bool: return bool(self.STRIPE_SECRET_KEY and self.STRIPE_WEBHOOK_SECRET)

    @property
    def email_configured(self) -> bool: return bool(self.RESEND_API_KEY and self.FROM_EMAIL)

    @property
    def push_configured(self) -> bool: return bool(self.VAPID_PUBLIC_KEY and self.VAPID_PRIVATE_KEY)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        case_sensitive=True, extra="ignore", validate_default=True,
    )

settings = Settings()