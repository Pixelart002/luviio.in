import os
from decimal import Decimal
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "MyStore"
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

    # CORS — set your actual frontend domain in .env
    ALLOWED_ORIGINS: str = "https://yourfrontend.com"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Order pricing — move to .env to change without redeploy
    SHIPPING_THRESHOLD: Decimal = Decimal("75.00")
    SHIPPING_FLAT: Decimal = Decimal("9.99")
    TAX_RATE: Decimal = Decimal("0.08")

    @field_validator("SB_URL", "SB_KEY", "SB_SERVICE_ROLE_KEY")
    @classmethod
    def supabase_must_be_set(cls, v: str, info) -> str:
        # Skip validation in development — .env might not have all keys
        if os.getenv("APP_ENV", "production") != "development" and not v:
            raise ValueError(f"{info.field_name} must be set in environment")
        return v

    @field_validator("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET")
    @classmethod
    def stripe_must_be_set(cls, v: str, info) -> str:
        if os.getenv("APP_ENV", "production") != "development" and not v:
            raise ValueError(f"{info.field_name} must be set in environment")
        return v

    @property
    def cors_origins(self) -> List[str]:
        if self.APP_ENV == "development":
            return ["*"]
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


settings = Settings()