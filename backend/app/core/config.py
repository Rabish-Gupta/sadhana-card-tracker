from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sadhana Card Tracker API"
    environment: str = "development"
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/sadhana_tracker"
    )
    sql_echo: bool = False

    # MVP authentication configuration. Refresh tokens and external identity providers
    # are intentionally deferred; the project currently uses one short-lived access token.
    jwt_secret_key: str = "development-only-change-me-use-at-least-32-bytes"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # MVP starts with one seeded VOICE organization while retaining a multi-organization schema.
    default_organization_code: str = "VOICE"

    # Step 11 automation. The scheduler is process-local while PostgreSQL advisory
    # locks provide cross-process mutual exclusion, so multiple API workers can safely
    # attempt the same lifecycle tick without duplicating domain work.
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 60
    scheduler_run_on_startup: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
