from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Read from environment variables or backend/.env. Defaults match docker-compose.yml."""

    model_config = SettingsConfigDict(env_file=PROJECT_DIR / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://noticeboard:noticeboard@localhost:5437/noticeboard"
    test_database_url: str = "postgresql+psycopg://noticeboard:noticeboard@localhost:5437/noticeboard_test"

    # Signs and verifies JWTs. The default is for local development only.
    jwt_secret: str = "dev-only-change-me-0123456789abcdef0123456789abcdef"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 480  # one working day

    # bcrypt cost factor: each +1 doubles hashing time. 12 is about 0.25 s; the tests use 4.
    bcrypt_rounds: int = 12

    # How often the server runs the 48-hour escalation check in the background. 0 turns it off.
    escalation_interval_minutes: int = 15


settings = Settings()
