from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    APP_NAME: str = "MyStore"
    APP_ENV: str = "production"

    SB_URL: str = ""
    SB_KEY: str = ""
    SB_SERVICE_ROLE_KEY: str = ""

    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    RESEND_API_KEY: str = ""
    FROM_EMAIL: str = "orders@mystore.com"

    # Set your actual frontend domain in .env — no claude.ai here
    ALLOWED_ORIGINS: str = "https://yourfrontend.com"

    RATE_LIMIT_PER_MINUTE: int = 60

    @field_validator("SB_URL", "SB_KEY", "SB_SERVICE_ROLE_KEY")
    @classmethod
    def supabase_must_be_set(cls, v: str, info) -> str:
        if not v:
            raise ValueError(f"{info.field_name} must be set in environment")
        return v

    @field_validator("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET")
    @classmethod
    def stripe_must_be_set(cls, v: str, info) -> str:
        if not v:
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