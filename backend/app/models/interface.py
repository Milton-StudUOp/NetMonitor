import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InterfaceStatus(str, enum.Enum):
    UP = "UP"
    DOWN = "DOWN"
    ADMIN_DOWN = "ADMIN_DOWN"
    UNKNOWN = "UNKNOWN"
    TESTING = "TESTING"


class Interface(Base):
    __tablename__ = "interfaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    interface_name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    snmp_index: Mapped[int | None] = mapped_column(Integer, nullable=True)  # ifIndex
    status: Mapped[InterfaceStatus] = mapped_column(Enum(InterfaceStatus), default=InterfaceStatus.UNKNOWN)
    admin_status: Mapped[InterfaceStatus] = mapped_column(Enum(InterfaceStatus), default=InterfaceStatus.UNKNOWN)
    speed_mbps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bytes_in: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes_out: Mapped[int] = mapped_column(BigInteger, default=0)
    errors_in: Mapped[int] = mapped_column(Integer, default=0)
    errors_out: Mapped[int] = mapped_column(Integer, default=0)
    discards_in: Mapped[int] = mapped_column(Integer, default=0)
    discards_out: Mapped[int] = mapped_column(Integer, default=0)
    last_change: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    device: Mapped["Device"] = relationship("Device", back_populates="interfaces")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return f"<Interface {self.interface_name} device={self.device_id} status={self.status}>"
