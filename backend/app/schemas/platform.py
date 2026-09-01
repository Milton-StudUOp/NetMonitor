from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IconRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    key: str
    name: str
    category: str
    lucide_name: str | None
    custom_data: str | None
    mime_type: str | None
    is_builtin: bool


class DatabaseConnectionInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    database_type: str
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    database_name: str = Field(min_length=1, max_length=255)
    username: str | None = None
    password: str | None = None
    ssl_enabled: bool = False
    enabled: bool = True

    @field_validator("database_type")
    @classmethod
    def supported_type(cls, value: str) -> str:
        value = value.upper()
        if value not in {"SQLITE", "POSTGRESQL", "MYSQL", "MSSQL", "ORACLE"}:
            raise ValueError("Unsupported database type")
        return value


class DatabaseConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    database_type: str
    host: str | None
    port: int | None
    database_name: str
    username: str | None
    ssl_enabled: bool
    enabled: bool
    password_configured: bool = False
    last_status: str
    last_error: str | None
    last_tested_at: datetime | None


class DatabaseDataSourceInput(BaseModel):
    connection_id: int
    name: str = Field(min_length=1, max_length=128)
    query_text: str = Field(min_length=6, max_length=10000)
    parameters: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("query_text")
    @classmethod
    def read_only_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.lower().startswith("select ") or ";" in normalized:
            raise ValueError("Only one read-only SELECT statement is allowed")
        return normalized


class DatabaseDataSourceRead(DatabaseDataSourceInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    last_status: str
    last_error: str | None
    last_tested_at: datetime | None


class NotificationIntegrationInput(BaseModel):
    provider: str
    name: str
    enabled: bool = False
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)

    @field_validator("provider")
    @classmethod
    def supported_provider(cls, value: str) -> str:
        value = value.upper()
        if value not in {"EMAIL", "TELEGRAM", "WHATSAPP"}:
            raise ValueError("Unsupported notification provider")
        return value


class NotificationIntegrationRead(BaseModel):
    id: int
    provider: str
    name: str
    enabled: bool
    config: dict[str, Any]
    secrets_configured: list[str]
    last_status: str
    last_error: str | None
    last_tested_at: datetime | None


class NotificationRuleInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    event_type: str
    severity: str
    source: str | None = None
    channels: list[str] = Field(min_length=1)
    recipients: list[str] = Field(default_factory=list)
    reminder_minutes: int = Field(default=0, ge=0)
    notify_recovery: bool = True
    enabled: bool = True

    @field_validator("severity")
    @classmethod
    def normalize_severity(cls, value: str) -> str:
        normalized = value.upper()
        return "INFORMATION" if normalized == "INFO" else normalized


class NotificationRuleRead(NotificationRuleInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


class PositionInput(BaseModel):
    device_id: int
    x: float
    y: float


class TopologyLayoutInput(BaseModel):
    layout_mode: str = "free"
    positions: list[PositionInput]


class SystemSettingsInput(BaseModel):
    timezone: str = "UTC"
    retention_days: int = Field(default=90, ge=1, le=3650)
    default_monitoring_interval: int = Field(default=30, ge=1)
    failure_threshold: int = Field(default=3, ge=1)
    success_threshold: int = Field(default=2, ge=1)


class DiscoveryRequest(BaseModel):
    target: str = Field(min_length=1)
    methods: list[str] = Field(default_factory=lambda: ["ICMP", "TCP"])
    ports: list[int] = Field(default_factory=lambda: [22, 23, 80, 443, 161, 8080, 8443])
    timeout_seconds: float = Field(default=0.8, ge=0.1, le=10)
    snmp_community: str | None = None
    snmp_version: str = "2c"
    snmp_username: str | None = None
    snmp_auth_key: str | None = None
    snmp_priv_key: str | None = None


class DiscoveredDevice(BaseModel):
    ip_address: str
    hostname: str | None = None
    status: str
    latency_ms: float | None = None
    open_ports: list[int] = Field(default_factory=list)
    snmp_available: bool = False
    manufacturer: str | None = None
    model: str | None = None
    device_type: str = "OTHER"
    interfaces: list[dict[str, Any]] = Field(default_factory=list)


class DiscoveryImportDevice(DiscoveredDevice):
    name: str
    location: str = "Descoberta de rede"
    group_name: str | None = None
    icon_id: int | None = None
    monitoring_method: str = "ICMP"
    snmp_community: str | None = None


class DiscoveryImportRequest(BaseModel):
    devices: list[DiscoveryImportDevice] = Field(min_length=1)
