"""
Luviio Settings — Production Grade
====================================
Central configuration using Pydantic Settings.
Production defaults are deliberately restrictive; deployment-specific origins
must be supplied explicitly through ALLOWED_ORIGINS.
"""
import re
from typing import List
from urllib.parse import urlsplit

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "luviio"
    APP_ENV: str = "production"
    DEBUG: bool = False

    SB_URL: str = ""
    SB_KEY: str = ""
    SB_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""

    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    RESEND_API_KEY: str = ""
    FROM_EMAIL: str = "Luviio <orders@luviio.in>"

    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_CLAIM_EMAIL: str = "mailto:admin@luviio.in"

    OLA_MAPS_API_KEY: str = ""

    FRONTEND_URL: str = "https://www.luviio.in"
    ALLOWED_ORIGINS: str = "https://luviio.in,https://www.luviio.in"
    # Narrow patterns for Luviio-owned preview deployments. Never use a universal
    # HTTPS wildcard for credentialed production API responses.
    CORS_PREVIEW_ORIGIN_PATTERNS: str = (
        r"^https://jubilant-space-system-[a-z0-9-]+\.app\.github\.dev$,"
        r"^https://my-frontend-git-[a-z0-9-]+-pixelart002s-projects\.vercel\.app$,"
        r"^https://my-frontend-ascu-git-[a-z0-9-]+-pixelart002s-projects\.vercel\.app$"
    )

    RATE_LIMIT_PER_MINUTE: int = 60
    TRUSTED_PROXY_IPS: str = ""
    SENTRY_DSN: str = ""
    APP_VERSION: str = "unknown"

    TAXONOMY_API_BASE_URL: str = "https://hsn.krakelabsindia.com"
    TAXONOMY_API_KEY: str = ""
    TAXONOMY_API_TIMEOUT_SECONDS: float = 3.0
    TAXONOMY_ENFORCE_PRODUCT_TAX: bool = True

    @field_validator(
        "SB_URL", "SB_KEY", "SB_SERVICE_ROLE_KEY",
        "SUPABASE_JWT_SECRET",
        "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
    )
    @classmethod
    def require_keys_in_production(cls, v: str, info: ValidationInfo) -> str:
        app_env = info.data.get("APP_ENV", "production")
        if app_env not in ("development", "test") and not v:
            raise ValueError(f"{info.field_name} is required in production")
        return v

    @staticmethod
    def _normalized_https_origin(value: str) -> str | None:
        """Return a canonical HTTPS origin, excluding paths and credentials."""
        try:
            parsed = urlsplit(str(value or "").strip())
            # Production browser origins must be HTTPS and may not embed userinfo.
            if (
                parsed.scheme.lower() != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
            ):
                return None
            # Accessing .port validates that any port is numeric and in range.
            _ = parsed.port
            return f"https://{parsed.netloc.lower()}"
        except (ValueError, TypeError):
            return None

    @property
    def cors_origins(self) -> List[str]:
        configured = [
            origin.strip()
            for origin in self.ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]

        # Keep the previous non-production semantics so local/test setups that
        # explicitly use '*' continue to work. Production never trusts '*'.
        if not self.is_production:
            return configured

        origins: list[str] = []
        for value in configured:
            if value == "*":
                continue
            normalized = self._normalized_https_origin(value)
            if normalized and normalized not in origins:
                origins.append(normalized)

        # FRONTEND_URL is already a trusted deployment setting. Include its
        # exact origin even if ALLOWED_ORIGINS was accidentally set to '*',
        # and normalize common trailing-slash/path mistakes to an origin.
        frontend_origin = self._normalized_https_origin(self.FRONTEND_URL)
        if frontend_origin and frontend_origin not in origins:
            origins.append(frontend_origin)

        # Luviio serves the storefront on the apex/www hosts and the app on
        # app.luviio.in. These exact HTTPS origins are trusted; this does not
        # authorize arbitrary wildcard origins.
        try:
            frontend = urlsplit(str(self.FRONTEND_URL or "").strip())
            if (
                frontend.scheme.lower() == "https"
                and frontend.hostname in {"luviio.in", "www.luviio.in"}
                and frontend.port is None
                and frontend.username is None
                and frontend.password is None
            ):
                # First-party storefront and application origins.
                for origin in (
                    "https://luviio.in",
                    "https://www.luviio.in",
                    "https://app.luviio.in",
                ):
                    if origin not in origins:
                        origins.append(origin)
        except (ValueError, TypeError):
            pass

        return origins

    @property
    def cors_preview_origin_patterns(self) -> List[str]:
        return [
            pattern.strip()
            for pattern in self.CORS_PREVIEW_ORIGIN_PATTERNS.split(",")
            if pattern.strip()
        ]

    def is_allowed_browser_origin(self, origin: str | None) -> bool:
        """Check an exact origin or a narrow first-party preview-host pattern."""
        if not origin or origin == "null":
            return False

        if origin in self.cors_origins:
            return True

        if not self.is_production and "*" in self.cors_origins:
            return True

        if not self.is_production:
            return False

        for pattern in self.cors_preview_origin_patterns:
            try:
                if re.fullmatch(pattern, origin):
                    return True
            except re.error:
                # Malformed optional pattern configuration fails closed.
                continue

        return False

    @property
    def trusted_proxy_ips(self) -> List[str]:
        return [item.strip() for item in self.TRUSTED_PROXY_IPS.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def stripe_configured(self) -> bool:
        return bool(self.STRIPE_SECRET_KEY and self.STRIPE_WEBHOOK_SECRET)

    @property
    def email_configured(self) -> bool:
        return bool(self.RESEND_API_KEY and self.FROM_EMAIL)

    @property
    def push_configured(self) -> bool:
        return bool(self.VAPID_PUBLIC_KEY and self.VAPID_PRIVATE_KEY)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        validate_default=True,
    )


settings = Settings()
