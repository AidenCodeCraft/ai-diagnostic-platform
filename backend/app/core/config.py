from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "AI Diagnostic Platform"
    VERSION: str = "0.1.0"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql://ai:ai@localhost:5432/diagnostic"
    UPLOAD_DIR: str = "data/raw"

    class Config:
        env_file = ".env"


settings = Settings()
