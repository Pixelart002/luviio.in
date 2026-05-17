import os
from decimal import Decimal
from typing import List

from pydantic import field_validator, ValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    APP_NAME: str = "luviio"
    APP_ENV: str = "production"

    # Supabase
    SB_URL: str = ""
    SB_KEY: str = ""
    SB_SERVICE_ROLE_KEY: str = ""

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Resend (email)
    RESEND_API_KEY: str = ""
    FROM_EMAIL: str = "orders@mystore.com"

    # CORS — Updated with Vercel URL
    ALLOWED_ORIGINS: str = "https://luviio.in,https://www.luviio.in,http://localhost:7700,http://127.0.0.1:7700,https://my-frontend-c4s409o9f-pixelart002s-projects.vercel.app"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Pricing (Pydantic V2 natively handles Decimal parsing!)
    SHIPPING_THRESHOLD: Decimal = Decimal("75.00")
    SHIPPING_FLAT: Decimal = Decimal("9.99")
    TAX_RATE: Decimal = Decimal("0.08")

    @field_validator("SB_URL", "SB_KEY", "SB_SERVICE_ROLE_KEY", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET")
    @classmethod
    def require_keys_in_production(cls, v: str, info: ValidationInfo) -> str:
        # FIX: Use info.data to read APP_ENV parsed from the .env file
        app_env = info.data.get("APP_ENV", "production")
        
        if app_env != "development" and not v:
            raise ValueError(f"{info.field_name} must be set in production environment")
        return v

    @property
    def cors_origins(self) -> List[str]:
        # 🔥 KOYEB BYPASS: Strictly enforcing these domains. 
        # This prevents any stray '*' in Koyeb's environment variables from breaking login.
        return [
            "https://luviio.in",
            "https://www.luviio.in",
            "http://localhost:7700",
            "http://127.0.0.1:7700",
            "https://my-frontend-c4s409o9f-pixelart002s-projects.vercel.app"
        ]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    # Use SettingsConfigDict for Pydantic V2 best practices
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
