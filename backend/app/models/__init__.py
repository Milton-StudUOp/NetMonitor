from app.database import Base  # noqa: F401 — ensures Base is shared
from app.models.device import Device, DeviceStatus, DeviceType  # noqa: F401
from app.models.interface import Interface, InterfaceStatus  # noqa: F401
from app.models.link import Link, LinkPriority, LinkStatus, LinkType  # noqa: F401
from app.models.redundancy_group import RedundancyGroup, RedundancyStatus, RedundancyType, ServiceCheckType  # noqa: F401
from app.models.monitoring_result import MonitoringResult, MonitoringTargetType, MonitoringStatus  # noqa: F401
from app.models.alert import Alert, AlertSeverity  # noqa: F401

__all__ = [
    "Base",
    "Device", "DeviceStatus", "DeviceType",
    "Interface", "InterfaceStatus",
    "Link", "LinkPriority", "LinkStatus", "LinkType",
    "RedundancyGroup", "RedundancyStatus", "RedundancyType", "ServiceCheckType",
    "MonitoringResult", "MonitoringTargetType", "MonitoringStatus",
    "Alert", "AlertSeverity",
]
