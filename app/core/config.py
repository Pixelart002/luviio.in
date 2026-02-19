from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    SB_URL: str
    SB_KEY: str
    SB_SERVICE_ROLE_KEY: str
    RESEND_API_KEY: str = ""
    SESSION_SECRET: str
    REDIRECT_URI_BASE: str
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    AI_DEBUGGER_URL: str = ""
    ENVIRONMENT: str = "development"
    CORS_ORIGINS: List[str] = ["http://localhost:8000"]
    ALLOWED_HOSTS: List[str] = ["localhost"]

    class Config:
        env_file = ".env"

settings = Settings()