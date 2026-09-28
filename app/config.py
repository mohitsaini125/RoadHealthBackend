"""
Centralized environment-dependent configuration.
All secrets/config MUST be read from the environment via this module.
Never hard-code secrets or import os.environ directly elsewhere.
"""
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "Road Health AI Backend"
    ENV: str = Field(default="development")
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = Field(default=False)

    # --- Database ---
    DATABASE_URL: str = Field(
        default="postgresql+psycopg2://postgres:155223@localhost:5432/road_health"
    )

    # --- JWT ---
    JWT_SECRET_KEY: str = Field(default="CHANGE_ME_IN_ENV")
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60 * 24)

    # --- Uploads ---
    UPLOAD_DIR: str = Field(default="app/uploads/reports")
    MAX_UPLOAD_SIZE_MB: int = Field(default=10)
    ALLOWED_IMAGE_EXTENSIONS: List[str] = Field(
        default_factory=lambda: [".jpg", ".jpeg", ".png", ".webp"]
    )

    # --- AI ---
    AI_MODEL_PATH: str = Field(default="")

    # --- Scheduler / Escalation ---
    SCHEDULER_ENABLED: bool = Field(default=True)
    ESCALATION_INTERVAL_MINUTES: int = Field(default=5)

    # --- CORS ---
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    # --- Escalation SLA (hours to repair deadline, by priority) ---
    # PLACEHOLDER VALUES — do not treat as final. The project owner must
    # confirm real SLA durations per priority before production use.
    SLA_HOURS_CRITICAL: int = Field(default=24)
    SLA_HOURS_HIGH: int = Field(default=72)
    SLA_HOURS_MEDIUM: int = Field(default=168)
    SLA_HOURS_LOW: int = Field(default=336)


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — import and call this, don't instantiate Settings() directly."""
    return Settings()


settings = get_settings()
