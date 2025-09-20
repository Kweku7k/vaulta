# core/config.py
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # v2-style config (no inner Config class)
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # ignore any keys you haven't declared
    )

    # Declare only what you actually use in code
    DATABASE_URL: str
    BRIDGE_API_KEY: str
    BRIDGE_BASE_URL: str

    # add others as you adopt them (optional if not used by app code)
    SQLALCHEMY_DATABASE_URL: Optional[str] = None
    RESEND_API_KEY: Optional[str] = None
    REDIS_URL: Optional[str] = None
    OVEX_SECRET: Optional[str] = None
    OVEX_API_KEY: Optional[str] = None
    JWT_SECRET: Optional[str] = None
    BRIDGE_LIVE_API_KEY: Optional[str] = None
    ENV: str = "DEV"

settings = Settings()