import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Identity, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.types import PortableJSON


class MonitoringTargetType(str, enum.Enum):
    DEVICE = "DEVICE"
    LINK = "LINK"
    INTERFACE = "INTERFACE"
    SERVICE = "SERVICE"
    REDUNDANCY_GROUP = "REDUNDANCY_GROUP"


class MonitoringStatus(str, enum.Enum):
    UP = "UP"
    DOWN = "DOWN"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"


class MonitoringResult(Base):
    """
    Time-series table — should be converted to TimescaleDB hypertable via migration.
    Stores all probe results for trend analysis and history.
    """
    __tablename__ = "monitoring_results"
    __table_args__ = (Index("ix_monitoring_result_target_time", "target_type", "target_id", "timestamp"), Index("ix_monitoring_result_status_time", "status", "timestamp"))

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True, index=True)
    target_type: Mapped[MonitoringTargetType] = mapped_column(Enum(MonitoringTargetType), nullable=False, index=True)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    status: Mapped[MonitoringStatus] = mapped_column(Enum(MonitoringStatus), nullable=False)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    packet_loss_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    details: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)

    def __repr__(self) -> str:
        return f"<MonitoringResult {self.target_type}:{self.target_id} {self.status} @ {self.timestamp}>"


class MetricAggregate(Base):
    __tablename__ = "metric_aggregates"
    __table_args__ = (
        UniqueConstraint("target_type", "target_id", "granularity", "bucket_start", name="uq_metric_aggregate_bucket"),
        Index("ix_metric_aggregate_lookup", "target_type", "target_id", "granularity", "bucket_start"),
    )
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[int] = mapped_column(Integer)
    granularity: Mapped[str] = mapped_column(String(16))
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sample_count: Mapped[int] = mapped_column(Integer)
    up_count: Mapped[int] = mapped_column(Integer)
    down_count: Mapped[int] = mapped_column(Integer)
    latency_sum: Mapped[float] = mapped_column(Float, default=0)
    latency_count: Mapped[int] = mapped_column(Integer, default=0)
    latency_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    packet_loss_sum: Mapped[float] = mapped_column(Float, default=0)
    packet_loss_count: Mapped[int] = mapped_column(Integer, default=0)
