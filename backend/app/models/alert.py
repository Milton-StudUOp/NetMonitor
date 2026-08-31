import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AlertSeverity(str, enum.Enum):
    INFORMATION = "INFORMATION"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    device_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("devices.id"), nullable=True, index=True)
    link_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("links.id"), nullable=True, index=True)
    redundancy_group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("redundancy_groups.id"), nullable=True, index=True
    )
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    notified_channels: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    device: Mapped["Device | None"] = relationship("Device", back_populates="alerts")  # type: ignore[name-defined]
    link: Mapped["Link | None"] = relationship("Link", back_populates="alerts")  # type: ignore[name-defined]
    redundancy_group: Mapped["RedundancyGroup | None"] = relationship(  # type: ignore[name-defined]
        "RedundancyGroup", back_populates="alerts"
    )

    def __repr__(self) -> str:
        return f"<Alert [{self.severity}] {self.title} resolved={self.is_resolved}>"
