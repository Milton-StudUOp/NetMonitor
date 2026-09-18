from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Identity, Integer, String, Text, UniqueConstraint, func
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
