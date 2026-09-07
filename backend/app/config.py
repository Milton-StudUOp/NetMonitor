from functools import lru_cache
from typing import Any, List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./network_monitor.db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # SNMP
    SNMP_COMMUNITY: str = "public"
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
    SECRET_KEY: str = "local-development-only"
    DEBUG: bool = False
    ALLOW_AGGRESSIVE_DISCOVERY: bool = False

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
