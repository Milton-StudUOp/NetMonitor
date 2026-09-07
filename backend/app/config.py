from functools import lru_cache
from pathlib import Path
from typing import Any, List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # The backend-specific file overrides the project-level file when both exist.
        env_file=(PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./network_monitor.db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # SNMP
    # No credential is supplied by the application. Configure SNMP explicitly.
    SNMP_COMMUNITY: str = ""
    SNMP_VERSION: str = "2c"

    # Monitoring intervals (seconds)
    INTERVAL_CRITICAL: int = 5
    INTERVAL_NORMAL: int = 30
    INTERVAL_SERVICES: int = 10

    # State machine thresholds
    FAILURES_TO_DOWN: int = 3
    SUCCESSES_TO_UP: int = 2
    PACKET_LOSS_THRESHOLD: float = 50.0

    # Notifications — Email
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "Network Monitor <alerts@example.com>"
    ALERT_EMAIL_RECIPIENTS: str = ""  # comma-separated

    # Notifications — Teams
    TEAMS_WEBHOOK_URL: str = ""

    # Notifications — Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # App
    SECRET_KEY: str
    DEBUG: bool = False
    ALLOW_AGGRESSIVE_DISCOVERY: bool = False
    AUTH_DISABLED: bool = False
    AUTH_SESSION_MINUTES: int
    PASSWORD_SCRYPT_N: int
    PASSWORD_SCRYPT_R: int
    PASSWORD_SCRYPT_P: int
    BOOTSTRAP_TOKEN: str | None = None
    CORS_ALLOWED_ORIGINS: str
    PASSWORD_RESET_MINUTES: int

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value: Any) -> bool:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "no", "off"}:
                return False
            if normalized in {"debug", "dev", "development", "true", "1", "yes", "on"}:
                return True
        return value

    @property
    def email_recipients(self) -> List[str]:
        return [r.strip() for r in self.ALERT_EMAIL_RECIPIENTS.split(",") if r.strip()]

    @field_validator("SECRET_KEY")
    @classmethod
    def secure_secret_key(cls, value: str) -> str:
        if len(value) < 32 or value in {"local-development-only", "replace-with-a-long-random-value"}:
            raise ValueError("SECRET_KEY must be a unique value of at least 32 characters")
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.CORS_ALLOWED_ORIGINS.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
