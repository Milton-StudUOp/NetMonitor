import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RedundancyStatus(str, enum.Enum):
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class RedundancyType(str, enum.Enum):
    LINK = "LINK"
    DEVICE = "DEVICE"


class ServiceCheckType(str, enum.Enum):
    ICMP = "ICMP"
    TCP = "TCP"
    HTTP = "HTTP"
    HTTPS = "HTTPS"
    NONE = "NONE"


class RedundancyGroup(Base):
    __tablename__ = "redundancy_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    redundancy_type: Mapped[RedundancyType] = mapped_column(
        Enum(RedundancyType), default=RedundancyType.LINK, nullable=False
    )
    primary_link_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("links.id"), nullable=True)
    secondary_link_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("links.id"), nullable=True)
    primary_device_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("devices.id"), nullable=True)
    secondary_device_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("devices.id"), nullable=True)
    status: Mapped[RedundancyStatus] = mapped_column(
        Enum(RedundancyStatus), default=RedundancyStatus.UNKNOWN
    )
    # Optional service-level check (on top of link checks)
    service_check_type: Mapped[ServiceCheckType] = mapped_column(
        Enum(ServiceCheckType), default=ServiceCheckType.NONE
    )
    service_check_target: Mapped[str | None] = mapped_column(String(256), nullable=True)
    service_check_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_evaluated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    primary_link: Mapped["Link | None"] = relationship(  # type: ignore[name-defined]
        "Link", foreign_keys=[primary_link_id]
    )
    secondary_link: Mapped["Link | None"] = relationship(  # type: ignore[name-defined]
        "Link", foreign_keys=[secondary_link_id]
    )
    primary_device: Mapped["Device | None"] = relationship(  # type: ignore[name-defined]
        "Device", foreign_keys=[primary_device_id]
    )
    secondary_device: Mapped["Device | None"] = relationship(  # type: ignore[name-defined]
        "Device", foreign_keys=[secondary_device_id]
    )
    alerts: Mapped[list["Alert"]] = relationship(  # type: ignore[name-defined]
        "Alert", back_populates="redundancy_group"
    )

    def __repr__(self) -> str:
        return f"<RedundancyGroup {self.name} status={self.status}>"
