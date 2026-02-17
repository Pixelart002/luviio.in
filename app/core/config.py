from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Luviio"
    SUPABASE_URL: str
    SUPABASE_KEY: str
    
    # In production, use .env file
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()