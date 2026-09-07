from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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

    @model_validator(mode="after")
    def apply_default_port(self):
        defaults = {"POSTGRESQL": 5432, "MYSQL": 3306, "MSSQL": 1433, "ORACLE": 1521}
        if self.database_type == "SQLITE":
            self.host = None
            self.port = None
        elif self.port is None:
            self.port = defaults[self.database_type]
        return self


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

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Integration name is required")
        return value[:100]

    @model_validator(mode="after")
    def normalize_configuration(self):
        allowed_config = {
            "EMAIL": {"smtp_server", "smtp_port", "username", "from_address", "recipients", "tls", "ssl"},
            "TELEGRAM": {"chat_id", "chat_ids"},
            "WHATSAPP": {"api_url", "sender_id", "recipient", "recipients"},
        }[self.provider]
        allowed_secrets = {"EMAIL": {"password"}, "TELEGRAM": {"bot_token"}, "WHATSAPP": {"api_token"}}[self.provider]
        unknown_config = set(self.config) - allowed_config
        unknown_secrets = set(self.secrets) - allowed_secrets
        if unknown_config or unknown_secrets:
            raise ValueError("Configuration contains unsupported fields for this provider")
        return self


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

    @field_validator("name")
    @classmethod
    def clean_rule_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Rule name is required")
        return value

    @field_validator("severity")
    @classmethod
    def normalize_severity(cls, value: str) -> str:
        normalized = value.upper()
        normalized = "INFORMATION" if normalized == "INFO" else normalized
        if normalized not in {"INFORMATION", "WARNING", "CRITICAL"}:
            raise ValueError("Unsupported notification severity")
        return normalized

    @field_validator("event_type")
    @classmethod
    def valid_event_type(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {"DEVICE_DOWN", "DEVICE_UP", "LINK_DOWN", "LINK_UP", "REDUNDANCY_DEGRADED", "REDUNDANCY_CRITICAL", "RECOVERY"}
        if normalized not in allowed:
            raise ValueError("Unsupported notification event")
        return normalized

    @field_validator("channels")
    @classmethod
    def valid_channels(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(channel.upper() for channel in value))
        if not normalized or any(channel not in {"EMAIL", "TELEGRAM", "WHATSAPP"} for channel in normalized):
            raise ValueError("Select at least one supported notification channel")
        return normalized

    @field_validator("recipients")
    @classmethod
    def clean_recipients(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))


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


class TopologySnapshotInput(TopologyLayoutInput):
    name: str = Field(min_length=1, max_length=128)
    viewport: dict[str, float] = Field(default_factory=dict)


class SystemSettingsInput(BaseModel):
    timezone: str = "UTC"
    retention_days: int = Field(default=90, ge=1, le=3650)
    aggregate_retention_days: int = Field(default=1825, ge=30, le=7300)
    default_monitoring_interval: int = Field(default=30, ge=1)
    failure_threshold: int = Field(default=3, ge=1)
    success_threshold: int = Field(default=2, ge=1)


class DiscoveryRequest(BaseModel):
    target: str = Field(min_length=1)
    methods: list[str] = Field(default_factory=lambda: ["ICMP"])
    port_scan_mode: str = "NONE"
    scan_profile: str = "SAFE"
    ports: list[int] = Field(default_factory=list)
    timeout_seconds: float | None = Field(default=None, ge=0.1, le=10)
    retries: int | None = Field(default=None, ge=0, le=3)
    concurrency: int | None = Field(default=None, ge=1, le=100)
    rate_limit: float | None = Field(default=None, ge=1, le=500)
    snmp_community: str | None = None
    snmp_version: str = "2c"
    snmp_username: str | None = None
    snmp_auth_key: str | None = None
    snmp_priv_key: str | None = None

    @model_validator(mode="after")
    def validate_discovery_options(self):
        self.port_scan_mode = self.port_scan_mode.upper()
        self.scan_profile = self.scan_profile.upper()
        if self.port_scan_mode not in {"NONE", "TOP_100", "CUSTOM"}:
            raise ValueError("Unsupported port scan mode")
        if self.scan_profile not in {"SAFE", "NORMAL", "AGGRESSIVE"}:
            raise ValueError("Unsupported scan profile")
        self.methods = list(dict.fromkeys(method.upper() for method in self.methods))
        if not set(self.methods).issubset({"ICMP", "SNMP"}):
            raise ValueError("Supported host discovery methods are ICMP and SNMP")
        if "SNMP" in self.methods and self.snmp_version != "3" and not self.snmp_community:
            raise ValueError("SNMP community is required for SNMP v1/v2c discovery")
        if "SNMP" in self.methods and self.snmp_version == "3" and not self.snmp_username:
            raise ValueError("SNMP username is required for SNMPv3 discovery")
        self.ports = sorted(set(self.ports))
        if any(port < 1 or port > 65535 for port in self.ports):
            raise ValueError("Ports must be between 1 and 65535")
        if len(self.ports) > 64:
            raise ValueError("Custom scans are limited to 64 ports")
        return self


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
    location: str = "Network discovery"
    group_name: str | None = None
    icon_id: int | None = None
    monitoring_method: str = "ICMP"
    snmp_community: str | None = None


class DiscoveryImportRequest(BaseModel):
    devices: list[DiscoveryImportDevice] = Field(min_length=1)
