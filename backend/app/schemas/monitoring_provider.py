from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WindowsConnectionInput(BaseModel):
    username: str = Field(min_length=1, max_length=256)
    password: str | None = Field(default=None, max_length=1024)
    port: int = Field(default=5986, ge=1, le=65535)
    use_https: bool = True
    verify_certificate: bool = True
    authentication: Literal["NTLM", "KERBEROS", "CREDSSP"] = "NTLM"
    enabled: bool = True


class WindowsConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    username: str
    port: int
    use_https: bool
    verify_certificate: bool
    authentication: str
    enabled: bool
    password_configured: bool = True


class LinuxConnectionInput(BaseModel):
    username: str = Field(min_length=1, max_length=256)
    secret: str | None = Field(default=None, max_length=16384)
    port: int = Field(default=22, ge=1, le=65535)
    authentication: Literal["SSH_PASSWORD", "SSH_KEY"] = "SSH_PASSWORD"
    verify_host_key: bool = True
    host_key: str | None = Field(default=None, max_length=4096)
    enabled: bool = True


class LinuxConnectionRead(BaseModel):
    username: str
    port: int
    authentication: str
    verify_host_key: bool
    enabled: bool
    secret_configured: bool = True
    host_key: str | None = None


class SNMPConnectionInput(BaseModel):
    version: Literal["1", "2c", "3"] = "2c"
    community: str | None = Field(default=None, max_length=256)
    username: str | None = Field(default=None, max_length=256)
    auth_key: str | None = Field(default=None, max_length=1024)
    priv_key: str | None = Field(default=None, max_length=1024)
    auth_protocol: Literal["NONE", "MD5", "SHA"] = "SHA"
    priv_protocol: Literal["NONE", "DES", "AES"] = "AES"
    port: int = Field(default=161, ge=1, le=65535)
    enabled: bool = True


class SNMPConnectionRead(BaseModel):
    version: str
    username: str | None = None
    port: int
    enabled: bool
    secret_configured: bool = True
    privacy_configured: bool = False


class WindowsCapabilityRead(BaseModel):
    device_id: int
    device_name: str
    connectivity: bool
    winrm: bool
    authentication: bool
    service_discovery: bool
    status: str
    error_code: str | None = None
    message: str
    operating_system: str | None = None
    powershell_version: str | None = None
    provider_mode: str | None = None
    capabilities: dict = Field(default_factory=dict)
    diagnostics: dict = Field(default_factory=dict)
    discovered_at: datetime | None = None


class SNMPCapabilityRead(BaseModel):
    device_id: int
    device_name: str
    connectivity: bool
    snmp: bool
    authentication: bool
    service_discovery: bool = False
    status: str
    error_code: str | None = None
    message: str
    operating_system: str | None = None
    provider_mode: str | None = None
    capabilities: dict = Field(default_factory=dict)
    diagnostics: dict = Field(default_factory=dict)
    discovered_at: datetime | None = None


class ServiceMonitoringUpdate(BaseModel):
    service_ids: list[int]
    monitored: bool = True
    expected_state: Literal["running", "stopped"] = "running"
    check_interval: int = Field(default=60, ge=30, le=86400)
    failure_threshold: int = Field(default=1, ge=1, le=1)
    recovery_threshold: int = Field(default=2, ge=1, le=20)
    severity: Literal["INFORMATION", "WARNING", "CRITICAL"] = "CRITICAL"
    notifications_enabled: bool = True


class MonitoringProfileInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    service_patterns: list[str] = Field(default_factory=list)
    metric_config: dict = Field(default_factory=dict)
    defaults: dict = Field(default_factory=dict)
    enabled: bool = True
