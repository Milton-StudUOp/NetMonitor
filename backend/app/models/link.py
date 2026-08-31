import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LinkType(str, enum.Enum):
    FIBER = "FIBER"
    ETHERNET = "ETHERNET"
    RADIO = "RADIO"
    VPN = "VPN"
    OTHER = "OTHER"


class LinkPriority(str, enum.Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"


class LinkStatus(str, enum.Enum):
    UP = "UP"
    DOWN = "DOWN"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    destination_device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    source_interface_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("interfaces.id"), nullable=True)
    destination_interface_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("interfaces.id"), nullable=True)
    link_type: Mapped[LinkType] = mapped_column(Enum(LinkType), nullable=False)
    priority: Mapped[LinkPriority] = mapped_column(Enum(LinkPriority), nullable=False)
    status: Mapped[LinkStatus] = mapped_column(Enum(LinkStatus), default=LinkStatus.UNKNOWN)
    is_critical: Mapped[bool] = mapped_column(default=False)
    monitoring_interval: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    source_device: Mapped["Device"] = relationship(  # type: ignore[name-defined]
        "Device", foreign_keys=[source_device_id], back_populates="outgoing_links"
    )
    destination_device: Mapped["Device"] = relationship(  # type: ignore[name-defined]
        "Device", foreign_keys=[destination_device_id], back_populates="incoming_links"
    )
    source_interface: Mapped["Interface | None"] = relationship(  # type: ignore[name-defined]
        "Interface", foreign_keys=[source_interface_id]
    )
    destination_interface: Mapped["Interface | None"] = relationship(  # type: ignore[name-defined]
        "Interface", foreign_keys=[destination_interface_id]
    )
    alerts: Mapped[list["Alert"]] = relationship("Alert", back_populates="link")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return f"<Link {self.name} {self.priority} status={self.status}>"
