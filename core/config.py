from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    BRIDGE_API_KEY: str
    BRIDGE_BASE_URL: str
    # other env vars...

    class Config:
        env_file = ".env"

settings = Settings()