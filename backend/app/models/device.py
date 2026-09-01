import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DeviceType(str, enum.Enum):
    SWITCH = "SWITCH"
    MEDIA_CONVERTER = "MEDIA_CONVERTER"
    ROUTER = "ROUTER"
    RADIO = "RADIO"
    FIREWALL = "FIREWALL"
    SERVER = "SERVER"
    ACCESS_POINT = "ACCESS_POINT"
    OTHER = "OTHER"


class DeviceStatus(str, enum.Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"
    DEGRADED = "DEGRADED"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv4 or IPv6
    gateway_ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    gateway_device_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("devices.id"), nullable=True, index=True
    )
    primary_link_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("links.id"), nullable=True, index=True
    )
    device_type: Mapped[DeviceType] = mapped_column(Enum(DeviceType), nullable=False)
    location: Mapped[str] = mapped_column(String(128), nullable=False)
    network: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    function: Mapped[str | None] = mapped_column(Text, nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    icon_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("icon_assets.id"), nullable=True)
    monitoring_method: Mapped[str] = mapped_column(String(24), default="ICMP")
    snmp_community: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snmp_port: Mapped[int] = mapped_column(Integer, default=161)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    monitoring_interval: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[DeviceStatus] = mapped_column(
        Enum(DeviceStatus), default=DeviceStatus.UNKNOWN, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    interfaces: Mapped[list["Interface"]] = relationship(  # type: ignore[name-defined]
        "Interface", back_populates="device", cascade="all, delete-orphan"
    )
    outgoing_links: Mapped[list["Link"]] = relationship(  # type: ignore[name-defined]
        "Link", foreign_keys="Link.source_device_id", back_populates="source_device"
    )
    incoming_links: Mapped[list["Link"]] = relationship(  # type: ignore[name-defined]
        "Link", foreign_keys="Link.destination_device_id", back_populates="destination_device"
    )
    alerts: Mapped[list["Alert"]] = relationship(  # type: ignore[name-defined]
        "Alert", back_populates="device"
    )
    gateway_device: Mapped["Device | None"] = relationship(  # type: ignore[name-defined]
        "Device", remote_side=[id], foreign_keys=[gateway_device_id], back_populates="dependent_devices"
    )
    dependent_devices: Mapped[list["Device"]] = relationship(  # type: ignore[name-defined]
        "Device", foreign_keys=[gateway_device_id], back_populates="gateway_device"
    )
    primary_link: Mapped["Link | None"] = relationship(  # type: ignore[name-defined]
        "Link", foreign_keys=[primary_link_id]
    )

    def __repr__(self) -> str:
        return f"<Device {self.name} ({self.device_type}) status={self.status}>"

    @property
    def snmp_configured(self) -> bool:
        return bool(self.snmp_community)
