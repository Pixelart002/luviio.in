from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, field_validator
from typing import List


class Settings(BaseSettings):
    # App
    APP_NAME: str = "MyStore"
    APP_ENV: str = "production"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    ALLOWED_ORIGINS: str = ""

    @property
    def cors_origins(self) -> List[str]:
        if self.APP_ENV == "development":
            return ["*"]
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Admin seed
    FIRST_ADMIN_EMAIL: str = "admin@mystore.com"
    FIRST_ADMIN_PASSWORD: str = "change-me"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
