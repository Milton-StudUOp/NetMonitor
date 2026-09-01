from typing import List, Optional
from pydantic import BaseModel

from app.models.device import DeviceStatus, DeviceType
from app.models.link import LinkStatus, LinkPriority, LinkType
from app.models.redundancy_group import RedundancyStatus


class TopologyNodeData(BaseModel):
    label: str
    ip_address: Optional[str] = None
    gateway_ip_address: Optional[str] = None
    gateway_device_id: Optional[int] = None
    primary_link_id: Optional[int] = None
    network: Optional[str] = None
    device_type: DeviceType
    status: DeviceStatus
    location: str
    is_critical: bool
    icon_id: Optional[int] = None
    icon_key: Optional[str] = None
    icon_name: Optional[str] = None
    icon_custom_data: Optional[str] = None
    icon_mime_type: Optional[str] = None


class TopologyNode(BaseModel):
    id: str  # e.g. "device_1"
    type: str = "customDevice"
    data: TopologyNodeData


class TopologyEdgeData(BaseModel):
    label: str
    status: LinkStatus
    priority: LinkPriority
    link_type: LinkType
    source_interface: Optional[str] = None
    destination_interface: Optional[str] = None
    network_warning: bool = False
    network_warning_reason: Optional[str] = None
    is_redundancy: bool = False
    redundancy_status: Optional[RedundancyStatus] = None


class TopologyEdge(BaseModel):
    id: str  # e.g. "link_1"
    source: str
    target: str
    animated: bool = False
    label: Optional[str] = None
    style: Optional[dict] = None
    labelStyle: Optional[dict] = None
    labelBgStyle: Optional[dict] = None
    data: TopologyEdgeData


class TopologyGraph(BaseModel):
    nodes: List[TopologyNode]
    edges: List[TopologyEdge]


class DashboardSummary(BaseModel):
    total_devices: int
    online_devices: int
    offline_devices: int
    degraded_devices: int
    unknown_devices: int
    total_links: int
    up_links: int
    down_links: int
    degraded_links: int
    total_redundancy_groups: int
    normal_redundancy_groups: int
    degraded_redundancy_groups: int
    critical_redundancy_groups: int
    active_alerts_count: int
    critical_alerts_count: int
