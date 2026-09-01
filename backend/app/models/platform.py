from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IconAsset(Base):
    __tablename__ = "icon_assets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(40), index=True)
    lucide_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    custom_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DatabaseConnection(Base):
    __tablename__ = "database_connections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    database_type: Mapped[str] = mapped_column(String(24), index=True)
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    database_name: Mapped[str] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    encrypted_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    ssl_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_status: Mapped[str] = mapped_column(String(24), default="UNTESTED")
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DatabaseDataSource(Base):
    __tablename__ = "database_data_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("database_connections.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    query_text: Mapped[str] = mapped_column(Text)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_status: Mapped[str] = mapped_column(String(24), default="UNTESTED")
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class NotificationIntegration(Base):
    __tablename__ = "notification_integrations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    public_config: Mapped[dict] = mapped_column(JSON, default=dict)
    encrypted_secrets: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_status: Mapped[str] = mapped_column(String(24), default="UNTESTED")
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class NotificationRule(Base):
    __tablename__ = "notification_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(24), index=True)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    channels: Mapped[list] = mapped_column(JSON, default=list)
    recipients: Mapped[list] = mapped_column(JSON, default=list)
    reminder_minutes: Mapped[int] = mapped_column(Integer, default=0)
    notify_recovery: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (UniqueConstraint("alert_id", "rule_id", name="uq_notification_delivery_alert_rule"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("notification_rules.id", ondelete="CASCADE"), index=True)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    delivery_count: Mapped[int] = mapped_column(Integer, default=1)
    last_kind: Mapped[str] = mapped_column(String(24), default="ALERT")


class TopologyPosition(Base):
    __tablename__ = "topology_positions"
    __table_args__ = (UniqueConstraint("device_id", name="uq_topology_position_device"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    layout_mode: Mapped[str] = mapped_column(String(16), default="free")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TopologySnapshot(Base):
    __tablename__ = "topology_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    layout_mode: Mapped[str] = mapped_column(String(16), default="free")
    positions: Mapped[list] = mapped_column(JSON, default=list)
    viewport: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
