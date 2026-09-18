from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Identity, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.types import PortableJSON


class DeviceMonitoringCredential(Base):
    __tablename__ = "device_monitoring_credentials"
    __table_args__ = (UniqueConstraint("device_id", "provider", name="uq_device_monitoring_provider"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="WINDOWS")
    username: Mapped[str] = mapped_column(String(256))
    encrypted_password: Mapped[str] = mapped_column(Text)
    port: Mapped[int] = mapped_column(Integer, default=5986)
    use_https: Mapped[bool] = mapped_column(Boolean, default=True)
    verify_certificate: Mapped[bool] = mapped_column(Boolean, default=True)
    authentication: Mapped[str] = mapped_column(String(24), default="NTLM")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DeviceCapability(Base):
    __tablename__ = "device_capabilities"
    __table_args__ = (UniqueConstraint("device_id", "provider", name="uq_device_capability_provider"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="WINDOWS")
    platform: Mapped[str] = mapped_column(String(32), default="windows")
    provider_mode: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    operating_system: Mapped[str | None] = mapped_column(String(256), nullable=True)
    powershell_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    capabilities: Mapped[dict] = mapped_column(PortableJSON, default=dict)
    diagnostics: Mapped[dict] = mapped_column(PortableJSON, default=dict)
    last_status: Mapped[str] = mapped_column(String(32), default="UNTESTED")
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DiscoveredService(Base):
    __tablename__ = "discovered_services"
    __table_args__ = (UniqueConstraint("device_id", "name", name="uq_discovered_service_device_name"),)
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(256))
    display_name: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_account: Mapped[str | None] = mapped_column(String(256), nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    start_mode: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    monitoring_provider: Mapped[str] = mapped_column(String(32), default="windows")
    monitored: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    expected_state: Mapped[str] = mapped_column(String(16), default="running")
    check_interval: Mapped[int] = mapped_column(Integer, default=60)
    failure_threshold: Mapped[int] = mapped_column(Integer, default=1)
    recovery_threshold: Mapped[int] = mapped_column(Integer, default=2)
    severity: Mapped[str] = mapped_column(String(24), default="CRITICAL")
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    monitor_state: Mapped[str] = mapped_column(String(24), default="UNKNOWN", index=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_successes: Mapped[int] = mapped_column(Integer, default=0)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ServiceCheckHistory(Base):
    __tablename__ = "service_check_history"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("discovered_services.id", ondelete="CASCADE"), index=True)
    observed_state: Mapped[str] = mapped_column(String(32))
    monitor_state: Mapped[str] = mapped_column(String(24), index=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    response_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class SystemMetricSnapshot(Base):
    __tablename__ = "system_metric_snapshots"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    uptime_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage: Mapped[list] = mapped_column(PortableJSON, default=list)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class MonitoringProfile(Base):
    __tablename__ = "monitoring_profiles"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_patterns: Mapped[list] = mapped_column(PortableJSON, default=list)
    metric_config: Mapped[dict] = mapped_column(PortableJSON, default=dict)
    defaults: Mapped[dict] = mapped_column(PortableJSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
