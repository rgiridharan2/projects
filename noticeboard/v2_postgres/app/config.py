from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Read from environment variables or v2_postgres/.env. Defaults match docker-compose.yml."""

    model_config = SettingsConfigDict(env_file=PROJECT_DIR / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://noticeboard:noticeboard@localhost:5433/noticeboard"
    test_database_url: str = "postgresql+psycopg://noticeboard:noticeboard@localhost:5433/noticeboard_test"


settings = Settings()
